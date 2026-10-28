"""Interview shortlist for three open roles (original FDE-Bench v2 case).

A growing company received about 250 applications for three roles (backend
engineer, data analyst, security analyst) and asks for an interview shortlist.
The request only says "shortlist the best"; what decides validity and quality
(how many per role, which skills are must-haves, which experience counts,
expired certificates, work authorization, one role per candidate, the
adverse-impact check on protected attributes and the referral habit) is in the
requirements and must be asked for. Every candidate has a hidden true job fit
per role; past hires' one-year performance scores are the learnable signal,
but those scores carry the old managers' bias on gender, age and nationality.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from fdebench2.casekit import Fatal, labels, read_csv, write_csv

# ── world ────────────────────────────────────────────────────────────────────

K = 8                                  # interview slots per role
PRESENT = (2026, 10)                   # "present" counts up to and including October 2026
CERT_CUTOFF = "2026-11-01"             # a certificate counts only if it expires on or after this day
AI_RATIO = 0.8                         # adverse-impact (four-fifths) threshold
AI_MIN_GROUP = 15                      # groups with fewer qualified candidates are not tested
PROTECTED = ("gender", "age_band", "nationality")
# Groups the adverse-impact check compares: gender as recorded, age under 40 vs 40 and over,
# nationality Singapore vs any other.
AI_GROUP = {"gender": lambda v: v,
            "age_band": lambda v: "40_and_over" if v in ("40s", "50p") else "under_40",
            "nationality": lambda v: "SG" if v == "SG" else "other"}

ROLES = {
    "R1": dict(must=("python", "sql"), nice={"kubernetes": 8, "aws": 6, "go": 3, "docker": 1},
               family="software_engineering", min_months=36, auth=True, year_w=4.0, cap=3.0,
               cert_bonus={"aws_sa": 5}, req_cert=(), edu={}),
    "R2": dict(must=("sql", "statistics"), nice={"ab_testing": 9, "python": 5, "tableau": 3, "power_bi": 1, "excel": 0},
               family="data_analytics", min_months=24, auth=False, year_w=4.5, cap=2.5,
               cert_bonus={"tableau_cert": 2}, req_cert=(), edu={"master": 4, "phd": 6}),
    "R3": dict(must=("network_security", "siem"), nice={"incident_response": 9, "cloud_security": 6, "linux": 2,
                                                       "python": 1},
               family="information_security", min_months=24, auth=True, year_w=3.5, cap=4.0,
               cert_bonus={"cissp": 5}, req_cert=("cissp", "security_plus"), edu={}),
}
PRIMARY = {"software_engineering": "R1", "data_analytics": "R2", "information_security": "R3"}
OTHER_FAMILIES = ("it_support", "project_management", "sales", "finance")
ALL_SKILLS = ("python", "java", "go", "sql", "kubernetes", "docker", "aws", "statistics", "excel", "tableau",
              "power_bi", "ab_testing", "r_lang", "network_security", "siem", "incident_response", "cloud_security",
              "linux", "scrum")
CERTS = ("aws_sa", "tableau_cert", "cissp", "security_plus", "pmp", "ccna")
# Old managers' rating habits, present in past performance scores but NOT in true job fit.
BIAS = {"gender": {"M": 6.0, "F": -5.0, "X": 0.0},
        "age_band": {"u30": 5.0, "30s": 3.0, "40s": -6.0, "50p": -10.0},
        "nationality": {"SG": 6.0}}


@dataclass
class Job:
    family: str
    start: tuple[int, int]
    end: tuple[int, int] | None        # None = present


@dataclass
class Cert:
    code: str
    issued: str
    expires: str


@dataclass
class Candidate:
    id: str
    applied: list[str]
    applied_on: str
    location: str
    auth: str
    edu: str
    grad_year: int
    skills: set[str]
    languages: list[str]
    gender: str
    age_band: str
    nationality: str
    jobs: list[Job]
    certs: list[Cert]
    referral: bool = False
    fit: dict[str, float] = field(default_factory=dict)
    grad_age: int = 22
    min_age: float = 22.0           # youngest age consistent with education and career

    def months_in(self, family: str) -> int:
        return sum(_months(j) for j in self.jobs if j.family == family)

    @property
    def total_months(self) -> int:
        return sum(_months(j) for j in self.jobs)

    def valid_certs(self) -> set[str]:
        return {c.code for c in self.certs if c.expires >= CERT_CUTOFF}


@dataclass
class World:
    candidates: list[Candidate]
    past_hires: list[dict]
    by_id: dict[str, Candidate] = field(default_factory=dict)

    def __post_init__(self):
        self.by_id = {c.id: c for c in self.candidates}


def _months(j: Job) -> int:
    ey, em = j.end or PRESENT
    return (ey * 12 + em) - (j.start[0] * 12 + j.start[1]) + 1


def _ym(n: int) -> tuple[int, int]:
    """Month index (year*12 + month-1) -> (year, month)."""
    return n // 12, n % 12 + 1


def meets_must(c: Candidate, role: str) -> bool:
    spec = ROLES[role]
    if not all(s in c.skills for s in spec["must"]):
        return False
    if c.months_in(spec["family"]) < spec["min_months"]:
        return False
    if spec["req_cert"] and not (c.valid_certs() & set(spec["req_cert"])):
        return False
    return True


def authorized(c: Candidate, role: str) -> bool:
    return not ROLES[role]["auth"] or c.auth != "needs_sponsorship"


def qualified(c: Candidate, role: str) -> bool:
    return role in c.applied and meets_must(c, role) and authorized(c, role)


def _fit_value(role: str, rel_years: float, skills: set[str], valid_certs: set[str], edu: str) -> float:
    spec = ROLES[role]
    v = 30.0 + spec["year_w"] * min(max(rel_years - spec["min_months"] / 12, 0.0), spec["cap"])
    v += sum(w for s, w in spec["nice"].items() if s in skills)
    v += sum(w for cc, w in spec["cert_bonus"].items() if cc in valid_certs)
    v += spec["edu"].get(edu, 0)
    return v


def _wchoice(rng: random.Random, table: dict):
    keys = list(table)
    return rng.choices(keys, weights=[table[k] for k in keys])[0]


def _age_band(age: float) -> str:
    return "u30" if age < 30 else "30s" if age < 40 else "40s" if age < 50 else "50p"


def _languages(rng: random.Random, nat: str) -> list[str]:
    first = {"SG": ["english", _wchoice(rng, {"mandarin": 6, "malay": 2, "tamil": 2})],
             "MY": ["malay", _wchoice(rng, {"english": 7, "mandarin": 3})],
             "IN": ["english", _wchoice(rng, {"hindi": 6, "tamil": 4})],
             "CN": ["mandarin"] + (["english"] if rng.random() < 0.75 else []),
             "PH": ["tagalog", "english"],
             "VN": ["vietnamese"] + (["english"] if rng.random() < 0.8 else []),
             "ID": ["indonesian"] + (["english"] if rng.random() < 0.8 else [])}[nat]
    if rng.random() < 0.08:
        extra = rng.choice(["japanese", "korean", "spanish"])
        if extra not in first:
            first.append(extra)
    return list(dict.fromkeys(first))


def _make_candidate(rng: random.Random, idx: int) -> Candidate:
    primary = _wchoice(rng, {"software_engineering": 34, "data_analytics": 28, "information_security": 30,
                             "other": 10})
    gender = _wchoice(rng, {"F": 46, "M": 50, "X": 4})
    nat = _wchoice(rng, {"SG": 40, "MY": 14, "IN": 15, "CN": 13, "PH": 10, "VN": 4, "ID": 4})
    edu = _wchoice(rng, {"diploma": 10, "bachelor": 58, "master": 27, "phd": 5})
    grad_age = {"diploma": 20, "bachelor": 22, "master": 24, "phd": 28}[edu] + rng.choice([0, 0, 1, 2, 4, 7])
    career = rng.choice([rng.randint(12, 72), rng.randint(36, 132), rng.randint(60, 200)])
    gap = rng.choice([0, 0, 0, 6, 12, 24])
    age = grad_age + (career + gap) / 12 + rng.choice([0, 0, 1, 3, 6, 10, 15]) + rng.uniform(0, 1)
    now = PRESENT[0] * 12 + PRESENT[1] - 1
    # Work history: back from the present (or a few months ago) in 1-5 jobs, no overlaps.
    n_jobs = max(1, min(5, career // rng.randint(18, 40) + 1))
    cuts = sorted(rng.sample(range(1, career), n_jobs - 1)) if career > n_jobs else []
    bounds = [0] + cuts + [career]
    end_idx = now - (0 if rng.random() < 0.65 else rng.randint(1, 8))
    start_idx = end_idx - career + 1
    jobs = []
    fam_main = primary if primary != "other" else rng.choice(OTHER_FAMILIES)
    # Some profiles straddle two of the open roles (e.g. engineer turned analyst) and apply to both.
    fam_two = rng.choice([f for f in PRIMARY if f != fam_main]) if primary in PRIMARY and rng.random() < 0.16 else None
    if fam_two:
        career = max(career, rng.randint(84, 180))
        n_jobs = max(n_jobs, 3)
        cuts = sorted(rng.sample(range(1, career), n_jobs - 1))
        bounds = [0] + cuts + [career]
        start_idx = end_idx - career + 1
        age = max(age, grad_age + (career + gap) / 12 + rng.uniform(0, 1))
    for k in range(n_jobs):
        if fam_two:
            fam = fam_main if (k % 2 == 0) != (rng.random() < 0.2) else fam_two
        else:
            fam = fam_main if rng.random() < 0.8 else rng.choice(
                [f for f in list(PRIMARY) + list(OTHER_FAMILIES) if f != fam_main])
        s, e = start_idx + bounds[k], start_idx + bounds[k + 1] - 1
        jobs.append(Job(fam, _ym(s), None if (k == n_jobs - 1 and e == now) else _ym(e)))
    # Skills follow the main family.
    main_role = PRIMARY.get(fam_main)
    my_roles = [r for r in (main_role, PRIMARY.get(fam_two)) if r]
    skills = set()
    for s in ALL_SKILLS:
        p = 0.08
        for r in my_roles:
            if s in ROLES[r]["must"]:
                p = max(p, 0.88)
            elif s in ROLES[r]["nice"]:
                p = max(p, 0.42)
        if s == "scrum":
            p = 0.3
        if s == "excel":
            p = max(p, 0.35)
        if rng.random() < p:
            skills.add(s)
    # Certificates: some still valid, some expired.
    certs = []
    probs = {"R1": {"aws_sa": 0.35, "ccna": 0.05}, "R2": {"tableau_cert": 0.3},
             "R3": {"cissp": 0.45, "security_plus": 0.75, "ccna": 0.2}}
    probs = {k: v for r in my_roles for k, v in probs[r].items()} if my_roles else {"pmp": 0.3}
    for code, p in probs.items():
        if rng.random() < p:
            while True:
                iy, im, idd = rng.randint(2021 if "R3" in my_roles else 2018, 2026), rng.randint(1, 12), rng.randint(1, 28)
                if (iy, im) > (2026, 9):
                    continue
                ey = iy + 3
                exp = f"{ey:04d}-{im:02d}-{idd:02d}"
                if not ("2026-10-15" <= exp <= "2026-11-15"):   # keep clear of the cut-off date
                    break
            certs.append(Cert(code, f"{iy:04d}-{im:02d}-{idd:02d}", exp))
    if nat == "SG":
        auth = _wchoice(rng, {"citizen": 82, "permanent_resident": 18})
    else:
        auth = _wchoice(rng, {"permanent_resident": 22, "work_pass": 42, "needs_sponsorship": 36})
    location = "overseas" if auth == "needs_sponsorship" and rng.random() < 0.7 else _wchoice(
        rng, {"central": 4, "east": 2, "west": 2, "north": 2})
    applied = list(my_roles) if my_roles else [rng.choice(list(ROLES))]
    if len(applied) == 1 and rng.random() < 0.25:
        applied.append(rng.choice([r for r in ROLES if r not in applied]))
    applied.sort()
    day = rng.randint(0, 24)
    return Candidate(id=f"C{idx:03d}", applied=applied, applied_on=f"2026-10-{1 + day:02d}", location=location,
                     auth=auth, edu=edu, grad_year=int(2026 - (age - grad_age)), skills=skills,
                     languages=_languages(rng, nat), gender=gender, age_band=_age_band(age), nationality=nat,
                     jobs=jobs, certs=certs, grad_age=grad_age, min_age=grad_age + (career + gap) / 12)


def _near_threshold(c: Candidate) -> bool:
    return any(abs(c.months_in(ROLES[r]["family"]) - ROLES[r]["min_months"]) <= 1 for r in c.applied)


def _past_hires(rng: random.Random) -> list[dict]:
    rows = []
    for i in range(360):
        role = list(ROLES)[i % 3]
        spec = ROLES[role]
        years = round(min(16.0, spec["min_months"] / 12 + rng.expovariate(1 / 3.2)), 1)
        skills = set(spec["must"]) | {s for s in spec["nice"] if rng.random() < 0.45}
        skills |= {s for s in ALL_SKILLS if s not in skills and rng.random() < 0.08}
        certs = {cc for cc in spec["cert_bonus"] if rng.random() < 0.35}
        if spec["req_cert"] and not certs:
            certs.add("security_plus")
        gender = _wchoice(rng, {"F": 40, "M": 56, "X": 4})
        nat = _wchoice(rng, {"SG": 48, "MY": 13, "IN": 13, "CN": 11, "PH": 9, "VN": 3, "ID": 3})
        edu = _wchoice(rng, {"diploma": 10, "bachelor": 58, "master": 27, "phd": 5})
        grad_age = {"diploma": 20, "bachelor": 22, "master": 24, "phd": 28}[edu] + rng.choice([0, 0, 1, 2, 4, 7])
        hire_year = rng.randint(2021, 2025)
        age = grad_age + years + rng.choice([0, 0, 1, 2, 3, 6]) + rng.uniform(0, 1)
        band = _age_band(age)
        referral = rng.random() < 0.1
        score = _fit_value(role, years, skills, certs, edu) + rng.gauss(0, 4.5)
        score += BIAS["gender"][gender] + BIAS["age_band"][band] + BIAS["nationality"].get(nat, -2.0)
        rows.append(dict(id=f"H{i + 1:03d}", role=role,
                         hire_date=f"{hire_year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                         years=years, skills=sorted(skills, key=ALL_SKILLS.index), certs=sorted(certs), edu=edu,
                         grad_year=int(hire_year - (age - grad_age)), gender=gender, age_band=band, nationality=nat,
                         referral=referral, score=round(max(0.0, min(100.0, score)), 1)))
    rows.sort(key=lambda r: r["hire_date"])
    for i, r in enumerate(rows):
        r["id"] = f"H{i + 1:03d}"
    return rows


def _balance_protected(rng: random.Random, cands: list[Candidate]) -> None:
    """Protected attributes carry no job signal: among qualified candidates, walk down the fit order and hand
    out gender, age (under 40 / 40 and over) and nationality (Singapore / other) in balanced pairs, keeping
    every record self-consistent (age vs. career, work authorization vs. nationality, languages)."""
    rank: dict[str, tuple] = {}
    for role in ROLES:
        q = sorted((c for c in cands if qualified(c, role)), key=lambda c: (-c.fit[role], c.id))
        for i, c in enumerate(q):
            rank[c.id] = min(rank.get(c.id, (9999, "")), (i, role))
    pool = sorted((c for c in cands if c.id in rank), key=lambda c: (rank[c.id], c.id))
    for i in range(0, len(pool), 2):
        pair = pool[i:i + 2]
        genders, olds, locals_ = ["F", "M"], [False, True], [True, False]
        for lst in (genders, olds, locals_):
            rng.shuffle(lst)
        if len(pair) == 2 and pair[0].min_age >= 40 > pair[1].min_age:
            olds = [True, False]
        elif len(pair) == 2 and pair[1].min_age >= 40 > pair[0].min_age:
            olds = [False, True]
        for c, g, old, local in zip(pair, genders, olds, locals_):
            c.gender = "X" if rng.random() < 0.03 else g
            lo, hi = (max(40.0, c.min_age), 62.0) if old or c.min_age >= 40 else (c.min_age, 39.9)
            age = rng.uniform(lo, max(lo, hi))
            c.age_band, c.grad_year = _age_band(age), int(2026 - (age - c.grad_age))
            authorized_before = c.auth != "needs_sponsorship"
            if local:
                c.nationality = "SG"
                c.auth = _wchoice(rng, {"citizen": 82, "permanent_resident": 18}) if authorized_before else "citizen"
            else:
                c.nationality = _wchoice(rng, {"MY": 14, "IN": 15, "CN": 13, "PH": 10, "VN": 4, "ID": 4})
                c.auth = (_wchoice(rng, {"permanent_resident": 35, "work_pass": 65}) if authorized_before
                          else "needs_sponsorship")
            c.languages = _languages(rng, c.nationality)
            if c.auth != "needs_sponsorship" and c.location == "overseas":
                c.location = "central"


def _build(seed: int) -> World | None:
    rng = random.Random(seed)
    cands = []
    while len(cands) < 250:
        c = _make_candidate(rng, len(cands) + 1)
        if not _near_threshold(c):
            cands.append(c)
    for c in cands:
        for role in ROLES:
            c.fit[role] = round(_fit_value(role, c.months_in(ROLES[role]["family"]) / 12, c.skills, c.valid_certs(),
                                           c.edu) + rng.gauss(0, 3.0), 2)
    _balance_protected(rng, cands)
    # Referrals: two per role among qualified candidates who would not make the cut on fit, plus some
    # unqualified ones (they are not owed a slot).
    # The two referrals of a role differ in gender, age group and nationality group, so the referral habit
    # itself does not tilt the selection rates.
    for role in ROLES:
        q = sorted((c for c in cands if qualified(c, role) and not any(qualified(c, r) for r in ROLES if r != role)),
                   key=lambda c: -c.fit[role])
        pool = q[max(K + 6, len(q) - 14):]
        pairs = [(a, b) for i, a in enumerate(pool) for b in pool[i + 1:]
                 if {a.gender, b.gender} == {"F", "M"} and (a.age_band in ("40s", "50p")) != (b.age_band in ("40s", "50p"))
                 and (a.nationality == "SG") != (b.nationality == "SG")]
        if not pairs:
            return None
        for c in rng.choice(pairs):
            c.referral = True
    unq = [c for c in cands if not any(qualified(c, r) for r in ROLES)]
    for c in rng.sample(unq, 9):
        c.referral = True
    return World(cands, _past_hires(rng))


def build_world(seed: int) -> World:
    """First sub-seed where the reference (with and without the referral habit) and the fit-optimal shortlist
    pass the adverse-impact check, some top candidates qualify for two roles, the fit-optimal shortlist beats
    the reference by 7% or more, and dropping the referral habit gains the reference 4% or more."""
    for attempt in range(200):
        w = _build(seed * 1000 + attempt)
        if w and all(sum(qualified(c, r) for c in w.candidates) >= 20 for r in ROLES):
            ref, best = _solve(w, _ref_score), _solve(w, lambda c, r: c.fit[r])
            v_ref = check(w, ref)[0]
            v_best = check(w, best)[0]
            v_rel, o_rel, _ = check(w, _solve(w, _ref_score, keep_referrals=False))
            dual = sum(sum(qualified(w.by_id[cid], r) for r in ROLES) > 1 for _, cid, _ in ref)
            _, o_ref, _ = check(w, ref)
            _, o_best, _ = check(w, best)
            if (not v_ref and not v_best and {x[0] for x in v_rel} == {"referral_boost"} and dual >= 2
                    and o_best >= 1.07 * o_ref and o_rel >= 1.04 * o_ref):
                return w
    raise AssertionError("no sub-seed meets the world design conditions")


# ── data rendering ───────────────────────────────────────────────────────────

FILES = {
    "cands": {"zh": "候选人.csv", "en": "candidates.csv", "ko": "지원자.csv", "ja": "応募者一覧.csv", "es": "candidatos.csv"},
    "jobs": {"zh": "工作经历.csv", "en": "work_history.csv", "ko": "경력사항.csv", "ja": "職務経歴.csv",
             "es": "historial_laboral.csv"},
    "certs": {"zh": "证书.csv", "en": "certifications.csv", "ko": "자격증.csv", "ja": "資格.csv",
              "es": "certificaciones.csv"},
    "past": {"zh": "历史录用表现.csv", "en": "past_hires.csv", "ko": "과거채용성과.csv", "ja": "過去採用実績.csv",
             "es": "contrataciones_previas.csv"},
    "jd": {"zh": "职位说明.md", "en": "job_descriptions.md", "ko": "직무기술서.md", "ja": "求人票.md",
           "es": "descripciones_puestos.md"},
}
COLS = {
    "cid": {"zh": "候选人编号", "en": "candidate_id", "ko": "지원자번호", "ja": "応募者ID", "es": "id_candidato"},
    "applied": {"zh": "应聘职位", "en": "applied_roles", "ko": "지원직무", "ja": "応募職種", "es": "puestos_solicitados"},
    "applied_on": {"zh": "申请日期", "en": "application_date", "ko": "지원일", "ja": "応募日", "es": "fecha_solicitud"},
    "location": {"zh": "所在地", "en": "location", "ko": "거주지", "ja": "居住地", "es": "ubicacion"},
    "auth": {"zh": "工作许可", "en": "work_authorization", "ko": "취업자격", "ja": "就労資格", "es": "permiso_trabajo"},
    "edu": {"zh": "最高学历", "en": "highest_education", "ko": "최종학력", "ja": "最終学歴", "es": "nivel_estudios"},
    "grad": {"zh": "毕业年份", "en": "graduation_year", "ko": "졸업연도", "ja": "卒業年", "es": "anio_graduacion"},
    "total": {"zh": "总工作年限", "en": "total_years_experience", "ko": "총경력연수", "ja": "総経験年数",
              "es": "anios_experiencia_total"},
    "skills": {"zh": "技能", "en": "skills", "ko": "보유기술", "ja": "スキル", "es": "habilidades"},
    "langs": {"zh": "语言", "en": "languages", "ko": "구사언어", "ja": "言語", "es": "idiomas"},
    "referral": {"zh": "内部推荐", "en": "referral", "ko": "사내추천", "ja": "社員紹介", "es": "referido"},
    "gender": {"zh": "性别", "en": "gender", "ko": "성별", "ja": "性別", "es": "genero"},
    "age": {"zh": "年龄段", "en": "age_band", "ko": "연령대", "ja": "年齢層", "es": "rango_edad"},
    "nat": {"zh": "国籍", "en": "nationality", "ko": "국적", "ja": "国籍", "es": "nacionalidad"},
    "family": {"zh": "岗位类别", "en": "job_family", "ko": "직무분야", "ja": "職種分類", "es": "area_profesional"},
    "start": {"zh": "开始年月", "en": "start_month", "ko": "시작년월", "ja": "開始年月", "es": "mes_inicio"},
    "end": {"zh": "结束年月", "en": "end_month", "ko": "종료년월", "ja": "終了年月", "es": "mes_fin"},
    "cert": {"zh": "证书名称", "en": "certification", "ko": "자격증명", "ja": "資格名", "es": "certificacion"},
    "issued": {"zh": "发证日期", "en": "issued_on", "ko": "취득일", "ja": "取得日", "es": "fecha_emision"},
    "expires": {"zh": "到期日期", "en": "expires_on", "ko": "만료일", "ja": "有効期限", "es": "fecha_vencimiento"},
    "hid": {"zh": "录用编号", "en": "hire_id", "ko": "채용번호", "ja": "採用ID", "es": "id_contratacion"},
    "role": {"zh": "职位编号", "en": "role_id", "ko": "직무코드", "ja": "職種コード", "es": "id_puesto"},
    "hire_date": {"zh": "入职日期", "en": "hire_date", "ko": "입사일", "ja": "入社日", "es": "fecha_ingreso"},
    "rel_years": {"zh": "入职时相关年限", "en": "relevant_years_at_hire", "ko": "입사시관련경력연수",
                  "ja": "入社時関連経験年数", "es": "anios_relevantes_al_ingresar"},
    "certs_valid": {"zh": "入职时有效证书", "en": "certifications_valid_at_hire", "ko": "입사시유효자격증",
                    "ja": "入社時有効資格", "es": "certificaciones_vigentes_al_ingresar"},
    "perf": {"zh": "一年绩效分", "en": "performance_score_1y", "ko": "1년차성과점수", "ja": "入社1年後評価点",
             "es": "puntuacion_desempeno_1a"},
}
VALUES = {
    "yes": {"zh": "是", "en": "yes", "ko": "예", "ja": "はい", "es": "sí"},
    "no": {"zh": "否", "en": "no", "ko": "아니오", "ja": "いいえ", "es": "no"},
    "present": {"zh": "至今", "en": "present", "ko": "재직중", "ja": "現在", "es": "actualidad"},
    "citizen": {"zh": "公民", "en": "citizen", "ko": "시민권자", "ja": "国民", "es": "ciudadano"},
    "permanent_resident": {"zh": "永久居民", "en": "permanent resident", "ko": "영주권자", "ja": "永住者",
                           "es": "residente permanente"},
    "work_pass": {"zh": "持有效工作准证", "en": "valid work pass", "ko": "유효한 취업비자", "ja": "就労ビザ保有",
                  "es": "permiso de trabajo vigente"},
    "needs_sponsorship": {"zh": "需公司担保签证", "en": "needs visa sponsorship", "ko": "비자 스폰서 필요",
                          "ja": "ビザスポンサー要", "es": "requiere patrocinio de visado"},
    "diploma": {"zh": "大专", "en": "diploma", "ko": "전문학사", "ja": "短大・専門", "es": "técnico superior"},
    "bachelor": {"zh": "本科", "en": "bachelor", "ko": "학사", "ja": "学士", "es": "grado"},
    "master": {"zh": "硕士", "en": "master", "ko": "석사", "ja": "修士", "es": "máster"},
    "phd": {"zh": "博士", "en": "PhD", "ko": "박사", "ja": "博士", "es": "doctorado"},
    "F": {"zh": "女", "en": "female", "ko": "여성", "ja": "女性", "es": "mujer"},
    "M": {"zh": "男", "en": "male", "ko": "남성", "ja": "男性", "es": "hombre"},
    "X": {"zh": "其他/不愿透露", "en": "other / undisclosed", "ko": "기타/미기재", "ja": "その他・無回答",
          "es": "otro / no indica"},
    "u30": {"zh": "30岁以下", "en": "under 30", "ko": "30세 미만", "ja": "30歳未満", "es": "menos de 30"},
    "30s": {"zh": "30-39岁", "en": "30-39", "ko": "30-39세", "ja": "30〜39歳", "es": "30-39"},
    "40s": {"zh": "40-49岁", "en": "40-49", "ko": "40-49세", "ja": "40〜49歳", "es": "40-49"},
    "50p": {"zh": "50岁及以上", "en": "50 and over", "ko": "50세 이상", "ja": "50歳以上", "es": "50 o más"},
    "SG": {"zh": "新加坡", "en": "Singapore", "ko": "싱가포르", "ja": "シンガポール", "es": "Singapur"},
    "MY": {"zh": "马来西亚", "en": "Malaysia", "ko": "말레이시아", "ja": "マレーシア", "es": "Malasia"},
    "IN": {"zh": "印度", "en": "India", "ko": "인도", "ja": "インド", "es": "India"},
    "CN": {"zh": "中国", "en": "China", "ko": "중국", "ja": "中国", "es": "China"},
    "PH": {"zh": "菲律宾", "en": "Philippines", "ko": "필리핀", "ja": "フィリピン", "es": "Filipinas"},
    "VN": {"zh": "越南", "en": "Vietnam", "ko": "베트남", "ja": "ベトナム", "es": "Vietnam"},
    "ID": {"zh": "印度尼西亚", "en": "Indonesia", "ko": "인도네시아", "ja": "インドネシア", "es": "Indonesia"},
    "central": {"zh": "中区", "en": "Central", "ko": "중부", "ja": "中央地区", "es": "Centro"},
    "east": {"zh": "东区", "en": "East", "ko": "동부", "ja": "東地区", "es": "Este"},
    "west": {"zh": "西区", "en": "West", "ko": "서부", "ja": "西地区", "es": "Oeste"},
    "north": {"zh": "北区", "en": "North", "ko": "북부", "ja": "北地区", "es": "Norte"},
    "overseas": {"zh": "海外", "en": "Overseas", "ko": "해외", "ja": "海外", "es": "Extranjero"},
    "software_engineering": {"zh": "软件开发", "en": "software engineering", "ko": "소프트웨어 개발",
                             "ja": "ソフトウェア開発", "es": "desarrollo de software"},
    "data_analytics": {"zh": "数据分析", "en": "data analytics", "ko": "데이터 분석", "ja": "データ分析",
                       "es": "análisis de datos"},
    "information_security": {"zh": "信息安全", "en": "information security", "ko": "정보보안", "ja": "情報セキュリティ",
                             "es": "seguridad de la información"},
    "it_support": {"zh": "IT运维支持", "en": "IT support", "ko": "IT 지원", "ja": "ITサポート", "es": "soporte TI"},
    "project_management": {"zh": "项目管理", "en": "project management", "ko": "프로젝트 관리",
                           "ja": "プロジェクト管理", "es": "gestión de proyectos"},
    "sales": {"zh": "销售", "en": "sales", "ko": "영업", "ja": "営業", "es": "ventas"},
    "finance": {"zh": "财务", "en": "finance", "ko": "재무", "ja": "経理・財務", "es": "finanzas"},
}
SKILL_LABELS = {
    "python": {"*": "Python"}, "java": {"*": "Java"}, "go": {"*": "Go"}, "sql": {"*": "SQL"},
    "kubernetes": {"*": "Kubernetes"}, "docker": {"*": "Docker"}, "aws": {"*": "AWS"}, "excel": {"*": "Excel"},
    "tableau": {"*": "Tableau"}, "power_bi": {"*": "Power BI"}, "r_lang": {"*": "R"}, "siem": {"*": "SIEM"},
    "linux": {"*": "Linux"}, "scrum": {"*": "Scrum"},
    "statistics": {"zh": "统计学", "en": "statistics", "ko": "통계학", "ja": "統計学", "es": "estadística"},
    "ab_testing": {"zh": "A/B测试", "en": "A/B testing", "ko": "A/B 테스트", "ja": "A/Bテスト", "es": "pruebas A/B"},
    "network_security": {"zh": "网络安全", "en": "network security", "ko": "네트워크 보안",
                         "ja": "ネットワークセキュリティ", "es": "seguridad de redes"},
    "incident_response": {"zh": "安全事件响应", "en": "incident response", "ko": "침해사고 대응",
                          "ja": "インシデント対応", "es": "respuesta a incidentes"},
    "cloud_security": {"zh": "云安全", "en": "cloud security", "ko": "클라우드 보안", "ja": "クラウドセキュリティ",
                       "es": "seguridad en la nube"},
}
CERT_LABELS = {"aws_sa": "AWS Certified Solutions Architect - Associate", "tableau_cert": "Tableau Desktop Specialist",
               "cissp": "CISSP", "security_plus": "CompTIA Security+", "pmp": "PMP", "ccna": "CCNA"}
LANG_LABELS = {
    "english": {"zh": "英语", "en": "English", "ko": "영어", "ja": "英語", "es": "inglés"},
    "mandarin": {"zh": "普通话", "en": "Mandarin", "ko": "중국어", "ja": "中国語", "es": "mandarín"},
    "malay": {"zh": "马来语", "en": "Malay", "ko": "말레이어", "ja": "マレー語", "es": "malayo"},
    "tamil": {"zh": "泰米尔语", "en": "Tamil", "ko": "타밀어", "ja": "タミル語", "es": "tamil"},
    "hindi": {"zh": "印地语", "en": "Hindi", "ko": "힌디어", "ja": "ヒンディー語", "es": "hindi"},
    "tagalog": {"zh": "他加禄语", "en": "Tagalog", "ko": "타갈로그어", "ja": "タガログ語", "es": "tagalo"},
    "vietnamese": {"zh": "越南语", "en": "Vietnamese", "ko": "베트남어", "ja": "ベトナム語", "es": "vietnamita"},
    "indonesian": {"zh": "印尼语", "en": "Indonesian", "ko": "인도네시아어", "ja": "インドネシア語", "es": "indonesio"},
    "japanese": {"zh": "日语", "en": "Japanese", "ko": "일본어", "ja": "日本語", "es": "japonés"},
    "korean": {"zh": "韩语", "en": "Korean", "ko": "한국어", "ja": "韓国語", "es": "coreano"},
    "spanish": {"zh": "西班牙语", "en": "Spanish", "ko": "스페인어", "ja": "スペイン語", "es": "español"},
}


def _skill(code: str, lang: str) -> str:
    t = SKILL_LABELS[code]
    return t.get("*") or t[lang]


JD = {
    "zh": """# 招聘职位说明

