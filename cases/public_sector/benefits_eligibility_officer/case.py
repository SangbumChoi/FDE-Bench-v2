"""Household living-support benefit determinations (original FDE-Bench v2 case).

A city's social-services office has a backlog of ~300 applications for a
monthly household living-support benefit. The request only says "decide who
qualifies and how much"; the rules that decide validity and quality (who
counts in the household, the earned-income disregard, the asset test and its
exemptions, the residency period and the date format, this year's uprating,
the disability supplement, the budget cap per household size, the renewal
policy, the scoring) are in the requirements and must be asked for.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from fdebench2.casekit import Fatal, labels, number, read_csv, write_csv

# ── rules of the world ───────────────────────────────────────────────────────

N_HOUSEHOLDS = 300
UPRATING = 0.032                      # this year's table = last year's * 1.032, rounded down to 10
EARNED_FLAT = 150                     # per earner, per month
EARNED_KEEP = 0.70                    # 30% of the remaining earned income is also ignored
DISABILITY_SUPPLEMENT = 120           # per disabled member living at the address
ASSET_BASE, ASSET_PER_EXTRA = 6000, 3000
RESIDENCY_MONTHS = 6
WRONG_DECISION_PENALTY = 400
# last year's (2025) table: household size -> (standard amount, maximum housing allowance)
LAST_YEAR = {1: (640, 380), 2: (1020, 460), 3: (1310, 540), 4: (1580, 610), 5: (1820, 670),
             6: (2040, 720), 7: (2250, 720), 8: (2460, 720), 9: (2670, 720), 10: (2880, 720)}
# this year's budget-law cap on the monthly amount, by household size (6 and more share one cap)
CAP = {1: 1050, 2: 1450, 3: 1800, 4: 2100, 5: 2350, 6: 2550}
REASON_CODES = ("APPROVED", "RENEWAL", "DENY_RESIDENCY", "DENY_ASSETS", "DENY_INCOME")
APPROVE_CODES = ("APPROVED", "RENEWAL")
INCOME_TYPES = ("earned", "pension", "unemployment", "child_support", "other")
ASSET_TYPES = ("savings", "residence", "car", "investments", "other_property")


def this_year(size: int) -> tuple[int, int]:
    std, house = LAST_YEAR[min(size, 10)]
    return (math.floor(std * (1 + UPRATING) / 10) * 10, math.floor(house * (1 + UPRATING) / 10) * 10)


def cap(size: int) -> int:
    return CAP[min(size, 6)]


def asset_limit(size: int) -> int:
    return ASSET_BASE + ASSET_PER_EXTRA * (size - 1)


def months_before(d: dt.date, months: int) -> dt.date:
    y, m = d.year, d.month - months
    while m <= 0:
        y, m = y - 1, m + 12
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31,
            30, 31][m - 1]
    return dt.date(y, m, min(d.day, last))


@dataclass
class Member:
    no: int
    relation: str          # applicant | spouse | child | parent | sibling | other
    age: int
    at_address: bool
    disabled: bool
    income: dict[str, int]


@dataclass
class Household:
    id: str
    renewal: bool
    applied: dt.date
    resident_since: dt.date
    rent: int
    members: list[Member]
    assets: list[tuple[str, int]]
    last_amount: int | None = None
    # truth
    size: int = 0
    eligible: bool = False
    amount: int = 0
    reason: str = ""


@dataclass
class World:
    households: list[Household] = field(default_factory=list)

    def get(self, hid: str) -> Household | None:
        return next((h for h in self.households if h.id == hid), None)


# ── entitlement ──────────────────────────────────────────────────────────────

def countable_assets(h: Household) -> int:
    cars = sorted((v for t, v in h.assets if t == "car"), reverse=True)
    other = sum(v for t, v in h.assets if t not in ("residence", "car"))
    return other + sum(cars[1:])           # primary residence and one car (the most valuable) are exempt


def countable_income(h: Household, per_earner: bool = True) -> float:
    home = [m for m in h.members if m.at_address]
    earned = [m.income["earned"] for m in home if m.income["earned"] > 0]
    if per_earner:
        counted = sum(max(0, e - EARNED_FLAT) * EARNED_KEEP for e in earned)
    else:  # the flat amount applied once per household
        counted = max(0, sum(earned) - EARNED_FLAT) * EARNED_KEEP
    return counted + sum(m.income[k] for m in home for k in INCOME_TYPES if k != "earned")


def assess(h: Household, per_earner: bool = True, uprate: bool = True) -> tuple[bool, int, str]:
    size = sum(m.at_address for m in h.members)
    if h.resident_since > months_before(h.applied, RESIDENCY_MONTHS):
        return False, 0, "DENY_RESIDENCY"
    if countable_assets(h) > asset_limit(size):
        return False, 0, "DENY_ASSETS"
    std, house = this_year(size) if uprate else LAST_YEAR[min(size, 10)]
    disabled = sum(m.disabled for m in h.members if m.at_address)
    need = std + min(h.rent, house) + DISABILITY_SUPPLEMENT * disabled
    amount = min(cap(size), math.floor(need - countable_income(h, per_earner)))
    if amount <= 0:
        return False, 0, "DENY_INCOME"
    return True, amount, "RENEWAL" if h.renewal else "APPROVED"


# ── world ────────────────────────────────────────────────────────────────────

def _member_income(rng: random.Random, relation: str, age: int, has_kids: bool, single: bool) -> dict[str, int]:
    inc = {k: 0 for k in INCOME_TYPES}
    if relation in ("applicant", "spouse", "sibling", "other") or (relation == "child" and age >= 18):
        if age < 66 and rng.random() < (0.5 if relation == "applicant" else 0.42):
            inc["earned"] = rng.randrange(200, 2000, 10)
        elif age < 66 and relation in ("applicant", "spouse") and rng.random() < 0.25:
            inc["unemployment"] = rng.randrange(300, 720, 10)
    if relation in ("applicant", "spouse", "parent") and age >= 65:
        inc["pension"] = rng.randrange(280, 900, 10)
    if relation == "applicant" and has_kids and single and rng.random() < 0.55:
        inc["child_support"] = rng.randrange(100, 420, 10)
    if relation in ("applicant", "spouse") and rng.random() < 0.08:
        inc["other"] = rng.randrange(40, 300, 10)
    return inc


def _make_household(rng: random.Random, idx: int, renewal: bool) -> Household:
    applied = dt.date(2026, 9, 1) + dt.timedelta(days=rng.randrange(0, 50))
    a_age = rng.randint(21, 82)
    married = a_age >= 24 and rng.random() < 0.45
    n_kids = rng.choice([0, 0, 0, 1, 1, 2, 2, 3, 4]) if a_age < 62 else rng.choice([0, 0, 0, 1])
    spec = [("applicant", a_age)]
    if married:
        spec.append(("spouse", max(20, a_age + rng.randint(-6, 6))))
    for _ in range(n_kids):
        spec.append(("child", rng.randint(0, 17) if a_age < 42 else rng.randint(3, 24)))
    if rng.random() < 0.10 and a_age < 60:
        spec.append(("parent", min(95, a_age + rng.randint(22, 34))))
    if rng.random() < 0.05:
        spec.append((rng.choice(["sibling", "other"]), rng.randint(18, 60)))
    members = []
    for no, (rel, age) in enumerate(spec, start=1):
        away = {"applicant": 0.0, "spouse": 0.07, "parent": 0.15, "sibling": 0.2, "other": 0.2}.get(rel)
        if rel == "child":
            away = 0.5 if age >= 18 else 0.03
        at_home = rng.random() >= away
        inc = _member_income(rng, rel, age, n_kids > 0, not married)
        if not at_home and inc["earned"] == 0 and rel != "child" and rng.random() < 0.7:
            inc["earned"] = rng.randrange(400, 1800, 10)   # e.g. working in another city
        if not at_home and rel == "child" and age >= 18 and rng.random() < 0.6:
            inc["earned"] = rng.randrange(300, 1200, 10)
        members.append(Member(no, rel, age, at_home, rng.random() < 0.08, inc))
    owner = rng.random() < 0.15
    rent = 0 if owner else rng.randrange(240, 920, 10)
    assets: list[tuple[str, int]] = []
    if owner:
        assets.append(("residence", rng.randrange(60000, 210000, 1000)))
    savings = int(rng.choice([rng.uniform(0, 3000), rng.uniform(0, 3000), rng.uniform(0, 3000), rng.uniform(1000, 9000),
                              rng.uniform(4000, 20000)]))
    if savings > 0:
        assets.append(("savings", savings))
    if rng.random() < 0.5:
        assets.append(("car", rng.randrange(1500, 14000, 100)))
        if rng.random() < 0.15:
            assets.append(("car", rng.randrange(1000, 7000, 100)))
    if rng.random() < 0.14:
        assets.append(("investments", rng.randrange(800, 15000, 100)))
    if rng.random() < 0.04:
        assets.append(("other_property", rng.randrange(20000, 90000, 1000)))
    roll = rng.random()
    if renewal or roll >= 0.13:
        since = applied - dt.timedelta(days=rng.randint(400 if renewal else 300, 9000))
    elif roll < 0.07:
        since = applied - dt.timedelta(days=rng.randint(20, 160))
    else:  # around the six-month line
        since = months_before(applied, RESIDENCY_MONTHS) + dt.timedelta(days=rng.randint(-8, 8))
    return Household(f"H{idx:03d}", renewal, applied, since, rent, members, assets)


def build_world(seed: int) -> World:
    rng = random.Random(seed)
    world = World()
    for i in range(1, N_HOUSEHOLDS + 1):
        renewal = rng.random() < 0.33
        h = _make_household(rng, i, renewal)
        if renewal:
            size = sum(m.at_address for m in h.members)
            # a renewal household passed the asset test last year and still does
            while countable_assets(h) > asset_limit(size):
                h.assets = [(t, v // 2 if t not in ("residence",) else v) for t, v in h.assets]
            # last year's award: last year's table, with last year's (different) income
            factor = rng.choice([rng.uniform(0.55, 0.95), rng.uniform(0.75, 1.1), rng.uniform(0.9, 1.2)])
            std, house = LAST_YEAR[min(size, 10)]
            disabled = sum(m.disabled for m in h.members if m.at_address)
            need = std + min(h.rent, house) + DISABILITY_SUPPLEMENT * disabled
            last = math.floor(need - factor * countable_income(h))
            h.last_amount = min(cap(size), max(last, rng.randrange(60, 300, 10)))
        h.size = sum(m.at_address for m in h.members)
        h.eligible, h.amount, h.reason = assess(h)
        world.households.append(h)
    return world


# ── data rendering ───────────────────────────────────────────────────────────

FILES = {
    "apps": {"zh": "申请清单.csv", "en": "applications.csv", "ko": "신청목록.csv", "ja": "申請一覧.csv",
             "es": "solicitudes.csv"},
    "members": {"zh": "家庭成员.csv", "en": "household_members.csv", "ko": "가구원.csv", "ja": "世帯員.csv",
                "es": "miembros_hogar.csv"},
    "assets": {"zh": "资产申报.csv", "en": "assets.csv", "ko": "재산신고.csv", "ja": "資産申告.csv",
               "es": "patrimonio.csv"},
    "table": {"zh": "2025年度金额表.csv", "en": "amount_table_2025.csv", "ko": "2025년_지급액표.csv",
              "ja": "2025年度支給額表.csv", "es": "tabla_importes_2025.csv"},
    "leaflet": {"zh": "居民须知.md", "en": "citizen_leaflet.md", "ko": "시민안내문.md", "ja": "市民向けご案内.md",
                "es": "folleto_ciudadano.md"},
}
COLS = {
    "hid": {"zh": "家庭编号", "en": "household_id", "ko": "가구번호", "ja": "世帯番号", "es": "id_hogar"},
    "type": {"zh": "申请类型", "en": "application_type", "ko": "신청유형", "ja": "申請種別", "es": "tipo_solicitud"},
    "applied": {"zh": "申请日期", "en": "application_date", "ko": "신청일", "ja": "申請日", "es": "fecha_solicitud"},
    "since": {"zh": "本市居住起始日", "en": "resident_since", "ko": "시거주시작일", "ja": "市内居住開始日",
              "es": "residente_desde"},
    "rent": {"zh": "月租金", "en": "monthly_rent", "ko": "월세", "ja": "月額家賃", "es": "alquiler_mensual"},
    "last": {"zh": "上年度月发放额", "en": "last_year_monthly_amount", "ko": "전년도월지급액", "ja": "前年度月額支給額",
             "es": "importe_mensual_ano_anterior"},
    "no": {"zh": "成员序号", "en": "member_no", "ko": "가구원번호", "ja": "世帯員番号", "es": "num_miembro"},
    "rel": {"zh": "与申请人关系", "en": "relationship", "ko": "신청인과의관계", "ja": "続柄", "es": "parentesco"},
    "age": {"zh": "年龄", "en": "age", "ko": "나이", "ja": "年齢", "es": "edad"},
    "home": {"zh": "居住在申请地址", "en": "lives_at_address", "ko": "신청주소거주", "ja": "申請住所に居住",
             "es": "vive_en_domicilio"},
    "dis": {"zh": "残疾", "en": "disability", "ko": "장애", "ja": "障害", "es": "discapacidad"},
    "earned": {"zh": "工资收入", "en": "earned_income", "ko": "근로소득", "ja": "就労収入", "es": "ingresos_trabajo"},
    "pension": {"zh": "养老金", "en": "pension", "ko": "연금", "ja": "年金", "es": "pension"},
    "unemployment": {"zh": "失业金", "en": "unemployment_benefit", "ko": "실업급여", "ja": "失業給付",
                     "es": "prestacion_desempleo"},
    "child_support": {"zh": "子女抚养费", "en": "child_support", "ko": "양육비", "ja": "養育費",
                      "es": "pension_alimenticia"},
    "other": {"zh": "其他收入", "en": "other_income", "ko": "기타소득", "ja": "その他収入", "es": "otros_ingresos"},
    "atype": {"zh": "资产类型", "en": "asset_type", "ko": "재산종류", "ja": "資産種別", "es": "tipo_bien"},
    "value": {"zh": "价值", "en": "value", "ko": "평가액", "ja": "評価額", "es": "valor"},
    "size": {"zh": "家庭人数", "en": "household_size", "ko": "가구원수", "ja": "世帯人数", "es": "tamano_hogar"},
    "std": {"zh": "基本生活金额", "en": "standard_amount", "ko": "기준생계액", "ja": "基準生活額", "es": "importe_base"},
    "house": {"zh": "住房补贴上限", "en": "max_housing_allowance", "ko": "주거비상한", "ja": "住居費上限",
              "es": "max_ayuda_vivienda"},
}
VALUES = {
    "new": {"zh": "新申请", "en": "new", "ko": "신규", "ja": "新規", "es": "nueva"},
    "renewal": {"zh": "续期", "en": "renewal", "ko": "갱신", "ja": "更新", "es": "renovación"},
    "yes": {"zh": "是", "en": "yes", "ko": "예", "ja": "はい", "es": "sí"},
    "no": {"zh": "否", "en": "no", "ko": "아니오", "ja": "いいえ", "es": "no"},
    "applicant": {"zh": "本人", "en": "applicant", "ko": "본인", "ja": "本人", "es": "solicitante"},
    "spouse": {"zh": "配偶", "en": "spouse", "ko": "배우자", "ja": "配偶者", "es": "cónyuge"},
    "child": {"zh": "子女", "en": "child", "ko": "자녀", "ja": "子", "es": "hijo/a"},
    "parent": {"zh": "父母", "en": "parent", "ko": "부모", "ja": "父母", "es": "padre/madre"},
    "sibling": {"zh": "兄弟姐妹", "en": "sibling", "ko": "형제자매", "ja": "兄弟姉妹", "es": "hermano/a"},
    "other": {"zh": "其他", "en": "other", "ko": "기타", "ja": "その他", "es": "otro"},
    "savings": {"zh": "存款", "en": "savings", "ko": "예금", "ja": "預貯金", "es": "ahorros"},
    "residence": {"zh": "自住房产", "en": "home_owned", "ko": "거주주택", "ja": "居住用不動産", "es": "vivienda_habitual"},
    "car": {"zh": "汽车", "en": "car", "ko": "자동차", "ja": "自動車", "es": "coche"},
    "investments": {"zh": "投资理财", "en": "investments", "ko": "투자자산", "ja": "投資資産", "es": "inversiones"},
    "other_property": {"zh": "其他房产", "en": "other_property", "ko": "기타부동산", "ja": "その他不動産",
                       "es": "otros_inmuebles"},
}


def fmt_date(d: dt.date, lang: str) -> str:
    if lang in ("zh", "ja"):
        return f"{d.year}年{d.month}月{d.day}日"
    if lang == "ko":
        return f"{d.year}. {d.month}. {d.day}."
    return f"{d.day:02d}/{d.month:02d}/{d.year}"   # en, es: day/month/year


LEAFLET = {
    "en": """# Household Living Support: what you need to know

