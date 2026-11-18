"""Write GT.md (the case's ground truth in five parts) and CLIENT_REVIEW.md (what the simulated client answers from).

Run from the repository root:  python cases/healthcare/hospital_appointment_scheduler/gt_report.py [gt] [client]
GT.md takes every number in its audit tables from dataset/audit.json (`fdebench2 audit-case`, public world), and two
tables from the case itself (bending the follow-up habit and the economics of overbooking, replayed in-process on the
public settings); the prose around them is fixed here. Neither file quotes the audit's fingerprint, so writing them
again after a fresh audit of the same sources gives the same files. Both are case docs (cases.CASE_DOCS), outside the
audit's fingerprint, so writing them never makes the stored audit stale; this script is a source of the audit, like
case.py.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from statistics import median

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2]))

from fdebench2.audit import (cross_flag_summary, false_negatives, findings, shortcut_summary, summarize,  # noqa: E402
                             target_summary, tier_order)
from fdebench2.cases import NativeCase  # noqa: E402

LANGS = ("en", "zh", "ko", "ja", "es")

# Why each rule is a hard gate, in the client's terms.
RULE_WHY = {
    "well_formed": "the engine must be able to apply every action: a malformed one, an unknown request or a date "
                   "outside the window cannot be booked, and a call that fails leaves the office without a plan",
    "no_double_booking": "a doctor sees one patient a slot (easy and medium plan for everyone coming)",
    "slot_capacity": "hard: an overbooked slot holds two follow-ups at most, never a new patient's long visit",
    "slot_length": "the calendar's slots are the doctors' time; a new patient needs two consecutive ones",
    "department_match": "a patient is seen in the department they were referred to",
    "holiday_closure": "the closed clinic has no doctor on City Day, whatever the calendar says",
    "not_before_earliest": "the patient cannot come earlier (results, travel, the GP's referral)",
    "interpreter_capacity": "a new patient who does not share a language with the doctor needs an in-person "
                            "interpreter, and there are only so many a day",
    "referral_validity": "the health authority pays a new-patient visit only on a valid referral letter (it was "
                         "enforced but missing from case.yaml before the audit)",
    "lab_capacity": "the lab's fasting draws a day",
    "test_before_visit": "the results take a working day",
    "doctor_available": "an absent doctor sees nobody",
    "urgent_window": "the contract with the health authority: urgent referrals are seen within two working days",
    "urgent_reserve": "the contract keeps room for urgent referrals two or more days ahead",
    "move_notice": "patients must be told of a new date or time three working days ahead",
    "waitlist_priority": "the office's published order of the waitlist",
    "overbooking_limit": "the cap on double-booked slots a doctor accepts per session",
    "one_per_department": "a duplicate request is the same need: a second appointment would block a slot for "
                          "nothing",
    "status_table": "the departments staff their clinics from the daily table (mandatory output, new with the "
                    "audit: a call without it, or a table without a department's three numbers, is unusable)",
    "follow_up_same_doctor": "the office's habit (patients expect the doctor who knows them). The one bendable rule: "
                             "the head of the outpatient office can grant exceptions",
}
# How each fixed fact is misread in its ablation (case.py misreading()).
ABLATION = {
    "reserve_release": "the office's practice the export shows: the reserve kept for urgent patients, also the day "
                       "before (`hold_reserve`)",
    "follow_up_doctor": "follow-ups with whichever doctor of the department is free first, as some in the export "
                        "were (`bend`)",
    "move_notice": "a change needs a day's notice and costs nothing: patients booked later are pulled forward into "
                   "tomorrow's empty slots (`move_notice_days` 1, `pull_forward`)",
    "status_table": "the table as the pilot reports it: no slot held back, the reserve counted as free "
                    "(`table_no_reserve`)",
    "staff_notes": "the notes followed: the director's acquaintances booked tomorrow morning, D10's afternoons kept "
                   "free (`follow_notes`, `head_note`)",
    "duplicates": "easy/medium: a second request of a patient for the department not booked again (`dedupe`); hard: "
                  "each request booked (`dedupe` off)",
    "overbooking": "easy/medium: follow-ups doubled up where a patient may stay away (`overbook`); hard: never "
                   "two in a slot, as in the export (`no_overbook`)",
    "referral_expiry": "easy: referral dates acted on; medium/hard: ignored",
    "blood_test": "easy: blood tests acted on (test days within a lab cap); medium/hard: ignored",
    "doctor_absence": "easy: absence notices acted on (appointments moved or released, the doctor not booked); "
                      "medium/hard: ignored",
    "interpreter_absence": "the interpreter's absence ignored",
    "collision_cost": "no cost stated, so a collision costs nothing: every follow-up that can be doubled up is "
                      "(`collision_cost` 0)",
}
# What tells a correct program from the misreading (case.py _diagnose), from the trace of its own run.
DIAGNOSTIC = {
    "urgent_reserve": "no S/R booking two or more days ahead in a reserve slot after the first two (or after 09:00 "
                      "while 09:00 is kept), and no day's table that is exactly the table of another reserve size",
    "reserve_release": "S/R requests booked into tomorrow's reserve slots (none in the whole period: not enforced), "
                       "and none into 09:00/09:20 two or more days ahead (from 09:00 on)",
    "follow_up_doctor": "every follow-up placed with its own doctor",
    "interpreters": "no day over the interpreters (the interpreter's absence day aside when that alone explains it), "
                    "and no priority breach that only an interpreter the program thought taken explains",
    "holiday_clinic": "no City Day booking in the closed clinic, and no day's table that is exactly the table with "
                      "another clinic (or none) closed",
    "move_notice": "no change of date or time inside the notice period (not determinable when the run changes "
                   "nothing)",
    "waitlist_priority": "no priority breach that only the order explains (each breach goes to the reading that "
                         "explains every request it passed over and the most breaches)",
    "status_table": "a table every day, never exactly the pilot's (held_back 0) nor one holding tomorrow's empty "
                    "reserve back too, where those differ",
    "staff_notes": "no breach that only a note explains, and bookings into D10's afternoons after the note",
    "duplicates": "easy/medium: no breach that only a patient's second request explains; hard: no second "
                  "appointment and no table that counts requests",
    "overbooking": "easy/medium: no slot holding two; hard: some slot holding two follow-ups",
    "referral_expiry": "easy: no breach that only an expired referral explains; medium/hard: no visit after the "
                       "referral and no table counting expired ones",
    "blood_test": "easy: no breach that only a blood test explains; medium/hard: no test missing or late",
    "lab_cap": "no day over the lab's cap, and no breach that only a lab day the program thought full explains",
    "doctor_absence": "easy: absent doctors' appointments kept and booked; medium/hard: none left on an absent day, "
                      "no table counting the absent days",
    "interpreter_absence": "the absence day within the reduced number",
    "overbooking_cap": "no session over the cap",
    "collision_cost": "at most half of the overbooked slots hold two patients who both come with more than an even "
                      "chance",
}
# Facts that were targets (or clauses of targets) before this audit and are not now. They stay in requirements.md,
# where the client still answers them when asked.
REMOVED = [
    ("`interface`", "the deliverable's interface is shown to the agent in every condition (case.yaml "
                    "`deliverable_spec`): a contract, not a fact to elicit"),
    ("`evaluation_period`", "the program answers whatever day it is called for; the dates change no decision"),
    ("`visit_length`", "the export's appointments carry their `slots` (2 for every new patient, 1 for every "
                       "follow-up), and so does every `book` entry the program gets: the data shows it"),
    ("`urgent_window`", "the reference books every urgent request into tomorrow's reserve, so a window of 1, 2, 3 "
                        "or 10 days gives the same program (REVIEW.md F3); the rule stays a hard gate"),
    ("`scoring`", "\"stop losing doctor time to empty slots\" is the request itself; the rest of it (waiting by "
                  "urgency, unbooked requests, changes) is how the objective is computed (part 3)"),
    ("`easy_scope`, `medium_scope` (bundles)", "split into one fact per subject, each in every tier where the "
                                              "client must say how to treat it: `doctor_absence`, `referral_expiry`, "
                                              "`blood_test`, `duplicates`, `overbooking` (easy and medium say what "
                                              "is out of scope, medium and hard what is in). The interpreter's "
                                              "absence in easy is not a target: acting on it loses nothing in two of "
                                              "the three public settings"),
    ("`no_show_rates`", "a careful agent reads them off the data: every request carries the patient's past and "
                        "missed appointments, and the export's attendance table with booking and visit dates shows "
                        "the lead-time effect (the reference fits it there)"),
    ("`several_departments`", "keeping a patient's two departments on one day changes the operations value by 0.0 "
                              "to 0.01 of the scale (ten such patients, 3 per extra trip)"),
    ("`scoring_hard`", "split: what counts with no-shows (the expected visits) is how the objective is computed; "
                       "the collision cost is a client fact (`collision_cost`, now three empty slots, was \"a little "
                       "more than one\")"),
    ("`urgent_reserve` (the old bundle)", "split into `urgent_reserve` (the reserve's size, exactly the drawn "
                                          "`reserve_slots`) and `reserve_release` (released for tomorrow)"),
    ("`blood_test` (the old bundle)", "split into `blood_test` (the test day) and `lab_cap` (exactly the drawn "
                                      "`lab_cap`)"),
    ("`overbooking` (the old bundle)", "split into `overbooking` (two follow-ups to a slot, hard; none, easy and "
                                       "medium) and `overbooking_cap` (exactly the drawn `overbooked_per_session`)"),
]


def _num(x, digits=3):
    return "–" if x is None else f"{x:.{digits}f}"


def _table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def _fact(text: str) -> str:
    """A target's English text with its parameters written generically and its tier markers spelled out."""
    text = re.sub(r"<!-- tier: ([a-z ]+) -->", lambda m: f"[{m.group(1)}] ", text)
    text = re.sub(r"<!-- /tier -->", " ", text)
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: f"*{m.group(1)}*", text).replace("|", "/").strip()