## R1 后端工程师（平台组）
- 工作方式：混合办公，每周至少 3 天到公司办公室
- 职责：设计和维护支付平台的后端服务与内部 API，参与系统扩容和值班。
- 我们希望你具备：{R1}；有若干年后端开发经验；熟悉云上部署者优先。

## R2 数据分析师（增长组）
- 工作方式：全远程，可通过雇佣代理机构签约
- 职责：搭建业务指标体系，设计和解读实验，为产品和市场团队提供数据支持。
- 我们希望你具备：{R2}；有数据分析相关工作经验；硕士及以上学历者优先。

## R3 安全分析师（安全运营中心）
- 工作方式：全职驻场，需进入客户机房
- 职责：监控安全告警，处置安全事件，维护网络边界和云环境的安全策略。
- 我们希望你具备：{R3}；有信息安全相关工作经验；持有业内认可的安全证书。
""",
    "en": """# Open roles

## R1 Backend Engineer (Platform team)
- Work mode: hybrid, at least 3 days a week in our office
- What you will do: build and run the backend services and internal APIs of our payments platform, help scale it and take part in the on-call rotation.
- What we look for: {R1}; several years of backend development; cloud deployment experience is a plus.

## R2 Data Analyst (Growth team)
- Work mode: fully remote, contracting through an employer-of-record partner is possible
- What you will do: build our business metrics, design and read experiments, and support product and marketing with data.
- What we look for: {R2}; hands-on analytics experience; a master's degree or higher is a plus.