Household Living Support helps households in our city whose income is not enough to cover everyday living costs
and housing. It is paid every month.

**Who can apply?** Households that live in the city and have limited income and savings. Please tell us about
everyone in your family, and whether they live with you.

**How is the amount worked out?** We look at what a household of your size needs for everyday living, add an
amount towards your rent (up to a limit), and then take your household's income into account. Not all of your
earnings from work are counted, so working always pays off. Members with a disability may receive extra support.
The amounts for each household size are published every year.

**Savings and property.** Households with substantial savings or property are expected to use them first. Your
home and a car you need are treated fairly.

**Renewals.** If you already receive support, please renew every year so your payments continue.

**Living in the city.** Support is for residents of the city. Newcomers may need to wait a while before they
can receive it.

If you have questions, please visit your local service counter.
""",
    "zh": """# 家庭生活补助 居民须知

家庭生活补助用于帮助本市收入不足以维持日常生活和住房开支的家庭，按月发放。

**谁可以申请？** 居住在本市、收入和存款有限的家庭。请如实申报全部家庭成员，并说明他们是否与您同住。

**补助金额怎么算？** 我们会参考与您家庭人数相当的日常生活所需，再加上一部分房租补贴（有上限），然后扣除家庭收入。
工资收入不会全部计入，所以工作总是划算的。家中有残疾成员的，可能获得额外补助。各家庭人数对应的金额每年公布一次。

