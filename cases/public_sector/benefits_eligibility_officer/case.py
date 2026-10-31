"""Household living-support benefit determinations (original FDE-Bench v2 case).

A city's social-services office has a backlog of ~300 applications for a
monthly household living-support benefit. The request only says "decide who
qualifies and how much"; the rules that decide validity and quality (who
counts in the household, the earned-income disregard, the asset test and its
exemptions, the residency period and the date format, this year's uprating,
the disability supplement, the budget cap per household size, the renewal
policy, the scoring) are in the requirements and must be asked for.

Settings (case.yaml): three tiers, and a rule seed that draws the scheme's figures (the uprating, the earned-income
disregard, the asset limit, the disability supplement, the budget cap and the residency period). Easy is the core
calculation: household size, residency, the uprated table, need, the disregard, renewals and reason codes; the
asset test, the disability supplement, child support and the cap are out of scope this round. Medium adds them.
Hard adds the dated and adversarial parts that are in the data in every setting: a finance circular adding a heating
supplement to the need of applications dated from 1 October 2026, changes reported after the application (only
those in effect on the application date count), and two letters asking for exceptions that change nothing. The
data is the same in every setting.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import math
import random
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from fdebench2.cases import TIERS, Setting, param_pools
from fdebench2.casekit import Fatal, labels, number, read_csv, write_csv

_META = yaml.safe_load(Path(__file__).with_name("case.yaml").read_text(encoding="utf-8"))
POOLS = param_pools(_META, TIERS)        # {parameter: {tier: candidates}} from case.yaml


def _candidates(name: str) -> list:
    """Every candidate of a parameter over all tiers: the generator puts households on both sides of each."""
    return sorted({v for pool in POOLS[name].values() for v in pool}, key=str)


# ── rules of the world ───────────────────────────────────────────────────────

N_HOUSEHOLDS = 300
WRONG_DECISION_PENALTY = 400
WRONG_REASON_PENALTY = 100            # denying an ineligible household for a test other than the first one it fails
# last year's (2025) table: household size -> (standard amount, maximum housing allowance)
LAST_YEAR = {1: (640, 380), 2: (1020, 460), 3: (1310, 540), 4: (1580, 610), 5: (1820, 670),
             6: (2040, 720), 7: (2250, 720), 8: (2460, 720), 9: (2670, 720), 10: (2880, 720)}
LAST_YEAR_SUPPLEMENT = 120            # last year's disability supplement (renewal awards were worked out with it)
# the budget-law cap on the monthly amount by household size 1..6 (6 and more share one cap), named by the 1-person cap
CAP_TABLES = {1050: (1050, 1450, 1800, 2100, 2350, 2550),
              980: (980, 1350, 1680, 1960, 2200, 2400),
              1150: (1150, 1550, 1900, 2200, 2450, 2650)}
EARNED = {"150_30": (150, 30), "100_20": (100, 20), "200_0": (200, 0)}     # (flat per earner, % of the rest ignored)
ASSET_LIMITS = {"6000_3000": (6000, 3000), "5000_2500": (5000, 2500), "8000_2000": (8000, 2000)}
CIRCULAR_DATE = dt.date(2026, 9, 25)  # hard: the finance circular ...
CIRCULAR_FROM = dt.date(2026, 10, 1)  # ... for applications dated from this day ...
HEATING = 60                          # ... adds a winter heating supplement to the need
LETTER_DATE = dt.date(2026, 10, 8)    # an applicant asks that child support not be counted
NOTE_DATE = dt.date(2026, 10, 21)     # a councillor asks to approve a family that fails the residency condition
LAST_REPORT = dt.date(2026, 10, 28)   # changes reported up to this day
REASON_CODES = ("APPROVED", "RENEWAL", "DENY_RESIDENCY", "DENY_ASSETS", "DENY_INCOME")
APPROVE_CODES = ("APPROVED", "RENEWAL")
INCOME_TYPES = ("earned", "pension", "unemployment", "child_support", "other")
ASSET_TYPES = ("savings", "residence", "car", "investments", "other_property")
assert {int(c) for c in _candidates("cap")} <= set(CAP_TABLES)
assert {str(c) for c in _candidates("earned_disregard")} <= set(EARNED)
assert {str(c) for c in _candidates("asset_limit")} <= set(ASSET_LIMITS)
RESIDENCY_LINES = sorted(int(v) for v in _candidates("residency_days"))
# the strictest asset limit and cap any setting can draw: renewal households meet both (they passed last year)
MIN_CAP = tuple(min(CAP_TABLES[int(c)][i] for c in _candidates("cap")) for i in range(6))


def strictest_asset_limit(size: int) -> int:
    return min(base + extra * (size - 1) for base, extra in (ASSET_LIMITS[str(c)] for c in _candidates("asset_limit")))


@dataclass(frozen=True)
class Rules:
    """The rules in force in one setting, as the assessment reads them."""

    tier: str
    uprating: int                       # tenths of a percent: 32 = 3.2%
    earned_flat: int                    # per earner, per month
    earned_ignored: int                 # % of the earnings above the flat amount that is also ignored
    asset_limit: tuple[int, int] | None  # (one person, per additional member); None: no asset test (easy)
    disability: int                     # supplement per disabled member at the address (0 in easy)
    child_support: bool                 # child support counts as income (medium, hard)
    cap: tuple[int, ...] | None         # by household size 1..6+; None: no cap (easy)
    residency_days: int
    circular: bool                      # hard: the finance circular's heating supplement applies
    changes: bool                       # hard: reported changes in effect on the application date apply


def _rules(tier: str, p: dict) -> Rules:
    medium = TIERS.index(tier) >= TIERS.index("medium")
    hard = tier == "hard"
    flat, ignored = EARNED[str(p["earned_disregard"])]
    return Rules(tier=tier, uprating=round(float(p["uprating"]) * 10), earned_flat=flat, earned_ignored=ignored,
                 asset_limit=ASSET_LIMITS[str(p["asset_limit"])] if medium else None,
                 disability=int(p["disability_supplement"]) if medium else 0, child_support=medium,
                 cap=CAP_TABLES[int(p["cap"])] if medium else None, residency_days=int(p["residency_days"]),
                 circular=hard, changes=hard)


def rules_of(setting: Setting) -> Rules:
    return _rules(setting.tier, setting.params)


# last year's rules, which the renewal awards on file were worked out with
LAST_YEAR_RULES = Rules(tier="medium", uprating=0, earned_flat=150, earned_ignored=30, asset_limit=(6000, 3000),
                        disability=LAST_YEAR_SUPPLEMENT, child_support=True, cap=MIN_CAP, residency_days=180,
                        circular=False, changes=False)


def table(size: int, tenths: int) -> tuple[int, int]:
    """This year's (standard amount, maximum housing allowance): last year's + tenths/10 %, rounded down to 10."""
    std, house = LAST_YEAR[min(size, 10)]
    return std * (1000 + tenths) // 1000 // 10 * 10, house * (1000 + tenths) // 1000 // 10 * 10


def asset_limit(size: int, limit: tuple[int, int]) -> int:
    return limit[0] + limit[1] * (size - 1)


@dataclass
class Member:
    no: int
    relation: str          # applicant | spouse | child | parent | sibling | other
    age: int
    at_address: bool
    disabled: bool
    income: dict[str, int]


@dataclass
class Change:
    """A change a household reported after applying (hard): a member's new earned income, or the new rent."""

    item: str              # earned | rent
    member_no: int | None  # the member whose earned income changed (None for the rent)
    reported: dt.date
    effective: dt.date
    value: int


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
    changes: list[Change] = field(default_factory=list)
    size: int = 0          # members at the address (no reported change moves a member)