def _diag(s: dict) -> str:
    return "no" if not s["has_diagnostic"] else ("untested" if s["separates"] is None else
                                                "separates" if s["separates"] else "does not separate")


def _range(xs, digits=3):
    xs = [x for x in xs if x is not None]
    return "–" if not xs else _num(min(xs), digits) if min(xs) == max(xs) else f"{_num(min(xs), digits)}–{_num(max(xs), digits)}"


def _bending_policies() -> list[tuple[str, float, float]]:
    """(policy, the share of quality in its final score, its soft-rule penalty) for the shipped policies that let a
    business-policy rule bend (configs/policies/*.yaml)."""
    out = []
    for path in sorted((ROOT.parents[2] / "configs" / "policies").glob("*.yaml")):
        policy = yaml.safe_load(path.read_text(encoding="utf-8"))
        if (policy.get("rule_classes") or {}).get("business_policy") == "soft" and policy.get("exceptions") != "forbidden":
            weights = policy.get("weights") or {}
            out.append((path.stem, weights.get("quality", 0.0) / sum(weights.values()),
                        float(policy.get("soft_rule_penalty", 0.1))))
    return out


BENDS = {"every follow-up": {"bend": True}, "absent doctors' patients": {"bend_absence": True},
         "tomorrow's idle slots": {"bend_idle": True}}