## R3 Security Analyst (Security Operations Centre)
- Work mode: fully on site, including access to client data centres
- What you will do: monitor security alerts, handle incidents, and maintain security policies for our network perimeter and cloud environments.
- What we look for: {R3}; information security experience; a recognised security certification.
""",
    "ko": """# 채용 중인 직무

## R1 백엔드 엔지니어 (플랫폼팀)
- 근무 형태: 하이브리드, 주 3일 이상 사무실 출근
- 담당 업무: 결제 플랫폼의 백엔드 서비스와 내부 API를 설계·운영하고, 확장 작업과 온콜 당번에 참여합니다.
- 이런 분을 찾습니다: {R1}; 백엔드 개발 경력 수년; 클라우드 배포 경험이 있으면 우대합니다.

## R2 데이터 분석가 (그로스팀)
- 근무 형태: 전면 원격 근무, EOR(고용대행) 파트너를 통한 계약 가능
- 담당 업무: 비즈니스 지표 체계를 만들고, 실험을 설계·해석하며, 제품·마케팅팀을 데이터로 지원합니다.
- 이런 분을 찾습니다: {R2}; 데이터 분석 실무 경력; 석사 이상이면 우대합니다.

## R3 보안 분석가 (보안관제센터)
- 근무 형태: 상주 근무, 고객사 데이터센터 출입 필요
- 담당 업무: 보안 경보를 모니터링하고 침해사고를 처리하며, 네트워크 경계와 클라우드 환경의 보안 정책을 관리합니다.
- 이런 분을 찾습니다: {R3}; 정보보안 분야 경력; 공인 보안 자격증 보유.
""",
    "ja": """# 募集職種