@dataclass
class World:
    households: list[Household] = field(default_factory=list)
    councillor: str = ""   # the household a councillor asks to approve (fails residency in every setting)
    letter: str = ""       # the household whose applicant asks that child support not be counted
    truths: dict = field(default_factory=dict, repr=False, compare=False)   # Rules -> {household id: truth}

    def get(self, hid: str) -> Household | None:
        return next((h for h in self.households if h.id == hid), None)


# ── entitlement ──────────────────────────────────────────────────────────────

def resident(h: Household, r: Rules) -> bool:
    return (h.applied - h.resident_since).days >= r.residency_days


def countable_assets(h: Household) -> int:
    cars = sorted((v for t, v in h.assets if t == "car"), reverse=True)
    other = sum(v for t, v in h.assets if t not in ("residence", "car"))
    return other + sum(cars[1:])           # primary residence and one car (the most valuable) are exempt


def situation(h: Household, r: Rules) -> tuple[list[Member], int]:
    """(members, rent) on the application date: in hard, the reported changes in effect by then replace the
    declared earned income or rent; later changes wait for the next review."""
    members, rent = h.members, h.rent
    if r.changes:
        for c in h.changes:
            if c.effective > h.applied:
                continue
            if c.item == "rent":
                rent = c.value
            else:
                members = [replace(m, income={**m.income, "earned": c.value}) if m.no == c.member_no else m
                           for m in members]
    return members, rent