**存款和财产。** 拥有较多存款或财产的家庭，应先使用自有资产。自住房和必要的汽车会被合理对待。

**续期。** 已经在领取补助的家庭，请每年办理续期，以免中断发放。

**在本市居住。** 补助面向本市居民。新迁入的居民可能需要等待一段时间才能申请。

如有疑问，请到就近的服务窗口咨询。
""",
    "ko": """# 가구 생활지원금 안내

가구 생활지원금은 소득만으로는 생활비와 주거비를 감당하기 어려운 우리 시 가구를 돕기 위한 제도이며, 매월 지급됩니다.

**누가 신청할 수 있나요?** 우리 시에 살면서 소득과 재산이 적은 가구입니다. 가족 모두를 빠짐없이 적어 주시고, 함께
살고 있는지도 알려 주세요.

**지급액은 어떻게 정해지나요?** 가구 규모에 맞는 기본 생활비에 월세 일부(상한 있음)를 더한 뒤, 가구 소득을 고려해
정합니다. 일해서 번 돈은 전부 소득으로 보지 않으므로, 일하는 것이 항상 유리합니다. 장애가 있는 가구원이 있으면 추가
지원을 받을 수 있습니다. 가구원수별 금액은 매년 공고합니다.

**예금과 재산.** 예금이나 재산이 많은 가구는 먼저 그것을 활용하셔야 합니다. 살고 계신 집과 꼭 필요한 자동차는
합리적으로 고려합니다.