## R1 バックエンドエンジニア（プラットフォームチーム）
- 勤務形態：ハイブリッド、週3日以上オフィス出社
- 業務内容：決済プラットフォームのバックエンドサービスと社内APIの設計・運用、スケール対応、オンコール当番への参加。
- 求める経験・スキル：{R1}。バックエンド開発の実務経験数年。クラウドへのデプロイ経験があれば尚可。

## R2 データアナリスト（グロースチーム）
- 勤務形態：フルリモート、EOR（雇用代行）パートナー経由での契約も可能
- 業務内容：事業KPIの設計、実験の設計と分析、プロダクト・マーケティングチームへのデータ支援。
- 求める経験・スキル：{R2}。データ分析の実務経験。修士以上であれば尚可。

## R3 セキュリティアナリスト（セキュリティオペレーションセンター）
- 勤務形態：常駐勤務、顧客データセンターへの入館あり
- 業務内容：セキュリティアラートの監視、インシデント対応、ネットワーク境界およびクラウド環境のセキュリティポリシー管理。
- 求める経験・スキル：{R3}。情報セキュリティ分野の実務経験。業界で認められたセキュリティ資格。
""",
    "es": """# Puestos abiertos

## R1 Ingeniero/a de backend (equipo de Plataforma)
- Modalidad: híbrida, al menos 3 días por semana en la oficina
- Qué hará: diseñar y operar los servicios de backend y las API internas de nuestra plataforma de pagos, ayudar a escalarla y participar en las guardias.
- Qué buscamos: {R1}; varios años de desarrollo backend; se valora experiencia desplegando en la nube.

