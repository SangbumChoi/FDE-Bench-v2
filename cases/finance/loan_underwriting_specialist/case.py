"""Personal-loan underwriting (original FDE-Bench v2 case).

A lender's credit team wants a decision (approve / decline / refer) and an
approved amount for a batch of pending applications for its one unsecured
personal-loan product, with past funded loans and their outcomes as training
data. All applicants are salaried. The request only says "tell us which to
approve and for how much"; what decides validity and quality is the lender's
credit policy and the rules it must comply with.

The data is the same in every setting: installment loans and credit lines,
income documents, bureau file numbers and duplicate applications are always
there. The tier decides which rules are in force this round:

  easy    the underwriting core: one product PL36 and its limits
          (min .. min(product max, annual income, requested amount)); annual
          gross income = 12 x declared base salary + documented bonus only; one
          bureau is the policy score (the other is reference only); active
          delinquency always declined; DSR after the loan capped, counting
          installment loans only (credit lines are out of scope this round);
          decline reason codes in a fixed order; protected attributes never used
          (planted twins); short job tenure goes to manual review (the bendable
          habit)
  medium  + credit lines in the DSR as a 5-year amortization of the balance
          plus interest; a +1.5 point stress add-on above 60,000 of total debt;
          a share of the approved amount goes to near-prime applicants
  hard    + income verification (the lowest of the declared and documented
          salaries; a document far below the declared salary must be referred)
          and one loan per person (duplicates linked by the bureau file number,
          with a DUPLICATE reason code)

The rule set (A / B / C) sets the parameters: which bureau is the policy bureau
and its cutoff, the near-prime threshold, the DSR cap, the near-prime quota, the
discrepancy threshold and the tenure of the review habit.
"""

from __future__ import annotations

import datetime as dt
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from fdebench2.casekit import Fatal, labels, number, read_csv, write_csv, write_xlsx

# ── the product and the credit policy (known to the client only) ─────────────

PRODUCT = "PL36"
TERM = 36                 # months
APR = 11.9                # % per year
MIN_AMOUNT, MAX_AMOUNT = 1000, 50000
MARGIN = 0.10             # lifetime margin on the approved amount
LGD = 0.60
REFER_COST = 60.0

LINE_YEARS = 5            # credit lines: balance amortized over 5 years for the DSR (medium, hard)
STRESS_THRESHOLD = 60000  # total unsecured debt after the loan above this ... (medium, hard)
STRESS_ADD = 1.5          # ... adds 1.5 points to the new loan's rate in the DSR
CODES = ("DELINQUENCY", "LOW_SCORE", "DSR_EXCEEDED", "DUPLICATE", "CREDIT_RISK")   # DUPLICATE: hard only

N_HISTORY = 3000
N_SINGLES = 375
N_TWINS = 25
N_DUPLICATES = 24         # second applications by applicants already in the batch
TOL = 0.01


def installment(amount: float, apr: float = APR) -> float:
    """Monthly installment of a fully amortizing loan over TERM months."""
    r = apr / 100 / 12
    return amount * r / (1 - (1 + r) ** -TERM)


def installment_per_1000() -> float:
    return round(installment(1000), 2)


@dataclass
class Debt:
    kind: str            # installment | credit_line
    balance: int
    monthly_payment: int = 0     # installment loans
    rate: float = 0.0            # credit lines, % per year
    line_limit: int = 0          # credit lines

    @property
    def annual_service(self) -> float:
        if self.kind == "installment":
            return 12.0 * self.monthly_payment
        return self.balance / LINE_YEARS + self.balance * self.rate / 100


@dataclass
class Doc:
    kind: str            # payslip | employer_letter
    base_salary: int     # monthly base salary shown on the document


@dataclass
class App:
    """One application as it is in the data; the setting's policy reads it through _View."""

    id: str
    date: str
    requested: int
    age_band: str
    gender: str
    nationality: str
    tenure: int                  # months in the current job
    base_salary: int             # monthly, as declared on the application (verified in the history)
    bonus: int                   # annual
    bonus_documented: bool
    stated_income: int           # monthly, self-declared, never used
    score_a: int                 # bureau A, 0-1000 (the true risk follows it)
    score_b: int                 # bureau B, 0-1000 (runs ~50 higher, noisier)
    inquiries: int
    history_months: int
    delinquent: bool
    debts: list[Debt] = field(default_factory=list)
    funded: int = 0              # history only
    defaulted: bool = False      # history only
    twin_of: str = ""
    docs: list[Doc] = field(default_factory=list)   # pending only
    person: str = ""             # bureau file number (one per person)
    dup_of: str = ""             # the application this one duplicates

    @property
    def verified_base(self) -> int:
        """The lowest of the declared and documented monthly base salaries (the real salary)."""
        return min([self.base_salary] + [d.base_salary for d in self.docs])

    @property
    def true_income(self) -> float:
        return 12.0 * self.verified_base + (self.bonus if self.bonus_documented else 0.0)

    def true_dsr(self, amount: float) -> float:
        """The economic debt-service ratio: every debt, the real salary, the product rate."""
        return (sum(d.annual_service for d in self.debts) + 12.0 * installment(amount)) / self.true_income


def true_pd(a: App, amount: float) -> float:
    """Lifetime default probability at this amount (protected attributes play no part)."""
    d = a.true_dsr(amount)
    z = (-2.55 - 0.011 * (a.score_a - 760) + 2.6 * (d - 0.25) + 11.0 * max(0.0, d - 0.32)
         + 0.16 * a.inquiries - 0.30 * math.log(max(a.history_months, 3) / 60)
         + 0.7 * (a.tenure < 12) + 1.4 * max(0.0, (690 - a.score_a) / 100) ** 2
         + 1.3 * max(0.0, (820 - a.score_a) / 100))
    return 1 / (1 + math.exp(-z))