**갱신.** 이미 지원을 받고 계신 분은 지급이 끊기지 않도록 매년 갱신 신청을 해 주세요.

**시 거주.** 지원은 우리 시 주민을 위한 것입니다. 새로 이사 오신 분은 일정 기간이 지나야 받을 수 있습니다.

궁금한 점은 가까운 민원 창구로 문의해 주세요.
""",
    "ja": """# 世帯生活支援金のご案内

世帯生活支援金は、収入だけでは日々の生活費や住居費をまかなうことが難しい市内の世帯を支えるための制度で、毎月お支払い
します。

**申請できる方** 市内にお住まいで、収入や貯蓄が少ない世帯の方です。ご家族全員について、同居されているかどうかも含めて
お知らせください。

**支給額の考え方** 世帯の人数に応じた日常生活に必要な額に、家賃の一部（上限あり）を加え、そこから世帯の収入を考慮して
決めます。働いて得た収入はすべてが収入として数えられるわけではありませんので、働くほど手元に残ります。障害のある方が
いる世帯には、加算がある場合があります。世帯人数ごとの金額は毎年公表しています。

**貯蓄や財産について** 多額の貯蓄や財産がある世帯は、まずそれをご活用いただくことになります。お住まいの住宅や必要な
自動車については、適切に配慮します。