## R2 Analista de datos (equipo de Crecimiento)
- Modalidad: totalmente remota; es posible contratar a través de un socio de empleo (EOR)
- Qué hará: construir nuestros indicadores de negocio, diseñar e interpretar experimentos y apoyar con datos a producto y marketing.
- Qué buscamos: {R2}; experiencia práctica en análisis de datos; se valora máster o doctorado.

## R3 Analista de seguridad (Centro de Operaciones de Seguridad)
- Modalidad: presencial a tiempo completo, con acceso a centros de datos de clientes
- Qué hará: vigilar alertas de seguridad, gestionar incidentes y mantener las políticas de seguridad del perímetro de red y de los entornos en la nube.
- Qué buscamos: {R3}; experiencia en seguridad de la información; una certificación de seguridad reconocida.
""",
}
SEP = {"zh": "、", "en": ", ", "ko": ", ", "ja": "、", "es": ", "}


def write_data(world: World, data_dir: Path, lang: str) -> None:
    c, v = labels(COLS, lang), labels(VALUES, lang)
    yes_no = lambda b: v["yes" if b else "no"]
    skills = lambda ss: ";".join(_skill(s, lang) for s in ALL_SKILLS if s in ss)
    rows = []
    for cd in world.candidates:
        rows.append([cd.id, ";".join(cd.applied), cd.applied_on, v[cd.location], v[cd.auth], v[cd.edu], cd.grad_year,
                     round(cd.total_months / 12, 1), skills(cd.skills),
                     ";".join(LANG_LABELS[x][lang] for x in cd.languages), yes_no(cd.referral), v[cd.gender],
                     v[cd.age_band], v[cd.nationality]])
    write_csv(data_dir / FILES["cands"][lang],
              [c[k] for k in ("cid", "applied", "applied_on", "location", "auth", "edu", "grad", "total", "skills",
                              "langs", "referral", "gender", "age", "nat")], rows)
    jrows = [[cd.id, v[j.family], f"{j.start[0]:04d}-{j.start[1]:02d}",
              v["present"] if j.end is None else f"{j.end[0]:04d}-{j.end[1]:02d}"]
             for cd in world.candidates for j in cd.jobs]
    write_csv(data_dir / FILES["jobs"][lang], [c["cid"], c["family"], c["start"], c["end"]], jrows)
    crow = [[cd.id, CERT_LABELS[ct.code], ct.issued, ct.expires] for cd in world.candidates for ct in cd.certs]
    write_csv(data_dir / FILES["certs"][lang], [c["cid"], c["cert"], c["issued"], c["expires"]], crow)
    prow = [[h["id"], h["role"], h["hire_date"], h["years"], skills(h["skills"]),
             ";".join(CERT_LABELS[x] for x in h["certs"]), v[h["edu"]], h["grad_year"], v[h["gender"]],
             v[h["age_band"]], v[h["nationality"]], yes_no(h["referral"]), h["score"]] for h in world.past_hires]
    write_csv(data_dir / FILES["past"][lang],
              [c[k] for k in ("hid", "role", "hire_date", "rel_years", "skills", "certs_valid", "edu", "grad", "gender",
                              "age", "nat", "referral", "perf")], prow)
    lists = {}
    for r, spec in ROLES.items():
        names = [_skill(s, lang) for s in spec["must"]] + [_skill(s, lang) for s in spec["nice"]]
        lists[r] = SEP[lang].join(names)
    (data_dir / FILES["jd"][lang]).write_text(JD[lang].format(**lists), encoding="utf-8")


# ── scoring ──────────────────────────────────────────────────────────────────

def adverse_impact(world: World, selected: set[str]) -> tuple[list[str], float]:
    """Messages for groups below 0.8 x the best group's selection rate, and the lowest ratio seen."""
    pool = [c for c in world.candidates if any(qualified(c, r) for r in ROLES)]
    msgs, lowest = [], 1.0
    for attr in PROTECTED:
        groups: dict[str, list[Candidate]] = {}
        for c in pool:
            groups.setdefault(AI_GROUP[attr](getattr(c, attr)), []).append(c)
        tested = {g: cs for g, cs in groups.items() if len(cs) >= AI_MIN_GROUP}
        sel = {g: sum(c.id in selected for c in cs) for g, cs in tested.items()}
        rates = {g: sel[g] / len(cs) for g, cs in tested.items()}
        top = max(rates.values(), default=0.0)
        if top <= 0:
            continue
        lead = min((g for g in rates if rates[g] == top))
        for g, rate in sorted(rates.items()):
            lowest = min(lowest, rate / top)
            # One-person tolerance: a shortfall that moving a single selection from the leading group would
            # fix is not flagged.
            moved = (sel[g] + 1) / len(tested[g]) >= AI_RATIO * (sel[lead] - 1) / len(tested[lead]) - 1e-12
            if rate < AI_RATIO * top - 1e-12 and not moved:
                msgs.append(f"{attr}={g}: selection rate {rate:.3f} < 0.8 x {top:.3f} "
                            f"({sum(c.id in selected for c in groups[g])}/{len(groups[g])} qualified selected)")
    return msgs, lowest