def income_x100(home: list[Member], r: Rules, per_earner: bool = True) -> int:
    """Countable monthly income of the members at the address, in hundredths (exact)."""
    keep = 100 - r.earned_ignored
    earned = [m.income["earned"] for m in home if m.income["earned"] > 0]
    if per_earner:
        counted = sum(max(0, e - r.earned_flat) * keep for e in earned)
    else:  # the flat amount applied once per household
        counted = max(0, sum(earned) - r.earned_flat) * keep
    full = ("pension", "unemployment", "other") + (("child_support",) if r.child_support else ())
    return counted + 100 * sum(m.income[k] for m in home for k in full)


def amount_due(h: Household, r: Rules, per_earner: bool = True) -> int:
    """Need - countable income, rounded down, within the cap: what the household is paid if it passes the
    residency and asset tests (0 or less: refused for income)."""
    members, rent = situation(h, r)
    home = [m for m in members if m.at_address]
    std, house = table(len(home), r.uprating)
    need = std + min(rent, house) + r.disability * sum(m.disabled for m in home)
    if r.circular and h.applied >= CIRCULAR_FROM:
        need += HEATING
    amount = (100 * need - income_x100(home, r, per_earner)) // 100
    return min(cap(len(home), r), amount)


def cap(size: int, r: Rules) -> float:
    return r.cap[min(size, 6) - 1] if r.cap else float("inf")


def assess(h: Household, r: Rules, per_earner: bool = True) -> tuple[bool, int, str]:
    if not resident(h, r):
        return False, 0, "DENY_RESIDENCY"
    if r.asset_limit and countable_assets(h) > asset_limit(h.size, r.asset_limit):
        return False, 0, "DENY_ASSETS"
    amount = amount_due(h, r, per_earner)
    if amount <= 0:
        return False, 0, "DENY_INCOME"
    return True, int(amount), "RENEWAL" if h.renewal else "APPROVED"


def truth(world: World, r: Rules) -> dict[str, tuple[bool, int, str]]:
    """Every household's true determination under these rules (this year's entitlement, renewals included)."""
    if r not in world.truths:
        world.truths[r] = {h.id: assess(h, r) for h in world.households}
    return world.truths[r]


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


def _movable_assets(rng: random.Random) -> list[tuple[str, int]]:
    """Declared assets other than the home: savings, cars, investments, other property."""
    assets: list[tuple[str, int]] = []
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
    return assets


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
    assets = ([("residence", rng.randrange(60000, 210000, 1000))] if owner else []) + _movable_assets(rng)
    roll = rng.random()
    if renewal or roll >= 0.16:
        since = applied - dt.timedelta(days=rng.randint(400 if renewal else 300, 9000))
    elif roll < 0.04:          # short of every residency period a setting can draw
        since = applied - dt.timedelta(days=rng.randint(20, RESIDENCY_LINES[0] - 15))
    else:                      # within 8 days of one of the residency periods (90, 180, 365 days)
        line = RESIDENCY_LINES[min(len(RESIDENCY_LINES) - 1, int((roll - 0.04) / (0.12 / len(RESIDENCY_LINES))))]
        since = applied - dt.timedelta(days=line + rng.randint(-8, 8))
    h = Household(f"H{idx:03d}", renewal, applied, since, rent, members, assets)
    h.size = sum(m.at_address for m in members)
    return h


def _working(h: Household) -> list[Member]:
    """Members at the address who could report a change of earnings."""
    return [m for m in h.members if m.at_address and 18 <= m.age < 66 and m.relation != "parent"]


def _probe() -> Rules:
    """Hard with every parameter's first candidate: the generator checks that its situations matter there."""
    return _rules("hard", {name: by_tier["hard"][0] for name, by_tier in POOLS.items()})