def _q(module, view, res, base):
    obj = module._objective(res, module._reference_run(view)["value"])
    return (obj - base) / (1.0 - base)


def _base(module, view):
    res = module.run_inprocess(view, module.ref_config(view, hold_reserve=True, no_overbook=True))
    return module._objective(res, module._reference_run(view)["value"])


def _bend_rows(case: NativeCase, cap: float) -> list[list[str]]:
    """Per public setting: the reference bending the follow-up habit three ways (every follow-up with whichever
    doctor is free first; only the patients of a doctor with a notified absence; only to fill tomorrow's slots that
    are still empty), scored with the habit relaxed (an approved exception): its quality gain over the reference,
    the exceptions it takes, and what the best of them nets in the final score under each policy that allows the
    bend (its quality share / the quality cap x the gain, less its soft-rule penalty)."""
    module, rows = case.module, []
    policies = _bending_policies()
    for tier in case.tiers:
        for seed in case.rule_seeds:
            c = case.at(tier, seed)
            view = module._View(c.world, c.setting)
            base = _base(module, view)
            cells, gains = [], []
            for name, switch in BENDS.items():
                res = module.run_inprocess(view, module.ref_config(view, **switch))
                other = sorted({r for r, _ in res["violations"]} - {"follow_up_same_doctor"})
                assert not other, (c.setting.label, name, other)
                g = _q(module, view, res, base) - 1.0
                gains.append(g)
                cells.append(f"{g:+.3f} ({res['metrics']['colleague_follow_ups']})")
            best = max(gains)
            row = [c.setting.label] + cells
            for _, share, penalty in policies:
                net = share / cap * best - penalty
                row.append(f"{net:+.3f} ({'pays' if net > 0.005 else 'loses' if net < -0.005 else 'about even'})")
            rows.append(row)
    return rows


def _overbooking_rows(case: NativeCase) -> tuple[list[list[str]], list[list[float]]]:
    """Per public hard setting: the quality of the reference (selective overbooking) and of the same program never
    overbooking, overbooking every follow-up it can (as if a collision cost nothing) and overbooking with the
    patients' true no-show rates (hindsight); and the qualities alone."""
    module, rows, qs = case.module, [], []
    for seed in case.rule_seeds:
        c = case.at("hard", seed)
        view = module._View(c.world, c.setting)
        base = _base(module, view)
        oracle = {r.id: r.base_p for r in c.world.reqs}
        cells, q = [], []
        for switch in ({}, {"no_overbook": True}, {"collision_cost": 0.0}, {"oracle_p": oracle}):
            res = module.run_inprocess(view, module.ref_config(view, **switch))
            assert not res["violations"], (seed, switch, res["violations"])
            m = res["metrics"]
            q.append(_q(module, view, res, base))
            cells.append(f"{q[-1]:.3f} ({m['overbooked_slots']}, {m['collision_cost']:.0f})")
        rows.append([c.setting.label, str(c.drawn_params["overbooked_per_session"])] + cells)
        qs.append(q)
    return rows, qs


SLIPS = {"one entry wrong every day": "entry", "one department's row wrong every day": "row",
         "held_back with tomorrow's reserve": {"table_hold_tomorrow": True},
         "the calendar as listed (closures, absences)": {"table_calendar_as_is": True},
         "expired referrals counted (medium+)": {"table_count_expired": True},
         "requests, not patients (hard)": {"table_count_requests": True},
         "the pilot's table (held_back 0)": {"table_no_reserve": True}}


def _slip_rows(case: NativeCase) -> list[list[str]]:
    """Per public setting: the quality of the reference's bookings with a table that slips one way (a cell is "–"
    where the slip changes nothing in that tier), and the share of the table's entries that are wrong."""
    module, rows = case.module, []
    sched_cls = module._module().Scheduler
    for tier in case.tiers:
        for seed in case.rule_seeds:
            c = case.at(tier, seed)
            view = module._View(c.world, c.setting)
            base = _base(module, view)
            row = [c.setting.label]
            for name, how in SLIPS.items():
                if ("medium+" in name and not view.medium) or ("(hard)" in name and not view.hard):
                    row.append("–")
                    continue
                if isinstance(how, dict):
                    res = module.run_inprocess(view, module.ref_config(view, **how))
                else:
                    sched = sched_cls(module._rt(module.ref_config(view)))

                    def decide(x, sched=sched, how=how):
                        out = module._rt(sched.on_day(module._rt(x)))
                        row_ = out["status_table"]["IM"]
                        for k in (("waitlist",) if how == "entry" else tuple(row_)):
                            row_[k] += 1
                        return out, None
                    res = module.replay(view, decide)
                assert not res["violations"], (c.setting.label, name, res["violations"])
                row.append(f"{_q(module, view, res, base):.3f} ({1 - res['accuracy']:.2f})")
            rows.append(row)
    return rows