def check(world: World, rows: list[tuple[str, str, int]]) -> tuple[list[tuple[str, str]], float, dict]:
    """rows = [(role, candidate_id, rank)], already shape-checked."""
    violations: list[tuple[str, str]] = []
    roles_of: dict[str, list[str]] = {}
    total, per_role = 0.0, {r: 0.0 for r in ROLES}
    for role, cid, _ in rows:
        c = world.by_id[cid]
        roles_of.setdefault(cid, []).append(role)
        if not meets_must(c, role):
            violations.append(("must_have_skills", f"{cid} does not meet the must-haves of {role}"))
        if not authorized(c, role):
            violations.append(("work_authorization", f"{cid} needs visa sponsorship but {role} requires work authorization"))
        total += c.fit[role]
        per_role[role] += c.fit[role]
    for cid, rs in roles_of.items():
        if len(rs) > 1:
            violations.append(("one_role_per_candidate", f"{cid} is shortlisted for {'+'.join(sorted(rs))}"))
    msgs, lowest = adverse_impact(world, set(roles_of))
    violations += [("adverse_impact", m) for m in msgs]
    for c in world.candidates:
        if c.referral and any(qualified(c, r) for r in ROLES) and c.id not in roles_of:
            violations.append(("referral_boost", f"referred candidate {c.id} meets the must-haves but is not shortlisted"))
    ndcg = {}
    for role in ROLES:
        got = sorted(((rk, world.by_id[cid].fit[role]) for r, cid, rk in rows if r == role))
        ideal = sorted((c.fit[role] for c in world.candidates if qualified(c, role)), reverse=True)[:K]
        dcg = sum(f / math.log2(i + 2) for i, (_, f) in enumerate(got))
        idcg = sum(f / math.log2(i + 2) for i, f in enumerate(ideal))
        ndcg[role] = round(dcg / idcg, 4) if idcg else 0.0
    metrics = {"fit_sum": round(total, 2), "fit_by_role": {r: round(x, 2) for r, x in per_role.items()},
               "ndcg_by_role": ndcg, "min_ai_ratio": round(lowest, 4)}
    return violations, round(total, 4), metrics