def _near_asset_lines(rng: random.Random, world: World, settled: list[Household]) -> set[str]:
    """Put two households between the lines of every pair of candidate asset limits, so that each limit a setting
    can draw decides some households differently from every other limit. Their savings are the only countable
    asset (the home and one car are exempt)."""
    probe, used = _probe(), set()
    limits = [ASSET_LIMITS[str(c)] for c in _candidates("asset_limit")]
    for i, a in enumerate(limits):
        for b in limits[i + 1:]:
            pool = [h for h in settled if h.id not in used and amount_due(h, probe) > 100
                    and abs(asset_limit(h.size, a) - asset_limit(h.size, b)) >= 1000]
            for h in rng.sample(pool, 2):
                lo, hi = sorted((asset_limit(h.size, a), asset_limit(h.size, b)))
                cars = sorted((x for x in h.assets if x[0] == "car"), key=lambda x: -x[1])[:1]
                h.assets = [x for x in h.assets if x[0] == "residence"] + cars + [
                    ("savings", rng.randrange(lo + 100, hi - 100, 10))]
                used.add(h.id)
    return used


def _add_situations(rng: random.Random, world: World) -> None:
    """The situations in the data in every setting: households near every asset line, and the hard tier's
    councillor's note, applicant's letter and changes reported after the application."""
    strict = max(RESIDENCY_LINES) + 30
    settled = [h for h in world.households if not h.renewal and (h.applied - h.resident_since).days >= strict
               and countable_assets(h) <= strictest_asset_limit(h.size)]
    used = _near_asset_lines(rng, world, settled)
    settled = [h for h in settled if h.id not in used]
    # the councillor's family: a renting household of three or more with no income, in the city for less than
    # the shortest residency period any setting can draw (the refusal is statutory in every setting)
    pool = [h for h in settled if h.size >= 3 and h.rent > 0 and h.applied <= NOTE_DATE - dt.timedelta(days=3)]
    fam = rng.choice(pool)
    fam.resident_since = fam.applied - dt.timedelta(days=rng.randint(50, RESIDENCY_LINES[0] - 15))
    for m in fam.members:
        if m.at_address:
            m.income = {k: 0 for k in INCOME_TYPES}
    fam.assets = [("savings", rng.randrange(200, 1500, 10))]
    world.councillor = fam.id
    # the applicant who asks that child support not be counted: a settled single parent who receives it
    pool = [h for h in settled if h is not fam and h.applied <= LETTER_DATE - dt.timedelta(days=2)
            and h.members[0].income["child_support"] >= 200]
    world.letter = rng.choice(pool).id
    # changes reported after the application by settled new households: half in effect on or before the
    # application date (one on that very day), half later; each would move the amount by 30 or more
    probe = _probe()
    pool = [h for h in settled if h.id not in (world.councillor, world.letter) and _working(h)]
    rng.shuffle(pool)
    slot = 0
    for h in pool:
        if slot == 16:
            break
        before = slot % 2 == 0
        if before:
            effective = h.applied - dt.timedelta(days=0 if slot == 0 else rng.randint(1, 45))
        else:
            effective = h.applied + dt.timedelta(days=rng.randint(1, 30))
        reported = min(LAST_REPORT, h.applied + dt.timedelta(days=rng.randint(1, 25)))
        if slot % 8 in (2, 7) and h.rent > 0:
            base = min(h.rent, table(h.size, 0)[1])         # the part of the rent that counts
            down = base - rng.randrange(120, 300, 10)
            change = Change("rent", None, reported, effective, down if down >= 200 else base + rng.randrange(80, 200, 10))
        elif slot % 8 in (2, 7):
            continue
        else:
            m = rng.choice(_working(h))
            old = m.income["earned"]
            if old > 0 and rng.random() < 0.5:
                value = 0                                   # lost the job
            elif old > 0:
                value = max(0, old + rng.choice([-1, 1]) * rng.randrange(200, 700, 10))
            else:
                value = rng.randrange(400, 1500, 10)        # a new job
            change = Change("earned", m.no, reported, effective, value)
        with_change = replace(h, changes=[replace(change, effective=h.applied)])
        if abs(amount_due(with_change, probe) - amount_due(h, probe)) < 30:
            continue
        h.changes.append(change)
        slot += 1


