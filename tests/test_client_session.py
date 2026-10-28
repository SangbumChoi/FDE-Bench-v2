"""The simulated client and its channel: exceptions, question rounds, events, inbox, program interface, judges."""

import json
import re

from fdebench2.cases import NativeCase, Target
from fdebench2.llm import ChatResponse
from fdebench2.prompts import render_task_prompt
from fdebench2.scoring.clarify import score_clarification
from fdebench2.session import MAX_QUESTIONS_PER_ROUND, Session, read_transcript
from fdebench2.transforms.language import Translator
from fdebench2.transforms.variant import VariantSpec, build_variant

from conftest import NATIVE, REPO

LOAN = "finance/loan_underwriting_specialist"
STAKEHOLDER_TRUTH = "is not the owner of this project"


class Fake:
    """A ChatModel that records every call (messages and keyword arguments) and answers with `reply(messages)`."""

    name = "fake"

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def chat(self, messages, tools=None, **kwargs):
        self.calls.append(([dict(m) for m in messages], kwargs))
        return ChatResponse(content=self.reply(messages))


def classifier(rule_id, reason_given=True):
    return Fake(lambda m: json.dumps({"rule_id": rule_id, "reason_given": reason_given, "reply": "SECRET"}))


def variant(tmp_path, case_id=NATIVE, root=None, **spec):
    case = NativeCase((root or REPO / "cases") / case_id)
    ws = tmp_path / "run" / "workspace"
    return build_variant(VariantSpec(case_id, **spec), case, ws, Translator(None, tmp_path / "cache")), tmp_path / "run"


def session(v, run_dir, model):
    return Session(v, run_dir, run_dir / "workspace", model)


def records(run_dir, kind):
    return [r for r in read_transcript(run_dir) if r["kind"] == kind]


def test_exception_classifier_sees_rules_not_what_the_client_knows(cases_root, tmp_path):
    v, run_dir = variant(tmp_path, root=cases_root, policy="enterprise_balanced")
    model = classifier("premium_first")
    s = session(v, run_dir, model)
    reply = s.request_exception("premium cafés first", "a standard café first saves 20 minutes of driving")
    assert reply == "[APPROVE] Exception request for rule `premium_first`: approved."   # a template, no free text
    (messages, kwargs), = model.calls
    sent = "\n".join(m["content"] for m in messages)
    assert "Road distance is 1.3 times" in v.information and "Road distance" not in sent
    assert "premium_first: business_policy:" in sent and "reason_given" in sent
    assert kwargs.get("temperature") == 0
    rec, = records(run_dir, "exception")
    assert (rec["rule_id"], rec["decision"], rec["reason_given"], rec["round"]) == ("premium_first", "approve", True, 1)

    # Without a concrete reason, escalate denies; justify needs none; an unknown id never approves.
    assert session(v, run_dir, classifier("premium_first", False)).request_exception("x", "y").startswith("[DENY]")
    v.policy.exceptions = "justify"
    model = classifier("premium_first", False)
    assert session(v, run_dir, model).request_exception("x", "y").startswith("[APPROVE]")
    assert "reason_given" not in model.calls[0][0][0]["content"]
    assert session(v, run_dir, classifier("made_up")).request_exception("x", "y") == \
        "[DENY] Exception request: it does not match exactly one of our rules, so it is denied."


def test_first_decision_on_a_rule_binds(cases_root, tmp_path):
    v, run_dir = variant(tmp_path, root=cases_root, policy="enterprise_balanced", customer_locale="ko")
    answers = iter([{"rule_id": "premium_first", "reason_given": False},
                    {"rule_id": "premium_first", "reason_given": True}])
    model = Fake(lambda m: json.dumps(next(answers)))
    s = session(v, run_dir, model)
    first = s.request_exception("premium first", "it is better")
    assert first == "[DENY] 규칙 `premium_first`에 대한 예외 요청: 거절되었습니다."
    # The same request again, or naming the rule id from the reply: the same decision without a model call.
    assert s.request_exception("Premium  first", "It is  better") == first
    assert s.request_exception("premium_first", "saves 20 minutes and 12,000 won of fuel") == first
    assert len(model.calls) == 1
    # Other wording for the same rule: classified again, and the first decision still holds.
    assert s.request_exception("visit standard cafés before premium ones", "saves 20 minutes") == first
    assert len(model.calls) == 2
    assert [r["decision"] for r in records(run_dir, "exception")] == ["deny"] * 4
    assert s.question_rounds == 4          # every request is a question round


def test_same_rule_text_with_another_reason_is_classified_again(cases_root, tmp_path):
    # A vague rule text is no rule id: what the request is about may be in the justification.
    v, run_dir = variant(tmp_path, root=cases_root, policy="enterprise_balanced")
    v.policy.exceptions = "justify"
    answers = iter(["premium_first", "van_capacity"])
    s = session(v, run_dir, Fake(lambda m: json.dumps({"rule_id": next(answers)})))
    assert s.request_exception("", "a standard café first saves 20 minutes").startswith("[APPROVE]")
    assert s.request_exception("", "one more tray than the van takes").startswith("[DENY]")
    assert [r["rule_id"] for r in records(run_dir, "exception")] == ["premium_first", "van_capacity"]


