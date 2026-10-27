"""Outpatient appointment booking (original FDE-Bench v2 case).

A mid-size outpatient hospital has a backlog of appointment requests and asks
for them to be booked into the doctors' free slots over the next two weeks.
The request only says "book them"; what decides validity and quality is in the
requirements and must be asked for. One dataset serves nine settings (tiers x
rule sets); the setting decides which rules apply and their parameters:

  easy    the booking core: day/month/year dates, two slots for a new patient,
          the urgent window, a clinic closed on a municipal holiday, follow-ups
          with the previous doctor (a bendable habit; one orthopedist is on
          leave in week 1), in-person interpreters capped per day for new
          patients with paid remote interpreting for follow-ups, and the
          waiting / unbooked costs
  medium  + referral letters that expire (new patients) and a fasting blood
          test that must be done at least one working day before the visit,
          with a daily lab capacity
  hard    + no-shows: each booked patient stays away with some probability
          (a hidden per-patient rate, plus one point per working day of lead
          time; past attendance is in the data) and follow-ups may be
          overbooked two to a slot, a few per doctor session; quality adds the
          expected cost of idle slots and of overbooked patients colliding

  rule sets A/B/C: which clinic closes on the holiday, the urgent window, the
          number of interpreters, the "soon" window, the lab cap and the
          overbooking cap (case.yaml)
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field
from pathlib import Path

from fdebench2.casekit import Fatal, labels, read_csv, write_csv

# ── world ────────────────────────────────────────────────────────────────────

START = dt.date(2026, 11, 16)                                   # Monday
DAYS = [START + dt.timedelta(days=i) for i in range(14) if (START + dt.timedelta(days=i)).weekday() < 5]
DAY_INDEX = {d: i for i, d in enumerate(DAYS)}
HOLIDAY = dt.date(2026, 11, 23)                                 # municipal holiday: one clinic closes (rule set)
LEAVE_DOCTOR, LEAVE_DAYS = "D11", set(DAYS[:5])                  # an orthopedist on leave in week 1
SLOT = 20
AM = [9 * 60 + SLOT * k for k in range(9)]                      # 09:00 .. 11:40
PM = [13 * 60 + SLOT * k for k in range(12)]                    # 13:00 .. 16:40
NOON = 12 * 60
REMOTE_COST = 3                                                  # a follow-up interpreted remotely
URGENT_MIN, URGENT_MAX = 1, 3                                    # the urgent window across rule sets (days)
WEIGHT = {"U": 3, "S": 2, "R": 1}
UNSEEN_PENALTY = 60                                              # a request not booked (hard: or not attended)
SOON_LATE_PENALTY = 20
LEAD0 = 2                                                        # requests were taken 2 working days before 16 Nov
LEAD_SLOPE = 0.01                                                # no-show rate + 1 point per working day of lead
HIST_LEAD = 5                                                    # past appointments had ~5 working days of lead
COLLISION_COST = 25                                              # both patients of an overbooked slot turn up
IDLE_COST = 10                                                   # a booked slot whose patient does not turn up
INTERP_DETOUR = 1                                                # reference: wait 1 day rather than use an interpreter
DEPTS = ["IM", "CARD", "DERM", "ORTH", "PED"]
LANGS = ["L0", "F1", "F2", "F3", "F4"]                           # L0 = the local language


@dataclass
class Doctor:
    id: str
    dept: str
    langs: list[str]
    sessions: list[tuple[int, str]]      # (weekday 0-4, "AM"|"PM")


@dataclass
class Request:
    id: str
    patient: str
    dept: str
    prev: str | None                     # previous doctor for a follow-up, None for a new patient
    urgency: str                         # U | S | R
    note: int
    lang: str
    earliest: dt.date
    referral: dt.date | None = None      # medium+: last day the new patient's referral letter is valid
    test: bool = False                   # medium+: needs a fasting blood test >= 1 working day before the visit
    base_p: float = 0.0                  # hard: hidden no-show rate at zero lead time
    past: int = 0                        # hard: past appointments at this hospital
    missed: int = 0                      # hard: of which not attended

    @property
    def new(self) -> bool:
        return self.prev is None

    @property
    def ref_day(self) -> int:
        """Working-day index from which waiting is counted (the horizon start if the earliest date is before it)."""
        return DAY_INDEX[max(self.earliest, START)]

    def last_day(self, urgent_days: int) -> int:
        """Last working-day index the request may be booked on (urgent window, referral expiry)."""
        last = min(self.ref_day + urgent_days, len(DAYS) - 1) if self.urgency == "U" else len(DAYS) - 1
        if self.referral is not None:
            last = min(last, max((i for i, d in enumerate(DAYS) if d <= self.referral), default=-1))
        return last


@dataclass
class World:
    doctors: list[Doctor]
    free: dict                           # (doctor id, date) -> sorted list of free slot starts (minutes)
    requests: list[Request]
    _cache: dict = field(default_factory=dict)

    def doctor(self, did: str) -> Doctor | None:
        return next((d for d in self.doctors if d.id == did), None)

    def request(self, rid: str) -> Request | None:
        if "req" not in self._cache:
            self._cache["req"] = {r.id: r for r in self.requests}
        return self._cache["req"].get(rid)


class _View:
    """The world as one setting sees it: which tier's rules apply and the rule set's parameters."""

    def __init__(self, world: World, setting):
        self._w, self.setting = world, setting
        self.medium, self.hard = setting.at_least("medium"), setting.at_least("hard")
        self.urgent_days = int(setting["urgent_days"])
        self.interpreters = int(setting["interpreters_per_day"])
        self.lab_cap = int(setting["lab_cap"])
        self.ob_max = int(setting["overbooked_per_session"])
        self.soon_days = int(setting["soon_days"])
        self.closed_dept = setting["closed_dept"]
        self._cache = world._cache.setdefault(("setting", setting.label), {})

    def __getattr__(self, name):
        return getattr(self._w, name)


def no_show(req: Request, day: dt.date) -> float:
    """True probability that the patient does not turn up on `day` (hard tier)."""
    return min(0.9, req.base_p + LEAD_SLOPE * (DAY_INDEX[day] + LEAD0))


DOCTOR_PLAN = [  # (dept, foreign languages, sessions)
    ("IM", ["F1"], [(0, "AM"), (1, "PM"), (3, "PM")]),
    ("IM", [], [(0, "PM"), (2, "PM"), (4, "PM")]),
    ("IM", ["F2"], [(1, "AM"), (2, "PM"), (4, "PM")]),
    ("IM", [], [(3, "AM"), (3, "PM"), (4, "AM")]),
    ("CARD", ["F1"], [(0, "PM"), (2, "AM"), (3, "PM")]),
    ("CARD", [], [(1, "PM"), (4, "AM")]),
    ("CARD", ["F3"], [(0, "AM"), (2, "PM"), (4, "PM")]),
    ("DERM", ["F1"], [(0, "AM"), (0, "PM"), (2, "PM"), (4, "PM")]),
    ("DERM", [], [(0, "PM"), (1, "PM"), (3, "AM"), (3, "PM")]),
    ("ORTH", ["F4"], [(0, "PM"), (2, "AM"), (4, "PM")]),
    ("ORTH", [], [(1, "AM"), (1, "PM"), (3, "PM")]),
    ("ORTH", ["F1", "F2"], [(2, "PM"), (4, "AM")]),
    ("PED", ["F1"], [(0, "PM"), (1, "AM"), (2, "PM"), (3, "PM")]),
    ("PED", [], [(1, "PM"), (3, "AM"), (4, "PM")]),
]
DEPT_WEIGHT = {"IM": 0.28, "CARD": 0.16, "DERM": 0.2, "ORTH": 0.18, "PED": 0.18}
PREV_WEIGHT = {"D11": 3}                                         # the orthopedist on leave has a long follow-up list
TEST_SHARE = {"IM": 0.45, "CARD": 0.45, "PED": 0.15}
N_REQUESTS = 320
TAKEN = 0.38


def build_world(seed: int) -> World:
    """Everything every setting needs (the data is the same in all of them)."""
    rng = random.Random(seed)
    doctors = [Doctor(f"D{i + 1:02d}", dept, ["L0"] + fl, sess) for i, (dept, fl, sess) in enumerate(DOCTOR_PLAN)]
    free = {}
    for doc in doctors:
        for day in DAYS:
            starts = []
            for wd, half in doc.sessions:
                if wd == day.weekday():
                    starts += AM if half == "AM" else PM
            # Part of every session is already taken by appointments booked earlier.
            kept = [s for s in starts if rng.random() >= TAKEN]
            if kept and not (doc.id == LEAVE_DOCTOR and day in LEAVE_DAYS):
                free[(doc.id, day)] = sorted(kept)
    by_dept = {d: [doc for doc in doctors if doc.dept == d] for d in DEPTS}
    early = [START - dt.timedelta(days=k) for k in range(1, 8) if (START - dt.timedelta(days=k)).weekday() < 5]

    def open_days(docs, days):
        return [day for day in days for d in docs
                if (d, day) in free and day != HOLIDAY]           # any clinic may be the one closed

    requests = []
    patients = rng.sample(range(10000, 99999), N_REQUESTS)
    for i in range(N_REQUESTS):
        dept = rng.choices(DEPTS, weights=[DEPT_WEIGHT[d] for d in DEPTS])[0]
        urgency = rng.choices(["U", "S", "R"], weights=[0.08, 0.27, 0.65])[0]
        follow = rng.random() < 0.5
        prev = (rng.choices(by_dept[dept], weights=[PREV_WEIGHT.get(d.id, 1) for d in by_dept[dept]])[0].id
                if follow else None)
        lang = "L0" if rng.random() < 0.8 else rng.choice(LANGS[1:])
        if urgency == "U":
            # Urgent referrals came in recently: earliest date within the first week and a half of the horizon,
            # chosen so that the follow-up doctor (if any) holds a clinic within the urgent window.
            docs = [prev] if prev else [d.id for d in by_dept[dept]]
            while True:
                k = rng.randrange(0, 8)
                if open_days(docs, DAYS[k:k + URGENT_MIN + 1]):
                    break
            earliest = DAYS[k]
        else:
            earliest = rng.choice(early) if rng.random() < 0.45 else rng.choice(DAYS[:-2])
        requests.append(Request(f"R{i + 1:03d}", f"P{patients[i]}", dept, prev, urgency, rng.randrange(3), lang,
                                earliest))

    # The facts only higher tiers' rules use come from their own random streams.
    rm = random.Random(seed * 7 + 1)
    for r in requests:
        docs = [r.prev] if r.prev else [d.id for d in by_dept[r.dept]]
        if rm.random() < TEST_SHARE.get(r.dept, 0.0):
            # An urgent request keeps its test only if a clinic is open the working day after its reference day.
            r.test = r.urgency != "U" or bool(open_days(docs, DAYS[r.ref_day + 1:r.ref_day + URGENT_MIN + 1]))
        if r.new:
            if rm.random() < 0.35:
                # The letter runs out inside the horizon, but never before the patient can come
                # (nor, for an urgent request, inside its window).
                first = min(r.ref_day + (URGENT_MAX if r.urgency == "U" else 0), len(DAYS) - 1)
                last = rm.randrange(first, len(DAYS))
                r.referral = DAYS[max(last, 2)]
            else:
                r.referral = START + dt.timedelta(days=rm.randrange(30, 150))
    rh = random.Random(seed * 7 + 2)
    for r in requests:
        r.base_p = round(rh.betavariate(4, 8) if rh.random() < 0.15 else rh.betavariate(2, 14), 4)
        if not r.new:
            r.past = rh.randint(2, 14)
            r.missed = sum(rh.random() < r.base_p + LEAD_SLOPE * HIST_LEAD for _ in range(r.past))
    return World(doctors, free, requests)


# ── data rendering ───────────────────────────────────────────────────────────

FILES = {
    "doctors": {"zh": "医生名单.csv", "en": "doctors.csv", "ko": "의사목록.csv", "ja": "医師一覧.csv",
                "es": "medicos.csv"},
    "slots": {"zh": "空闲号源.csv", "en": "free_slots.csv", "ko": "예약가능시간.csv", "ja": "空き枠.csv",
              "es": "huecos_libres.csv"},
    "requests": {"zh": "预约申请.csv", "en": "appointment_requests.csv", "ko": "예약요청.csv", "ja": "予約依頼.csv",
                 "es": "solicitudes_cita.csv"},
    "notice": {"zh": "门诊通知.txt", "en": "clinic_notices.txt", "ko": "진료안내.txt", "ja": "外来のお知らせ.txt",
               "es": "avisos_consultas.txt"},
    "attendance": {"zh": "就诊记录.csv", "en": "attendance_history.csv", "ko": "내원이력.csv", "ja": "受診履歴.csv",
                   "es": "historial_asistencia.csv"},
}
COLS = {
    "doctor": {"zh": "医生编号", "en": "doctor_id", "ko": "의사ID", "ja": "医師ID", "es": "id_medico"},
    "name": {"zh": "姓名", "en": "name", "ko": "이름", "ja": "氏名", "es": "nombre"},
    "dept": {"zh": "科室", "en": "department", "ko": "진료과", "ja": "診療科", "es": "especialidad"},
    "langs": {"zh": "会说的语言", "en": "languages", "ko": "구사언어", "ja": "対応言語", "es": "idiomas"},
    "sessions": {"zh": "出诊时间", "en": "clinic_sessions", "ko": "진료일정", "ja": "外来担当", "es": "consultas"},
    "date": {"zh": "日期", "en": "date", "ko": "날짜", "ja": "日付", "es": "fecha"},
    "start": {"zh": "开始时间", "en": "start", "ko": "시작시각", "ja": "開始時刻", "es": "inicio"},
    "request": {"zh": "申请编号", "en": "request_id", "ko": "요청ID", "ja": "依頼ID", "es": "id_solicitud"},
    "patient": {"zh": "患者编号", "en": "patient_id", "ko": "환자ID", "ja": "患者ID", "es": "id_paciente"},
    "visit": {"zh": "就诊类型", "en": "visit_type", "ko": "진료구분", "ja": "受診区分", "es": "tipo_visita"},
    "urgency": {"zh": "紧急程度", "en": "urgency", "ko": "긴급도", "ja": "緊急度", "es": "urgencia"},
    "note": {"zh": "分诊备注", "en": "triage_note", "ko": "접수메모", "ja": "受付メモ", "es": "nota_triaje"},
    "lang": {"zh": "首选语言", "en": "preferred_language", "ko": "희망언어", "ja": "希望言語",
             "es": "idioma_preferido"},
    "prev": {"zh": "上次接诊医生", "en": "previous_doctor", "ko": "이전담당의", "ja": "前回担当医",
             "es": "medico_anterior"},
    "earliest": {"zh": "最早可约日期", "en": "earliest_date", "ko": "희망시작일", "ja": "受診可能日", "es": "fecha_desde"},
    "referral": {"zh": "转诊单有效期至", "en": "referral_valid_until", "ko": "의뢰서유효기한", "ja": "紹介状有効期限",
                 "es": "volante_valido_hasta"},
    "test": {"zh": "就诊前检查", "en": "pre_visit_test", "ko": "사전검사", "ja": "事前検査", "es": "prueba_previa"},
    "past": {"zh": "既往预约次数", "en": "past_appointments", "ko": "과거예약수", "ja": "過去予約数",
             "es": "citas_previas"},
    "missed": {"zh": "爽约次数", "en": "missed_appointments", "ko": "미내원수", "ja": "無断キャンセル数",
               "es": "citas_perdidas"},
}
VALUES = {
    "new": {"zh": "初诊", "en": "new patient", "ko": "초진", "ja": "初診", "es": "primera visita"},
    "follow": {"zh": "复诊", "en": "follow-up", "ko": "재진", "ja": "再診", "es": "revisión"},
    "blood": {"zh": "空腹抽血", "en": "fasting blood test", "ko": "공복 채혈", "ja": "空腹時採血",
              "es": "análisis de sangre en ayunas"},
    "AM": {"zh": "上午", "en": "AM", "ko": "오전", "ja": "午前", "es": "mañana"},
    "PM": {"zh": "下午", "en": "PM", "ko": "오후", "ja": "午後", "es": "tarde"},
    "IM": {"zh": "内科", "en": "Internal Medicine", "ko": "내과", "ja": "内科", "es": "Medicina Interna"},
    "CARD": {"zh": "心内科", "en": "Cardiology", "ko": "심장내과", "ja": "循環器内科", "es": "Cardiología"},
    "DERM": {"zh": "皮肤科", "en": "Dermatology", "ko": "피부과", "ja": "皮膚科", "es": "Dermatología"},
    "ORTH": {"zh": "骨科", "en": "Orthopedics", "ko": "정형외과", "ja": "整形外科", "es": "Traumatología"},
    "PED": {"zh": "儿科", "en": "Pediatrics", "ko": "소아청소년과", "ja": "小児科", "es": "Pediatría"},
}
LANG_NAMES = {
    "zh": {"L0": "中文", "F1": "英语", "F2": "韩语", "F3": "俄语", "F4": "越南语"},
    "en": {"L0": "English", "F1": "Spanish", "F2": "Chinese", "F3": "Vietnamese", "F4": "Arabic"},
    "ko": {"L0": "한국어", "F1": "영어", "F2": "중국어", "F3": "베트남어", "F4": "러시아어"},
    "ja": {"L0": "日本語", "F1": "英語", "F2": "中国語", "F3": "ベトナム語", "F4": "ポルトガル語"},
    "es": {"L0": "español", "F1": "inglés", "F2": "árabe", "F3": "rumano", "F4": "chino"},
}
NAMES = {
    "zh": ["王建华", "李敏", "张伟", "刘芳", "陈志强", "杨雪", "赵磊", "黄静", "周涛", "吴婷", "徐明", "孙丽", "马超",
           "胡琳"],
    "en": ["Alan Hughes", "Priya Shah", "Martin Cole", "Grace Okafor", "Simon Reid", "Laura Bennett", "Tom Fischer",
           "Hannah Moore", "Owen Price", "Chloe Walsh", "Ben Carter", "Ruth Ellis", "Sam Doyle", "Nina Patel"],
    "ko": ["김민준", "이서연", "박지훈", "최수진", "정우성", "강하은", "조현우", "윤지아", "장도윤", "임소영", "한재민",
           "오유나", "서준호", "신예린"],
    "ja": ["佐藤健一", "鈴木美咲", "高橋翔", "田中由美", "伊藤大輔", "渡辺真理", "山本拓也", "中村彩", "小林誠", "加藤恵",
           "吉田亮", "山田さくら", "松本悠", "井上奈々"],
    "es": ["Javier Morales", "Lucía Fernández", "Andrés Ruiz", "Carmen Navarro", "Pablo Herrera", "Elena Castro",
           "Miguel Ortega", "Sara Domínguez", "Raúl Vega", "Marta Iglesias", "Diego Ramos", "Ana Molina",
           "Jorge Serrano", "Paula Gil"],
}
WEEKDAYS = {
    "zh": ["周一", "周二", "周三", "周四", "周五"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri"],
    "ko": ["월", "화", "수", "목", "금"],
    "ja": ["月", "火", "水", "木", "金"],
    "es": ["lun", "mar", "mié", "jue", "vie"],
}
LIST_SEP = {"zh": "、", "en": "; ", "ko": ", ", "ja": "・", "es": "; "}
NOTES = {
    "U": {
        "zh": ["症状迅速加重，转诊医生要求尽快复查", "转诊医生标注检查结果异常", "疼痛剧烈，现用药物无法控制"],
        "en": ["symptoms getting worse quickly, referring GP asks for a prompt review",
               "abnormal test result flagged by the referring doctor", "severe pain not controlled by current medication"],
        "ko": ["증상이 빠르게 악화되어 의뢰 의사가 신속한 진료를 요청함", "의뢰 의사가 검사 결과 이상을 표시함",
               "현재 약으로 조절되지 않는 심한 통증"],
        "ja": ["症状が急速に悪化しており、紹介元の医師が早めの診察を希望", "紹介元の医師が検査結果の異常を指摘",
               "現在の薬で抑えられない強い痛み"],
        "es": ["los síntomas empeoran rápido; el médico de cabecera pide revisión pronto",
               "resultado de prueba anómalo señalado por el médico que deriva",
               "dolor intenso que no cede con la medicación actual"],
    },
    "S": {
        "zh": ["症状已持续数周", "需要尽快调整用药", "社区医生转诊，不宜久等"],
        "en": ["symptoms ongoing for several weeks", "medication needs adjusting soon",
               "GP referral, should not wait long"],
        "ko": ["몇 주째 증상이 지속됨", "곧 약 조정이 필요함", "동네 의원 의뢰, 오래 기다리면 안 됨"],
        "ja": ["数週間症状が続いている", "近いうちに薬の調整が必要", "かかりつけ医からの紹介、あまり待たせられない"],
        "es": ["síntomas desde hace varias semanas", "hay que ajustar la medicación pronto",
               "derivación del médico de cabecera; no conviene esperar mucho"],
    },
    "R": {
        "zh": ["常规检查", "年度复查", "轻微的老毛病"],
        "en": ["routine check", "annual review", "mild long-standing complaint"],
        "ko": ["정기 검진", "연례 점검", "오래된 가벼운 증상"],
        "ja": ["定期チェック", "年1回の経過観察", "以前からの軽い症状"],
        "es": ["control rutinario", "revisión anual", "molestia leve de larga evolución"],
    },
}
NOTICE = {
    "zh": "门诊通知\n\n1. 2026年11月23日（周一）为本市市民日，属于地方公共假日。\n"
          "当天门诊照常开放，各科室按平时的出诊安排接诊；如有调整，以各科室通知为准。\n\n"
          "2. 骨科{name}医生（D11）11月16日至20日休年假，期间不出诊。\n",
    "en": "Clinic notices\n\n1. Monday 23 November 2026 is City Day, a municipal public holiday.\n"
          "The outpatient building is open that day and clinics run on their usual schedule, "
          "unless a department announces otherwise.\n\n"
          "2. Orthopedics: Dr {name} (D11) is on annual leave from 16 to 20 November and holds no clinics that week.\n",
    "ko": "진료 안내\n\n1. 2026년 11월 23일(월)은 시민의 날로 지방 공휴일입니다.\n"
          "당일 외래는 정상 운영하며 각 진료과는 평소 일정대로 진료합니다. 변경 사항은 진료과별로 따로 안내합니다.\n\n"
          "2. 정형외과 {name} 선생님(D11)은 11월 16일~20일 연차 휴가로 그 주에는 진료하지 않습니다.\n",
    "ja": "外来のお知らせ\n\n1. 2026年11月23日（月）は市民の日（市の祝日）です。\n"
          "当日も外来は開いており、各診療科は通常どおりの担当表で診療します。変更がある場合は各診療科からお知らせします。\n\n"
          "2. 整形外科の{name}医師（D11）は11月16日〜20日まで年次休暇のため、その週の外来はありません。\n",
    "es": "Avisos de consultas\n\n1. El lunes 23 de noviembre de 2026 es el Día de la Ciudad, festivo local.\n"
          "Ese día el edificio de consultas externas abre y las consultas siguen su horario habitual, "
          "salvo que una especialidad avise de lo contrario.\n\n"
          "2. Traumatología: el Dr./la Dra. {name} (D11) está de vacaciones del 16 al 20 de noviembre y no pasa "
          "consulta esa semana.\n",
}


def _hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def write_data(world: World, data_dir: Path, lang: str) -> None:
    c, v, ln = labels(COLS, lang), labels(VALUES, lang), LANG_NAMES[lang]
    sep = LIST_SEP[lang]
    write_csv(data_dir / FILES["doctors"][lang], [c["doctor"], c["name"], c["dept"], c["langs"], c["sessions"]],
              [[d.id, NAMES[lang][i], v[d.dept], sep.join(ln[x] for x in d.langs),
                sep.join(f"{WEEKDAYS[lang][wd]} {v[h]}" for wd, h in sorted(d.sessions, key=lambda s: (s[0], s[1])))]
               for i, d in enumerate(world.doctors)])
    write_csv(data_dir / FILES["slots"][lang], [c["doctor"], c["date"], c["start"]],
              [[did, day.isoformat(), _hhmm(s)] for (did, day), starts in sorted(world.free.items())
               for s in starts])
    header = [c["request"], c["patient"], c["dept"], c["visit"], c["urgency"], c["note"], c["lang"], c["prev"],
              c["earliest"], c["referral"], c["test"]]
    rows = []
    for r in world.requests:
        row = [r.id, r.patient, v[r.dept], v["new" if r.new else "follow"], r.urgency,
               NOTES[r.urgency][lang][r.note], ln[r.lang], r.prev or "", r.earliest.strftime("%d/%m/%Y")]
        row += [r.referral.strftime("%d/%m/%Y") if r.referral else "", v["blood"] if r.test else ""]
        rows.append(row)
    write_csv(data_dir / FILES["requests"][lang], header, rows)
    leave_name = NAMES[lang][int(LEAVE_DOCTOR[1:]) - 1]
    (data_dir / FILES["notice"][lang]).write_text(NOTICE[lang].format(name=leave_name), encoding="utf-8")
    write_csv(data_dir / FILES["attendance"][lang], [c["patient"], c["past"], c["missed"]],
              [[r.patient, r.past, r.missed] for r in sorted(world.requests, key=lambda r: r.patient) if r.past])


# ── scoring ──────────────────────────────────────────────────────────────────

Booking = tuple  # (request, doctor, day, start minute, test day or None)


def _need(req: Request, start: int) -> list[int]:
    return [start, start + SLOT] if req.new else [start]


def _parse(world: World, rows: list[dict]) -> list[Booking]:
    out, seen = [], set()
    for k, row in enumerate(rows):
        rid, did = str(row.get("request_id", "")).strip(), str(row.get("doctor_id", "")).strip()
        req, doc = world.request(rid), world.doctor(did)
        if req is None:
            raise Fatal(f"row {k + 1}: unknown request_id {rid!r}")
        if rid in seen:
            raise Fatal(f"row {k + 1}: request {rid} is booked more than once")
        seen.add(rid)
        if doc is None:
            raise Fatal(f"row {k + 1}: unknown doctor_id {did!r}")
        days = []
        for col in ("date", "test_date"):
            raw = str(row.get(col) or "").strip()
            if col == "test_date" and not raw:
                days.append(None)
                continue
            try:
                day = dt.date.fromisoformat(raw)
            except ValueError as e:
                raise Fatal(f"row {k + 1}: {col} must be YYYY-MM-DD, got {row.get(col)!r}") from e
            if day not in DAY_INDEX:
                raise Fatal(f"row {k + 1}: {col} {day} is not a working day between 2026-11-16 and 2026-11-27")
            days.append(day)
        try:
            h, m = str(row.get("start", "")).strip().split(":")
            start = int(h) * 60 + int(m)
        except ValueError as e:
            raise Fatal(f"row {k + 1}: start must be HH:MM, got {row.get('start')!r}") from e
        out.append((req, doc, days[0], start, days[1] if req.test else None))
    return out


def evaluate(world: World, bookings: list[Booking]) -> tuple[list, float, dict]:
    violations: list[tuple[str, str]] = []
    used: dict[tuple[str, dt.date, int], list[Request]] = {}
    interp_new: dict[dt.date, int] = {}
    interp_all: dict[dt.date, int] = {}
    lab: dict[dt.date, int] = {}
    booked = set()
    wait_cost = late_soon = 0
    expected_missed = idle = 0.0
    for req, doc, day, start, test in bookings:
        booked.add(req.id)
        where = f"{req.id} with {doc.id} on {day} {_hhmm(start)}"
        if doc.dept != req.dept:
            violations.append(("department_match", f"{where}: request is for {req.dept}, doctor is {doc.dept}"))
        free = world.free.get((doc.id, day), [])
        for s in _need(req, start):
            if s not in free:
                violations.append(("slot_length", f"{where}: needs the free slot {_hhmm(s)}"
                                                  f"{' (new patients take two consecutive slots)' if req.new else ''}"))
            used.setdefault((doc.id, day, s), []).append(req)
        if day == HOLIDAY and doc.dept == world.closed_dept:
            violations.append(("holiday_closure", f"{where}: the {world.closed_dept} clinic is closed on {HOLIDAY}"))
        if day < req.earliest:
            violations.append(("not_before_earliest", f"{where}: before the earliest date {req.earliest}"))
        if req.prev and doc.id != req.prev:
            violations.append(("follow_up_same_doctor", f"{where}: follow-up must be with {req.prev}"))
        if req.lang not in doc.langs:
            interp_all[day] = interp_all.get(day, 0) + 1
            if req.new:
                interp_new[day] = interp_new.get(day, 0) + 1
        wait = DAY_INDEX[day] - req.ref_day
        if req.urgency == "U" and wait > world.urgent_days:
            violations.append(("urgent_within_2_days", f"{where}: urgent request waits {wait} working days"))
        if world.medium:
            if req.referral is not None and day > req.referral:
                violations.append(("referral_validity", f"{where}: the referral expired on {req.referral}"))
            if req.test:
                if test is None or test >= day or test < req.earliest:
                    violations.append(("test_before_visit", f"{where}: the blood test must be on a working day from "
                                                            f"{req.earliest} to the day before the visit (got {test})"))
                if test is not None:
                    lab[test] = lab.get(test, 0) + 1
        if req.urgency == "S" and wait > world.soon_days:
            late_soon += 1
        wait_cost += WEIGHT[req.urgency] * max(wait, 0)
        if world.hard:
            expected_missed += no_show(req, day)
    overbooked: dict[tuple[str, dt.date, str], int] = {}
    collision = 0.0
    for (did, day, s), reqs in sorted(used.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        if world.hard and len(reqs) <= 2:
            # The slot's time is lost only if every patient booked into it stays away.
            p_all = 1.0
            for r in reqs:
                p_all *= no_show(r, day)
            idle += IDLE_COST * p_all
        if len(reqs) == 1:
            continue
        what = f"{did} on {day} {_hhmm(s)} holds {', '.join(r.id for r in reqs)}"
        if not world.hard:
            violations.append(("no_double_booking", what))
        elif len(reqs) > 2 or any(r.new for r in reqs):
            violations.append(("slot_capacity", f"{what}: at most two follow-ups may share a slot"))
        else:
            key = (did, day, "AM" if s < NOON else "PM")
            overbooked[key] = overbooked.get(key, 0) + 1
            collision += COLLISION_COST * (1 - no_show(reqs[0], day)) * (1 - no_show(reqs[1], day))
    for (did, day, half), n in sorted(overbooked.items()):
        if n > world.ob_max:
            violations.append(("overbooking_limit", f"{did} {day} {half}: {n} overbooked slots, at most {world.ob_max}"))
    remote = 0
    for day in sorted(interp_all):
        if interp_new.get(day, 0) > world.interpreters:
            violations.append(("interpreter_capacity", f"{day}: {interp_new[day]} new-patient visits need an "
                                                       f"in-person interpreter, only {world.interpreters} available"))
        remote += max(0, interp_all[day] - world.interpreters)
    for day, n in sorted(lab.items()):
        if n > world.lab_cap:
            violations.append(("lab_capacity", f"{day}: {n} blood tests, the lab takes {world.lab_cap} a day"))
    unbooked = [r for r in world.requests if r.id not in booked]
    for r in unbooked:
        if r.urgency == "U":
            violations.append(("urgent_within_2_days", f"urgent request {r.id} is not booked"))
    objective = (wait_cost + UNSEEN_PENALTY * len(unbooked) + SOON_LATE_PENALTY * late_soon
                 + REMOTE_COST * remote + idle + collision)
    metrics = {"booked": len(booked), "unbooked": len(unbooked), "weighted_waiting_days": wait_cost,
               "soon_booked_late": late_soon, "remote_interpreted": remote}
    if world.medium:
        metrics["blood_tests"] = sum(lab.values())
    if world.hard:
        metrics.update(expected_no_shows=round(expected_missed, 3), overbooked_slots=sum(overbooked.values()),
                       expected_idle_cost=round(idle, 3), expected_collision_cost=round(collision, 3))
    return violations, round(float(objective), 6), metrics


def score(world: World, submission_dir: Path, setting) -> dict:
    world = _View(world, setting)
    try:
        rows = read_csv(submission_dir, "bookings.csv", ["request_id", "doctor_id", "date", "start"])
        violations, objective, metrics = evaluate(world, _parse(world, rows))
    except Fatal as e:
        return {"fatal": str(e)}
    return {"violations": violations, "objective": objective, "metrics": metrics}


# ── reference solution ───────────────────────────────────────────────────────

PRIOR_A, PRIOR_B = 2.0, 8.0                                      # reference: shrink past rates toward ~20 %


def estimated_no_show(req: Request, day: dt.date) -> float:
    """The reference's no-show estimate: shrunk past rate, moved from the historical lead to this one."""
    hist = (req.missed + PRIOR_A) / (req.past + PRIOR_A + PRIOR_B)
    return min(0.9, max(0.0, hist + LEAD_SLOPE * (DAY_INDEX[day] + LEAD0 - HIST_LEAD)))