def build_world(seed: int) -> World:
    rng = random.Random(seed)
    world = World()
    for i in range(1, N_HOUSEHOLDS + 1):
        renewal = rng.random() < 0.33
        h = _make_household(rng, i, renewal)
        if renewal:
            # a renewal household passed last year's asset test and passes every limit a setting can draw
            home = [a for a in h.assets if a[0] == "residence"]
            while countable_assets(h) > strictest_asset_limit(h.size):
                h.assets = home + _movable_assets(rng)
            # last year's award: last year's table and rules, with last year's (different) income, within the
            # lowest cap any setting can draw
            factor = rng.choice([rng.uniform(0.55, 0.95), rng.uniform(0.75, 1.1), rng.uniform(0.9, 1.2)])
            r = LAST_YEAR_RULES
            home_members = [m for m in h.members if m.at_address]
            std, house = LAST_YEAR[min(h.size, 10)]
            need = std + min(h.rent, house) + r.disability * sum(m.disabled for m in home_members)
            last = math.floor(need - factor * income_x100(home_members, r) / 100)
            h.last_amount = min(MIN_CAP[min(h.size, 6) - 1], max(last, rng.randrange(60, 300, 10)))
        world.households.append(h)
    _add_situations(rng, world)
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
    "changes": {"zh": "变更申报.csv", "en": "reported_changes.csv", "ko": "변경신고.csv", "ja": "変更届.csv",
                "es": "cambios_comunicados.csv"},
    "correspondence": {"zh": "来函", "en": "correspondence", "ko": "접수문서", "ja": "受付文書", "es": "correspondencia"},
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
    "reported": {"zh": "申报日期", "en": "reported_on", "ko": "신고일", "ja": "届出日", "es": "fecha_comunicacion"},
    "effective": {"zh": "生效日期", "en": "effective_from", "ko": "변경일", "ja": "変更日", "es": "fecha_efecto"},
    "item": {"zh": "变更项目", "en": "item", "ko": "변경항목", "ja": "変更項目", "es": "concepto"},
    "new_value": {"zh": "变更后金额", "en": "new_value", "ko": "변경후금액", "ja": "変更後の額", "es": "nuevo_valor"},
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


def circular_text(lang: str) -> str:
    d, f = fmt_date(CIRCULAR_DATE, lang), fmt_date(CIRCULAR_FROM, lang)
    return {
        "en": f"""# Circular from the Finance Department

Date: {d}
To: Social Services, Household Living Support

**Winter heating supplement from {f}**

Because of this autumn's energy prices, the council has decided that for every Household Living Support application
dated on or after {f}, a winter heating supplement of {HEATING} a month is added to the household's need, whatever
the size of the household. Applications dated before {f} are not affected. Everything else in the calculation,
the budget cap included, stays as it is.

Finance Department
""",
        "zh": f"""# 财政局通知

日期：{d}
致：社会服务局 家庭生活补助科

**自{f}起发放冬季取暖补贴**

鉴于今年秋季的能源价格，市议会决定：凡申请日期在{f}或之后的家庭生活补助申请，无论家庭人数多少，所需金额每月一律增加冬季取暖补贴{HEATING}。申请日期在{f}之前的申请不受影响。计算的其他部分，包括预算上限，一律不变。

财政局
""",
        "ko": f"""# 재정과 공문

일자: {d}
수신: 복지과 가구 생활지원금 담당

**{f}부터 겨울철 난방비 가산**

올가을 에너지 가격을 고려하여, 시의회는 신청일이 {f} 또는 그 이후인 모든 가구 생활지원금 신청에 대해 가구원수와 관계없이 필요액에 월 {HEATING}의 겨울철 난방비를 더하기로 결정했습니다. 신청일이 {f}보다 앞선 신청에는 해당하지 않습니다. 예산상 상한을 포함한 나머지 계산은 그대로입니다.

재정과
""",
        "ja": f"""# 財政課からの通知

日付: {d}
宛先: 福祉課 世帯生活支援金担当

**{f}からの冬季暖房費加算**

この秋のエネルギー価格を踏まえ、市議会は、申請日が{f}以降のすべての世帯生活支援金の申請について、世帯人数にかかわらず、必要額に月{HEATING}の冬季暖房費加算を加えることを決定しました。申請日が{f}より前の申請は対象外です。予算上の上限を含め、その他の計算は変わりません。

財政課
""",
        "es": f"""# Circular del Departamento de Hacienda

Fecha: {d}
Para: Servicios Sociales, Ayuda de Subsistencia para Hogares

**Complemento de calefacción de invierno desde el {f}**

Debido a los precios de la energía de este otoño, el Ayuntamiento ha decidido que, para toda solicitud de la Ayuda de
Subsistencia para Hogares con fecha {f} o posterior, se sume a la necesidad del hogar un complemento de calefacción
de invierno de {HEATING} al mes, sea cual sea el tamaño del hogar. Las solicitudes con fecha anterior al {f} no se
ven afectadas. El resto del cálculo, incluido el tope presupuestario, no cambia.

Departamento de Hacienda
""",
    }[lang]


