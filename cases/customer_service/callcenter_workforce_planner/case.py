"""Call-center weekly shift rostering (original FDE-Bench v2 case).

A multilingual customer-support center needs next week's roster. The request
only says "make sure we have enough people on the phones"; what decides
validity and quality is in the requirements and must be asked for. The case
has settings (DESIGN.md, Settings): three tiers on the same data and request,
and rule parameters that a rule seed draws from candidate pools (case.yaml
`params:`).

- easy: the core staffing problem: one language per agent per shift, contract
  shift types, the full-time and part-time contract weeks (nobody works beyond
  them), the rest time between two shifts, leave in a differently formatted
  file, a regional holiday on a drawn weekday that cuts that day's demand, and
  the price of a missing agent that trades under-staffing against labor cost
  (paid by the shift, except the part-timers' guaranteed weeks and the new
  hires' training salary, which are paid whether or not they are rostered).
- medium: plus overtime (one extra full-time shift a week, only with the
  operations manager's approval and at 1.5 times the rate: a business policy
  that an approved exception can bend) and the new-hire buddy rule.
- hard: plus a dated sick call: the team lead's note in the data says the
  agent it names will be back on Monday and should be rostered as usual, but
  the doctor's certificate the client received the next morning keeps them off
  sick for the first days of the week.

The parameters: the price of a missing agent, the full-time and the part-time
contract week, the rest hours, the holiday's day and its share of the
forecast, and the last day of the sick leave.

Ground truth audit (fdebench2.audit, GT.md): `ablations`, `shortcuts`,
`robust_solution`, `best_known_solution`, `objective_bound` and `diagnose`
are at the end of the file.
"""

from __future__ import annotations

import dataclasses
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
OVERTIME = 1.5                             # pay factor of a full-timer's shift beyond the contract week
RATE = {"FT": 22.0, "PT": 18.0}            # per hour


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
        end = min(6, start + length - 1)
        if k == 3:  # the rejected request stays within Mon 9 - Thu 12, so no day above 12 gives d/m/y away
            start, end = min(start, 3), min(end, 3)
        leave.append({"agent": aid, "from": DAYS[start], "to": DAYS[end], "approved": k != 3})
    return World(agents, demand, leave)


def sick_agent(world: World) -> Agent:
    """The agent the team lead's note is about: an experienced full-timer with no leave request, whose main
    language has the fewest experienced speakers (the lowest id on a tie). Their absence is felt."""
    seniors = [a for a in world.agents if not a.new_hire]
    speakers = {l: sum(l in a.langs for a in seniors) for l in LANGS}
    asked = {l["agent"] for l in world.leave}
    pool = [a for a in seniors if a.contract == "FT" and a.id not in asked]
    return min(pool, key=lambda a: (speakers[a.langs[0]], a.id))


# ── the setting's rules ──────────────────────────────────────────────────────