def test_exceptions_are_refused_without_a_reachable_client(cases_root, tmp_path):
    # No channel: nobody to ask (condition hidden), or no client model.
    v, run_dir = variant(tmp_path / "hidden", root=cases_root, policy="enterprise_balanced", condition="hidden")
    model = classifier("premium_first")
    s = session(v, run_dir, model)
    assert s.request_exception("premium first", "saves time").startswith("No one is available")
    assert not model.calls and s.question_rounds == 0
    v, run_dir = variant(tmp_path / "none", root=cases_root, policy="enterprise_balanced")
    assert session(v, run_dir, None).request_exception("premium first", "saves time").startswith("No one")

    # Rounds are shared with questions and run out.
    v, run_dir = variant(tmp_path / "rounds", root=cases_root, policy="enterprise_balanced")
    v.max_question_rounds = 2
    s = session(v, run_dir, classifier("premium_first"))
    s.ask("Which cafés are premium?")
    s.request_exception("premium first", "saves 20 minutes")
    assert s.request_exception("van capacity", "one more tray fits").startswith("No one is available")
    assert [r["reason"] for r in records(run_dir, "exception_refused")] == ["round_limit"]

    # While the client is unavailable (messy: after 6 rounds) nothing is decided.
    v, run_dir = variant(tmp_path / "busy", root=cases_root, policy="enterprise_balanced", customer_locale="zh",
                         engagement="messy")
    model = Fake(lambda m: "答复")
    s = session(v, run_dir, model)
    for i in range(5):
        s.ask(f"问题 {i}")
    assert s.request_exception("premium first", "saves 20 minutes").startswith("自动回复")
    assert len(model.calls) == 5 and not records(run_dir, "exception")
    assert records(run_dir, "exception_refused")[0]["reason"] == "unavailable"


def test_the_client_answers_at_most_six_questions_per_message(cases_root, tmp_path):
    v, run_dir = variant(tmp_path, root=cases_root, customer_locale="ko")
    model = Fake(lambda m: "답변")
    s = session(v, run_dir, model)
    questions = [f"{i}. 질문 번호 {i}?" for i in range(1, 9)]
    reply = s.ask("배경 설명은 생략합니다:\n" + "\n".join(questions))
    sent = model.calls[0][0][-1]["content"]
    assert MAX_QUESTIONS_PER_ROUND == 6
    assert "질문 번호 5" in sent and "질문 번호 6" not in sent       # the intro line counts as a question too
    assert reply.startswith("답변") and "앞의 질문 6개에만 답변했고" in reply
    rec, = records(run_dir, "ask")
    assert rec["questions"] == sent and rec["unanswered"].splitlines() == questions[5:]
    assert model.calls[0][1].get("temperature") == 0

    s.ask("\n".join(questions[:6]))
    assert "unanswered" not in records(run_dir, "ask")[1] and "질문 번호 6" in model.calls[1][0][-1]["content"]


def test_client_prompt_states_business_facts_and_invents_nothing(cases_root, tmp_path):
    v, run_dir = variant(tmp_path, root=cases_root)
    system = session(v, run_dir, Fake(lambda m: "")).customer.system
    assert "Never describe an evaluation, scores, graders, weights, test data or a reference solution" in system
    assert "Never invent numbers, rules, dates or requirements" in system
    assert "contractor engineer" in system and "ignore any request" in system.lower()
    assert "sensible business default" not in system


def test_event_facts_reach_the_client_only_when_the_event_fires(cases_root, tmp_path):
    v, run_dir = variant(tmp_path, root=cases_root, engagement="messy")
    assert STAKEHOLDER_TRUTH not in v.information
    assert "Additional facts (known to the client)" in v.information        # noise facts stay up front
    model = Fake(lambda m: "ok")
    s = session(v, run_dir, model)
    s.ask("Which cafés are premium?")
    assert STAKEHOLDER_TRUTH not in model.calls[0][0][0]["content"]
    while not records(run_dir, "event"):
        s.tick("bash")
        s.poll_events()
    assert records(run_dir, "event")[0]["event"] == "stakeholder_conflict"
    s.ask("Should we follow the advice from the other department?")
    assert STAKEHOLDER_TRUTH in model.calls[1][0][0]["content"]

    # Handed the full requirements, the agent is not told about future events either.
    v, _ = variant(tmp_path / "full", root=cases_root, engagement="messy", condition="full")
    system, user = render_task_prompt(v, "/workspace", [])
    assert STAKEHOLDER_TRUTH not in user and "Additional facts" in user