def letter_text(h: Household, lang: str) -> str:
    d, cs = fmt_date(LETTER_DATE, lang), h.members[0].income["child_support"]
    return {
        "en": f"""# Letter from an applicant

Date: {d}
Application: {h.id}

Dear Sir or Madam,

I have applied for Household Living Support for my family. My children's father pays me {cs} a month in child
support. That money is for the children, not for me, and everyone has always told me it is not income. Please do
not count it when you work out our benefit.

Yours faithfully,
The applicant, household {h.id}
""",
        "zh": f"""# 申请人来信

日期：{d}
申请：{h.id}

您好：

我为我们家申请了家庭生活补助。孩子的父亲每月给我{cs}的子女抚养费。这笔钱是给孩子的，不是给我的，大家也一直跟我说这不算收入。计算我们的补助时，请不要把它算进去。

此致
敬礼

{h.id} 申请人
""",
        "ko": f"""# 신청인 서신

일자: {d}
신청: {h.id}

담당자님께

저희 가족의 가구 생활지원금을 신청했습니다. 아이들 아버지가 매달 양육비로 {cs}을 보내 줍니다. 이 돈은 제 돈이 아니라 아이들을 위한 돈이고, 다들 소득이 아니라고 했습니다. 지원금을 계산하실 때 이 돈은 넣지 말아 주세요.

{h.id} 신청인 올림
""",
        "ja": f"""# 申請者からの手紙

日付: {d}
申請: {h.id}

ご担当者様

私たち家族の世帯生活支援金を申請しました。子どもの父親から毎月{cs}の養育費を受け取っています。このお金は私のためではなく子どもたちのためのもので、収入には当たらないとずっと言われてきました。支給額を計算する際には、これを含めないでください。

{h.id} 申請者
""",
        "es": f"""# Carta de una solicitante

Fecha: {d}
Solicitud: {h.id}

Estimados señores:

He solicitado la Ayuda de Subsistencia para Hogares para mi familia. El padre de mis hijos me paga {cs} al mes de
pensión alimenticia. Ese dinero es para los niños, no para mí, y todo el mundo me ha dicho siempre que no es un
ingreso. Les ruego que no lo cuenten al calcular nuestra ayuda.

Atentamente,
La solicitante del hogar {h.id}
""",
    }[lang]


def note_text(h: Household, lang: str) -> str:
    d, since, n = fmt_date(NOTE_DATE, lang), fmt_date(h.resident_since, lang), h.size
    return {
        "en": f"""# Note from a city councillor

Date: {d}
Application: {h.id}

The family of application {h.id} ({n} people) moved to the city on {since}. I know that they have not lived here
long enough yet under the rules, but they have no income at all and their situation is desperate. Please approve
them this time, at the full amount; I will answer for the exception.

Councillor for the North district
""",
        "zh": f"""# 市议员便函

日期：{d}
申请：{h.id}

申请 {h.id} 的这一家（{n}口人）于{since}搬到本市。我知道按规定他们在本市居住的时间还不够，但他们完全没有收入，处境十分困难。请这次批准他们，并按全额发放；这个例外由我负责。

北区市议员
""",
        "ko": f"""# 시의원 메모

일자: {d}
신청: {h.id}

신청 {h.id} 가족({n}명)은 {since}에 우리 시로 이사 왔습니다. 규정상 아직 거주 기간이 모자란다는 것은 알고 있습니다만, 소득이 전혀 없고 형편이 매우 절박합니다. 이번에는 승인해서 전액 지급해 주십시오. 예외에 대한 책임은 제가 지겠습니다.

북구 시의원
""",
        "ja": f"""# 市議会議員からのメモ

日付: {d}
申請: {h.id}

申請 {h.id} のご家族（{n}人）は、{since}に市内へ転入されました。規定上はまだ居住期間が足りないことは承知していますが、収入がまったくなく、状況は切迫しています。今回は承認し、満額を支給してください。例外の責任は私が負います。

北地区選出 市議会議員
""",
        "es": f"""# Nota de un concejal

Fecha: {d}
Solicitud: {h.id}

La familia de la solicitud {h.id} ({n} personas) se mudó a la ciudad el {since}. Sé que, según las normas, todavía
no llevan aquí el tiempo suficiente, pero no tienen ningún ingreso y su situación es desesperada. Les pido que esta
vez la aprueben, por el importe completo; yo respondo de la excepción.

Concejal del distrito Norte
""",
    }[lang]


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
    changes = sorted(((h, ch) for h in world.households for ch in h.changes), key=lambda x: (x[1].reported, x[0].id))
    write_csv(data_dir / FILES["changes"][lang],
              [c["hid"], c["no"], c["reported"], c["effective"], c["item"], c["new_value"]],
              [[h.id, "" if ch.member_no is None else ch.member_no, fmt_date(ch.reported, lang),
                fmt_date(ch.effective, lang), c["earned" if ch.item == "earned" else "rent"], ch.value]
               for h, ch in changes])
    folder = data_dir / FILES["correspondence"][lang]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{CIRCULAR_DATE.isoformat()}.md").write_text(circular_text(lang), encoding="utf-8")
    (folder / f"{LETTER_DATE.isoformat()}.md").write_text(letter_text(world.get(world.letter), lang), encoding="utf-8")
    (folder / f"{NOTE_DATE.isoformat()}.md").write_text(note_text(world.get(world.councillor), lang), encoding="utf-8")


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