def _cost(world: World, req: Request, day: dt.date) -> float:
    wait = DAY_INDEX[day] - req.ref_day
    c = WEIGHT[req.urgency] * wait + (SOON_LATE_PENALTY if req.urgency == "S" and wait > world.soon_days else 0)
    return c + (IDLE_COST * len(_need(req, 0)) * estimated_no_show(req, day) if world.hard else 0)


class _Plan:
    """Bookings under construction, with slot occupancy, interpreter and lab counts."""

    def __init__(self, world: World):
        self.world = world
        self.book: dict = {}             # request id -> (req, doc, day, start, need, speaks, test)
        self.used: dict = {}             # (doctor id, day, minute) -> [request ids]
        self.interp_new: dict = {}
        self.interp_all: dict = {}
        self.lab: dict = {}

    def test_day(self, req: Request, di: int) -> dt.date | None:
        """Latest lab day with room from the earliest date up to the day before visit day `di` (None: no test)."""
        for ti in range(di - 1, -1, -1):
            if DAYS[ti] < req.earliest:
                break
            if self.lab.get(DAYS[ti], 0) < self.world.lab_cap:
                return DAYS[ti]
        return None

    def options(self, req: Request, ignore_used: bool = False) -> list:
        """Feasible (day, doctor, start, test day) for req, best first: earliest day (a day later for an
        interpreted visit), own-language doctor, fewest cut free runs, earliest start."""
        w, out = self.world, []
        docs = [d for d in w.doctors if d.dept == req.dept and (req.prev is None or d.id == req.prev)]
        for di in range(req.ref_day, req.last_day(w.urgent_days) + 1):
            day = DAYS[di]
            if day < req.earliest:
                continue
            test = None
            if w.medium and req.test:
                test = self.test_day(req, di)
                if test is None:
                    continue
            for doc in docs:
                if day == HOLIDAY and doc.dept == w.closed_dept:
                    continue
                speaks = req.lang in doc.langs
                if not speaks and req.new and self.interp_new.get(day, 0) >= w.interpreters:
                    continue
                free = w.free.get((doc.id, day), [])
                for s in free:
                    need = _need(req, s)
                    if not all(x in free for x in need):
                        continue
                    if not ignore_used and any((doc.id, day, x) in self.used for x in need):
                        continue
                    loose = sum(1 for x in (need[0] - SLOT, need[-1] + SLOT)
                                if x in free and (doc.id, day, x) not in self.used)
                    key = (_cost(w, req, day) + (0 if speaks else INTERP_DETOUR), not speaks, loose, s, doc.id)
                    out.append((key, day, doc, s, need, speaks, test))
        out.sort(key=lambda o: o[0])
        return out

    def add(self, req, day, doc, s, need, speaks, test) -> None:
        self.book[req.id] = (req, doc, day, s, need, speaks, test)
        for x in need:
            self.used.setdefault((doc.id, day, x), []).append(req.id)
        if not speaks:
            self.interp_all[day] = self.interp_all.get(day, 0) + 1
            if req.new:
                self.interp_new[day] = self.interp_new.get(day, 0) + 1
        if test is not None:
            self.lab[test] = self.lab.get(test, 0) + 1

    def remove(self, rid: str) -> tuple:
        req, doc, day, s, need, speaks, test = b = self.book.pop(rid)
        for x in need:
            self.used[(doc.id, day, x)].remove(rid)
            if not self.used[(doc.id, day, x)]:
                del self.used[(doc.id, day, x)]
        if not speaks:
            self.interp_all[day] -= 1
            if req.new:
                self.interp_new[day] -= 1
        if test is not None:
            self.lab[test] -= 1
        return b

    def restore(self, b: tuple) -> None:
        req, doc, day, s, need, speaks, test = b
        self.add(req, day, doc, s, need, speaks, test)

    def overbook_options(self, req: Request) -> list:
        """Hard tier: slots of req's follow-up doctor already holding one follow-up, in sessions with room."""
        w, out = self.world, []
        if not req.prev or req.urgency == "U":
            return out
        doc = w.doctor(req.prev)
        for di in range(req.ref_day, req.last_day(w.urgent_days) + 1):
            day = DAYS[di]
            if day < req.earliest or (day == HOLIDAY and doc.dept == w.closed_dept):
                continue
            test = self.test_day(req, di) if req.test else None
            if req.test and test is None:
                continue
            speaks = req.lang in doc.langs
            for s in w.free.get((doc.id, day), []):
                held = self.used.get((doc.id, day, s), [])
                if len(held) != 1 or w.request(held[0]).new:
                    continue
                half = s < NOON
                n_ob = sum(1 for x in w.free.get((doc.id, day), [])
                           if (x < NOON) == half and len(self.used.get((doc.id, day, x), [])) > 1)
                if n_ob >= w.ob_max:
                    continue
                p, q = estimated_no_show(req, day), estimated_no_show(w.request(held[0]), day)
                # Joining a slot: own waiting cost; collision if both come; the slot's idle risk drops from q to p*q.
                delta = (_cost(w, req, day) - IDLE_COST * p + COLLISION_COST * (1 - p) * (1 - q)
                         - IDLE_COST * q * (1 - p) + (0 if speaks else INTERP_DETOUR))
                out.append(((delta, s), day, doc, s, [s], speaks, test))
        out.sort(key=lambda o: o[0])
        return out