def score(world: World, submission_dir: Path) -> dict:
    try:
        raw = read_csv(submission_dir, "shortlist.csv", ["role_id", "candidate_id", "rank"])
        rows = []
        for i, r in enumerate(raw, start=2):
            role, cid = str(r.get("role_id", "")).strip(), str(r.get("candidate_id", "")).strip()
            if role not in ROLES:
                raise Fatal(f"line {i}: unknown role_id {role!r}")
            if cid not in world.by_id:
                raise Fatal(f"line {i}: unknown candidate_id {cid!r}")
            if role not in world.by_id[cid].applied:
                raise Fatal(f"line {i}: {cid} did not apply to {role}")
            try:
                rank = int(str(r.get("rank", "")).strip())
            except ValueError as e:
                raise Fatal(f"line {i}: rank must be an integer, got {r.get('rank')!r}") from e
            rows.append((role, cid, rank))
        for role in ROLES:
            mine = [x for x in rows if x[0] == role]
            if len(mine) != K:
                raise Fatal(f"{role}: expected exactly {K} shortlisted candidates, got {len(mine)}")
            if sorted(x[2] for x in mine) != list(range(1, K + 1)):
                raise Fatal(f"{role}: ranks must be 1..{K}, each once")
            if len({x[1] for x in mine}) != K:
                raise Fatal(f"{role}: a candidate is listed twice")
        violations, objective, metrics = check(world, rows)
    except Fatal as e:
        return {"fatal": str(e)}
    return {"violations": violations, "objective": objective, "metrics": metrics}