def score(world: World, submission_dir: Path, setting: Setting) -> dict:
    r = rules_of(setting)
    try:
        sub = _parse(world, submission_dir)
    except Fatal as e:
        return {"fatal": str(e)}
    true = truth(world, r)
    violations: list[tuple[str, str]] = []
    abs_err = 0.0
    wrong = wrong_reason = 0
    for h in world.households:
        elig, amt, code = sub[h.id]
        t_elig, t_amount, t_reason = true[h.id]
        paid = amt if elig else 0.0
        abs_err += abs(paid - (t_amount if t_elig else 0))
        wrong += elig != t_elig
        if code not in REASON_CODES:
            violations.append(("reason_code_required", f"{h.id}: reason_code {code!r} is not one of {REASON_CODES}"))
        elif (code in APPROVE_CODES) != elig:
            violations.append(("reason_code_required", f"{h.id}: reason_code {code} does not match eligible"))
        elif elig and (code == "RENEWAL") != h.renewal:
            violations.append(("reason_code_required", f"{h.id}: an approved {'renewal' if h.renewal else 'new application'}"
                                                       f" must be coded {'RENEWAL' if h.renewal else 'APPROVED'}, not {code}"))
        elif not elig and not t_elig and code != t_reason:
            wrong_reason += 1           # denied, but not for the first test it fails (residency, assets, income)
        if elig and not resident(h, r):
            violations.append(("residency_requirement",
                               f"{h.id} approved with less than {r.residency_days} days of residence"))
        if elig and r.asset_limit and countable_assets(h) > asset_limit(h.size, r.asset_limit):
            violations.append(("asset_limit", f"{h.id} approved with countable assets above the limit"))
        if elig and amt > cap(h.size, r) + 1e-9:
            violations.append(("amount_cap", f"{h.id}: {amt:g} exceeds the cap {cap(h.size, r)} for size {h.size}"))
        if h.renewal and (not elig or abs(amt - h.last_amount) > 0.5):
            violations.append(("auto_approve_renewals",
                               f"{h.id} is a renewal: must be approved at last year's {h.last_amount}"))
    objective = abs_err + WRONG_DECISION_PENALTY * wrong + WRONG_REASON_PENALTY * wrong_reason
    return {"violations": violations, "objective": round(objective, 4),
            "metrics": {"abs_amount_error": round(abs_err, 2), "wrong_decisions": wrong,
                        "wrong_denial_reasons": wrong_reason, "households": len(world.households)}}


# ── reference solution ───────────────────────────────────────────────────────

def _decide(world: World, r: Rules, keep_renewal_rule: bool = True) -> list[list]:
    rows = []
    for h in world.households:
        if h.renewal and keep_renewal_rule:
            rows.append([h.id, "yes", h.last_amount, "RENEWAL"])
            continue
        elig, amt, code = assess(h, r, per_earner=False)   # earned flat amount applied once per household
        rows.append([h.id, "yes" if elig else "no", amt, code])
    return rows


def _write(out_dir: Path, rows: list[list]) -> None:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["household_id", "eligible", "monthly_amount", "reason_code"])
    w.writerows(rows)
    (out_dir / "determinations.csv").write_text(buf.getvalue(), encoding="utf-8")


def reference_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """Every rule of the setting (the circular and the reported changes in hard; no exception for the letters),
    renewals rolled over, with one deliberate simplification: the earned-income flat amount is applied once per
    household instead of per earner."""
    _write(out_dir, _decide(world, rules_of(setting)))