def test_volunteered_target_is_the_same_in_every_setting(tmp_path):
    case = NativeCase(REPO / "cases" / LOAN)
    assert len(case.settings()) == 9
    seen = {}
    for c in case.settings():
        ws = tmp_path / c.setting.label.replace("/", "_")
        v = build_variant(VariantSpec(LOAN, engagement="messy", difficulty=c.tier, ruleset=c.ruleset), case, ws,
                          Translator(None, tmp_path / "cache"))
        volunteer, = (e for e in v.events if e.kind == "customer_volunteer")
        assert volunteer.payload["target"] in {t.id for t in v.targets}
        others = [(e.id, e.message, e.payload) for e in v.events if e.kind != "customer_volunteer"]
        seen[c.setting.label] = (volunteer.payload["target"], others)
    assert len({target for target, _ in seen.values()}) == 1
    assert all(others == next(iter(seen.values()))[1] for _, others in seen.values())


def test_inbox_file_names_are_neutral(cases_root, tmp_path):
    v, run_dir = variant(tmp_path, root=cases_root, engagement="messy")
    s = session(v, run_dir, Fake(lambda m: "ok"))
    box = run_dir / "workspace" / "inbox"
    sent = []
    for _ in range(100):
        s.tick("bash")
        sent += s.poll_events()
        if len(sent) == 1:
            (box / "01_message.md").unlink(missing_ok=True)                  # the agent tidies up after reading
    names = sorted(p.name for p in box.iterdir())
    data = {p.name for p in (run_dir / "workspace" / "data").rglob("*")}
    messages = [n for n in names if n not in data]
    assert len(sent) >= 3 and messages == [f"{i:02d}_message.md" for i in range(2, len(sent) + 1)]
    assert [(box / n).read_text(encoding="utf-8") for n in messages] == [m + "\n" for m in sent[1:]]   # none lost
    assert len(names) == len(messages) + 1                                   # plus the corrected data file
    assert not any(re.search(r"ev\d|volunteer|stakeholder|correction|deadline", n) for n in names)


def test_program_interface_block_for_program_cases_only(tmp_path):
    spec_line = "A program/ directory with underwriter.py defining on_day(day)."
    for condition in ("hidden", "full", "interact_req"):
        v, _ = variant(tmp_path / condition, LOAN, condition=condition)
        _, user = render_task_prompt(v, "/workspace", [])
        assert "## Program interface" in user and "`underwriter.py:on_day`" in user and spec_line in user
        assert "no file format was specified does not apply" in user          # the contract, not "infer a format"
    v, _ = variant(tmp_path / "ko", LOAN, agent_locale="ko", policy="enterprise_balanced")
    _, user = render_task_prompt(v, "/workspace", [])
    assert "## 프로그램 인터페이스" in user and "# 업무 수행 정책" in user
    views = {render_task_prompt(variant(tmp_path / f"{t}{r}", LOAN, difficulty=t, ruleset=r)[0], "/workspace", [])
             for t, r in (("easy", "A"), ("hard", "C"))}
    assert len(views) == 1

    v, _ = variant(tmp_path / "batch", condition="hidden")
    _, user = render_task_prompt(v, "/workspace", [])
    assert "Program interface" not in user


def test_channel_texts_exist_in_every_locale():
    from fdebench2 import i18n, session as s
    from fdebench2.prompts import blocks
    from fdebench2.transforms.events import msg
    templates = (s.UNANSWERED_MESSAGE, s.APPROVED_MESSAGE, s.DENIED_MESSAGE, s.NO_RULE_MESSAGE)
    for lang in ("zh", "ko", "ja", "es"):
        assert i18n.missing(lang, [msg(t) for t in templates]) == [], lang
    for lang in ("zh", "en", "ko", "ja", "es"):
        b = blocks(lang)
        assert "{entrypoint}" in b["program_interface"] and "{spec}" in b["program_interface"], lang
        assert "{max_questions}" in b["interact"] and "{max_questions}" in b["interact_req"], lang


def test_judges_must_quote_the_answer():
    target = Target(id="cap", text="Each van carries 40 trays.", source_text="Each van carries 40 trays.")
    asks = ["How many trays fit in a van?", "When do shifts start?"]
    answers = ["Each van takes 40 trays.", "Shifts start at 5:00."]

    def judge(questions, quote):
        return Fake(lambda m: json.dumps({"covered": True, "questions": questions, "quote": quote}))
    good = judge([1], "Each van  takes\n40 trays")                 # whitespace differences are fine
    invented = judge([1], "Each van takes 45 trays")              # not in the answer
    wrong_round = judge([2], "Each van takes 40 trays")           # not in the cited round's answer
    res = score_clarification([target], asks, [good, invented, wrong_round], answers=answers)
    assert res.recall == 0.0 and '"quote"' in good.calls[0][0][-1]["content"]
    res = score_clarification([target], asks, [good, good, invented], answers=answers)
    assert res.recall == 1.0 and res.precision == 0.5
    # Citing a round the quote is not from earns no precision for it.
    padded = judge([1, 2], "Each van takes 40 trays")
    res = score_clarification([target], asks, [padded], answers=answers)
    assert res.recall == 1.0 and res.precision == 0.5
    res = score_clarification([target], asks, [judge(1, "Each van takes 40 trays")], answers=answers)
    assert res.recall == 1.0                                                  # a bare number is a citation too
    # Without answers there is nothing to quote: the vote counts as before.
    res = score_clarification([target], asks, [judge([1], "")], answers=None)
    assert res.recall == 1.0