def _solve(world: World) -> list[Booking]:
    """Greedy by priority (urgent, soon, routine; each by reference date) into the cheapest feasible slot; one
    repair pass that books a left-over request when moving a single blocking booking makes room; in the hard
    tier, then overbook left-over follow-ups where the expected collision costs less than leaving them out."""
    if "ref" in world._cache:
        return list(world._cache["ref"])
    plan = _Plan(world)
    order = sorted(world.requests, key=lambda r: ("USR".index(r.urgency), r.ref_day, r.id))
    for req in order:
        opts = plan.options(req)
        if opts:
            plan.add(req, *opts[0][1:])
    for req in order * 2:
        if req.id in plan.book:
            continue
        for _, day, doc, s, need, speaks, test in plan.options(req, ignore_used=True):
            blockers = {rid for x in need for rid in plan.used.get((doc.id, day, x), [])}
            if len(blockers) != 1:
                continue
            old = plan.remove(blockers.pop())
            if test is not None and plan.lab.get(test, 0) >= world.lab_cap:
                plan.restore(old)
                continue
            plan.add(req, day, doc, s, need, speaks, test)
            alt = plan.options(old[0])
            if alt and (_cost(world, req, day) + _cost(world, old[0], alt[0][1]) - _cost(world, old[0], old[2])
                        < UNSEEN_PENALTY):
                plan.add(old[0], *alt[0][1:])
                break
            plan.remove(req.id)
            plan.restore(old)
    if world.hard:
        for req in order:
            if req.id in plan.book:
                continue
            opts = plan.overbook_options(req)
            if opts and opts[0][0][0] < UNSEEN_PENALTY:
                plan.add(req, *opts[0][1:])
    out = sorted(((b[0], b[1], b[2], b[3], b[6]) for b in plan.book.values()), key=lambda b: b[0].id)
    world._cache["ref"] = out
    return list(out)