def gt(case: NativeCase) -> str:
    audit = json.loads((ROOT / "dataset" / "audit.json").read_text(encoding="utf-8"))
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    targets = yaml.safe_load((ROOT / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8"))
    spec = {t["id"]: t for t in targets}
    tiers = tier_order(audit["settings"])
    counts = {t: len(audit["settings"][t]) for t in tiers}
    th = audit["thresholds"]
    cap = float(meta.get("quality_cap") or 1.0)
    policies = _bending_policies()
    out = [
        f"# Ground truth: {case.id}", "",
        "The ground truth (GT) of a setting in five parts, with the reference as supporting evidence. Generated by "
        f"`gt_report.py` from `dataset/audit.json` (`fdebench2 audit-case`, public world seed {audit['world_seed']}): "
        f"{sum(counts.values())} settings, " + ", ".join(f"{t} {counts[t]}" for t in tiers) + " (each tier's public "
        "panel plus admissible parameter combinations). Damage is 1 − credit, credit = 0 for an invalid program, "
        "else the quality score clipped to [0, 1]; a target bites in a setting when misreading it alone loses at "
        f"least {th['ablation_min_damage']:.2f} of the credit (for a drawn parameter: its least harmful wrong "
        "candidate). The program runs the 20 hidden working days once per evaluation; the diagnostic reads the "
        "trace of that run.", "",
        "## 1. Client facts (targets)", "",
        "One row per target: the fact, the tiers where it is in force, how the audit misreads it (a drawn parameter: "
        "the reference written for each other candidate; another fact: the reference program with that one fact "
        "read the most natural wrong way from the agent's view, everything else unchanged), the damage range over "
        "the settings where it is in force, the settings where it bites per tier (k/n) and whether its diagnostic "
        "(`enforced`, part 5) tells the reference from the misreading.", "",
    ]
    rows = []
    for t in target_summary(audit):
        tid = t["target"]
        s = spec[tid]
        how = f"the reference of each other candidate of `{s['param']}`" if s.get("param") else ABLATION[tid]
        rows.append([f"`{tid}`", _fact(s["text"]), ", ".join(t["tiers"]), how, _range([t["low"], t["high"]]),
                     ", ".join(f"{tier} {k}/{n}" for tier, (k, n) in t["per_tier"].items()), _diag(t)])
    out += _table(["target", "fact", "in force", "ablation (the natural misreading)", "damage", "bites k/n",
                   "diagnostic"], rows)
    out += ["", "What the agent's view shows, and so what each misreading is: the export's four weeks keep 09:00 "
            "and 09:20 for urgent patients only (most mornings empty), never put two patients in a slot, and have "
            "some follow-ups seen by a colleague; the pilot keeps the reserve too and reports `held_back` 0; the "
            "outpatient office's e-mail says every clinic runs on City Day unless a department says otherwise. "
            "None of the client's facts can be read off it: where the data shows a practice, it is the office's old "
            "one, and the client's answer differs.", "",
            "Facts that are no longer targets (they stay in requirements.md, and the client still answers them when "
            "asked):", ""]
    out += [f"- {name}: {why}" for name, why in REMOVED]
    out += ["", "## 2. Validity checks (hard gates)", "",
            "A program that breaks any of these is invalid and earns no credit. A program that cannot be loaded is "
            "fatal; a call that fails or times out (10 s) breaks `well_formed`.", ""]
    rows = []
    for r in meta["rules"]:
        rows.append([f"`{r['id']}`", r["class"], ", ".join(r.get("tiers", tiers)), RULE_WHY[r["id"]]])
    out += _table(["rule", "class", "tiers", "why it is a hard gate"], rows)
    out += ["", "**Mandatory outputs.** Every call returns its actions and the status table with a row for every "
            "department code and its three whole numbers (`status_table`). Every entry of a valid table that is not "
            "exact costs as much as two empty slots in the operations value (part 3).", "",
            "**The bendable habit.** `follow_up_same_doctor` is the one business-policy rule. With an approved "
            "exception the rule is switched off; a follow-up seen by a colleague then counts a tenth of a slot less "
            "(−1 a visit: the colleague needs longer), and the policy takes its soft-rule penalty off the final "
            "score (" + ", ".join(f"{penalty:g} under `{name}`" for name, _, penalty in policies) + "), in which "
            "quality is one component (" + ", ".join(f"{share:.0%} under `{name}`" for name, share, _ in policies)
            + " when every component applies, earning full credit at the quality cap "
            f"{cap:g}). The table bends the reference three ways, scored with the rule relaxed: its quality gain "
            "over the reference (and the exceptions taken), and what the best of the three nets in the final score "
            "of a program below the cap (the quality share / the cap × the gain − the penalty). So the bend pays in "
            "some settings and loses in others. Before the audit a follow-up with a colleague cost nothing, and "
            "bending every follow-up gained 0.09–0.27 of quality in every setting; easy has no absence to bend "
            "around (a locum covers it).", ""]
    out += _table(["setting"] + [f"gain: {name} (exceptions)" for name in BENDS]
                  + [f"best bend net, `{name}`" for name, _, _ in policies], _bend_rows(case, cap))
    out += ["", "**Shortcuts.** The programs a lazy or gaming engineer would deliver; each is invalid or scores at "
            f"most {th['shortcut_max_quality']:.1f} in every measured setting. The literal program (the request done "
            "exactly as written, `literal_solution`: the pilot's rules, the office's reserve practice, every notice "
            "acted on) and its near misses keep one client rule it breaks, or all of them, and with all of them "
            "either release tomorrow's reserve or report the client's table; they stay invalid or at the baseline "
            "and below, because keeping the reserve for the day before and the pilot's table are not rules but the "
            "two facts that carry the score, and one of them alone is not enough. Copying the office and changing "
            "one thing (releasing the reserve with the pilot's table; in hard, overbooking blind with the reserve "
            "kept) and reporting constants (the pilot day's numbers) are closed too.", ""]
    out += _table(["shortcut", "what it does", "closed", "best quality where valid"],
                  [[f"`{s['name']}`", s["description"], f"{s['closed']}/{s['settings']}", _num(s["best_quality"])]
                   for s in shortcut_summary(audit)])
    out += ["", "## 3. Objective (higher is better)", "",
            "objective = operations value / the reference's operations value (same setting). The operations value "
            "over the clinic days 10 November – 7 December:", "",
            "- +10 per patient-slot seen (a new patient two slots); in hard × the chance the patient comes (their own "
            "rate plus 1 point per working day of lead, at most 90% away);",
            "- −0.4 × urgency weight (U 3, S 2, R 1) per working day a request (hard: a patient's need in a "
            "department) waits, from its first possible day to its appointment, or to 8 December;",
            "- −10 per request never booked (that could come before 18 December); a patient's cancellation closes the "
            "request;",
            "- −4 per change the hospital makes to an appointment (move or release);",
            "- −1 per follow-up seen by another doctor than the patient's own (only under the exception);",
            "- −20 per entry of the daily status table that is not exact (15 entries a day; as much as two empty "
            "slots: the departments staff their clinics from the table);",
            "- hard: −30 × the chance both patients of an overbooked slot come (three empty slots; was 12), and −3 "
            "per extra hospital day of a patient booked in several departments.", "",
            "**Uncertainty.** The hard tier is expected-value scoring over the patients' no-shows. About one patient "
            "in six misses most appointments (rates around 0.6), the rest rarely do (around 0.06), and only the "
            "patient's record shows which; the history's attendance at known lead times shows the lead effect. A "
            "second follow-up in a slot is worth its own chance of coming and the waiting and unbooked cost it "
            "saves, less 30 × both chances: a pair pays when one of the two is likely to stay away, and loses when "
            "both are likely to come. Before the audit (12 for a collision, and a narrower spread of rates) "
            "overbooking every eligible slot scored as well as choosing (F2).", ""]
    ob_rows, ob_q = _overbooking_rows(case)
    out += _table(["setting", "cap per session", "reference: selective (pairs, collision cost)", "never overbook",
                   "every eligible slot (collisions free)", "true no-show rates (hindsight)"], ob_rows)
    out += ["", f"Overbooking pays (never overbooking loses {_range([1 - q[1] for q in ob_q])} of the scale), "
            f"choosing whom to pair pays more (pairing blind loses {_range([1 - q[2] for q in ob_q])}), and knowing "
            f"the true rates would add {_range([q[3] - 1 for q in ob_q])}: the hard tier measures risk selection.", "",
            "**The status table.** Each entry that is not exact costs 20, so a slip costs in proportion to how many "
            "entries it gets wrong, and the table cannot buy bookings back. The reference's own bookings with a "
            "table that slips (quality; the share of the 300 entries that are wrong):", ""]
    out += _table(["setting"] + list(SLIPS), _slip_rows(case))
    out += ["", "Until the check, the table's accuracy multiplied the objective: one entry wrong every day then "
            "cost 0.12–0.29 of the scale on the public settings, one department's row 0.36–0.86, and counting expired "
            "referrals (medium) up to the whole scale (medium/s10 kept 0.0004), because the scale is narrow where the "
            "baseline is close (0.23–0.26 of the objective on most easy and medium settings).", "",
            "## 4. Reference and bounds", "",
            "- **Reference** (`reference_solution`): `reference/scheduler.py` with the setting's `config.json`. Each "
            "day it moves (medium+) the absent doctors' appointments and the interpreter's excess, then books the "
            "waitlist and the new requests in the drawn priority order into the earliest feasible slot (the reserve "
            "only for U, or for tomorrow, every cap and date rule); in hard a waiting follow-up is doubled up next "
            "to a booked follow-up of its doctor where that is worth more than its free slot or than waiting (the "
            "chances estimated from the patient's record shrunk to the history's rate, and the lead), within the "
            "cap; it reports the exact table.",
            "- **Baseline** (quality 0, `baseline_solution`): the office's practice without an engineer: the same "
            "program, but the urgent reserve is never released for tomorrow and nothing is double-booked.",
            "- **Best known** (`best_known_solution`): the reference tuned on the hidden period itself (hindsight): "
            "coordinate search over packing (prefer slots next to occupied ones), in hard the patients' true no-show "
            "rates and the value of a free slot and of a booked request in the overbooking rule, keeping a move while "
            "the run stays valid and its objective grows.",
            "- **Bound** (`objective_bound`, proven): a linear relaxation with perfect information. Every request (hard: "
            "need) gets at most one appointment on a day from its first possible one (medium+ a day later with a "
            "fasting test, not after its referral; an urgent one within its window), with its own doctor or any of "
            "its department; the book's appointments stay or move for 4 from day 3 on; a doctor-day holds at most "
            "its calendar slots (none in the closed clinic or on an absence); hard a session also holds its "
            "overbooking cap of second follow-ups, worth their visit less collisions of at least 30 × (p1 + p2 − 1) "
            "with each chance at its lowest. Order, reserve, interpreters, lab, slot positions and arrival times are "
            "relaxed, which leaves it loose (the gaps in the table below; hard counts every visit at a day's "
            "lead). Its scope is every valid program, the habit kept.", ""]
    known = [b["best_known_quality"] for b in audit["bounds"] if b["best_known_quality"] is not None]
    gaps = [b["gap_to_bound"] for b in audit["bounds"] if b["gap_to_bound"] is not None]
    by_tier = {t: [b["best_known_quality"] for b in audit["bounds"] if b["setting"].startswith(t + "/")
                   and b["best_known_quality"] is not None] for t in tiers}
    out += [f"- **quality_cap** = {meta.get('quality_cap')}: the best known quality is {_range(known)} over the "
            f"measured settings (" + ", ".join(f"{t} {_range(v)}" for t, v in by_tier.items()) + f"; median "
            f"{median(known):.3f}), and the bound is {_range(gaps, 3)} above the reference.", ""]
    out += _table(["setting", "reference", "baseline", "span", "best known", "its quality", "bound", "bound quality",
                   "gap ref–bound"],
                  [[b["setting"], _num(b["reference"], 4), _num(b["baseline"], 3), _num(b["span"]),
                    _num(b["best_known"], 4), _num(b["best_known_quality"]), _num(b["bound"], 4),
                    _num(b["bound_quality"]), _num(b["gap_to_bound"])] for b in audit["bounds"]])
    out += ["", "**Value of asking** (the GT's claim that the client must be asked): per tier, the best program "
            "that never asks against the reference of each setting. `never asks, knows the fixed facts` is the best "
            "of the other settings' references and the baseline (it measures the drawn parameters only); `never "
            "asks (robust)` is `robust_solution`, written from the agent's view and the tier's pools alone, with "
            "the strongest reading of the fixed facts: tomorrow's reserve slots left empty by the urgent requests "
            "given to the waitlist (the program runs once a day, after the clinics, so nothing else can use them), "
            "held_back as the reserve it still holds (the export's two slots), one patient a slot (hard: overbooking "
            "with no cost for a collision), follow-ups with their doctor, notes not followed, five days' notice; "
            "drawn rules on their safe side where there is one (no booking in any clinic that may close on City "
            "Day, the larger reserve held, the smallest overbooking cap) and otherwise the pilot's order, its three "
            "interpreters and the middle lab cap; it is even given the tier's scope. The waitlist order, the "
            "interpreters and the lab cap have no safe side: the priority rule makes passing over a waiting patient "
            "for want of an interpreter or a lab place the client has as invalid as booking one too many, and "
            "dropping every booking that some candidate order forbids keeps it valid in every setting but at about "
            "a quarter of the reference's operations value. With the export's practice and the pilot's table "
            "instead (the reserve kept, `held_back` 0) a never-asking program earns 0 everywhere: keeping the "
            "reserve caps it at the baseline, and the pilot's table costs it two thirds of the table.", ""]
    out += _table(["tier", "never asks, knows the fixed facts", "value of the parameters", "never asks (robust)",
                   "value of asking"],
                  [[tier, _num(v["never_asks_params"]), _num(v["voi_params"]), _num(v["never_asks"]), _num(v["voi"])]
                   for tier, v in ((t, audit["voi"][t]) for t in tier_order(audit["voi"]))])
    out += ["", "## 5. Diagnostic cases", "",
            "`score()` records a trace of the program's own run (per call: the rule breaches with what each one "
            "concerns, the appointments placed and released, the doubled-up slots, the reported table, the true "
            "table and the table each misreading would give; at the end the overbooked pairs' chances of coming), "
            "and `diagnose()` reads it, so the program runs once per evaluation. A priority breach is given to one "
            "reading: of those that explain every request it passed over (an interpreter, a blood test, a referral "
            "date, a second request, a release, a note on the booked request, another candidate order), the one "
            "that explains the most breaches; a breach nothing explains is the order's. A day's table follows a "
            "reading only when it is exactly that reading's table.", ""]
    ref_fail = {tid: [e["label"] for tier in tiers for e in audit["settings"][tier]
                      if not e.get("skipped") and e["reference_enforced"].get(tid) is False] for tid in spec}
    rows = []
    for t in target_summary(audit):
        tid = t["target"]
        bad = sorted(set(t["undiagnosed"]) | set(ref_fail[tid]))
        rows.append([f"`{tid}`", DIAGNOSTIC[tid], _diag(t), ", ".join(bad) or "–"])
    out += _table(["target", "what tells a correct program from the misreading", "result", "settings where it fails"],
                  rows)
    out += ["", "**Reliability on other deliverables.** A run's \"enforced\" stage applies the diagnostic to the "
            "agent's program, which is neither the reference nor an ablation. Per target, the settings where it "
            "calls a deliverable not enforced, of those where it gives a verdict: the best known solution (valid and "
            "built with every fact of its setting, so each False would be a false negative), the ablations of the "
            "target that also flag another target (of the settings where the ablation bites; it misreads only its "
            "own fact), and the baseline (each setting's own: it keeps the reserve, so `reserve_release` is rightly "
            "False there) and `robust_solution` (its tier's), which do not know every fact, so a False there may be "
            "right.", ""]
    negatives, cross, profile = false_negatives(audit), cross_flag_summary(audit), audit.get("diagnostic_profile") or {}

    def cell(false, n):
        return f"{false}/{n}" if n else "–"
    rows = []
    for tid in spec:
        fn, cf = negatives.get(tid), cross.get(tid)
        flags = cell(len(cf["flagged"]), cf["biting"]) if cf else "–"
        if cf and cf["others"]:
            flags += " (" + ", ".join(f"`{u}`" for u in cf["others"]) + ")"
        rows.append([f"`{tid}`", cell(len(fn["false"]), fn["diagnosed"]) if fn else "–", flags]
                    + [cell(p[tid]["false"], p[tid]["diagnosed"]) if tid in (p := profile.get(name) or {}) else "–"
                       for name in ("baseline", "robust_solution")])
    out += _table(["target", "best known", "ablation flags another target", "baseline", "robust_solution"], rows)
    errors = (audit.get("diagnose_errors") or {}).get("count", 0)
    out += ["", f"`diagnose()` raised in {errors} evaluation(s) of the audit.", "", "## Findings of the audit", ""]
    found = summarize(findings(audit, meta.get("quality_cap")))
    out += [f"- {x}" for x in found] or ["- none: every check passes"]
    return "\n".join(out) + "\n"


# The question an engineer would naturally ask, and how to find the passages of requirements.md the client answers
# from: each spec is a list of tokens that must all occur in a passage of en (a bullet with its indented lines, or a
# paragraph; a token starting with ^ must start it), "first" takes the first such passage, "all" every one. Every
# locale's requirements.md has the same passages in the same order, so the other locales quote the same passages.
QUESTIONS = {
    "urgent_reserve": ("How many morning slots are kept for urgent patients, and which?",
                       [(["{{reserve_slots}}", "{{reserve_times}}"], "first"),
                        (["Until now the office kept only"], "first")]),
    "reserve_release": ("Your office keeps 09:00 and 09:20 for urgent patients even the day before: should the "
                        "program do the same?", [(["Releasing the reserve"], "first")]),
    "follow_up_doctor": ("Must a follow-up always be booked with the patient's previous doctor?",
                         [(["`previous_doctor`", "exception"], "first")]),
    "interpreters": ("How many in-person interpreters do you have, and who needs one?",
                     [(["{{interpreters_per_day}} in-person"], "first")]),
    "holiday_clinic": ("Is any clinic closed on City Day, 23 November?", [(["{{closed_dept}} clinic is closed"],
                                                                           "first")]),
    "move_notice": ("How much notice do patients need when you change their appointment?",
                    [(["**date or time**"], "first"), (["Every change we make"], "first")]),
    "waitlist_priority": ("In which order are waiting requests booked?",
                          [(["{{waitlist_order}}"], "first"), (["**higher priority**"], "first")]),
    "status_table": ("What exactly should the status table count?",
                     [(["^- `free_slots`"], "first"), (["^- `held_back`"], "first"), (["^- `waitlist`"], "first"),
                      (["staff their clinics"], "first"), (["The status table every day"], "first"),
                      (["for every entry of the daily status table"], "first")]),
    "staff_notes": ("What do we do with notes like \"the director's acquaintance, tomorrow morning\"?",
                    [(["Notes carry no weight"], "first")]),
    "duplicates": ("A patient sometimes asks twice for the same department: one appointment or two?",
                   [(["A second request from the same patient"], "all"),
                    (["**same patient for the same department**"], "first")]),
    "overbooking": ("About a fifth of the patients do not come: may the program book two patients into one slot?",
                    [(["so no overbooking"], "all"), (["**overbooking of follow-ups**"], "first")]),
    "referral_expiry": ("Does referral_valid_until matter for booking?",
                        [(["referral desk"], "first"), (["referral letter is valid until"], "first")]),
    "blood_test": ("What does pre_visit_test mean for the booking?",
                   [(["the lab books the fasting tests"], "first"), (["`pre_visit_test` is true"], "first")]),
    "lab_cap": ("How many fasting blood tests can the lab take a day?",
                [(["{{lab_cap}} blood tests per working day"], "first")]),
    "doctor_absence": ("What should the program do when a doctor_absence notice arrives?",
                       [(["a locum"], "first"), (["`doctor_absence`: the doctor holds no clinics"], "first")]),
    "interpreter_absence": ("What does an interpreter_absence notice change?",
                            [(["`interpreter_absence`: on that"], "first")]),
    "overbooking_cap": ("How many slots may a doctor have overbooked in one session?",
                        [(["{{overbooked_per_session}} overbooked slots per session"], "first")]),
    "collision_cost": ("What does it cost you when both patients of an overbooked slot come?",
                       [(["three empty slots"], "first"), (["− 30 ×"], "first")]),
}


def _passages(text: str) -> list[str]:
    """Bullets (each with its indented continuation lines) and paragraphs, each with the opening setting markers
    (tier, when) that stand right before it, so the reviewer sees in which settings it is said."""
    out, cur, markers = [], [], []
    for line in text.splitlines():
        starts = line.startswith("- ") or (line and not line.startswith(" ") and not line.startswith("<!--"))
        if starts:
            if cur:
                out.append("\n".join(cur))
            cur, markers = markers + [line], []
        elif line.startswith("  ") and cur:
            cur.append(line)
        else:
            if cur:
                out.append("\n".join(cur))
            cur = []
            if line.startswith("<!-- ") and not line.startswith("<!-- /"):
                markers.append(line)
            elif line.startswith("<!-- /"):
                markers = []
    if cur:
        out.append("\n".join(cur))
    return out


def _body(p: str) -> str:
    return "\n".join(line for line in p.splitlines() if not re.fullmatch(r"<!-- [^>]* -->", line))


def _tokens_of(text: str, files: dict[str, str]) -> list[str]:
    """The tokens a translation must keep: parameters, dates, clock times, numbers of 10 and more or with a decimal
    (a month number, 11月, is left out), and what stands in backticks (a field name as it is; a localized file name
    as the file it stands for)."""
    out = set(re.findall(r"\{\{\w+\}\}", text))
    for code in re.findall(r"`([^`]+)`", text):
        out.add(f"`file:{files[code]}`" if code in files else f"`{code}`")
    t = re.sub(r"`[^`]+`|\{\{\w+\}\}", " ", text)
    out |= set(re.findall(r"\d{4}-\d{2}-\d{2}", t)) | set(re.findall(r"\d{1,2}:\d{2}", t))
    t = re.sub(r"\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}", " ", t)
    # a date written in words (23 November, 23 de noviembre, 11月23日, 11월 23일) and a fraction (10분의 1): its
    # numbers are words in another locale
    t = re.sub(r"\d{1,2}月\d{1,2}日|\d{1,2}월 ?\d{1,2}일|\d{1,2} (?:de )?(?:October|November|December|octubre|"
               r"noviembre|diciembre)|\d+ ?(?:분의|分の) ?\d+", " ", t)
    t = re.sub(r"\d{1,2} ?[月월]", " ", t)
    t = re.sub(r"(\d),(\d{1,2})(?!\d)", r"\1.\2", t)
    out |= {n for n in re.findall(r"(?<![0-9A-Za-z_.])\d+(?:\.\d+)?(?![0-9A-Za-z_])", t) if "." in n or float(n) >= 10}
    return sorted(out)


def client_review(case: NativeCase) -> str:
    module = case.module
    texts = {lang: (ROOT / "locales" / lang / "requirements.md").read_text(encoding="utf-8") for lang in LANGS}
    passages = {lang: _passages(texts[lang]) for lang in LANGS}
    lengths = {lang: len(p) for lang, p in passages.items()}
    if len(set(lengths.values())) != 1:
        raise SystemExit(f"the locales' requirements.md have different passages: {lengths}")
    targets = yaml.safe_load((ROOT / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8"))
    files = {lang: {names[lang]: key for key, names in module.FILES.items()} for lang in LANGS}

    def matches(p: str, toks: list) -> bool:
        return all(_body(p).startswith(t[1:]) if t.startswith("^") else t in p for t in toks)

    def indices(specs) -> list[int]:
        out = []
        for toks, which in specs:
            hits = [i for i, p in enumerate(passages["en"]) if matches(p, toks)]
            out += hits[:1] if which == "first" else hits
        return list(dict.fromkeys(out))

    out = ["# Client answers: human review", "",
           "The simulated client answers only from `locales/<lang>/requirements.md` (plus event facts; this case has "
           "none). For every target: the question an engineer would naturally ask, the passages each locale answers "
           "from (quoted as written, with setting markers and parameters; a parameter is worded per locale by "
           "`params.<name>.labels` in case.yaml or by `derive_params` in case.py), a machine pre-check and an empty "
           "verdict for a human reviewer. Generated by `gt_report.py`.", "",
           "Pre-check: (1) the passages are found in en (every locale's requirements.md has the same passages in the "
           "same order, so the others quote the same ones); (2) the same parameters, dates, clock times, numbers "
           "and names in backticks in every locale (a localized file name compared as the file it stands for); (3) "
           "the other targets that share a passage, i.e. what the passage would answer beyond the question (the "
           "client may state them together when asked).", "",
           "**Status: awaiting human review.** No passage below has been reviewed by a person yet.", ""]
    found = {t["id"]: indices(QUESTIONS[t["id"]][1]) for t in targets}
    for t in targets:
        tid = t["id"]
        idx = found[tid]
        scope = ", ".join(t["tiers"]) if t.get("tiers") else ""
        out += [f"## `{tid}`" + (f" ({scope})" if scope else ""), "",
                f"**Question.** {QUESTIONS[tid][0]}", "", f"**Target (en).** {t['text']}", ""]
        for lang in LANGS:
            out += [f"**{lang}:**", ""]
            for i in idx or [None]:
                out += ["> " + line for line in (passages[lang][i] if i is not None else "(not found)").splitlines()]
                out.append(">")
            out.pop()
            out.append("")
        checks = ["passages found (" + str(len(idx)) + ")" if idx else "NOT FOUND in en"]
        toks = {lang: _tokens_of("\n".join(passages[lang][i] for i in idx), files[lang]) for lang in LANGS}
        ref = toks["en"]
        diff = {lang: (sorted(set(ref) - set(n)), sorted(set(n) - set(ref))) for lang, n in toks.items()
                if set(n) != set(ref)}
        checks.append("tokens differ from en: " + "; ".join(f"{lang} lacks {a or '–'}, adds {b or '–'}"
                                                             for lang, (a, b) in diff.items()) if diff else
                      "same parameters, dates, times, numbers and names in all five locales: " + (", ".join(ref) or
                                                                                                  "none"))
        same = [o for o, f in found.items() if o != tid and set(f) & set(idx)]
        checks.append("the passages also state: " + (", ".join(f"`{o}`" for o in same) if same else
                                                       "nothing else that is a target"))
        out += ["**Machine pre-check.**", ""] + [f"- {c}" for c in checks] + ["", "Reviewer verdict:", ""]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    which = sys.argv[1:] or ["gt", "client"]      # "client" needs no audit, "gt" reads dataset/audit.json
    the_case = NativeCase(ROOT)
    if "client" in which:
        (ROOT / "CLIENT_REVIEW.md").write_text(client_review(the_case), encoding="utf-8")
        print("wrote", ROOT / "CLIENT_REVIEW.md")
    if "gt" in which:
        (ROOT / "GT.md").write_text(gt(the_case), encoding="utf-8")
        print("wrote", ROOT / "GT.md")