@dataclass
class World:
    history: list[App] = field(default_factory=list)
    pending: list[App] = field(default_factory=list)
    _cache: dict = field(default_factory=dict, repr=False)

    def by_id(self) -> dict[str, App]:
        if "by_id" not in self._cache:
            self._cache["by_id"] = {a.id: a for a in self.pending}
        return self._cache["by_id"]

    def twin_pairs(self) -> list[tuple[str, str]]:
        return [(a.twin_of, a.id) for a in self.pending if a.twin_of]

    def same_person(self) -> dict[str, list[str]]:
        """Application id -> the other pending applications of the same person."""
        if "persons" not in self._cache:
            groups: dict[str, list[str]] = {}
            for a in self.pending:
                groups.setdefault(a.person, []).append(a.id)
            self._cache["persons"] = {x: [y for y in g if y != x] for g in groups.values() if len(g) > 1 for x in g}
        return self._cache["persons"]


class _View:
    """The world as one setting's policy sees it: which tier's rules apply and the rule set's parameters."""

    def __init__(self, world: World, setting):
        self._w, self.setting = world, setting
        self.medium, self.hard = setting.at_least("medium"), setting.at_least("hard")
        self.bureau = str(setting["policy_bureau"])
        self.min_score = int(setting["min_score"])
        self.near_prime_below = int(setting["near_prime_below"])
        self.max_dsr = float(setting["max_dsr_pct"]) / 100
        self.quota = float(setting["quota_pct"]) / 100
        self.discrepancy = float(setting["discrepancy_pct"]) / 100
        self.min_tenure = int(setting["min_tenure"])
        self._cache = world._cache.setdefault(("setting", setting.label), {})

    def __getattr__(self, name):
        return getattr(self._w, name)

    # ── the policy's reading of an application ──────────────────────────────
    def score(self, a: App) -> int:
        return a.score_a if self.bureau == "A" else a.score_b

    def base(self, a: App) -> int:
        """Hard: the verified salary; easy and medium use the declared one."""
        return a.verified_base if self.hard else a.base_salary

    def income(self, a: App) -> float:
        return 12.0 * self.base(a) + (a.bonus if a.bonus_documented else 0.0)

    def debts(self, a: App) -> list[Debt]:
        """Easy counts installment loans only; medium and hard add credit lines."""
        return a.debts if self.medium else [d for d in a.debts if d.kind == "installment"]

    def stressed(self, a: App, amount: float) -> bool:
        return self.medium and sum(d.balance for d in a.debts) + amount > STRESS_THRESHOLD

    def dsr(self, a: App, amount: float) -> float:
        apr = APR + (STRESS_ADD if self.stressed(a, amount) else 0.0)
        return (sum(d.annual_service for d in self.debts(a)) + 12.0 * installment(amount, apr)) / self.income(a)

    def cap(self, a: App) -> float:
        """Product / income / request cap on the limit (before the DSR)."""
        return min(MAX_AMOUNT, self.income(a), a.requested)

    def max_limit(self, a: App) -> int:
        """Largest whole amount within the caps and the DSR (may be below the product minimum)."""
        key = ("max_limit", a.id)
        if key not in self._cache:
            lo, hi = 0, int(math.floor(self.cap(a) + 1e-9))
            if self.dsr(a, hi) > self.max_dsr:
                while hi - lo > 1:       # dsr() only increases with the amount (the stress add-on jumps up)
                    mid = (lo + hi) // 2
                    lo, hi = (mid, hi) if self.dsr(a, mid) <= self.max_dsr else (lo, mid)
                hi = lo
            self._cache[key] = hi
        return self._cache[key]

    def near_prime(self, a: App) -> bool:
        return self.score(a) < self.near_prime_below

    def short_tenure(self, a: App) -> bool:
        return a.tenure < self.min_tenure

    def discrepant(self, a: App) -> bool:
        """Hard: a document shows a salary more than the threshold below the declared one (must be referred)."""
        return self.hard and a.base_salary - a.verified_base > self.discrepancy * a.base_salary + 1e-9

    def main_driver(self, a: App, other_approved: bool = False) -> str:
        """The decline reason code that must be used if this application is declined
        (other_approved: hard, another application of the same person is approved in the batch)."""
        if a.delinquent:
            return "DELINQUENCY"
        if self.score(a) < self.min_score:
            return "LOW_SCORE"
        if self.max_limit(a) < MIN_AMOUNT:
            return "DSR_EXCEEDED"
        if other_approved and self.hard:
            return "DUPLICATE"
        return "CREDIT_RISK"


AGE_BANDS = ("18-25", "26-35", "36-50", "51-65", "66+")