**更新について** すでに支援を受けている方は、支給が途切れないよう毎年更新の手続きをお願いします。

**市内居住について** 支援は市民の方が対象です。転入されたばかりの方は、一定期間お待ちいただく場合があります。

ご不明な点は、お近くの窓口までお問い合わせください。
""",
    "es": """# Ayuda de Subsistencia para Hogares: lo que debe saber

La Ayuda de Subsistencia para Hogares apoya a los hogares de nuestra ciudad cuyos ingresos no alcanzan para cubrir
los gastos de la vida diaria y la vivienda. Se paga cada mes.

**¿Quién puede solicitarla?** Los hogares que viven en la ciudad y tienen ingresos y ahorros limitados. Indíquenos
todas las personas de su familia y si viven con usted.

**¿Cómo se calcula el importe?** Partimos de lo que necesita un hogar de su tamaño para la vida diaria, sumamos una
cantidad para el alquiler (con un límite) y después tenemos en cuenta los ingresos del hogar. No todo lo que usted
gana trabajando se cuenta como ingreso, así que trabajar siempre compensa. Las personas con discapacidad pueden
recibir un apoyo adicional. Los importes para cada tamaño de hogar se publican cada año.

**Ahorros y bienes.** Se espera que los hogares con ahorros o bienes importantes los utilicen primero. Su vivienda
y un coche necesario se tratan de forma justa.

