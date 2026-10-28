"""Call-center weekly shift rostering (original FDE-Bench v2 case).

A multilingual customer-support center needs next week's roster. The request
only says "make sure we have enough people on the phones"; what decides
validity and quality (one language per agent per shift, contract limits, rest
time, leave in a differently formatted file, a public holiday that cuts demand,
the overtime premium, the new-hire buddy habit, the under-staffing penalty) is
in the requirements and must be asked for.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from fdebench2.casekit import Fatal, labels, read_json, write_csv, write_xlsx

# ── world ────────────────────────────────────────────────────────────────────

WEEK_START = dt.date(2026, 11, 9)          # Monday
DAYS = [WEEK_START + dt.timedelta(days=i) for i in range(7)]
HOLIDAY = 2                                # Wednesday 2026-11-11: demand is 60 % of the forecast (rounded up)
HOLIDAY_FACTOR = 0.6
OPEN_MIN, CLOSE_MIN = 8 * 60, 22 * 60      # phones open 08:00-22:00
SLOT = 30
N_SLOTS = (CLOSE_MIN - OPEN_MIN) // SLOT   # 28 half-hour slots per day
LANGS = ["ko", "ja", "en", "zh", "es"]
SHIFTS = {  # id: (start minute, length minutes, contract)
    "S0800": (8 * 60, 480, "FT"), "S1000": (10 * 60, 480, "FT"), "S1200": (12 * 60, 480, "FT"),
    "S1400": (14 * 60, 480, "FT"),
    "P0800": (8 * 60, 240, "PT"), "P1200": (12 * 60, 240, "PT"), "P1600": (16 * 60, 240, "PT"),
    "P1800": (18 * 60, 240, "PT"),
}
MAX_SHIFTS = {"FT": 5, "PT": 3}
REGULAR_FT_SHIFTS = 4                      # the 5th full-time shift of the week is overtime
OVERTIME = 1.5
RATE = {"FT": 22.0, "PT": 18.0}            # per hour
MIN_REST = 11 * 60
UNDER_WEIGHT = 40.0                        # per missing agent per half-hour slot


@dataclass
class Agent:
    id: str
    name: str
    contract: str            # FT | PT
    langs: list[str]
    new_hire: bool


@dataclass
class World:
    agents: list[Agent]
    demand: dict             # (day index, slot, lang) -> agents needed, as in the forecast file
    leave: list[dict] = field(default_factory=list)   # {agent, from, to, approved}
    _cache: dict = field(default_factory=dict)

    def agent(self, aid: str) -> Agent | None:
        if "by_id" not in self._cache:
            self._cache["by_id"] = {a.id: a for a in self.agents}
        return self._cache["by_id"].get(aid)

    def need(self, d: int, s: int, lang: str) -> int:
        v = self.demand[(d, s, lang)]
        return math.ceil(v * HOLIDAY_FACTOR - 1e-9) if d == HOLIDAY else v

    def on_leave(self, aid: str, d: int) -> bool:
        day = DAYS[d]
        return any(l["agent"] == aid and l["approved"] and l["from"] <= day <= l["to"] for l in self.leave)


FIRST = ["Minji", "Yuki", "Wei", "Lucia", "Daniel", "Seojun", "Haruto", "Mei", "Carlos", "Emma", "Jiwoo", "Aoi",
         "Hao", "Sofia", "Liam", "Yuna", "Ren", "Xin", "Diego", "Olivia", "Hyejin", "Sora", "Lin", "Valeria",
         "Noah", "Dahye", "Kenta", "Jing", "Mateo", "Grace"]
LAST = ["Kim", "Sato", "Chen", "Garcia", "Brown", "Park", "Tanaka", "Wang", "Lopez", "Wilson", "Lee", "Suzuki",
        "Zhang", "Martinez", "Taylor", "Choi", "Ito", "Liu", "Torres", "Clark"]


def build_world(seed: int) -> World:
    rng = random.Random(seed)
    primaries = ["ko"] * 9 + ["en"] * 7 + ["ja"] * 5 + ["zh"] * 5 + ["es"] * 4
    rng.shuffle(primaries)
    pt_ids = set(rng.sample(range(30), 10))
    new_ids = set(rng.sample(sorted(set(range(30)) - pt_ids), 4))
    agents = []
    for i in range(30):
        langs = [primaries[i]]
        if primaries[i] != "en" and rng.random() < 0.55:
            langs.append("en")
        if rng.random() < 0.3:
            extra = rng.choice([l for l in LANGS if l not in langs])
            langs.append(extra)
        agents.append(Agent(id=f"A{i + 1:02d}", name=f"{FIRST[i]} {rng.choice(LAST)}",
                            contract="PT" if i in pt_ids else "FT", langs=langs, new_hire=i in new_ids))
    share = {"ko": 4.2, "en": 3.0, "ja": 2.0, "zh": 1.9, "es": 1.3}
    day_factor = [1.15, 1.05, 1.0, 1.0, 1.1, 0.75, 0.6]
    demand = {}
    for d in range(7):
        for s in range(N_SLOTS):
            h = 8 + s / 2
            curve = 0.55 + 0.45 * math.exp(-((h - 11) / 2.0) ** 2) + 0.35 * math.exp(-((h - 15.5) / 2.2) ** 2)
            curve *= 1.0 if h < 19 else 0.75
            for lang in LANGS:
                x = share[lang] * curve * day_factor[d] * rng.uniform(0.9, 1.1)
                demand[(d, s, lang)] = max(1, int(round(x)))
    on_leave = rng.sample([a.id for a in agents], 5)
    leave = []
    for k, aid in enumerate(on_leave):
        start = rng.randrange(0, 5)
        length = rng.choice([1, 2, 3])
        leave.append({"agent": aid, "from": DAYS[start], "to": DAYS[min(6, start + length - 1)], "approved": k != 3})
    return World(agents, demand, leave)


# ── data rendering ───────────────────────────────────────────────────────────

FILES = {
    # Names chosen so the workbook sorts first in every locale (the validator compares file-set shapes in name order).
    "staff": {"zh": "人员名单.xlsx", "en": "agents.xlsx", "ko": "고객센터_상담원명단.xlsx", "ja": "オペレーター一覧.xlsx",
              "es": "agentes.xlsx"},
    "forecast": {"zh": "话务量预测.csv", "en": "call_forecast.csv", "ko": "콜예측.csv", "ja": "入電予測.csv",
                 "es": "prevision_llamadas.csv"},
    "leave": {"zh": "请假记录.csv", "en": "leave.csv", "ko": "휴가목록.csv", "ja": "休暇一覧.csv", "es": "ausencias.csv"},
    "shifts": {"zh": "班次.csv", "en": "shifts.csv", "ko": "근무유형.csv", "ja": "シフト.csv", "es": "turnos.csv"},
    "cost": {"zh": "人工成本.csv", "en": "labor_cost.csv", "ko": "인건비.csv", "ja": "人件費.csv", "es": "costes.csv"},
}
SHEETS = {
    "staff": {"zh": "员工", "en": "staff", "ko": "상담원", "ja": "担当者", "es": "personal"},
    "skills": {"zh": "语言技能", "en": "skills", "ko": "언어능력", "ja": "対応言語", "es": "idiomas"},
}
COLS = {
    "agent": {"zh": "工号", "en": "agent_id", "ko": "상담원ID", "ja": "担当者ID", "es": "id_agente"},
    "name": {"zh": "姓名", "en": "name", "ko": "이름", "ja": "氏名", "es": "nombre"},
    "contract": {"zh": "用工类型", "en": "contract", "ko": "고용형태", "ja": "雇用形態", "es": "contrato"},
    "new_hire": {"zh": "新员工", "en": "new_hire", "ko": "신입여부", "ja": "新人", "es": "nuevo_ingreso"},
    "language": {"zh": "语言", "en": "language", "ko": "언어", "ja": "言語", "es": "idioma"},
    "date": {"zh": "日期", "en": "date", "ko": "날짜", "ja": "日付", "es": "fecha"},
    "weekday": {"zh": "星期", "en": "weekday", "ko": "요일", "ja": "曜日", "es": "dia_semana"},
    "slot": {"zh": "时段开始", "en": "slot_start", "ko": "시작시각", "ja": "開始時刻", "es": "inicio_franja"},
    "needed": {"zh": "所需坐席数", "en": "agents_needed", "ko": "필요인원", "ja": "必要人数", "es": "agentes_necesarios"},
    "from": {"zh": "开始日期", "en": "from", "ko": "시작일", "ja": "開始日", "es": "desde"},
    "to": {"zh": "结束日期", "en": "to", "ko": "종료일", "ja": "終了日", "es": "hasta"},
    "status": {"zh": "审批状态", "en": "status", "ko": "결재상태", "ja": "承認状況", "es": "estado"},
    "shift": {"zh": "班次编号", "en": "shift_id", "ko": "근무코드", "ja": "シフトコード", "es": "id_turno"},
    "start": {"zh": "上班时间", "en": "start", "ko": "시작", "ja": "開始", "es": "inicio"},
    "end": {"zh": "下班时间", "en": "end", "ko": "종료", "ja": "終了", "es": "fin"},
    "hours": {"zh": "时长_小时", "en": "hours", "ko": "근무시간", "ja": "時間数", "es": "horas"},
    "rate": {"zh": "时薪", "en": "hourly_rate", "ko": "시급", "ja": "時給", "es": "tarifa_hora"},
}
VALUES = {
    "FT": {"zh": "全职", "en": "full-time", "ko": "정규직", "ja": "正社員", "es": "jornada completa"},
    "PT": {"zh": "兼职", "en": "part-time", "ko": "파트타임", "ja": "パート", "es": "media jornada"},
    "yes": {"zh": "是", "en": "yes", "ko": "예", "ja": "はい", "es": "sí"},
    "no": {"zh": "否", "en": "no", "ko": "아니오", "ja": "いいえ", "es": "no"},
    "approved": {"zh": "已批准", "en": "approved", "ko": "승인", "ja": "承認済み", "es": "aprobada"},
    "rejected": {"zh": "已驳回", "en": "rejected", "ko": "반려", "ja": "却下", "es": "rechazada"},
    "ko": {"zh": "韩语", "en": "Korean", "ko": "한국어", "ja": "韓国語", "es": "coreano"},
    "ja": {"zh": "日语", "en": "Japanese", "ko": "일본어", "ja": "日本語", "es": "japonés"},
    "en": {"zh": "英语", "en": "English", "ko": "영어", "ja": "英語", "es": "inglés"},
    "zh": {"zh": "中文", "en": "Chinese", "ko": "중국어", "ja": "中国語", "es": "chino"},
    "es": {"zh": "西班牙语", "en": "Spanish", "ko": "스페인어", "ja": "スペイン語", "es": "español"},
}
WEEKDAYS = {
    "zh": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "ko": ["월", "화", "수", "목", "금", "토", "일"],
    "ja": ["月", "火", "水", "木", "金", "土", "日"],
    "es": ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"],
}


def _hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def write_data(world: World, data_dir: Path, lang: str) -> None:
    c, v = labels(COLS, lang), labels(VALUES, lang)
    write_xlsx(data_dir / FILES["staff"][lang], {
        SHEETS["staff"][lang]: ([c["agent"], c["name"], c["contract"], c["new_hire"]],
                                [[a.id, a.name, v[a.contract], v["yes" if a.new_hire else "no"]] for a in world.agents]),
        SHEETS["skills"][lang]: ([c["agent"], c["language"]],
                                 [[a.id, v[l]] for a in world.agents for l in a.langs]),
    })
    rows = [[DAYS[d].isoformat(), WEEKDAYS[lang][d], _hhmm(OPEN_MIN + s * SLOT), v[l], world.demand[(d, s, l)]]
            for d in range(7) for s in range(N_SLOTS) for l in LANGS]
    write_csv(data_dir / FILES["forecast"][lang], [c["date"], c["weekday"], c["slot"], c["language"], c["needed"]], rows)
    write_csv(data_dir / FILES["leave"][lang], [c["agent"], c["from"], c["to"], c["status"]],
              [[l["agent"], l["from"].strftime("%d/%m/%Y"), l["to"].strftime("%d/%m/%Y"),
                v["approved" if l["approved"] else "rejected"]] for l in world.leave])
    write_csv(data_dir / FILES["shifts"][lang], [c["shift"], c["start"], c["end"], c["hours"], c["contract"]],
              [[sid, _hhmm(st), _hhmm(st + ln), ln // 60, v[ct]] for sid, (st, ln, ct) in SHIFTS.items()])
    write_csv(data_dir / FILES["cost"][lang], [c["contract"], c["rate"]],
              [[v[ct], RATE[ct]] for ct in ("FT", "PT")])


# ── scoring ──────────────────────────────────────────────────────────────────

def _slots(shift: str) -> range:
    st, ln, _ = SHIFTS[shift]
    first = (st - OPEN_MIN) // SLOT
    return range(first, first + ln // SLOT)


def _parse(world: World, raw) -> list[tuple[str, int, str, str]]:
    if not isinstance(raw, list):
        raise Fatal("roster.json must be an object with an 'assignments' list")
    out = []
    day_index = {d.isoformat(): i for i, d in enumerate(DAYS)}
    for k, a in enumerate(raw):
        if not isinstance(a, dict):
            raise Fatal(f"assignment {k} is not an object")
        aid, day, shift, lang = (str(a.get(x, "")).strip() for x in ("agent", "day", "shift", "language"))
        if world.agent(aid) is None:
            raise Fatal(f"assignment {k}: unknown agent {aid!r}")
        if day not in day_index:
            raise Fatal(f"assignment {k}: day {day!r} is not a date of the week 2026-11-09..2026-11-15 (YYYY-MM-DD)")
        if shift not in SHIFTS:
            raise Fatal(f"assignment {k}: unknown shift {shift!r}")
        if lang not in LANGS:
            raise Fatal(f"assignment {k}: unknown language code {lang!r} (use one of {LANGS})")
        out.append((aid, day_index[day], shift, lang))
    return out


def evaluate_roster(world: World, assignments: list[tuple[str, int, str, str]]) -> tuple[list, float, dict]:
    violations: list[tuple[str, str]] = []
    by_agent: dict[str, list] = {}
    cover: dict[tuple[int, int, str], int] = {}
    senior: dict[tuple[int, int, str], int] = {}
    for aid, d, shift, lang in assignments:
        ag = world.agent(aid)
        by_agent.setdefault(aid, []).append((d, shift, lang))
        if lang not in ag.langs:
            violations.append(("skill_valid", f"{aid} does not speak {lang} ({DAYS[d]} {shift})"))
        if SHIFTS[shift][2] != ag.contract:
            violations.append(("shift_type", f"{aid} is {ag.contract} but works {shift} on {DAYS[d]}"))
        if world.on_leave(aid, d):
            violations.append(("leave_respected", f"{aid} is on approved leave on {DAYS[d]}"))
        for s in _slots(shift):
            cover[(d, s, lang)] = cover.get((d, s, lang), 0) + 1
            if not ag.new_hire:
                senior[(d, s, lang)] = senior.get((d, s, lang), 0) + 1
    cost = 0.0
    for aid, items in by_agent.items():
        ag = world.agent(aid)
        if len(items) > MAX_SHIFTS[ag.contract]:
            violations.append(("max_shifts", f"{aid} works {len(items)} shifts > {MAX_SHIFTS[ag.contract]}"))
        spans = sorted((d * 1440 + SHIFTS[sh][0], d * 1440 + SHIFTS[sh][0] + SHIFTS[sh][1], d, sh) for d, sh, _ in items)
        for (s1, e1, d1, sh1), (s2, e2, d2, sh2) in zip(spans, spans[1:]):
            if s2 - e1 < MIN_REST:
                violations.append(("min_rest", f"{aid}: only {(s2 - e1) / 60:.1f} h between {DAYS[d1]} {sh1} "
                                               f"and {DAYS[d2]} {sh2}"))
        for k, (d, sh, _) in enumerate(sorted(items)):
            pay = RATE[ag.contract] * SHIFTS[sh][1] / 60
            if ag.contract == "FT" and k >= REGULAR_FT_SHIFTS:
                pay *= OVERTIME
            cost += pay
        if ag.new_hire:
            for d, sh, lang in items:
                bad = [s for s in _slots(sh) if senior.get((d, s, lang), 0) == 0]
                if bad:
                    violations.append(("buddy_rule", f"new hire {aid} on {DAYS[d]} {sh} ({lang}) has no senior "
                                                     f"{lang} agent from {_hhmm(OPEN_MIN + bad[0] * SLOT)}"))
    under = sum(max(0, world.need(d, s, l) - cover.get((d, s, l), 0))
                for d in range(7) for s in range(N_SLOTS) for l in LANGS)
    objective = UNDER_WEIGHT * under + cost
    return violations, objective, {"under_covered_agent_slots": under, "labor_cost": round(cost, 2),
                                   "assignments": len(assignments)}


def score(world: World, submission_dir: Path) -> dict:
    try:
        doc = read_json(submission_dir, "roster.json")
        assignments = _parse(world, doc.get("assignments") if isinstance(doc, dict) else None)
        if not assignments:
            raise Fatal("roster.json has no assignments")
        violations, objective, metrics = evaluate_roster(world, assignments)
    except Fatal as e:
        return {"fatal": str(e)}
    return {"violations": violations, "objective": objective, "metrics": metrics}


# ── reference solution ───────────────────────────────────────────────────────

def _solve(world: World) -> list[tuple[str, int, str, str]]:
    """Greedy: repeatedly add the (agent, day, shift, language) with the best gain, honouring every rule."""
    if "ref" in world._cache:
        return list(world._cache["ref"])
    resid = {(d, s, l): world.need(d, s, l) for d in range(7) for s in range(N_SLOTS) for l in LANGS}
    senior = {k: 0 for k in resid}
    work: dict[str, dict[int, str]] = {a.id: {} for a in world.agents}
    chosen: list[tuple[str, int, str, str]] = []

    def feasible(a: Agent, d: int, sh: str) -> bool:
        mine = work[a.id]
        if d in mine or len(mine) >= MAX_SHIFTS[a.contract] or world.on_leave(a.id, d):
            return False
        st, ln, _ = SHIFTS[sh]
        if d - 1 in mine:
            pst, pln, _ = SHIFTS[mine[d - 1]]
            if st + 1440 - (pst + pln) < MIN_REST:
                return False
        if d + 1 in mine:
            if SHIFTS[mine[d + 1]][0] + 1440 - (st + ln) < MIN_REST:
                return False
        return True

    while True:
        best = None
        for a in world.agents:
            n = len(work[a.id])
            pay = RATE[a.contract] * (8 if a.contract == "FT" else 4)
            if a.contract == "FT" and n >= REGULAR_FT_SHIFTS:
                pay *= OVERTIME
            for d in range(7):
                for sh, (_, _, ct) in SHIFTS.items():
                    if ct != a.contract or not feasible(a, d, sh):
                        continue
                    for l in a.langs:
                        slots = _slots(sh)
                        if a.new_hire and any(senior[(d, s, l)] == 0 for s in slots):
                            continue
                        gain = UNDER_WEIGHT * sum(1 for s in slots if resid[(d, s, l)] > 0) - pay
                        # Prefer seniors slightly, so that new hires find buddies later.
                        key = (gain, 0 if a.new_hire else 1, -len(a.langs))
                        if gain > 0 and (best is None or key > best[0]):
                            best = (key, a, d, sh, l)
        if best is None:
            break
        _, a, d, sh, l = best
        work[a.id][d] = sh
        chosen.append((a.id, d, sh, l))
        for s in _slots(sh):
            resid[(d, s, l)] -= 1
            if not a.new_hire:
                senior[(d, s, l)] += 1
    world._cache["ref"] = list(chosen)
    return chosen


def _dump(assignments) -> dict:
    return {"assignments": [{"agent": a, "day": DAYS[d].isoformat(), "shift": sh, "language": l}
                            for a, d, sh, l in sorted(assignments, key=lambda x: (x[1], x[2], x[0]))]}


def reference_solution(world: World, out_dir: Path) -> None:
    (out_dir / "roster.json").write_text(json.dumps(_dump(_solve(world)), indent=2), encoding="utf-8")


def violating_examples(world: World) -> dict:
    """One deliverable per rule that breaks exactly that rule (for the validator).

    Small edits of the reference, tried in this order: change the language of one assignment, add one
    assignment, move one assignment of an agent to another day, shift or language. Moving matters when every
    agent who could break a rule is already at their weekly maximum (e.g. all approved-leave agents are
    part-timers with 3 shifts): adding a shift would then also break max_shifts, moving one does not.
    """
    ref = _solve(world)
    wanted = {"skill_valid", "shift_type", "max_shifts", "min_rest", "leave_respected", "buddy_rule"}
    found: dict[str, list] = {}

    def consider(cand):
        v = {r for r, _ in evaluate_roster(world, cand)[0]}
        if len(v) == 1:
            r = next(iter(v))
            if r in wanted and r not in found:
                found[r] = cand

    def candidates():
        for i, (aid, d, sh, l) in enumerate(ref):
            for l2 in LANGS:
                if l2 != l:
                    yield ref[:i] + [(aid, d, sh, l2)] + ref[i + 1:]
        for a in world.agents:
            for d in range(7):
                for sh in SHIFTS:
                    for l in a.langs:
                        yield ref + [(a.id, d, sh, l)]
        for i, (aid, d, sh, l) in enumerate(ref):
            for d2 in range(7):
                for sh2 in SHIFTS:
                    for l2 in world.agent(aid).langs:
                        if (d2, sh2, l2) != (d, sh, l):
                            yield ref[:i] + [(aid, d2, sh2, l2)] + ref[i + 1:]

    for cand in candidates():
        consider(cand)
        if len(found) == len(wanted):
            break
    missing = wanted - set(found)
    if missing:
        raise AssertionError(f"no clean violating example for {sorted(missing)}")

    def write(cand):
        return lambda out: (out / "roster.json").write_text(json.dumps(_dump(cand)), encoding="utf-8")

    return {r: write(c) for r, c in found.items()}