def _poisson(rng: random.Random, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, rng.random()
    while p > limit:
        k += 1
        p *= rng.random()
    return k


def _applicant(rng: random.Random, aid: str, date: str) -> tuple[App, int]:
    """The applicant with their installment loans, and how many credit lines they hold."""
    age = rng.choices(AGE_BANDS, weights=(14, 30, 32, 18, 6))[0]
    ai = AGE_BANDS.index(age)
    gender = rng.choice(("female", "male"))
    foreign = rng.random() < 0.18
    history = max(3, int(rng.uniform(0.15, 1.0) * (60, 170, 300, 420, 480)[ai] * (0.55 if foreign else 1.0)))
    tenure = max(1, int(rng.expovariate(1 / (8 + 28 * ai))))
    base = int(round(min(18000, max(1500, 3800 * math.exp(rng.gauss(0, 0.42)))), -1))
    has_bonus = rng.random() < 0.45
    bonus = int(round(base * rng.uniform(0.5, 3.0), -2)) if has_bonus else 0
    documented = has_bonus and rng.random() < 0.70
    stated = int(round((base + bonus / 12) * rng.uniform(0.98, 1.15), -1))
    income = 12 * base + (bonus if documented else 0)
    a_score = int(min(990, max(300, rng.gauss(835, 80) + 6 * min(ai, 3))))
    b_score = int(min(1000, max(300, a_score + rng.gauss(55, 30))))
    inquiries = _poisson(rng, 0.7 + max(0.0, (780 - a_score) / 90))
    requested = int(min(MAX_AMOUNT, max(MIN_AMOUNT, round(income * math.exp(rng.gauss(math.log(0.5), 0.6)) / 500)
                                         * 500)))
    delinquent = rng.random() < 0.03 + 0.12 * (a_score < 700)
    debts, lines = [], 0
    for _ in range(rng.choices((0, 1, 2, 3), weights=(25, 35, 25, 15))[0]):
        if rng.random() < 0.55:
            bal = int(round(income * rng.uniform(0.05, 0.6), -1))
            months = rng.choice((12, 24, 36, 48, 60))
            pay = int(round(bal * (0.09 / 12) / (1 - (1 + 0.09 / 12) ** -months)))
            debts.append(Debt("installment", bal, monthly_payment=max(pay, 10)))
        else:
            lines += 1
    return App(aid, date, requested, age, gender, "foreign" if foreign else "domestic", tenure, base, bonus,
               documented, stated, a_score, b_score, inquiries, history, delinquent, debts), lines


def _add_lines(rng: random.Random, a: App, n: int) -> None:
    """The applicant's credit lines (drawn from their own stream)."""
    for _ in range(n):
        lim = int(round(a.true_income * rng.uniform(0.1, 0.5), -2))
        bal = int(round(lim * rng.uniform(0.0, 1.0), -1))
        a.debts.append(Debt("credit_line", bal, rate=rng.choice((6.9, 8.4, 9.9, 12.5)), line_limit=lim))


def _add_docs(rng: random.Random, a: App) -> None:
    """A payslip for everyone, an employer letter for about two in three. Most agree with the
    application; some show a lower salary, a few far lower (the applicant overstated it)."""
    kinds = ["payslip"] + (["employer_letter"] if rng.random() < 0.65 else [])
    u = rng.random()
    gap = 0.0 if u < 0.70 else rng.uniform(0.02, 0.15) if u < 0.86 else rng.uniform(0.15, 0.25) if u < 0.93 \
        else rng.uniform(0.25, 0.45)
    low = rng.randrange(len(kinds))
    for k, kind in enumerate(kinds):
        if k == low:
            f = 1 - gap
        elif gap:
            f = 1 - rng.uniform(0.0, gap)
        else:
            f = 1.05 if rng.random() < 0.15 else 1.0      # an employer letter that rounds the salary up
        a.docs.append(Doc(kind, int(round(a.base_salary * f, -1))))


def _copy(a: App) -> App:
    return App(**{**a.__dict__, "debts": [Debt(**d.__dict__) for d in a.debts],
                  "docs": [Doc(**d.__dict__) for d in a.docs]})


def build_world(seed: int) -> World:
    """Everything every setting needs (the data is the same in all of them)."""
    w = World()
    rc_h, rc_p = random.Random(seed * 10 + 1), random.Random(seed * 10 + 2)
    rl_h, rl_p = random.Random(seed * 10 + 3), random.Random(seed * 10 + 4)
    rh = random.Random(seed * 10 + 5)

    # History: loans funded at the requested amount under the older, looser policy (verified salaries).
    while len(w.history) < N_HISTORY:
        date = (dt.date(2023, 7, 1) + dt.timedelta(days=rc_h.randrange(730))).isoformat()
        a, lines = _applicant(rc_h, "", date)
        u = rc_h.random()
        _add_lines(rl_h, a, lines)
        if a.delinquent or a.score_a < 560 or a.true_dsr(a.requested) > 0.55:
            continue
        a.funded = a.requested
        a.defaulted = u < true_pd(a, a.requested)
        w.history.append(a)
    w.history.sort(key=lambda a: a.date)
    for k, a in enumerate(w.history, start=1):
        a.id = f"H{k:05d}"

    # Pending batch: singles plus planted twins that differ only in protected attributes.
    base = []
    for _ in range(N_SINGLES):
        a, lines = _applicant(rc_p, "", f"2026-10-{rc_p.randint(12, 23)}")
        base.append((a, lines))
    for a, lines in base:
        _add_lines(rl_p, a, lines)
        _add_docs(rh, a)
    base = [a for a, _ in base]
    twins = []
    for a in rc_p.sample(base, N_TWINS):
        b = _copy(a)
        b.age_band = rc_p.choice([x for x in AGE_BANDS if x != a.age_band])
        b.gender = "male" if a.gender == "female" else "female"
        b.nationality = "domestic" if a.nationality == "foreign" else "foreign"
        twins.append((a, b))
    allapps = base + [b for _, b in twins]
    rc_p.shuffle(allapps)
    numbers = sorted(rc_p.sample(range(1, 10000), len(allapps)))
    for k, a in zip(numbers, allapps):
        a.id = f"P{k:04d}"
    for a, b in twins:
        b.twin_of = a.id

    # Duplicates: a second application by someone already in the batch, a few days later and for another
    # amount; some of them declare a higher salary than the first time (their documents are the same).
    in_twins = {x.id for pair in twins for x in pair}
    used = set(numbers)
    free = [k for k in range(1, 10000) if k not in used]
    for a in rh.sample(sorted((x for x in base if x.id not in in_twins), key=lambda x: x.id), N_DUPLICATES):
        b = _copy(a)
        b.id = f"P{free.pop(rh.randrange(len(free))):04d}"
        b.dup_of = a.id
        b.date = f"2026-10-{min(23, int(a.date[-2:]) + rh.randint(0, 5))}"
        while b.requested == a.requested:
            b.requested = int(min(MAX_AMOUNT, max(MIN_AMOUNT, round(a.requested * rh.uniform(0.5, 1.8) / 500)
                                                  * 500)))
        if rh.random() < 0.5:
            f = rh.uniform(1.12, 1.40)
            b.base_salary = int(round(a.base_salary * f, -1))
            b.stated_income = int(round(a.stated_income * f, -1))
        allapps.append(b)
    people = rh.sample(range(1000000, 9999999), len(w.history) + len(allapps))
    for a, num in zip(w.history + allapps, people):
        a.person = f"BF{num}"
    orig = {a.id: a for a in allapps}
    for a in allapps:
        if a.dup_of:
            a.person = orig[a.dup_of].person
    w.pending = sorted(allapps, key=lambda a: a.id)
    return w


# ── data rendering ───────────────────────────────────────────────────────────

FILES = {
    "history": {"zh": "历史贷款申请.csv", "en": "past_applications.csv", "ko": "과거_대출신청.csv",
                "ja": "過去の申込実績.csv", "es": "solicitudes_historicas.csv"},
    "pending": {"zh": "待审批申请.csv", "en": "pending_applications.csv", "ko": "심사대기_신청.csv",
                "ja": "審査待ち申込.csv", "es": "solicitudes_pendientes.csv"},
    "bureau": {"zh": "征信数据.csv", "en": "credit_bureau.csv", "ko": "신용평가_정보.csv",
               "ja": "信用情報.csv", "es": "buro_credito.csv"},
    "debts": {"zh": "现有负债.csv", "en": "existing_debts.csv", "ko": "기존_부채.csv",
              "ja": "既存債務.csv", "es": "deudas_existentes.csv"},
    "product": {"zh": "产品说明表.xlsx", "en": "product_sheet.xlsx", "ko": "상품안내표.xlsx",
                "ja": "商品概要表.xlsx", "es": "ficha_producto.xlsx"},
    "docs": {"zh": "收入证明材料.csv", "en": "income_documents.csv", "ko": "소득증빙_서류.csv",
             "ja": "収入証明書類.csv", "es": "justificantes_ingresos.csv"},
}
SHEET = {"zh": "个人贷款", "en": "personal_loan", "ko": "개인대출", "ja": "個人ローン", "es": "prestamo_personal"}
COLS = {
    "id": {"zh": "申请编号", "en": "application_id", "ko": "신청번호", "ja": "申込番号", "es": "id_solicitud"},
    "date": {"zh": "申请日期", "en": "application_date", "ko": "신청일", "ja": "申込日", "es": "fecha_solicitud"},
    "requested": {"zh": "申请金额", "en": "requested_amount", "ko": "신청금액", "ja": "申込金額",
                  "es": "importe_solicitado"},
    "age": {"zh": "年龄段", "en": "age_band", "ko": "연령대", "ja": "年齢層", "es": "tramo_edad"},
    "gender": {"zh": "性别", "en": "gender", "ko": "성별", "ja": "性別", "es": "genero"},
    "nationality": {"zh": "国籍", "en": "nationality", "ko": "국적", "ja": "国籍", "es": "nacionalidad"},
    "tenure": {"zh": "现职月数", "en": "months_in_job", "ko": "현직장_근속월수", "ja": "現職勤続月数",
               "es": "meses_en_empleo"},
    "base": {"zh": "月基本工资", "en": "monthly_base_salary", "ko": "월_기본급", "ja": "月額基本給",
             "es": "salario_base_mensual"},
    "bonus": {"zh": "年度奖金", "en": "annual_bonus", "ko": "연간_상여금", "ja": "年間賞与", "es": "bonus_anual"},
    "bonus_doc": {"zh": "奖金有证明", "en": "bonus_documented", "ko": "상여금_증빙", "ja": "賞与証明あり",
                  "es": "bonus_justificado"},
    "stated": {"zh": "申报月收入", "en": "stated_monthly_income", "ko": "신고_월소득", "ja": "申告月収",
               "es": "ingreso_mensual_declarado"},
    "funded": {"zh": "放款金额", "en": "funded_amount", "ko": "실행금액", "ja": "実行金額",
               "es": "importe_concedido"},
    "defaulted": {"zh": "是否违约", "en": "defaulted", "ko": "부도여부", "ja": "デフォルト", "es": "impago"},
    "person": {"zh": "征信档案号", "en": "bureau_file_number", "ko": "신용정보_고유번호", "ja": "信用情報登録番号",
               "es": "numero_expediente_buro"},
    "score_a": {"zh": "A评分机构分数", "en": "bureau_a_score", "ko": "A평가사_점수", "ja": "A社スコア",
                "es": "puntuacion_buro_a"},
    "score_b": {"zh": "B评分机构分数", "en": "bureau_b_score", "ko": "B평가사_점수", "ja": "B社スコア",
                "es": "puntuacion_buro_b"},
    "inquiries": {"zh": "近6个月查询次数", "en": "inquiries_6m", "ko": "최근6개월_조회건수",
                  "ja": "直近6か月照会件数", "es": "consultas_6m"},
    "hist": {"zh": "信用记录月数", "en": "credit_history_months", "ko": "신용거래_개월수", "ja": "信用履歴月数",
             "es": "meses_historial_credito"},
    "delinquent": {"zh": "当前逾期", "en": "active_delinquency", "ko": "현재_연체", "ja": "延滞中",
                   "es": "morosidad_activa"},
    "debt_id": {"zh": "负债编号", "en": "debt_id", "ko": "부채번호", "ja": "債務番号", "es": "id_deuda"},
    "debt_type": {"zh": "负债类型", "en": "debt_type", "ko": "부채유형", "ja": "債務種別", "es": "tipo_deuda"},
    "balance": {"zh": "未偿余额", "en": "outstanding_balance", "ko": "잔액", "ja": "残高", "es": "saldo_pendiente"},
    "payment": {"zh": "月还款额", "en": "monthly_payment", "ko": "월상환액", "ja": "月返済額", "es": "cuota_mensual"},
    "line_rate": {"zh": "年利率_%", "en": "annual_rate_pct", "ko": "연이율_%", "ja": "年利_%", "es": "tipo_anual_pct"},
    "line_limit": {"zh": "授信额度", "en": "credit_limit", "ko": "약정한도", "ja": "極度額", "es": "limite_credito"},
    "doc_id": {"zh": "材料编号", "en": "document_id", "ko": "서류번호", "ja": "書類番号", "es": "id_justificante"},
    "doc_type": {"zh": "材料类型", "en": "document_type", "ko": "서류유형", "ja": "書類種別",
                 "es": "tipo_justificante"},
    "doc_base": {"zh": "材料所示月基本工资", "en": "monthly_base_salary_shown", "ko": "서류상_월_기본급",
                 "ja": "書類記載の月額基本給", "es": "salario_base_mensual_justificado"},
    "p_code": {"zh": "产品代码", "en": "product_code", "ko": "상품코드", "ja": "商品コード", "es": "codigo_producto"},
    "p_name": {"zh": "产品名称", "en": "product_name", "ko": "상품명", "ja": "商品名", "es": "nombre_producto"},
    "term": {"zh": "期限_月", "en": "term_months", "ko": "기간_개월", "ja": "期間_月", "es": "plazo_meses"},
    "rate": {"zh": "年利率_%", "en": "annual_rate_pct", "ko": "연이율_%", "ja": "年利_%", "es": "tipo_anual_pct"},
    "inst": {"zh": "每借1000月供", "en": "installment_per_1000", "ko": "대출1000당_월상환액",
             "ja": "借入1000あたり月返済額", "es": "cuota_por_1000"},
    "min_amt": {"zh": "最低金额", "en": "min_amount", "ko": "최소금액", "ja": "最低金額", "es": "importe_minimo"},
    "max_amt": {"zh": "最高金额", "en": "max_amount", "ko": "최대금액", "ja": "最高金額", "es": "importe_maximo"},
}
VALUES = {
    "yes": {"zh": "是", "en": "yes", "ko": "예", "ja": "はい", "es": "sí"},
    "no": {"zh": "否", "en": "no", "ko": "아니오", "ja": "いいえ", "es": "no"},
    "female": {"zh": "女", "en": "female", "ko": "여성", "ja": "女性", "es": "mujer"},
    "male": {"zh": "男", "en": "male", "ko": "남성", "ja": "男性", "es": "hombre"},
    "domestic": {"zh": "本国", "en": "domestic", "ko": "내국인", "ja": "国内", "es": "nacional"},
    "foreign": {"zh": "外籍", "en": "foreign", "ko": "외국인", "ja": "外国籍", "es": "extranjera"},
    "66+": {"zh": "66岁及以上", "en": "66+", "ko": "66세 이상", "ja": "66歳以上", "es": "66 o más"},
    "installment": {"zh": "分期贷款", "en": "installment loan", "ko": "분할상환대출", "ja": "分割返済ローン",
                    "es": "préstamo a plazos"},
    "credit_line": {"zh": "循环授信", "en": "credit line", "ko": "마이너스통장", "ja": "カードローン枠",
                    "es": "línea de crédito"},
    "payslip": {"zh": "工资单", "en": "payslip", "ko": "급여명세서", "ja": "給与明細", "es": "nómina"},
    "employer_letter": {"zh": "单位收入证明", "en": "employer letter", "ko": "재직·소득확인서",
                        "ja": "勤務先の収入証明", "es": "certificado de empresa"},
}
PRODUCT_NAME = {"zh": "安心贷 36期", "en": "Steady Loan 36", "ko": "스테디론 36", "ja": "ステディローン36",
                "es": "Préstamo Estable 36"}


def _app_cells(a: App, v: dict[str, str]) -> list:
    return [a.id, a.date, a.requested, v.get(a.age_band, a.age_band), v[a.gender], v[a.nationality], a.tenure,
            a.base_salary, a.bonus, (v["yes"] if a.bonus_documented else v["no"]) if a.bonus else "",
            a.stated_income]


def write_data(world: World, data_dir: Path, lang: str) -> None:
    c, v = labels(COLS, lang), labels(VALUES, lang)
    head = [c[k] for k in ("id", "date", "requested", "age", "gender", "nationality", "tenure", "base", "bonus",
                           "bonus_doc", "stated")]
    write_csv(data_dir / FILES["history"][lang], head + [c["funded"], c["defaulted"]],
              [_app_cells(a, v) + [a.funded, v["yes" if a.defaulted else "no"]] for a in world.history])
    write_csv(data_dir / FILES["pending"][lang], head, [_app_cells(a, v) for a in world.pending])
    everyone = sorted(world.history + world.pending, key=lambda a: a.id)
    write_csv(data_dir / FILES["bureau"][lang],
              [c[k] for k in ("id", "person", "score_a", "score_b", "inquiries", "hist", "delinquent")],
              [[a.id, a.person, a.score_a, a.score_b, a.inquiries, a.history_months, v["yes" if a.delinquent else "no"]]
               for a in everyone])
    rows = []
    for a in everyone:
        for k, d in enumerate(a.debts, start=1):
            line = d.kind == "credit_line"
            rows.append([a.id, f"{a.id}-D{k}", v[d.kind], d.balance, "" if line else d.monthly_payment,
                         d.rate if line else "", d.line_limit if line else ""])
    write_csv(data_dir / FILES["debts"][lang],
              [c[k] for k in ("id", "debt_id", "debt_type", "balance", "payment", "line_rate", "line_limit")], rows)
    write_csv(data_dir / FILES["docs"][lang], [c[k] for k in ("id", "doc_id", "doc_type", "doc_base")],
              [[a.id, f"{a.id}-S{k}", v[d.kind], d.base_salary]
               for a in world.pending for k, d in enumerate(a.docs, start=1)])
    write_xlsx(data_dir / FILES["product"][lang],
               {SHEET[lang]: ([c[k] for k in ("p_code", "p_name", "term", "rate", "inst", "min_amt", "max_amt")],
                              [[PRODUCT, PRODUCT_NAME[lang], TERM, APR, installment_per_1000(), MIN_AMOUNT,
                                MAX_AMOUNT]])})


# ── scoring ──────────────────────────────────────────────────────────────────

COLUMNS = ("application_id", "decision", "limit", "reason_code")
DECISIONS = ("approve", "decline", "refer")


def _others_approved(world: _View, dec: dict[str, tuple[str, float, str]]) -> set[str]:
    """Hard: applications whose person has another application approved in `dec`."""
    if not world.hard:
        return set()
    same = world.same_person()
    return {x for x in dec if any(dec.get(y, ("",))[0] == "approve" for y in same.get(x, ()))}


def evaluate_decisions(world: _View, dec: dict[str, tuple[str, float, str]], problems: list[str]):
    apps = world.by_id()
    problems = list(problems)
    missing = [a for a in apps if a not in dec]
    if missing:
        problems.append(f"{len(missing)} pending applications have no row, e.g. {missing[0]}")
    violations: list[tuple[str, str]] = []
    if problems:
        violations.append(("decision_complete", f"{len(problems)} problems, e.g. {problems[0]}"))
    keys = ["delinquency_decline", "score_cutoff", "dsr_cap", "limit_cap", "reason_code_required", "tenure_review",
            "no_protected_attributes"]
    if world.hard:
        keys += ["income_discrepancy_refer", "one_loan_per_applicant"]
    found: dict[str, list[str]] = {k: [] for k in keys}
    others = _others_approved(world, dec)
    profit = loss = approved = near = 0.0
    n = {d: 0 for d in DECISIONS}
    for aid, (d, lim, code) in dec.items():
        a = apps[aid]
        n[d] += 1
        if a.delinquent and d != "decline":
            found["delinquency_decline"].append(aid)
        if world.short_tenure(a) and not a.delinquent and d != "refer":
            found["tenure_review"].append(aid)
        if world.discrepant(a) and not a.delinquent and d != "refer":
            found["income_discrepancy_refer"].append(f"{aid} declared {a.base_salary}, documents {a.verified_base}")
        if d == "decline" and code != world.main_driver(a, aid in others):
            found["reason_code_required"].append(f"{aid} has {code or 'no code'!r}, main driver "
                                                 f"{world.main_driver(a, aid in others)}")
        if d == "refer":
            profit -= REFER_COST
        if d != "approve":
            continue
        if aid in others and all(aid < y for y in world.same_person()[aid] if dec.get(y, ("",))[0] == "approve"):
            found["one_loan_per_applicant"].append(f"{aid} and {', '.join(world.same_person()[aid])} "
                                                   f"(bureau file {a.person})")
        if world.score(a) < world.min_score:
            found["score_cutoff"].append(f"{aid} Bureau {world.bureau} {world.score(a)}")
        if lim < MIN_AMOUNT - TOL or lim > world.cap(a) + TOL:
            found["limit_cap"].append(f"{aid} limit {lim:g} outside [{MIN_AMOUNT}, {world.cap(a):.0f}]")
        if world.dsr(a, lim) > world.max_dsr + 1e-9:
            found["dsr_cap"].append(f"{aid} DSR {world.dsr(a, lim):.3f}")
        pd = true_pd(a, lim)
        profit += lim * MARGIN - LGD * pd * lim
        loss += LGD * pd * lim
        approved += lim
        near += lim if world.near_prime(a) else 0.0
    for x, y in world.twin_pairs():
        if x in dec and y in dec and (dec[x][0], round(dec[x][1], 2)) != (dec[y][0], round(dec[y][1], 2)):
            found["no_protected_attributes"].append(f"{x}/{y}")
    for rule, items in found.items():
        if items:
            violations.append((rule, f"{len(items)} applications, e.g. {items[0]}"))
    share = near / approved if approved else 0.0
    if world.medium and share < world.quota - 1e-9:
        violations.append(("near_prime_quota", f"near-prime share of the approved amount is {share:.3f} "
                                               f"< {world.quota:g}"))
    metrics = {"expected_profit": round(profit, 2), "expected_loss": round(loss, 2), "approved_amount": round(approved, 2),
               "near_prime_share": round(share, 4), "approved": n["approve"], "declined": n["decline"],
               "referred": n["refer"]}
    return violations, profit, metrics


def score(world: World, submission_dir: Path, setting) -> dict:
    world = _View(world, setting)
    try:
        rows = read_csv(submission_dir, "decisions.csv", COLUMNS)
        if not rows:
            raise Fatal("decisions.csv has no rows")
        apps = world.by_id()
        dec: dict[str, tuple[str, float, str]] = {}
        problems: list[str] = []
        for n, r in enumerate(rows, start=2):
            aid = str(r.get("application_id") or "").strip()
            if aid not in apps:
                raise Fatal(f"decisions.csv line {n}: unknown application_id {aid!r}")
            d = str(r.get("decision") or "").strip().lower()
            if d not in DECISIONS:
                raise Fatal(f"decisions.csv line {n}: decision {d!r} is not approve, decline or refer")
            lim = number(r.get("limit") or 0, f"decisions.csv line {n} limit")
            code = str(r.get("reason_code") or "").strip().upper()
            if aid in dec:
                problems.append(f"{aid} appears more than once")
            if d != "approve" and abs(lim) > TOL:
                problems.append(f"{aid} is {d} but has limit {lim:g}")
            if d == "approve" and lim <= 0:
                problems.append(f"{aid} is approved with limit {lim:g}")
            dec[aid] = (d, lim if d == "approve" else 0.0, code)
        violations, objective, metrics = evaluate_decisions(world, dec, problems)
    except Fatal as e:
        return {"fatal": str(e)}
    return {"violations": violations, "objective": objective, "metrics": metrics}


# ── reference solution ───────────────────────────────────────────────────────

def _features(a: App, amount: float) -> list[float]:
    """Scorecard features (every debt, the verified salary: the history's salaries are verified)."""
    return [1.0, (a.score_a - 760) / 100, a.true_dsr(amount), float(a.inquiries),
            math.log(max(a.history_months, 3) / 60)]


def _solve_linear(m: list[list[float]], b: list[float]) -> list[float]:
    k = len(b)
    aug = [row[:] + [b[i]] for i, row in enumerate(m)]
    for i in range(k):
        p = max(range(i, k), key=lambda r: abs(aug[r][i]))
        aug[i], aug[p] = aug[p], aug[i]
        for r in range(k):
            if r != i:
                f = aug[r][i] / aug[i][i]
                for j in range(i, k + 1):
                    aug[r][j] -= f * aug[i][j]
    return [aug[i][k] / aug[i][i] for i in range(k)]


def _fit(world: World) -> list[float]:
    """Plain logistic regression (IRLS) on a handful of features, from the history only."""
    if "beta" in world._cache:
        return world._cache["beta"]
    xs = [_features(a, a.funded) for a in world.history]
    ys = [1.0 if a.defaulted else 0.0 for a in world.history]
    k = len(xs[0])
    beta = [0.0] * k
    for _ in range(25):
        hess = [[1e-6 * (i == j) for j in range(k)] for i in range(k)]
        grad = [0.0] * k
        for x, y in zip(xs, ys):
            p = 1 / (1 + math.exp(-sum(b * v for b, v in zip(beta, x))))
            wgt = p * (1 - p)
            for i in range(k):
                grad[i] += (y - p) * x[i]
                for j in range(i, k):
                    hess[i][j] += wgt * x[i] * x[j]
        for i in range(k):
            for j in range(i):
                hess[i][j] = hess[j][i]
        step = _solve_linear(hess, grad)
        beta = [b + s for b, s in zip(beta, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    world._cache["beta"] = beta
    return beta


def _fix_codes(world: _View, dec: dict[str, tuple[str, float, str]]) -> None:
    """Give every decline the reason code of its main driver, given the approvals in `dec`."""
    apps = world.by_id()
    others = _others_approved(world, dec)
    for aid, (d, lim, code) in list(dec.items()):
        if d == "decline":
            dec[aid] = ("decline", 0.0, world.main_driver(apps[aid], aid in others))


def _decide(world: _View, tenure_review: bool = True) -> dict[str, tuple[str, float, str]]:
    """Scorecard + policy: approve the largest allowed amount when the predicted PD is below break-even (in hard,
    one application per person, the most profitable), then top up near-prime approvals (best predicted first,
    twins together) until the quota holds."""
    beta = _fit(world._w)
    pred = lambda a, amt: 1 / (1 + math.exp(-sum(b * v for b, v in zip(beta, _features(a, amt)))))  # noqa: E731
    gain = lambda a: world.max_limit(a) * (MARGIN - LGD * pred(a, world.max_limit(a)))  # noqa: E731
    apps = world.by_id()
    same = world.same_person() if world.hard else {}
    out: dict[str, tuple[str, float, str]] = {}
    candidates = []
    for a in world.pending:
        if a.delinquent:
            out[a.id] = ("decline", 0.0, "DELINQUENCY")
        elif world.discrepant(a):
            out[a.id] = ("refer", 0.0, "")
        elif tenure_review and world.short_tenure(a):
            out[a.id] = ("refer", 0.0, "")
        elif world.main_driver(a) != "CREDIT_RISK":
            out[a.id] = ("decline", 0.0, world.main_driver(a))
        elif pred(a, world.max_limit(a)) * LGD < MARGIN:
            out[a.id] = ("approve", float(world.max_limit(a)), "")
        else:
            out[a.id] = ("decline", 0.0, "CREDIT_RISK")
            if world.near_prime(a):
                candidates.append(a)
    for aid in sorted(same):                      # one loan per person: keep the most profitable approval
        group = [x for x in [aid] + same[aid] if out[x][0] == "approve"]
        for x in sorted(group, key=lambda x: (-gain(apps[x]), x))[1:]:
            out[x] = ("decline", 0.0, "")
    if world.medium:
        groups: dict[str, list[App]] = {}
        for a in candidates:
            groups.setdefault(a.twin_of or a.id, []).append(a)
        order = sorted(groups.values(), key=lambda g: (-gain(g[0]), g[0].id))

        def share() -> float:
            tot = sum(l for d, l, _ in out.values() if d == "approve")
            return sum(l for aid, (d, l, _) in out.items() if d == "approve" and world.near_prime(apps[aid])) / tot \
                if tot else 0
        for g in order:                     # planted twins share one group, so they stay identical
            if share() >= world.quota:
                break
            if any(out[y][0] == "approve" for x in g for y in same.get(x.id, ())):
                continue
            for x in g:
                out[x.id] = ("approve", float(world.max_limit(x)), "")
    _fix_codes(world, out)
    return out


def _write(out_dir: Path, dec: dict[str, tuple[str, float, str]]) -> None:
    write_csv(out_dir / "decisions.csv", list(COLUMNS),
              [[aid, d, f"{lim:.0f}" if d == "approve" else 0, code] for aid, (d, lim, code) in sorted(dec.items())])


def reference_solution(world: World, out_dir: Path, setting) -> None:
    _write(out_dir, _decide(_View(world, setting)))


def violating_examples(world: World, setting) -> dict:
    """One deliverable per rule of the setting that breaks exactly that rule (for the validator)."""
    world = _View(world, setting)
    ref = _decide(world)
    apps = world.by_id()
    twins = {x for pair in world.twin_pairs() for x in pair}
    singles = [a for a in world.pending if a.id not in twins and a.id not in world.same_person()]

    def rules_of(dec) -> set:
        return {r for r, _ in evaluate_decisions(world, dec, [])[0]}

    def changed(updates: dict, fix: bool = True) -> dict:
        dec = dict(ref)
        for aid, v in updates.items():
            if v is None:
                dec.pop(aid)
            else:
                dec[aid] = v
        if fix:
            _fix_codes(world, dec)
        return dec

    def find(rule: str, cands) -> dict:
        for dec in cands:
            if rules_of(dec) == {rule}:
                return dec
        raise AssertionError(f"no clean example for {rule} ({setting.label})")

    approve = lambda a, lim: ("approve", float(lim), "")    # noqa: E731
    floor_cap = lambda a: math.floor(world.cap(a) + 1e-9)    # noqa: E731
    ex = {
        "decision_complete": lambda: find("decision_complete", (changed({a.id: None}) for a in singles
                                                                 if ref[a.id][0] != "approve")),
        "delinquency_decline": lambda: find("delinquency_decline", (changed({a.id: ("refer", 0.0, "")})
                                                                     for a in singles if a.delinquent)),
        "score_cutoff": lambda: find("score_cutoff", (
            changed({a.id: approve(a, min(floor_cap(a), world.max_limit(a)))}) for a in singles
            if world.main_driver(a) == "LOW_SCORE" and min(floor_cap(a), world.max_limit(a)) >= MIN_AMOUNT)),
        "dsr_cap": lambda: find("dsr_cap", (changed({a.id: approve(a, floor_cap(a))}) for a in singles
                                            if world.main_driver(a) == "CREDIT_RISK"
                                            and world.max_limit(a) + 1 < world.cap(a))),
        "limit_cap": lambda: find("limit_cap", (changed({a.id: approve(a, floor_cap(a) + 1)}) for a in singles
                                                if world.main_driver(a) == "CREDIT_RISK"
                                                and world.dsr(a, floor_cap(a) + 1) <= world.max_dsr)),
        "reason_code_required": lambda: find("reason_code_required", (
            changed({a.id: ("decline", 0.0, "DSR_EXCEEDED")}, fix=False) for a in singles
            if ref[a.id] == ("decline", 0.0, "CREDIT_RISK"))),
        "tenure_review": lambda: find("tenure_review", (changed({a.id: approve(a, world.max_limit(a))})
                                                        for a in singles if world.short_tenure(a)
                                                        and world.main_driver(a) == "CREDIT_RISK")),
        "no_protected_attributes": lambda: find("no_protected_attributes", (
            changed({y: approve(apps[y], ref[x][1] - 500)}) for x, y in world.twin_pairs()
            if ref[x][0] == "approve" and ref[x][1] >= MIN_AMOUNT + 500)),
    }
    if world.medium:
        ex["near_prime_quota"] = lambda: find("near_prime_quota", [changed({
            aid: ("decline", 0.0, "") for aid, (d, _, _) in ref.items()
            if d == "approve" and world.near_prime(apps[aid])})])
    if world.hard:
        ex["income_discrepancy_refer"] = lambda: find("income_discrepancy_refer", (
            changed({a.id: ("decline", 0.0, "")}) for a in world.pending
            if world.discrepant(a) and not a.delinquent and a.id not in twins))
        ex["one_loan_per_applicant"] = lambda: find("one_loan_per_applicant", (
            changed({aid: approve(apps[aid], world.max_limit(apps[aid]))}) for aid in sorted(world.same_person())
            if ref[aid] == ("decline", 0.0, "DUPLICATE")))

    def make(build):
        def write(out: Path) -> None:
            _write(out, build())
        return write
    return {rule: make(build) for rule, build in ex.items()}