**Renovaciones.** Si ya recibe la ayuda, renuévela cada año para que los pagos no se interrumpan.

**Residir en la ciudad.** La ayuda es para los vecinos de la ciudad. Quienes acaban de llegar pueden tener que
esperar un tiempo antes de recibirla.

Si tiene preguntas, acuda a su oficina de atención más cercana.
""",
}


def write_data(world: World, data_dir: Path, lang: str) -> None:
    c, v = labels(COLS, lang), labels(VALUES, lang)
    yn = lambda b: v["yes" if b else "no"]  # noqa: E731
    write_csv(data_dir / FILES["apps"][lang],
              [c["hid"], c["type"], c["applied"], c["since"], c["rent"], c["last"]],
              [[h.id, v["renewal" if h.renewal else "new"], fmt_date(h.applied, lang), fmt_date(h.resident_since, lang),
                h.rent, "" if h.last_amount is None else h.last_amount] for h in world.households])
    write_csv(data_dir / FILES["members"][lang],
              [c["hid"], c["no"], c["rel"], c["age"], c["home"], c["dis"]] + [c[k] for k in INCOME_TYPES],
              [[h.id, m.no, v[m.relation], m.age, yn(m.at_address), yn(m.disabled)] + [m.income[k] for k in INCOME_TYPES]
               for h in world.households for m in h.members])
    write_csv(data_dir / FILES["assets"][lang], [c["hid"], c["atype"], c["value"]],
              [[h.id, v[t], val] for h in world.households for t, val in h.assets])
    write_csv(data_dir / FILES["table"][lang], [c["size"], c["std"], c["house"]],
              [[n, s, hs] for n, (s, hs) in LAST_YEAR.items()])
    (data_dir / FILES["leaflet"][lang]).write_text(LEAFLET[lang], encoding="utf-8")


# ── scoring ──────────────────────────────────────────────────────────────────

TRUE_WORDS = {"yes", "y", "true", "1"}
FALSE_WORDS = {"no", "n", "false", "0"}


def _parse(world: World, submission_dir: Path) -> dict[str, tuple[bool, float, str]]:
    rows = read_csv(submission_dir, "determinations.csv", ["household_id", "eligible", "monthly_amount", "reason_code"])
    out: dict[str, tuple[bool, float, str]] = {}
    for r in rows:
        hid = (r.get("household_id") or "").strip()
        if world.get(hid) is None:
            raise Fatal(f"unknown household_id {hid!r}")
        if hid in out:
            raise Fatal(f"{hid} appears more than once")
        e = (r.get("eligible") or "").strip().lower()
        if e not in TRUE_WORDS | FALSE_WORDS:
            raise Fatal(f"{hid}: eligible must be yes or no, got {r.get('eligible')!r}")
        amt = number((r.get("monthly_amount") or "0").strip() or "0", f"{hid}.monthly_amount")
        if amt < 0:
            raise Fatal(f"{hid}: negative monthly_amount")
        out[hid] = (e in TRUE_WORDS, amt, (r.get("reason_code") or "").strip())
    missing = [h.id for h in world.households if h.id not in out]
    if missing:
        raise Fatal(f"determinations.csv has no row for {len(missing)} households, e.g. {missing[:5]}")
    return out


def score(world: World, submission_dir: Path) -> dict:
    try:
        sub = _parse(world, submission_dir)
    except Fatal as e:
        return {"fatal": str(e)}
    violations: list[tuple[str, str]] = []
    abs_err = 0.0
    wrong = 0
    for h in world.households:
        elig, amt, code = sub[h.id]
        paid = amt if elig else 0.0
        abs_err += abs(paid - (h.amount if h.eligible else 0))
        wrong += elig != h.eligible
        if code not in REASON_CODES:
            violations.append(("reason_code_required", f"{h.id}: reason_code {code!r} is not one of {REASON_CODES}"))
        elif (code in APPROVE_CODES) != elig:
            violations.append(("reason_code_required", f"{h.id}: reason_code {code} does not match eligible"))
        if elig and h.resident_since > months_before(h.applied, RESIDENCY_MONTHS):
            violations.append(("residency_requirement", f"{h.id} approved with less than 6 months of residence"))
        if elig and countable_assets(h) > asset_limit(h.size):
            violations.append(("asset_limit", f"{h.id} approved with countable assets above the limit"))
        if elig and amt > cap(h.size) + 1e-9:
            violations.append(("amount_cap", f"{h.id}: {amt:g} exceeds the cap {cap(h.size)} for size {h.size}"))
        if h.renewal and (not elig or abs(amt - h.last_amount) > 0.5):
            violations.append(("auto_approve_renewals",
                               f"{h.id} is a renewal: must be approved at last year's {h.last_amount}"))
    objective = abs_err + WRONG_DECISION_PENALTY * wrong
    return {"violations": violations, "objective": round(objective, 4),
            "metrics": {"abs_amount_error": round(abs_err, 2), "wrong_decisions": wrong,
                        "households": len(world.households)}}


# ── reference solution ───────────────────────────────────────────────────────

def _decide(world: World, keep_renewal_rule: bool = True) -> list[list]:
    rows = []
    for h in world.households:
        if h.renewal and keep_renewal_rule:
            rows.append([h.id, "yes", h.last_amount, "RENEWAL"])
            continue
        elig, amt, code = assess(h, per_earner=False)   # earned flat amount applied once per household
        rows.append([h.id, "yes" if elig else "no", amt, code])
    return rows


def _write(out_dir: Path, rows: list[list]) -> None:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["household_id", "eligible", "monthly_amount", "reason_code"])
    w.writerows(rows)
    (out_dir / "determinations.csv").write_text(buf.getvalue(), encoding="utf-8")


def reference_solution(world: World, out_dir: Path) -> None:
    _write(out_dir, _decide(world))


def violating_examples(world: World) -> dict:
    """One deliverable per rule that breaks exactly that rule (for the validator)."""
    base = _decide(world)
    idx = {r[0]: i for i, r in enumerate(base)}

    def with_row(hid: str, row: list):
        rows = [list(r) for r in base]
        rows[idx[hid]] = row
        return lambda out: _write(out, rows)

    def would_be_paid(h: Household) -> int:
        size = h.size
        std, house = this_year(size)
        need = std + min(h.rent, house) + DISABILITY_SUPPLEMENT * sum(m.disabled for m in h.members if m.at_address)
        return min(cap(size), math.floor(need - countable_income(h)))

    res = next(h for h in world.households if h.reason == "DENY_RESIDENCY" and not h.renewal
               and countable_assets(h) <= asset_limit(h.size) and would_be_paid(h) > 0)
    ast = next(h for h in world.households if h.reason == "DENY_ASSETS" and not h.renewal and would_be_paid(h) > 0)
    new_ok = next(h for h in world.households if h.eligible and not h.renewal)
    ren = next(h for h in world.households if h.renewal and h.last_amount > 20)
    return {
        "residency_requirement": with_row(res.id, [res.id, "yes", would_be_paid(res), "APPROVED"]),
        "asset_limit": with_row(ast.id, [ast.id, "yes", would_be_paid(ast), "APPROVED"]),
        "amount_cap": with_row(new_ok.id, [new_ok.id, "yes", cap(new_ok.size) + 50, "APPROVED"]),
        "reason_code_required": with_row(new_ok.id, [new_ok.id, "yes", new_ok.amount, "OK"]),
        "auto_approve_renewals": with_row(ren.id, [ren.id, "yes", ren.last_amount - 10, "RENEWAL"]),
    }