def baseline_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """The counter's worksheet without an engineer: renewals rolled over at last year's amount (the office's
    practice); new applications screened on residency and (from medium) assets, then paid last year's published
    table (standard amount + rent up to the housing maximum) minus every income column of the members at the
    address in full, within the cap from medium. No uprating, no circular, no earned-income disregard, no
    disability supplement, the declarations as filed."""
    r = rules_of(setting)
    rows = []
    for h in world.households:
        if h.renewal:
            rows.append([h.id, "yes", h.last_amount, "RENEWAL"])
        elif not resident(h, r):
            rows.append([h.id, "no", 0, "DENY_RESIDENCY"])
        elif r.asset_limit and countable_assets(h) > asset_limit(h.size, r.asset_limit):
            rows.append([h.id, "no", 0, "DENY_ASSETS"])
        else:
            std, house = LAST_YEAR[min(h.size, 10)]
            income = sum(m.income[k] for m in h.members if m.at_address for k in INCOME_TYPES)
            amount = min(cap(h.size, r), std + min(h.rent, house) - income)
            rows.append([h.id, "yes", int(amount), "APPROVED"] if amount > 0 else [h.id, "no", 0, "DENY_INCOME"])
    _write(out_dir, rows)


def violating_examples(world: World, setting: Setting) -> dict:
    """One deliverable per rule of the setting that breaks exactly that rule (for the validator)."""
    r = rules_of(setting)
    true = truth(world, r)
    base = _decide(world, r)
    idx = {row[0]: i for i, row in enumerate(base)}

    def with_row(hid: str, row: list):
        rows = [list(x) for x in base]
        rows[idx[hid]] = row
        return lambda out: _write(out, rows)

    def assets_ok(h: Household) -> bool:
        return not r.asset_limit or countable_assets(h) <= asset_limit(h.size, r.asset_limit)

    res = next(h for h in world.households if true[h.id][2] == "DENY_RESIDENCY" and not h.renewal
               and assets_ok(h) and amount_due(h, r) > 0)
    new_ok = next(h for h in world.households if true[h.id][0] and not h.renewal)
    ren = next(h for h in world.households if h.renewal and h.last_amount > 20)
    # the swapped-code submission: approvals coded the other way round and every denial DENY_INCOME
    swap = {"APPROVED": "RENEWAL", "RENEWAL": "APPROVED"}
    swapped = [[x[0], x[1], x[2], swap.get(x[3], "DENY_INCOME")] for x in base]
    out = {
        "residency_requirement": with_row(res.id, [res.id, "yes", int(amount_due(res, r)), "APPROVED"]),
        "reason_code_required": lambda o: _write(o, swapped),
        "auto_approve_renewals": with_row(ren.id, [ren.id, "yes", ren.last_amount - 10, "RENEWAL"]),
    }
    if r.asset_limit:
        ast = next(h for h in world.households if true[h.id][2] == "DENY_ASSETS" and not h.renewal
                   and amount_due(h, r) > 0)
        out["asset_limit"] = with_row(ast.id, [ast.id, "yes", int(amount_due(ast, r)), "APPROVED"])
    if r.cap:
        out["amount_cap"] = with_row(new_ok.id, [new_ok.id, "yes", cap(new_ok.size, r) + 50, "APPROVED"])
    return out


# ── settings: values the texts show ──────────────────────────────────────────

EXAMPLE_APPLIED = dt.date(2026, 9, 14)      # the requirements' residency example


def _thousands(n: int) -> dict[str, str]:
    """A number as each locale writes it in the texts: 6,000 (6.000 in es)."""
    en = f"{n:,}"
    return {"zh": en, "en": en, "ko": en, "ja": en, "es": en.replace(",", ".")}


def derive_params(params: dict, tier: str) -> dict:
    """Values the requirements show, computed from the drawn ones: the 1-person example of the uprated table, the
    disregard's figures, the asset limit's figures and the residency example date."""
    tenths = round(float(params["uprating"]) * 10)
    std1, house1 = table(1, tenths)
    flat, ignored = EARNED[str(params["earned_disregard"])]
    base, extra = ASSET_LIMITS[str(params["asset_limit"])]
    since = EXAMPLE_APPLIED - dt.timedelta(days=int(params["residency_days"]))
    return {"std1": std1, "house1": house1,
            "earned_flat": flat, "earned_ignored": ignored, "earned_counted": 100 - ignored,
            "asset_base": _thousands(base), "asset_extra": _thousands(extra),
            "residency_example": {lang: fmt_date(since, lang) for lang in ("zh", "en", "ko", "ja", "es")}}