def _write(out_dir: Path, bookings) -> None:
    write_csv(out_dir / "bookings.csv", ["request_id", "doctor_id", "date", "start", "test_date"],
              [[r.id, d.id, day.isoformat(), _hhmm(s), t.isoformat() if t else ""] for r, d, day, s, t in bookings])


def reference_solution(world: World, out_dir: Path, setting) -> None:
    _write(out_dir, _solve(_View(world, setting)))


def violating_examples(world: World, setting) -> dict:
    """One deliverable per rule of the setting that breaks exactly that rule (for the validator)."""
    world = _View(world, setting)
    ref = _solve(world)

    def rules_of(bookings) -> set:
        return {v[0] for v in evaluate(world, bookings)[0]}

    def occupied(bookings) -> set:
        return {(d.id, day, x) for r, d, day, s, t in bookings for x in _need(r, s)}

    def find(rule: str, moves) -> list:
        for cand in moves():
            if rules_of(cand) == {rule}:
                return cand
        raise AssertionError(f"no clean example for {rule} ({world.setting.label})")

    def relocations(pred_req, pred_target):
        """Every single-booking move of a request matching pred_req to a free start matching pred_target."""
        def gen():
            for i, (r, d, day, s, t) in enumerate(ref):
                if not pred_req(r, d, day, s):
                    continue
                rest = ref[:i] + ref[i + 1:]
                occ = occupied(rest)
                for (did, dday), starts in sorted(world.free.items()):
                    doc = world.doctor(did)
                    for x in starts:
                        if (did, dday, x) in occ or not pred_target(r, d, day, s, doc, dday, x):
                            continue
                        yield rest + [(r, doc, dday, x, t)]
        return gen

    def stack(pred_pair):
        """Put the follow-up booking j onto the start of booking i, same doctor and day."""
        def gen():
            for i, (r, d, day, s, t) in enumerate(ref):
                for j, (r2, d2, day2, s2, t2) in enumerate(ref):
                    if i != j and d2.id == d.id and day2 == day and not r2.new and pred_pair(r, r2):
                        yield [b for k, b in enumerate(ref) if k != j] + [(r2, d, day, s, t2)]
        return gen

    def double():
        for i, (r, d, day, s, t) in enumerate(ref):
            for j, (r2, d2, day2, s2, t2) in enumerate(ref):
                if i != j and r2.dept == r.dept and not r2.new and (r2.prev in (None, d.id)) and r2.urgency != "U":
                    yield [b for k, b in enumerate(ref) if k != j] + [(r2, d, day, s, t2)]

    def too_many_overbooked():
        """Pair up follow-ups inside one doctor session until it holds one more overbooked slot than allowed."""
        sessions: dict = {}
        for k, (r, d, day, s, t) in enumerate(ref):
            sessions.setdefault((d.id, day, s < NOON), []).append(k)
        for key, idx in sorted(sessions.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
            starts = {}
            for k in idx:
                starts.setdefault(ref[k][3], []).append(k)
            ob = sum(1 for ks in starts.values() if len(ks) > 1)
            singles = [ks[0] for st, ks in sorted(starts.items()) if len(ks) == 1 and not ref[ks[0]][0].new]
            need = world.ob_max + 1 - ob
            if need <= 0 or len(singles) < 2 * need:
                continue
            out = list(ref)
            for p in range(need):
                a, b = singles[2 * p], singles[2 * p + 1]
                r2, d2, day2, s2, t2 = ref[b]
                out[b] = (r2, d2, day2, ref[a][3], t2)
            yield out

    def drop_urgent():
        for i, (r, d, day, s, t) in enumerate(ref):
            if r.urgency == "U":
                yield ref[:i] + ref[i + 1:]

    def pile(count, pred_req, move):
        """Apply single moves of matching bookings one after another until `count` exceeds its cap."""
        def gen():
            for target in DAYS:
                cand = list(ref)
                for b in ref:
                    if not pred_req(b, target):
                        continue
                    k = next((j for j, c in enumerate(cand) if c[0].id == b[0].id), None)
                    moved = None if k is None else move(cand, k, target)
                    if moved is None:
                        continue
                    cand = moved
                    if count(cand, target):
                        yield cand
                        break
        return gen

    def move_visit(cand, k, target):
        """Move booking k to a start of a same-department doctor who does not speak the patient's language,
        dropping routine bookings that sit in the way (leaving a request out only costs quality)."""
        r, d, day, s, t = cand[k]
        for doc in world.doctors:
            if doc.dept != r.dept or r.lang in doc.langs:
                continue
            free = world.free.get((doc.id, target), [])
            for x in free:
                need = _need(r, x)
                if not all(y in free for y in need):
                    continue
                drop = {j for j, (r2, d2, day2, s2, t2) in enumerate(cand) if j != k and d2.id == doc.id
                        and day2 == target and set(_need(r2, s2)) & set(need)}
                if any(cand[j][0].urgency == "U" or (cand[j][0].new and cand[j][0].lang not in doc.langs)
                       for j in drop):
                    continue
                return [b if j != k else (r, doc, target, x, t) for j, b in enumerate(cand) if j not in drop]
        return None

    def interp_count(cand, target):
        return sum(1 for r, d, day, s, t in cand if day == target and r.new and r.lang not in d.langs) \
            > world.interpreters

    def lab_count(cand, target):
        return sum(1 for r, d, day, s, t in cand if t == target) > world.lab_cap

    def move_test(cand, k, target):
        r, d, day, s, t = cand[k]
        return cand[:k] + [(r, d, day, s, target)] + cand[k + 1:]

    ex = {
        "slot_length": find("slot_length", relocations(
            lambda r, d, day, s: r.new and r.urgency == "R",
            lambda r, d, day, s, doc, dday, t: doc.id == d.id and dday == day)),
        "department_match": find("department_match", relocations(
            lambda r, d, day, s: r.new and r.urgency == "R" and r.lang == "L0",
            lambda r, d, day, s, doc, dday, t: doc.dept != r.dept and dday == day)),
        "holiday_closure": find("holiday_closure", relocations(
            lambda r, d, day, s: r.dept == world.closed_dept and r.urgency == "R",
            lambda r, d, day, s, doc, dday, t: dday == HOLIDAY and doc.dept == world.closed_dept)),
        "not_before_earliest": find("not_before_earliest", relocations(
            lambda r, d, day, s: r.earliest > START and r.urgency == "R" and not r.test,
            lambda r, d, day, s, doc, dday, t: dday < r.earliest and doc.id == d.id)),
        "interpreter_capacity": find("interpreter_capacity", pile(
            interp_count,
            lambda b, target: b[0].new and b[0].urgency == "R" and b[0].lang != "L0" and b[0].earliest <= target
            and (b[4] is None or b[4] < target) and (b[0].referral is None or b[0].referral >= target)
            and not (b[0].dept == world.closed_dept and target == HOLIDAY) and b[2] != target,
            move_visit)),
        "urgent_within_2_days": find("urgent_within_2_days", drop_urgent),
        "follow_up_same_doctor": find("follow_up_same_doctor", relocations(
            lambda r, d, day, s: not r.new and r.urgency == "R" and r.lang == "L0",
            lambda r, d, day, s, doc, dday, t: doc.dept == r.dept and doc.id != r.prev and dday == day)),
    }
    if world.hard:
        ex["slot_capacity"] = find("slot_capacity", stack(lambda r, r2: r.new))
        ex["overbooking_limit"] = find("overbooking_limit", too_many_overbooked)
    else:
        ex["no_double_booking"] = find("no_double_booking", double)
    if world.medium:
        ex["referral_validity"] = find("referral_validity", relocations(
            lambda r, d, day, s: r.referral is not None and r.referral < DAYS[-1] and r.urgency == "R",
            lambda r, d, day, s, doc, dday, t: doc.id == d.id and dday > r.referral))
        ex["test_before_visit"] = find("test_before_visit", lambda: (
            ref[:k] + [(r, d, day, s, day)] + ref[k + 1:] for k, (r, d, day, s, t) in enumerate(ref) if r.test))
        ex["lab_capacity"] = find("lab_capacity", pile(
            lab_count, lambda b, target: b[0].test and b[4] != target and b[0].earliest <= target < b[2],
            move_test))
    return {rule: (lambda out, b=b: _write(out, b)) for rule, b in ex.items()}