def derive_params(params: dict, tier: str) -> dict:
    """The contract weeks in shifts. A full-timer's weekly cap is the contract week in easy (no overtime this
    round) and one shift more from medium (the overtime shift, which needs approval); a part-timer's is their
    contract week in every tier."""
    regular = int(params["ft_week_hours"]) // 8
    return {"ft_regular_shifts": regular, "ft_max_shifts": regular + (0 if tier == "easy" else 1),
            "pt_max_shifts": int(params["pt_week_hours"]) // 4}


@dataclass(frozen=True)
class Rules:
    """What the scorer and the solvers read from a setting (hashable: plans are cached per Rules)."""

    weight: float                 # per missing agent per half-hour slot and language
    holiday_day: int | None       # index in DAYS of the regional holiday; None: no day is cut
    holiday_factor: float         # that day's share of the forecast, rounded up
    ft_regular: int               # the full-time contract week in shifts: the cap without overtime
    ft_max: int                   # the full-time weekly cap: ft_regular (easy) or one overtime shift more
    pt_max: int                   # the part-time contract week in shifts
    overtime: float               # pay factor of a full-timer's shifts beyond ft_regular
    min_rest: int | None          # minutes between two shifts of an agent; None: only one shift a day
    buddy: bool                   # new hires never alone on a language
    sick_agent: str | None        # the agent off sick on sick_days (hard)
    sick_days: frozenset = frozenset()
    pt_guaranteed: bool = True    # a part-timer's contract week is paid whether or not all of it is rostered
    training_salary: bool = True  # so is a new hire's (their training salary)

    @property
    def approval(self) -> bool:
        """Overtime exists and needs approval (medium, hard): a shift beyond the contract week breaks
        overtime_approval; in easy the contract week is the cap itself."""
        return self.ft_max > self.ft_regular

    def max_shifts(self, contract: str) -> int:
        return self.ft_max if contract == "FT" else self.pt_max

    def need(self, world: World, d: int, s: int, lang: str) -> int:
        v = world.demand[(d, s, lang)]
        return math.ceil(v * self.holiday_factor - 1e-9) if d == self.holiday_day else v

    def unavailable(self, world: World, aid: str, d: int) -> bool:
        return world.on_leave(aid, d) or (aid == self.sick_agent and d in self.sick_days)

    def planned(self) -> "Rules":
        """The rules a roster that asks for no exception plans with: no overtime shift."""
        return dataclasses.replace(self, ft_max=self.ft_regular)


def _day_index(value) -> int:
    return DAYS.index(dt.date.fromisoformat(str(value)))


def rules_for(world: World, setting) -> Rules:
    p, medium, hard = setting.params, setting.at_least("medium"), setting.at_least("hard")
    last_sick = dt.date.fromisoformat(str(p["sick_until"]))
    sick_days = frozenset(d for d in range(7) if DAYS[d] <= last_sick) if hard else frozenset()
    return Rules(weight=float(p["under_weight"]), holiday_day=_day_index(p["holiday_day"]),
                 holiday_factor=float(p["holiday_factor"]),
                 ft_regular=int(p["ft_regular_shifts"]), ft_max=int(p["ft_max_shifts"]),
                 pt_max=int(p["pt_max_shifts"]), overtime=OVERTIME, min_rest=int(p["min_rest"]) * 60,
                 buddy=medium, sick_agent=sick_agent(world).id if sick_days else None, sick_days=sick_days)


def rule_ids(setting) -> set[str]:
    """The rules of case.yaml that apply in the setting's tier."""
    ids = {"skill_valid", "shift_type", "max_shifts", "min_rest", "leave_respected"}
    if setting.at_least("medium"):
        ids |= {"overtime_approval", "buddy_rule"}
    if setting.at_least("hard"):
        ids.add("sick_leave")
    return ids


# ── data rendering ───────────────────────────────────────────────────────────

FILES = {
    "staff": {"zh": "人员名单.xlsx", "en": "agents.xlsx", "ko": "고객센터_상담원명단.xlsx", "ja": "オペレーター一覧.xlsx",
              "es": "agentes.xlsx"},
    "forecast": {"zh": "话务量预测.csv", "en": "call_forecast.csv", "ko": "콜예측.csv", "ja": "入電予測.csv",
                 "es": "prevision_llamadas.csv"},
    "leave": {"zh": "请假记录.csv", "en": "leave.csv", "ko": "휴가목록.csv", "ja": "休暇一覧.csv", "es": "ausencias.csv"},
    "shifts": {"zh": "班次.csv", "en": "shifts.csv", "ko": "근무유형.csv", "ja": "シフト.csv", "es": "turnos.csv"},
    "cost": {"zh": "人工成本.csv", "en": "labor_cost.csv", "ko": "인건비.csv", "ja": "人件費.csv", "es": "costes.csv"},
    "note": {"zh": "组长留言.txt", "en": "team_lead_note.txt", "ko": "팀장_메모.txt", "ja": "リーダーからの連絡.txt",
             "es": "nota_responsable_equipo.txt"},
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
    "FT": {"zh": "全职", "en": "full-time", "ko": "풀타임", "ja": "正社員", "es": "jornada completa"},
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
# The team lead's note (every setting): the agent is off sick and "will be fine by Monday, roster them as usual".
# In easy and medium that is what happens; in hard a doctor's certificate the client received the next morning
# keeps them off sick for the first days of the week (the requirements say so, the data does not).
NOTE = {
    "zh": ("发件人：{lang}组组长\n收件人：排班负责人\n时间：2026年11月5日（周四）17:40\n主题：{aid} 下周排班\n\n"
           "{name}（{aid}）从周三起因流感请病假。今天下午我和{first}通了电话，说周一就能好。"
           "下周请照常给{first}排班，{lang}组离不开这个人。\n"),
    "en": ("From: team lead, {lang} line\nTo: workforce planning\nSent: Thursday 5 November 2026, 17:40\n"
           "Subject: {aid} next week\n\n"
           "{name} ({aid}) has been off sick since Wednesday with the flu. I spoke to {first} this afternoon and "
           "they say they'll be fine by Monday. Please just roster {first} as usual next week, we can't spare "
           "them on the {lang} line.\n"),
    "ko": ("보낸 사람: {lang} 파트 팀장\n받는 사람: 근무표 담당\n보낸 시각: 2026년 11월 5일(목) 17:40\n"
           "제목: {aid} 다음 주 근무\n\n"
           "{name}({aid}) 님이 수요일부터 독감으로 병가 중입니다. 오늘 오후에 {first} 님과 통화했는데 월요일이면 "
           "괜찮다고 합니다. 다음 주에도 평소처럼 근무에 넣어 주세요. {lang} 파트에서 빠지면 안 되는 사람입니다.\n"),
    "ja": ("差出人：{lang}チーム リーダー\n宛先：シフト作成担当\n送信日時：2026年11月5日（木）17:40\n"
           "件名：{aid} 来週のシフト\n\n"
           "{name}さん（{aid}）は水曜日からインフルエンザで病欠しています。今日の午後に電話で話したところ、"
           "月曜日には大丈夫とのことです。来週もいつもどおりシフトに入れてください。{lang}チームには欠かせない人です。\n"),
    "es": ("De: responsable del equipo de {lang}\nPara: planificación de personal\n"
           "Enviado: jueves 5 de noviembre de 2026, 17:40\nAsunto: {aid}, la semana que viene\n\n"
           "{name} ({aid}) está de baja por gripe desde el miércoles. He hablado con {first} esta tarde y dice que "
           "el lunes estará bien. Por favor, incluid a {first} en el cuadrante como siempre la semana que viene: "
           "en el equipo de {lang} no podemos prescindir de esta persona.\n"),
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
    sick = sick_agent(world)
    (data_dir / FILES["note"][lang]).write_text(
        NOTE[lang].format(lang=v[sick.langs[0]], aid=sick.id, name=sick.name, first=sick.name.split()[0]),
        encoding="utf-8")


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


def _guaranteed(agent: Agent, R: Rules) -> int:
    """The shifts an agent is paid for whether or not they are rostered: a part-timer's contract week (guaranteed
    hours) and a new hire's (training salary); 0 for an experienced full-timer, who is paid for the shifts worked."""
    if agent.contract == "PT":
        return R.pt_max if R.pt_guaranteed else 0
    return R.ft_regular if agent.new_hire and R.training_salary else 0


def _pay(agent: Agent, n: int, R: Rules) -> float:
    """What an agent with `n` shifts costs: hours times rate, at least the guaranteed week (_guaranteed), and a
    full-timer's shifts beyond the contract week at the overtime factor (every shift of an agent has the same
    length)."""
    base = RATE[agent.contract] * (8 if agent.contract == "FT" else 4)
    extra = max(0, n - R.ft_regular) if agent.contract == "FT" else 0
    return base * max(n, _guaranteed(agent, R)) + base * (R.overtime - 1.0) * extra


def evaluate_roster(world: World, assignments: list[tuple[str, int, str, str]], R: Rules) -> tuple[list, float, dict]:
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
        if aid == R.sick_agent and d in R.sick_days:
            violations.append(("sick_leave", f"{aid} is off sick (doctor's certificate) on {DAYS[d]}"))
        for s in _slots(shift):
            cover[(d, s, lang)] = cover.get((d, s, lang), 0) + 1
            if not ag.new_hire:
                senior[(d, s, lang)] = senior.get((d, s, lang), 0) + 1
    overtime = 0
    for aid, items in by_agent.items():
        ag = world.agent(aid)
        if len(items) > R.max_shifts(ag.contract):
            violations.append(("max_shifts", f"{aid} works {len(items)} shifts > {R.max_shifts(ag.contract)}"))
        if ag.contract == "FT" and len(items) > R.ft_regular:
            overtime += len(items) - R.ft_regular
            if R.approval:
                violations.append(("overtime_approval", f"{aid} works {len(items)} shifts, {len(items) - R.ft_regular} "
                                                        f"beyond the contract week of {R.ft_regular}, without approval"))
        if R.min_rest is None:
            days = sorted(d for d, _, _ in items)
            for d in sorted({d for d in days if days.count(d) > 1}):
                violations.append(("min_rest", f"{aid} works {days.count(d)} shifts on {DAYS[d]}"))
        else:
            spans = sorted((d * 1440 + SHIFTS[sh][0], d * 1440 + SHIFTS[sh][0] + SHIFTS[sh][1], d, sh)
                           for d, sh, _ in items)
            for (s1, e1, d1, sh1), (s2, e2, d2, sh2) in zip(spans, spans[1:]):
                if s2 - e1 < R.min_rest:
                    violations.append(("min_rest", f"{aid}: only {(s2 - e1) / 60:.1f} h between {DAYS[d1]} {sh1} "
                                                   f"and {DAYS[d2]} {sh2}"))
        if ag.new_hire and R.buddy:
            for d, sh, lang in items:
                bad = [s for s in _slots(sh) if senior.get((d, s, lang), 0) == 0]
                if bad:
                    violations.append(("buddy_rule", f"new hire {aid} on {DAYS[d]} {sh} ({lang}) has no senior "
                                                     f"{lang} agent from {_hhmm(OPEN_MIN + bad[0] * SLOT)}"))
    cost = sum(_pay(a, len(by_agent.get(a.id, ())), R) for a in world.agents)
    under = sum(max(0, R.need(world, d, s, l) - cover.get((d, s, l), 0))
                for d in range(7) for s in range(N_SLOTS) for l in LANGS)
    objective = R.weight * under + cost
    return violations, objective, {"under_covered_agent_slots": under, "labor_cost": round(cost, 2),
                                   "assignments": len(assignments), "overtime_shifts": overtime}


def score(world: World, submission_dir: Path, setting) -> dict:
    try:
        doc = read_json(submission_dir, "roster.json")
        assignments = _parse(world, doc.get("assignments") if isinstance(doc, dict) else None)
        if not assignments:
            raise Fatal("roster.json has no assignments")
        violations, objective, metrics = evaluate_roster(world, assignments, rules_for(world, setting))
    except Fatal as e:
        return {"fatal": str(e)}
    # "trace" is private to case.py: diagnose() reads the parsed roster from it (evaluate() never copies it)
    return {"violations": violations, "objective": objective, "metrics": metrics, "trace": assignments}


# ── the planner ──────────────────────────────────────────────────────────────

N_LANG = len(LANGS)
N_CELLS = 7 * N_SLOTS * N_LANG
LANG_INDEX = {l: i for i, l in enumerate(LANGS)}
BY_CONTRACT = {ct: [sh for sh, (_, _, c) in SHIFTS.items() if c == ct] for ct in ("FT", "PT")}


def _cells(d: int, shift: str, langs) -> tuple[int, ...]:
    """The (day, slot, language) cells a shift covers, as indices into the planner's arrays."""
    return tuple((d * N_SLOTS + s) * N_LANG + LANG_INDEX[l] for l in langs for s in _slots(shift))


class _Planner:
    """A roster built agent by agent. Each agent's week is re-planned exactly given everyone else's (a dynamic
    program over the seven days: which shift and language each day, within the weekly cap, the rest time and, for a
    new hire, the buddy rule), agents in turn until no agent's week improves; then every pair of agents who share a
    language is taken off the roster and re-planned together, as long as that improves the objective. Deterministic.

    `multi` is the double-counting misreading (ablations): an agent on shift counts on every language they speak.
    """

    def __init__(self, world: World, R: Rules, multi: bool = False):
        self.world, self.R, self.multi, self.w = world, R, multi, R.weight
        self.need = [R.need(world, d, s, l) for d in range(7) for s in range(N_SLOTS) for l in LANGS]
        self.cover, self.senior, self.newh = [0] * N_CELLS, [0] * N_CELLS, [0] * N_CELLS
        self.week: dict[str, dict[int, tuple]] = {a.id: {} for a in world.agents}    # day -> (shift, lang, cells)
        self.options: dict[str, dict[int, list]] = {}
        for a in world.agents:
            first = a.langs[:1] if multi else a.langs
            self.options[a.id] = {
                d: [(sh, l, _cells(d, sh, a.langs if multi else (l,))) for sh in BY_CONTRACT[a.contract] for l in first]
                for d in range(7) if not R.unavailable(world, a.id, d)}
        self.rest_ok = {(s1, s2): R.min_rest is None or SHIFTS[s2][0] + 1440 - SHIFTS[s1][0] - SHIFTS[s1][1] >= R.min_rest
                        for shifts in BY_CONTRACT.values() for s1 in shifts for s2 in shifts}
        self.seniors = [a for a in world.agents if not a.new_hire]
        self.new_hires = [a for a in world.agents if a.new_hire]

    # ── state ──
    def _apply(self, a: Agent, cells, sign: int) -> None:
        mine = self.newh if a.new_hire else self.senior
        for c in cells:
            self.cover[c] += sign
            mine[c] += sign

    def set_week(self, a: Agent, week: dict) -> None:
        for _, _, cells in self.week[a.id].values():
            self._apply(a, cells, -1)
        self.week[a.id] = dict(week)
        for _, _, cells in week.values():
            self._apply(a, cells, +1)

    def objective(self) -> float:
        under = sum(n - c for n, c in zip(self.need, self.cover) if n > c)
        return self.w * under + sum(_pay(a, len(self.week[a.id]), self.R) for a in self.world.agents)

    def roster(self) -> list[tuple[str, int, str, str]]:
        return [(a.id, d, sh, l) for a in self.world.agents for d, (sh, l, _) in sorted(self.week[a.id].items())]

    # ── one agent's best week, everyone else's fixed ──
    def replan(self, a: Agent, shadow: Agent | None = None) -> float:
        """Give `a` the best week given the others; returns the gain (0 when the week stays as it is).

        `shadow` (a new hire who is off the roster, `a` experienced): each day's choices also count what the new
        hire would add by working that same shift beside `a`, so that `a` takes the shifts a new hire can share."""
        old = self.week[a.id]
        self.set_week(a, {})
        need, cover, w = self.need, self.cover, self.w
        old_value = -_pay(a, len(old), self.R)
        required: dict[int, list] = {}
        for d, (_, _, cells) in old.items():
            old_value += w * sum(1 for c in cells if cover[c] < need[c])
            if self.R.buddy and not a.new_hire:       # cells where a new hire would be left alone without `a`
                alone = [c for c in cells if self.newh[c] > 0 and self.senior[c] == 0]
                if alone:
                    required[d] = alone
        cap = self.R.max_shifts(a.contract)
        paired = self.R.buddy and a.new_hire
        extra = RATE[shadow.contract] * 8 if shadow is not None else 0.0
        states: dict[tuple, tuple] = {(None, 0): (0.0, ())}
        for d in range(7):
            day = self.options[a.id].get(d)
            must = required.get(d)
            choices = []
            for sh, l, cells in day or ():
                if paired and any(self.senior[c] == 0 for c in cells):
                    continue
                if must is not None and not set(must) <= set(cells):
                    continue
                gain = w * sum(1 for c in cells if cover[c] < need[c])
                if shadow is not None and l in shadow.langs and d in self.options[shadow.id]:
                    gain += max(0.0, w * sum(1 for c in cells if cover[c] + 1 < need[c]) - extra)
                choices.append((gain, sh, l, cells))
            new: dict[tuple, tuple] = {}
            for (prev, n), (value, week) in states.items():
                if must is None:
                    key = (None, n)
                    if key not in new or value > new[key][0] + 1e-9:
                        new[key] = (value, week)
                if n >= cap:
                    continue
                for gain, sh, l, cells in choices:
                    if prev is not None and not self.rest_ok[(prev, sh)]:
                        continue
                    key = (sh, n + 1)
                    v = value + gain
                    if key not in new or v > new[key][0] + 1e-9:
                        new[key] = (v, week + ((d, sh, l, cells),))
            states = new
            if not states:
                break
        best = None
        for (_, n), (value, week) in states.items():
            v = value - _pay(a, n, self.R)
            if best is None or v > best[0] + 1e-9:
                best = (v, week)
        if best is None or (shadow is None and best[0] <= old_value + 1e-9):
            self.set_week(a, old)
            return 0.0
        self.set_week(a, {d: (sh, l, cells) for d, sh, l, cells in best[1]})
        return best[0] - old_value

    def descend(self, sweeps: int = 60) -> None:
        """Agents in turn (experienced first, so that new hires find their buddies) until no week improves."""
        for _ in range(sweeps):
            if sum(self.replan(a) for a in self.seniors + self.new_hires) <= 1e-9:
                return

    # ── two agents at once ──
    def _together(self, group: list[Agent]) -> float:
        """Take two agents off the roster and re-plan them, in both orders; keep the best outcome if it beats the
        present one. An experienced agent and a new hire are also tried with the first planning for both
        (replan's `shadow`). New hires who share a language with a re-planned senior are re-planned after the
        group, so no new hire is ever left without a buddy."""
        dependants = [n for n in self.new_hires if self.R.buddy and n not in group
                      and any(not g.new_hire and set(g.langs) & set(n.langs) for g in group)]
        touched = group + dependants
        before = self.objective()
        start = {a.id: self.week[a.id] for a in touched}
        best = None
        orders = [(group, None), (group[::-1], None)]
        if self.R.buddy and group[0].new_hire != group[1].new_hire:
            senior, new = sorted(group, key=lambda a: a.new_hire)
            orders.append(([senior, new], new))
        for order, shadow in orders:
            for a in touched:
                self.set_week(a, {})
            if shadow is not None:
                self.replan(order[0], shadow)
                self.replan(shadow)
            for _ in range(2):
                for a in order:
                    self.replan(a)
            for n in dependants:
                self.replan(n)
            now = self.objective()
            if now < before - 1e-9 and (best is None or now < best[0] - 1e-9):
                best = (now, {a.id: self.week[a.id] for a in touched})
        for a in touched:
            self.set_week(a, {})
        for a in sorted(touched, key=lambda a: a.new_hire):
            self.set_week(a, (best[1] if best else start)[a.id])
        return before - best[0] if best else 0.0

    def improve(self, passes: int = 8) -> None:
        """Every pair of agents who share a language, re-planned together, until a pass gains nothing."""
        agents = self.world.agents
        pairs = [[a, b] for i, a in enumerate(agents) for b in agents[i + 1:] if set(a.langs) & set(b.langs)]
        for _ in range(passes):
            gain = sum(self._together(pair) for pair in pairs)
            self.descend()
            if gain <= 1e-9:
                return


def _solve(world: World, R: Rules, multi: bool = False) -> list[tuple[str, int, str, str]]:
    """The planner's roster under `R` (cached per rules; the same roster for the same rules)."""
    key = ("plan", R, multi)
    if key not in world._cache:
        p = _Planner(world, R, multi)
        p.descend()
        p.improve()
        world._cache[key] = p.roster()
    return list(world._cache[key])


def _dump(assignments) -> dict:
    return {"assignments": [{"agent": a, "day": DAYS[d].isoformat(), "shift": sh, "language": l}
                            for a, d, sh, l in sorted(assignments, key=lambda x: (x[1], x[2], x[0]))]}


def _write(roster, out_dir: Path) -> None:
    (Path(out_dir) / "roster.json").write_text(json.dumps(_dump(roster), indent=2), encoding="utf-8")


def reference_solution(world: World, out_dir: Path, setting) -> None:
    """The planner's roster under the setting's rules, without any exception (no overtime shift)."""
    _write(_solve(world, rules_for(world, setting).planned()), out_dir)


def _baseline(world: World, R: Rules) -> list[tuple[str, int, str, str]]:
    """The supervisor's fixed rota, drawn up without looking at the forecast: every senior agent works one shift
    all week in their first language, full-timers and part-timers their contract week (no overtime), on consecutive
    days from a start staggered within their language and contract; a day of approved leave (or, in hard, of the
    certified sick leave) is just left empty. Each new hire shadows the first senior full-timer on one of their
    languages (same days, same shift), or stays off the phones if there is none."""
    count: dict[tuple[str, str], int] = {}
    pattern: dict[str, tuple[str, list[int]]] = {}
    out = []
    for a in world.agents:
        if a.new_hire:
            continue
        lang = a.langs[0]
        k = count.get((a.contract, lang), 0)
        count[(a.contract, lang)] = k + 1
        shift = BY_CONTRACT[a.contract][k % len(BY_CONTRACT[a.contract])]
        n = R.ft_regular if a.contract == "FT" else R.pt_max
        days = [d for d in ((3 * k + i) % 7 for i in range(n)) if not R.unavailable(world, a.id, d)]
        out += [(a.id, d, shift, lang) for d in days]
        if a.contract == "FT":
            pattern.setdefault(lang, (shift, days))
    for a in world.agents:
        lang = next((l for l in a.langs if l in pattern), None) if a.new_hire else None
        if lang is not None:
            shift, days = pattern[lang]
            out += [(a.id, d, shift, lang) for d in days if not R.unavailable(world, a.id, d)]
    return out


def baseline_solution(world: World, out_dir: Path, setting) -> None:
    _write(_baseline(world, rules_for(world, setting)), out_dir)


# ── literal solution: the request as written ─────────────────────────────────

LITERAL_WEEK = 5         # literal_solution: no weekly cap in the agent's view, so the usual five-day week for all
LITERAL_WEIGHT = 1000.0  # literal_solution: "enough people on the phones so customers aren't left waiting":
                         # a missing agent outweighs any shift's pay, so the forecast is covered wherever it can be


def _greedy(world: World, R: Rules) -> list[tuple[str, int, str, str]]:
    """Repeatedly add the (agent, day, shift, language) with the best gain, honouring every rule of `R` (the
    case's first reference; literal_solution and its near misses in shortcuts() still plan with it)."""
    key = ("greedy", R)
    if key in world._cache:
        return list(world._cache[key])
    resid = {(d, s, l): R.need(world, d, s, l) for d in range(7) for s in range(N_SLOTS) for l in LANGS}
    senior = {k: 0 for k in resid}
    work: dict[str, dict[int, str]] = {a.id: {} for a in world.agents}
    chosen: list[tuple[str, int, str, str]] = []

    def feasible(a: Agent, d: int, sh: str) -> bool:
        mine = work[a.id]
        if d in mine or len(mine) >= R.max_shifts(a.contract) or R.unavailable(world, a.id, d):
            return False
        if R.min_rest is None:
            return True
        st, ln, _ = SHIFTS[sh]
        if d - 1 in mine:
            pst, pln, _ = SHIFTS[mine[d - 1]]
            if st + 1440 - (pst + pln) < R.min_rest:
                return False
        if d + 1 in mine:
            if SHIFTS[mine[d + 1]][0] + 1440 - (st + ln) < R.min_rest:
                return False
        return True

    while True:
        best = None
        for a in world.agents:
            n = len(work[a.id])
            pay = _pay(a, n + 1, R) - _pay(a, n, R)
            for d in range(7):
                for sh, (_, _, ct) in SHIFTS.items():
                    if ct != a.contract or not feasible(a, d, sh):
                        continue
                    for l in a.langs:
                        slots = _slots(sh)
                        if R.buddy and a.new_hire and any(senior[(d, s, l)] == 0 for s in slots):
                            continue
                        gain = R.weight * sum(1 for s in slots if resid[(d, s, l)] > 0) - pay
                        # Prefer seniors slightly, so that new hires find buddies later.
                        key_ = (gain, 0 if a.new_hire else 1, -len(a.langs))
                        if gain > 0 and (best is None or key_ > best[0]):
                            best = (key_, a, d, sh, l)
        if best is None:
            break
        _, a, d, sh, l = best
        work[a.id][d] = sh
        chosen.append((a.id, d, sh, l))
        for s in _slots(sh):
            resid[(d, s, l)] -= 1
            if not a.new_hire:
                senior[(d, s, l)] += 1
    world._cache[key] = list(chosen)
    return chosen


def _literal_rules(**known) -> Rules:
    """The request at face value (literal_solution), with `known` rules of a setting put in (its near misses)."""
    R = Rules(weight=LITERAL_WEIGHT, holiday_day=None, holiday_factor=1.0, ft_regular=LITERAL_WEEK, ft_max=LITERAL_WEEK,
              pt_max=LITERAL_WEEK, overtime=1.0, min_rest=None, buddy=False, sick_agent=None, pt_guaranteed=False,
              training_salary=False)
    return dataclasses.replace(R, **known)


def literal_solution(world: World, out_dir: Path) -> None:
    """The request at face value, from the agent's view: cover the forecast file as it is in every language
    ("enough people on the phones so customers aren't left waiting", a missing agent weighted above any shift's
    pay), each agent on one of their skills, full-timers on the 8-hour and part-timers on the 4-hour shifts as
    shifts.csv says, one shift a day and the usual five-day week for everyone (nothing in the view gives a weekly
    cap), leave read as the file's day/month dates with only approved requests, and the agent in the team lead's
    note rostered as usual, as the note asks. No holiday cut, rest time, overtime rule or new-hire pairing, which
    the view never mentions. The greedy under those readings; the same roster in every setting."""
    _write(_greedy(world, _literal_rules()), out_dir)


def violating_examples(world: World, setting) -> dict:
    """One deliverable per rule of the setting's tier that breaks exactly that rule (for the validator).

    Small edits of the reference, tried in this order: change the language of one assignment, add one
    assignment, move one assignment of an agent to another day, shift or language. Moving matters when every
    agent who could break a rule is already at their weekly maximum (e.g. all approved-leave agents are
    part-timers at their cap): adding a shift would then also break max_shifts, moving one does not.
    """
    R = rules_for(world, setting)
    ref = _solve(world, R.planned())
    wanted = rule_ids(setting)
    found: dict[str, list] = {}

    def consider(cand):
        v = {r for r, _ in evaluate_roster(world, cand, R)[0]}
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


# ── ground truth audit hooks (fdebench2.audit, GT.md) ────────────────────────

# The targets of locales/en/targets.yaml: the tier a fact is in force from, and the drawn parameter of the ones that
# are exactly one (the audit ablates those itself, with the reference of each other candidate).
TARGET_TIER = {"one_language": "easy", "understaffing_price": "easy", "ft_contract_week": "easy",
               "pt_contract_week": "easy", "min_rest": "easy", "holiday": "easy", "training_salary": "easy",
               "buddy_rule": "medium", "sick_call": "hard"}
TARGET_PARAM = {"understaffing_price": "under_weight", "ft_contract_week": "ft_week_hours",
                "pt_contract_week": "pt_week_hours", "min_rest": "min_rest"}


def _in_force(setting) -> list[str]:
    return [t for t, tier in TARGET_TIER.items() if setting.at_least(tier)]


def _misreading(R: Rules, target: str) -> tuple[Rules, bool]:
    """(the rules a planner works with when it misreads only `target` in its most natural way, whether it counts
    an agent on every language they speak):

    - one_language: a bilingual agent on shift counts on each of their languages at once (the roster then names
      their first language);
    - holiday: the forecast file as it is, no day cut;
    - training_salary: a new hire paid by the shift like everyone else in labor_cost.csv, so the planner gives them
      only the shifts that pay for themselves;
    - buddy_rule: new hires rostered like everyone else;
    - sick_call: the team lead's note followed, the agent rostered as usual."""
    plan = R.planned()
    if target == "one_language":
        return plan, True
    if target == "holiday":
        return dataclasses.replace(plan, holiday_day=None), False
    if target == "training_salary":
        return dataclasses.replace(plan, training_salary=False), False
    if target == "buddy_rule":
        return dataclasses.replace(plan, buddy=False), False
    if target == "sick_call":
        return dataclasses.replace(plan, sick_agent=None, sick_days=frozenset()), False
    raise KeyError(target)


def _misread_roster(world: World, R: Rules, target: str) -> list[tuple[str, int, str, str]]:
    """The planner's roster on the misreading of `target`, every other fact read right. Where the reference's own
    roster is valid under that reading and at least as good by it, the reference is kept: a misreading that does
    not change the best roster then costs nothing, instead of showing the planner's noise."""
    Rm, multi = _misreading(R, target)
    roster = _solve(world, Rm, multi)
    if not multi:
        ref = _solve(world, R.planned())
        broken, objective, _ = evaluate_roster(world, ref, Rm)
        if not broken and objective <= evaluate_roster(world, roster, Rm)[1] + 1e-9:
            return ref
    return roster


def ablations(world: World, setting) -> dict:
    """{target: write the roster that misreads only that fact} for the targets in force that are not a drawn
    parameter (those the audit ablates itself)."""
    R = rules_for(world, setting)
    return {t: (lambda out, t=t: _write(_misread_roster(world, R, t), out))
            for t in _in_force(setting) if t not in TARGET_PARAM}


def shortcuts(world: World, setting) -> dict:
    """Degenerate rosters a lazy or gaming agent might hand in; each must be invalid or score at most 0.5."""
    R = rules_for(world, setting)

    def one_shift(out: Path) -> None:
        """The rules kept minimally: a single shift (the first agent, their first shift and language)."""
        a = world.agents[0]
        day = next(d for d in range(7) if not R.unavailable(world, a.id, d))
        _write([(a.id, day, BY_CONTRACT[a.contract][0], a.langs[0])], out)

    def fixed_rota(out: Path) -> None:
        """The client's own fixed rota copied (the baseline)."""
        _write(_baseline(world, R), out)

    def fixed_rota_no_new_hires(out: Path) -> None:
        """The fixed rota with one change: new hires stay off the phones."""
        _write([x for x in _baseline(world, R) if not world.agent(x[0]).new_hire], out)

    def fixed_rota_peak(out: Path) -> None:
        """The fixed rota with one change: everyone on the 10:00 (full-time) or 12:00 (part-time) shift."""
        _write([(aid, d, "S1000" if world.agent(aid).contract == "FT" else "P1200", l)
                for aid, d, _, l in _baseline(world, R)], out)

    def same_shift_all_week(out: Path) -> None:
        """Constants: every experienced agent on their contract's first shift and language, from Monday on."""
        roster = []
        for a in world.agents:
            if a.new_hire:
                continue
            n = R.ft_regular if a.contract == "FT" else R.pt_max
            days = [d for d in range(7) if not R.unavailable(world, a.id, d)][:n]
            roster += [(a.id, d, BY_CONTRACT[a.contract][0], a.langs[0]) for d in days]
        _write(roster, out)

    def part_timers_only(out: Path) -> None:
        """The objective's arithmetic: only part-timers, the cheapest per half-hour (the planner, no full-timers)."""
        _write(_solve(world, dataclasses.replace(R.planned(), ft_regular=0, ft_max=0)), out)

    def one_day_only(out: Path) -> None:
        """A partial roster: the planner's roster for Monday alone, nobody on the other six days."""
        _write([x for x in _solve(world, R.planned()) if x[1] == 0], out)

    def weekdays_only(out: Path) -> None:
        """A partial roster: the planner's roster for Monday to Friday, nobody at the weekend."""
        _write([x for x in _solve(world, R.planned()) if x[1] < 5], out)

    def no_new_hires(out: Path) -> None:
        """The buddy rule kept vacuously: the planner's roster with the new hires taken off the phones."""
        _write([x for x in _solve(world, R.planned()) if not world.agent(x[0]).new_hire], out)

    def one_shift_each(out: Path) -> None:
        """The rules kept minimally: the planner with one shift a week for every agent."""
        _write(_solve(world, dataclasses.replace(R.planned(), ft_regular=1, ft_max=1, pt_max=1)), out)

    found = {f.__name__: f for f in (one_shift, fixed_rota, fixed_rota_no_new_hires, fixed_rota_peak,
                                      same_shift_all_week, part_timers_only, one_day_only, weekdays_only,
                                      no_new_hires, one_shift_each)}
    # the literal solution's near misses: the request as written with one of the rules it breaks satisfied
    literal = _greedy(world, _literal_rules())
    near = {"max_shifts": dict(ft_max=min(LITERAL_WEEK, R.ft_max), pt_max=R.pt_max),
            "min_rest": dict(min_rest=R.min_rest),
            "overtime_approval": dict(ft_max=min(LITERAL_WEEK, R.ft_regular)),
            "buddy_rule": dict(buddy=True),
            "sick_leave": dict(sick_agent=R.sick_agent, sick_days=R.sick_days)}
    what = {"max_shifts": "the weekly caps of both contracts", "min_rest": "the rest time between two shifts",
            "overtime_approval": "no shift beyond the full-time contract week",
            "buddy_rule": "no new hire alone on a language", "sick_leave": "the certified sick days"}
    for rule in sorted({r for r, _ in evaluate_roster(world, literal, R)[0]} & set(near)):
        def near_miss(out: Path, rule=rule) -> None:
            _write(_greedy(world, _literal_rules(**near[rule])), out)
        near_miss.__doc__ = f"The literal solution plus one rule: the request as written, with {what[rule]} kept."
        found[f"literal_plus_{rule}"] = near_miss
    return found


def robust_solution(world: World, out_dir: Path, tier: str, candidates: dict) -> None:
    """The best single roster without asking: the roster that keeps the strictest candidate of every rule the
    tier's pools hold (the shorter full-time and part-time contract weeks, no overtime shift, the longer rest and,
    in hard, the latest end of the sick leave), so it is valid in every setting of the tier, and that has the lowest
    expected objective over the settings it cannot tell apart: every price of a missing agent, holiday day and
    holiday share of the pools, equally likely (the exact optimum of that stochastic program, see _milp). It even
    pairs new hires with an experienced colleague from medium, which a planner that never asks could only do out of
    caution. Nothing in the view says which day is the holiday or what a missing agent costs, so it staffs each
    candidate day for the chance that it is the holiday and prices a shortfall at the average of the candidates;
    it reads labor_cost.csv as the view suggests, every shift paid by the hour (no guaranteed week, no training
    salary)."""
    medium, hard = tier != "easy", tier == "hard"
    regular = min(int(h) for h in candidates["ft_week_hours"]) // 8
    last_sick = max(dt.date.fromisoformat(str(v)) for v in candidates["sick_until"])
    sick_days = frozenset(d for d in range(7) if DAYS[d] <= last_sick) if hard else frozenset()
    R = Rules(weight=0.0, holiday_day=None, holiday_factor=1.0, ft_regular=regular, ft_max=regular,
              pt_max=min(int(h) for h in candidates["pt_week_hours"]) // 4, overtime=OVERTIME,
              min_rest=max(int(h) for h in candidates["min_rest"]) * 60, buddy=medium,
              sick_agent=sick_agent(world).id if sick_days else None, sick_days=sick_days, pt_guaranteed=False,
              training_salary=False)
    combos = [(float(w), _day_index(d), float(f)) for w in dict.fromkeys(candidates["under_weight"])
              for d in dict.fromkeys(candidates["holiday_day"]) for f in dict.fromkeys(candidates["holiday_factor"])]
    _write(_milp(world, R, tuple((1.0 / len(combos), *c) for c in combos))[0], out_dir)


MILP_SECONDS = 300.0     # _milp: HiGHS's time limit (never reached in the audit: 1-10 s per setting, robust_solution's
                         # stochastic program well under a minute)


def _milp(world: World, R: Rules, scenarios: tuple | None = None) -> tuple[list, float, float]:
    """The roster model as a mixed-integer program, solved by HiGHS (scipy): (roster, its objective, a proven
    lower bound on the objective of every roster that keeps the rules of `R`).

    Binaries x[agent, day, shift, language] for every assignment the rules allow (contract shift type, a skill,
    no leave or sick day); a continuous u[day, slot, language] >= need - the x that cover the cell (u >= 0, priced
    at the weight); one shift a day and the weekly cap per agent; for a full-timer a continuous o >= shifts - the
    contract week, priced at the overtime premium (at the whole overtime pay for a new hire, whose regular week
    is paid anyway); the guaranteed weeks (_guaranteed) are a constant, and the shifts within them cost nothing;
    for every pair of shifts on consecutive days that are less than the rest time apart, at most one of the two; for a new hire's assignment and each of its slots, at most the
    experienced agents assigned to that language in that slot. The bound is the solver's dual bound: the optimum
    when the search finishes within MILP_SECONDS, else what the branch and bound has proven by then.

    `scenarios` ((probability, weight, holiday day, holiday factor), ...; robust_solution) makes it the expected
    objective over settings that differ only in the price and the holiday: one u per cell and need level, priced at
    the probability-weighted price of the scenarios with that need (the probabilities sum to 1, so the labor cost
    counts once). None: the one setting of R."""
    scenarios = scenarios or ((1.0, R.weight, R.holiday_day, R.holiday_factor),)
    key = ("milp", R, scenarios)
    if key in world._cache:
        return world._cache[key]
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import coo_matrix

    xs = [(a.id, d, sh, l) for a in world.agents for d in range(7) if not R.unavailable(world, a.id, d)
          for sh in BY_CONTRACT[a.contract] for l in a.langs]
    cells = [(d, s, l) for d in range(7) for s in range(N_SLOTS) for l in LANGS]
    nx = len(xs)
    short: dict[tuple, float] = {}          # (cell, need) -> its expected price per missing agent
    for p, weight, day, factor in scenarios:
        Rs = dataclasses.replace(R, weight=weight, holiday_day=day, holiday_factor=factor)
        for c in cells:
            short[(c, Rs.need(world, *c))] = short.get((c, Rs.need(world, *c)), 0.0) + p * weight
    u_at = {k: nx + i for i, k in enumerate(short)}
    overtime = R.overtime > 1.0 and R.ft_max > R.ft_regular
    o_at = {a.id: nx + len(u_at) + i for i, a in enumerate(a for a in world.agents if a.contract == "FT")} \
        if overtime else {}
    n = nx + len(u_at) + len(o_at)
    cost = np.zeros(n)
    for j, (aid, _, sh, _) in enumerate(xs):
        cost[j] = 0.0 if _guaranteed(world.agent(aid), R) else RATE[world.agent(aid).contract] * SHIFTS[sh][1] / 60
    fixed = sum(_pay(a, 0, R) for a in world.agents)      # the guaranteed weeks, rostered or not
    for k, j in u_at.items():
        cost[j] = short[k]
    for aid, j in o_at.items():
        cost[j] = RATE["FT"] * 8 * (R.overtime if _guaranteed(world.agent(aid), R) else R.overtime - 1.0)
    entries, low, high = [], [], []

    def add(row: dict, lo: float, hi: float) -> None:
        entries.extend((len(low), j, v) for j, v in row.items())
        low.append(lo)
        high.append(hi)
    cover: dict = {c: [] for c in cells}
    seniors: dict = {c: [] for c in cells}
    per_day, per_agent, per_shift = {}, {}, {}
    for j, (aid, d, sh, l) in enumerate(xs):
        for s in _slots(sh):
            cover[(d, s, l)].append(j)
            if not world.agent(aid).new_hire:
                seniors[(d, s, l)].append(j)
        per_day.setdefault((aid, d), []).append(j)
        per_agent.setdefault(aid, []).append(j)
        per_shift.setdefault((aid, d, sh), []).append(j)
    for (c, need), j in u_at.items():
        add({j: 1.0, **{i: 1.0 for i in cover[c]}}, need, np.inf)
    for js in per_day.values():
        add({j: 1.0 for j in js}, -np.inf, 1.0)
    for aid, js in per_agent.items():
        add({j: 1.0 for j in js}, -np.inf, R.max_shifts(world.agent(aid).contract))
        if aid in o_at:
            add({o_at[aid]: 1.0, **{j: -1.0 for j in js}}, -R.ft_regular, np.inf)
    if R.min_rest is not None:
        for a in world.agents:
            for d in range(6):
                for s1 in BY_CONTRACT[a.contract]:
                    close = [s2 for s2 in BY_CONTRACT[a.contract]
                             if SHIFTS[s2][0] + 1440 - SHIFTS[s1][0] - SHIFTS[s1][1] < R.min_rest]
                    js = per_shift.get((a.id, d, s1), []) + [j for s2 in close for j in per_shift.get((a.id, d + 1, s2), [])]
                    if close and js:
                        add({j: 1.0 for j in js}, -np.inf, 1.0)
    if R.buddy:
        for j, (aid, d, sh, l) in enumerate(xs):
            if world.agent(aid).new_hire:
                for s in _slots(sh):
                    add({j: 1.0, **{k: -1.0 for k in seniors[(d, s, l)]}}, -np.inf, 0.0)
    r, c, v = zip(*entries)
    matrix = coo_matrix((v, (r, c)), shape=(len(low), n)).tocsr()
    integrality = np.zeros(n)
    integrality[:nx] = 1
    upper = np.full(n, np.inf)
    upper[:nx] = 1
    res = milp(cost, constraints=LinearConstraint(matrix, low, high), integrality=integrality,
               bounds=Bounds(np.zeros(n), upper), options={"time_limit": MILP_SECONDS, "mip_rel_gap": 0.0})
    bound = getattr(res, "mip_dual_bound", None)
    if res.x is None or bound is None or not math.isfinite(bound):
        raise AssertionError(f"the roster MILP gave no bound ({res.message})")
    roster = [xs[j] for j in range(nx) if res.x[j] > 0.5]
    world._cache[key] = (roster, float(res.fun) + fixed, float(bound) + fixed)
    return world._cache[key]


def best_known_solution(world: World, out_dir: Path, setting) -> None:
    """The best roster known that keeps every rule: the MILP's (the proven optimum when HiGHS finishes within
    MILP_SECONDS), or the reference's own where that is no better."""
    R = rules_for(world, setting)
    ref = _solve(world, R.planned())
    roster = _milp(world, R.planned())[0]
    broken, mine, _ = evaluate_roster(world, roster, R)
    _write(roster if not broken and mine < evaluate_roster(world, ref, R)[1] - 1e-9 else ref, out_dir)


def objective_bound(world: World, setting) -> float:
    """A proven lower bound on the objective of every roster that keeps every rule of the setting, the overtime
    approval included (a roster with an approved overtime exception is outside its scope): the dual bound of the
    MILP (see _milp), which HiGHS proves by branch and bound. The model has every assignment the rules allow as a
    column and every rule as constraints, so no valid roster is cut off."""
    return _milp(world, rules_for(world, setting).planned())[2]


# ── diagnostics: does a roster implement each client fact? ───────────────────

FOLLOWS_GAP = 0.05       # diagnose: a roster follows another reading when it is at least this much of the quality
                         # scale closer to that reading's best roster than to the true one's,
FOLLOWS_SHARE = 0.5      # and its distance to that reading's best roster is at most this share of the true one


def _reading_objective(world: World, roster, R: Rules, multi: bool = False) -> float:
    """The objective of a roster as a reading counts it (`multi`: every agent on each language they speak)."""
    if not multi:
        return evaluate_roster(world, roster, R)[1]
    cover = [0] * N_CELLS
    count: dict[str, int] = {}
    for aid, d, sh, _ in roster:
        count[aid] = count.get(aid, 0) + 1
        for c in _cells(d, sh, world.agent(aid).langs):
            cover[c] += 1
    under = sum(max(0, R.need(world, d, s, l) - cover[(d * N_SLOTS + s) * N_LANG + LANG_INDEX[l]])
                for d in range(7) for s in range(N_SLOTS) for l in LANGS)
    return R.weight * under + sum(_pay(a, count.get(a.id, 0), R) for a in world.agents)


def _pool(name: str, tier: str) -> list:
    """The candidates of a drawn parameter in a tier, read from case.yaml."""
    import yaml
    values = yaml.safe_load((Path(__file__).parent / "case.yaml").read_text(encoding="utf-8"))["params"][name]["values"]
    return list(dict.fromkeys(values[tier] if isinstance(values, dict) else values))


def _other_readings(setting, R: Rules, target: str) -> list[tuple[str, Rules, bool]]:
    """(name, rules, multi) of the readings a roster could follow in place of the true one for `target`: the other
    candidates of its parameter, or its natural misreading (for the holiday also the cut on another candidate day,
    at the true share)."""
    if target == "holiday":         # the forecast uncut, or the cut on another candidate day
        return [("the forecast uncut", _misreading(R, target)[0], False)] + [
            (f"the holiday on {v}", dataclasses.replace(R, holiday_day=_day_index(v)), False)
            for v in _pool("holiday_day", setting.tier) if _day_index(v) != R.holiday_day]
    if target not in TARGET_PARAM:
        Rm, multi = _misreading(R, target)
        return [("the misreading", Rm, multi)]
    name = TARGET_PARAM[target]
    out = []
    for v in _pool(name, setting.tier):
        if str(v) == str(setting.params[name]):
            continue
        if name == "under_weight":
            Ro = dataclasses.replace(R, weight=float(v))
        elif name == "ft_week_hours":
            Ro = dataclasses.replace(R, ft_regular=int(v) // 8, ft_max=int(v) // 8 + (R.ft_max - R.ft_regular))
        elif name == "pt_week_hours":
            Ro = dataclasses.replace(R, pt_max=int(v) // 4)
        else:
            Ro = dataclasses.replace(R, min_rest=int(v) * 60)
        out.append((f"{name} = {v}", Ro, False))
    return out


def diagnose(world: World, submission_dir: Path, setting, scored: dict) -> dict:
    """Per target in force: does the roster implement the fact (True, False, or None when it cannot tell)?

    A fact that is a rule is read off the rule: the part-time and full-time contract weeks (nobody above them), the
    rest time, the overtime approval, the buddy rule (None when no new hire is rostered) and the sick call (None
    when the agent in the note is not rostered at all). Every other fact, and a contract week or rest time that is
    kept, is measured against each other reading (another candidate of the parameter, or the natural misreading):
    the roster *follows* that reading when it loses at least FOLLOWS_GAP of the quality scale against the reference
    under the true reading, keeps that reading's rules (without an overtime exception) and is closer to the
    planner's best roster under that reading than to the true one's, by at least FOLLOWS_GAP of the scale and with
    at most FOLLOWS_SHARE of the distance. A roster that follows another reading does not implement the fact; a
    roster at least as good as the reference never follows one (a better roster than the planner's is not a
    misreading)."""
    roster = scored.get("trace")
    if roster is None:
        return {}
    R = rules_for(world, setting)
    broken = {r for r, _ in scored["violations"]}
    best = evaluate_roster(world, _solve(world, R.planned()), R)[1]
    scale = evaluate_roster(world, _baseline(world, R), R)[1] - best
    regret = scored["objective"] - best
    shifts: dict[str, int] = {}
    for aid, _, _, _ in roster:
        shifts[aid] = shifts.get(aid, 0) + 1
    most = {ct: max([n for aid, n in shifts.items() if world.agent(aid).contract == ct], default=0) for ct in ("FT", "PT")}
    enforced, evidence = {}, {}

    def follows(target: str) -> str | None:
        """The other reading of `target` the roster follows, if any."""
        if regret < FOLLOWS_GAP * scale:
            return None                                     # it loses next to nothing under the true reading
        for name, Ro, multi in _other_readings(setting, R, target):
            plan = Ro if multi else Ro.planned()
            if not multi and {r for r, _ in evaluate_roster(world, roster, plan)[0]}:
                continue                                    # it breaks that reading's own rules
            other = _reading_objective(world, roster, Ro, multi) - _reading_objective(world, _solve(world, plan, multi), Ro, multi)
            if regret - other >= FOLLOWS_GAP * scale and other <= FOLLOWS_SHARE * regret:
                return f"closer to the best roster under {name} ({other:.0f} above it) than to the true one's ({regret:.0f})"
        return None

    for t in _in_force(setting):
        why = None
        if t == "pt_contract_week" and most["PT"] > R.pt_max:
            why = f"a part-timer works {most['PT']} shifts, the contract week is {R.pt_max}"
        elif t == "ft_contract_week" and most["FT"] > R.ft_regular:
            why = f"a full-timer works {most['FT']} shifts, the contract week is {R.ft_regular}"
        elif t == "min_rest" and "min_rest" in broken:
            why = "two shifts of an agent are less than the rest time apart"
        elif t == "buddy_rule":
            if "buddy_rule" in broken:
                why = "a new hire is alone on a language"
            elif not any(world.agent(aid).new_hire for aid in shifts):
                enforced[t], evidence[t] = None, "no new hire is rostered"
                continue
        elif t == "sick_call":
            if "sick_leave" in broken:
                why = "the agent in the team lead's note is rostered on a certified sick day"
            elif R.sick_agent not in shifts:
                enforced[t], evidence[t] = None, "the agent in the team lead's note is not rostered at all"
                continue
        if why is None and t not in ("buddy_rule", "sick_call"):
            why = follows(t)
        enforced[t] = why is None
        evidence[t] = why or "keeps the rule and follows no other reading"
    return {"enforced": enforced, "evidence": evidence}