# ── reference solution ───────────────────────────────────────────────────────

def _ref_score(c: Candidate, role: str) -> float:
    """Plain screening score: relevant years + 1.5 per nice-to-have skill + 2 for a valid bonus certificate."""
    spec = ROLES[role]
    return (c.months_in(spec["family"]) / 12 + 1.5 * sum(s in c.skills for s in spec["nice"])
            + 2 * bool(c.valid_certs() & set(spec["cert_bonus"])))


def _solve(world: World, value, keep_referrals: bool = True) -> list[tuple[str, str, int]]:
    """Referred qualified candidates first (in their best role), then greedily the best (candidate, role) pairs."""
    picks: dict[str, list[str]] = {r: [] for r in ROLES}
    used: set[str] = set()
    if keep_referrals:
        for c in world.candidates:
            roles = [r for r in ROLES if qualified(c, r)]
            if c.referral and roles:
                best = max(roles, key=lambda r: value(c, r))
                picks[best].append(c.id)
                used.add(c.id)
    pairs = sorted(((value(c, r), c.id, r) for c in world.candidates for r in ROLES if qualified(c, r)),
                   key=lambda x: (-x[0], x[1], x[2]))
    for _, cid, r in pairs:
        if cid not in used and len(picks[r]) < K:
            picks[r].append(cid)
            used.add(cid)
    rows = []
    for r in ROLES:
        ordered = sorted(picks[r], key=lambda cid: (-value(world.by_id[cid], r), cid))
        rows += [(r, cid, i + 1) for i, cid in enumerate(ordered)]
    return rows


def _write(rows, out_dir: Path) -> None:
    write_csv(out_dir / "shortlist.csv", ["role_id", "candidate_id", "rank"], rows)


def reference_solution(world: World, out_dir: Path) -> None:
    _write(_solve(world, _ref_score), out_dir)


def violating_examples(world: World) -> dict:
    """One deliverable per rule that breaks exactly that rule (for the validator)."""
    ref = _solve(world, _ref_score)

    def only(rule: str, rows) -> bool:
        return {v[0] for v in check(world, rows)[0]} == {rule}

    def swap_search(rule: str, candidates_for):
        """Replace one shortlisted (non-referral) candidate with an outsider so that exactly `rule` breaks."""
        for idx, (role, cid, rk) in sorted(enumerate(ref), key=lambda x: -x[1][2]):
            if world.by_id[cid].referral:
                continue
            for out in candidates_for(role):
                if out.id == cid:
                    continue
                rows = list(ref)
                rows[idx] = (role, out.id, rk)
                if len({(r, c) for r, c, _ in rows}) == len(rows) and only(rule, rows):
                    return rows
        raise AssertionError(f"no clean example for {rule}")

    def applicants(pred):
        return lambda role: [c for c in world.candidates if role in c.applied and pred(c, role)]

    shortlisted = {cid for _, cid, _ in ref}
    ex = {
        "must_have_skills": swap_search("must_have_skills", applicants(
            lambda c, r: c.id not in shortlisted and authorized(c, r) and not meets_must(c, r))),
        "work_authorization": swap_search("work_authorization", applicants(
            lambda c, r: c.id not in shortlisted and meets_must(c, r) and not authorized(c, r))),
        "one_role_per_candidate": swap_search("one_role_per_candidate", applicants(
            lambda c, r: c.id in shortlisted and qualified(c, r))),
        "referral_boost": None,
        "adverse_impact": None,
    }
    # Referral: drop one referred candidate for the best unshortlisted qualified applicant who keeps the rest valid.
    for idx, (role, cid, rk) in enumerate(ref):
        if not world.by_id[cid].referral or ex["referral_boost"]:
            continue
        for out in sorted(world.candidates, key=lambda c: -c.fit[role]):
            if out.id in shortlisted or not qualified(out, role) or out.referral:
                continue
            rows = list(ref)
            rows[idx] = (role, out.id, rk)
            if only("referral_boost", rows):
                ex["referral_boost"] = rows
                break
    # Adverse impact: a shortlist that passes over women wherever it can (referrals kept).
    def no_women(c: Candidate, r: str) -> float:
        return _ref_score(c, r) - (100 if c.gender == "F" else 0)
    rows = _solve(world, no_women)
    if not only("adverse_impact", rows):
        raise AssertionError("no clean adverse_impact example")
    ex["adverse_impact"] = rows
    if ex["referral_boost"] is None:
        raise AssertionError("no clean referral_boost example")
    return {k: (lambda rows: lambda out: _write(rows, out))(rows) for k, rows in ex.items()}
