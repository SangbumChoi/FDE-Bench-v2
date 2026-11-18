"""Household living-support benefit determinations (original FDE-Bench v2 case).

A city's social-services office has a backlog of ~300 applications for a
monthly household living-support benefit. The request only says "decide who
qualifies and how much"; the rules that decide validity and quality (the
earned-income disregard, the residency period, this year's uprating, the asset
limit, the disability supplement, the budget cap, child support, the renewal
practice and what this round leaves to other desks) are in the requirements
and must be asked for.

Settings (case.yaml): three tiers, and a rule seed that draws the scheme's figures (the uprating, the earned-income
disregard, the asset limit, the disability supplement, the budget cap and the residency period). Easy is the core
calculation: residency, the uprated table, need, the disregard, renewals and reason codes; the asset test, the
disability supplement, child support and the cap are out of scope this round, and so are the reported changes and
the correspondence. Medium adds the asset test, the supplement, child support and the cap. Hard adds the dated and
adversarial parts that are in the data in every setting: a finance circular adding a heating supplement to the need
of applications dated from 1 October 2026, changes reported after the application (only those in effect on the
application date count), and two letters asking for exceptions that change nothing. The data is the same in every
setting.

Scoring (minimize): every household is measured against its true entitlement under this year's rules: |paid - true
amount| + 400 per wrong yes/no + 100 per refusal with the wrong reason. Renewals are rolled over at last year's
amount (the office's practice, a business-policy rule), so what that costs is the same for every answer that keeps
the practice, and only an approved exception can change it: the exception covers the whole renewal queue, and each
re-assessment costs REASSESSMENT_COST. The zero point is the client's own worksheet (baseline_solution), the
reference is the answer key (every rule of the setting applied exactly), and the bound is the renewal practice's own
cost (objective_bound).
"""

from __future__ import annotations

import calendar
import csv
import datetime as dt
import io
import math
import random
from collections import Counter
from dataclasses import dataclass, field, replace
from itertools import combinations, product
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
REASSESSMENT_COST = 200               # a caseworker's half day per renewal household, for the whole renewal queue,
                                      # once an approved exception re-assesses any renewal (equal treatment)
# last year's (2025) table: household size -> (standard amount, maximum housing allowance)
LAST_YEAR = {1: (640, 380), 2: (1020, 460), 3: (1310, 540), 4: (1580, 610), 5: (1820, 670),
             6: (2040, 720), 7: (2250, 720), 8: (2460, 720), 9: (2670, 720), 10: (2880, 720)}
LAST_YEAR_SUPPLEMENT = 120            # last year's disability supplement (renewal awards were worked out with it)
LAST_YEAR_EARNED = (150, 30)          # last year's earned-income disregard: the first 150, and 30% of the rest
# the budget-law cap on the monthly amount by household size 1..6 (6 and more share one cap), named by the 1-person cap
CAP_TABLES = {1050: (1050, 1450, 1800, 2100, 2350, 2550),
              980: (980, 1350, 1680, 1960, 2200, 2400),
              1150: (1150, 1550, 1900, 2200, 2450, 2650)}
LAST_YEAR_CAP = CAP_TABLES[980]       # last year's cap table (the client's worksheet still has it)
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
assert all(d % 30 in (0, 5) for d in RESIDENCY_LINES)      # 90, 180, 365 days: 3, 6, 12 calendar months
# the strictest asset limit and cap any setting can draw: renewal households meet both (they passed last year)
MIN_CAP = tuple(min(CAP_TABLES[int(c)][i] for c in _candidates("cap")) for i in range(6))
# the worksheet's cap (last year's) is never above a cap a setting can draw, so the worksheet keeps the cap rule
assert all(LAST_YEAR_CAP[i] <= CAP_TABLES[int(c)][i] for c in _candidates("cap") for i in range(6))


def strictest_asset_limit(size: int) -> int:
    return min(base + extra * (size - 1) for base, extra in (ASSET_LIMITS[str(c)] for c in _candidates("asset_limit")))


@dataclass(frozen=True)
class Rules:
    """How one assessment reads the scheme: the figures and facts in force in a setting (rules_of), and the switches
    that the client's worksheet, a misreading or the never-asks solver flips. The defaults are the client's reading."""

    tier: str
    uprating: int                       # tenths of a percent: 35 = 3.5% (0: last year's table)
    earned_flat: int                    # per earner, per month
    earned_ignored: int                 # % of the earnings above the flat amount that is also ignored
    asset_limit: tuple[int, int] | None  # (one person, per additional member); None: no asset test (easy)
    disability: int                     # supplement per disabled member at the address (0: none)
    child_support: bool                 # child support counts as income (medium, hard)
    cap: tuple[int, ...] | None         # by household size 1..6+; None: no cap (easy)
    residency_days: int
    circular: bool                      # the finance circular's heating supplement applies (hard)
    changes: str = "none"               # the reported changes that count: none (as filed) | in_effect (those that
                                        # took effect on or before the application date, hard) | all (every one,
                                        # the latest report winning) | rent (only the new rents in effect)
    disregard_on: str = "earner"        # earner (each earner at the address) | applicant (the applicant's own earnings
                                        # only, the other members' in full) | household (once for the household)
    away_earnings: str = "none"         # none | adults (the earnings of members living elsewhere who are not children
                                        # counted too)
    residency_months: bool = False      # the residency period counted in whole calendar months (90 days: 3 months)
    cars_exempt: str = "top"            # top (the most valuable car) | all | none
    letters: str = ""                   # the letters granted: "" none | both | approve (the councillor's family
                                        # approved whatever its residency) | child_support (the letter writer's child
                                        # support not counted)


def _rules(tier: str, p: dict) -> Rules:
    medium = TIERS.index(tier) >= TIERS.index("medium")
    hard = tier == "hard"
    flat, ignored = EARNED[str(p["earned_disregard"])]
    return Rules(tier=tier, uprating=round(float(p["uprating"]) * 10), earned_flat=flat, earned_ignored=ignored,
                 asset_limit=ASSET_LIMITS[str(p["asset_limit"])] if medium else None,
                 disability=int(p["disability_supplement"]) if medium else 0, child_support=medium,
                 cap=CAP_TABLES[int(p["cap"])] if medium else None, residency_days=int(p["residency_days"]),
                 circular=hard, changes="in_effect" if hard else "none")


def rules_of(setting: Setting) -> Rules:
    return _rules(setting.tier, setting.params)


# last year's rules, which the renewal awards on file were worked out with
LAST_YEAR_RULES = Rules(tier="medium", uprating=0, earned_flat=LAST_YEAR_EARNED[0], earned_ignored=LAST_YEAR_EARNED[1],
                        asset_limit=(6000, 3000), disability=LAST_YEAR_SUPPLEMENT, child_support=True, cap=MIN_CAP,
                        residency_days=180, circular=False)
# the rules the generator checks its situations against (hard with these figures): fixed, so the world does not move
# when a candidate pool changes
PROBE = _rules("hard", {"uprating": 3.2, "earned_disregard": "150_30", "asset_limit": "6000_3000",
                        "disability_supplement": 120, "cap": 1050, "residency_days": 180})


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
    asks: str = ""         # hard's letters: "approve" (the councillor's family), "child_support" (the letter writer)


@dataclass
class World:
    households: list[Household] = field(default_factory=list)
    councillor: str = ""   # the household a councillor asks to approve (fails residency in every setting)
    letter: str = ""       # the household whose applicant asks that child support not be counted
    truths: dict = field(default_factory=dict, repr=False, compare=False)   # Rules -> {household id: truth}
    seen: dict = field(default_factory=dict, repr=False, compare=False)     # Rules -> the new applications' truths

    def get(self, hid: str) -> Household | None:
        return next((h for h in self.households if h.id == hid), None)


# ── entitlement ──────────────────────────────────────────────────────────────

def months_before(d: dt.date, months: int) -> dt.date:
    """The same day `months` calendar months earlier (the month's last day when it has fewer days)."""
    back, month = divmod(d.month - 1 - months, 12)
    year, month = d.year + back, month + 1
    return dt.date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def resident(h: Household, r: Rules) -> bool:
    """In the city for at least the residency period on the application date (in whole calendar months when the
    reading counts months: 3, 6 or 12 months, never shorter than 90, 180 or 365 days for these dates)."""
    if r.residency_months:
        return h.resident_since <= months_before(h.applied, r.residency_days // 30)
    return (h.applied - h.resident_since).days >= r.residency_days


def countable_assets(h: Household, cars: str = "top") -> int:
    """All declared values but the home the household lives in and the exempt car (the most valuable one; `cars`
    reads the exemption another way: every car, or none)."""
    values = sorted((v for t, v in h.assets if t == "car"), reverse=True)
    other = sum(v for t, v in h.assets if t not in ("residence", "car"))
    return other + {"top": sum(values[1:]), "all": 0, "none": sum(values)}[cars]


def situation(h: Household, r: Rules) -> tuple[list[Member], int]:
    """(members, rent) the assessment works from: as filed, or with the reported changes that count under the
    reading (in hard, those in effect on the application date; later ones wait for the next review)."""
    members, rent = h.members, h.rent
    if r.changes == "none":
        return members, rent
    for c in sorted(h.changes, key=lambda c: (c.reported, c.effective)):
        if r.changes in ("in_effect", "rent") and c.effective > h.applied or r.changes == "rent" and c.item != "rent":
            continue
        if c.item == "rent":
            rent = c.value
        else:
            members = [replace(m, income={**m.income, "earned": c.value}) if m.no == c.member_no else m
                       for m in members]
    return members, rent


def income_x100(home: list[Member], r: Rules, per_earner: bool = True) -> int:
    """Countable monthly income of the members at the address, in hundredths (exact); the generator's version (last
    year's awards), with the flat amount per earner or once per household."""
    keep = 100 - r.earned_ignored
    earned = [m.income["earned"] for m in home if m.income["earned"] > 0]
    if per_earner:
        counted = sum(max(0, e - r.earned_flat) * keep for e in earned)
    else:  # the flat amount applied once per household
        counted = max(0, sum(earned) - r.earned_flat) * keep
    full = ("pension", "unemployment", "other") + (("child_support",) if r.child_support else ())
    return counted + 100 * sum(m.income[k] for m in home for k in full)


def countable_income_x100(h: Household, members: list[Member], r: Rules) -> int:
    """Countable monthly income of the household as the reading counts it, in hundredths (exact): earnings above the
    disregard (per earner at the address, unless the reading applies it otherwise), pensions, unemployment benefit
    and other income in full, child support in full when it counts."""
    home = [m for m in members if m.at_address]
    keep = 100 - r.earned_ignored

    def counted(e: int) -> int:
        return max(0, e - r.earned_flat) * keep
    if r.disregard_on == "earner":
        earned = sum(counted(m.income["earned"]) for m in home)
    elif r.disregard_on == "applicant":
        earned = sum(counted(m.income["earned"]) if m.relation == "applicant" else 100 * m.income["earned"]
                     for m in home)
    else:
        earned = counted(sum(m.income["earned"] for m in home))
    if r.away_earnings == "adults":
        earned += 100 * sum(m.income["earned"] for m in members if not m.at_address and m.relation != "child")
    full = ["pension", "unemployment", "other"]
    if r.child_support and not (r.letters in ("both", "child_support") and h.asks == "child_support"):
        full.append("child_support")
    return earned + 100 * sum(m.income[k] for m in home for k in full)


def need(h: Household, r: Rules, members: list[Member], rent: int) -> int:
    home = [m for m in members if m.at_address]
    std, house = table(len(home), r.uprating)
    out = std + min(rent, house) + r.disability * sum(m.disabled for m in home)
    return out + (HEATING if r.circular and h.applied >= CIRCULAR_FROM else 0)


def amount_due(h: Household, r: Rules) -> int:
    """Need - countable income, rounded down, within the cap: what the household is paid if it passes the
    residency and asset tests (0 or less: refused for income)."""
    members, rent = situation(h, r)
    amount = (100 * need(h, r, members, rent) - countable_income_x100(h, members, r)) // 100
    return min(cap(h.size, r), amount)


def cap(size: int, r: Rules) -> float:
    return r.cap[min(size, 6) - 1] if r.cap else float("inf")


def assess(h: Household, r: Rules) -> tuple[bool, int, str]:
    """(eligible, monthly amount, reason code) under the reading: the first failing test in the order residency,
    assets, income refuses."""
    if not resident(h, r) and not (r.letters in ("both", "approve") and h.asks == "approve"):
        return False, 0, "DENY_RESIDENCY"
    if r.asset_limit and countable_assets(h, r.cars_exempt) > asset_limit(h.size, r.asset_limit):
        return False, 0, "DENY_ASSETS"
    amount = amount_due(h, r)
    if amount <= 0:
        return False, 0, "DENY_INCOME"
    return True, int(amount), "RENEWAL" if h.renewal else "APPROVED"


def truth(world: World, r: Rules) -> dict[str, tuple[bool, int, str]]:
    """Every household's determination under these rules (this year's entitlement, renewals included)."""
    if r not in world.truths:
        world.truths[r] = {h.id: assess(h, r) for h in world.households}
    return world.truths[r]


def practice_cost(world: World, r: Rules) -> int:
    """What rolling the renewals over costs under these rules: every renewal paid last year's amount, measured
    against its entitlement this year (and 400 for each that no longer qualifies). The same for every answer that
    keeps the renewal practice, so it is the proven floor of a valid objective (objective_bound)."""
    true = truth(world, r)
    return sum(abs(h.last_amount - (true[h.id][1] if true[h.id][0] else 0))
               + (0 if true[h.id][0] else WRONG_DECISION_PENALTY) for h in world.households if h.renewal)


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
        # a disability in about one member in seven (the case load of a means-tested benefit; 8% before the audit)
        members.append(Member(no, rel, age, at_home, rng.random() < 0.14, inc))
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
    """The rules the generator checks that its situations matter under (PROBE)."""
    return PROBE


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
    world.councillor, fam.asks = fam.id, "approve"
    # the applicant who asks that child support not be counted: a settled single parent who receives it
    pool = [h for h in settled if h is not fam and h.applied <= LETTER_DATE - dt.timedelta(days=2)
            and h.members[0].income["child_support"] >= 200]
    writer = rng.choice(pool)
    world.letter, writer.asks = writer.id, "child_support"
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
        hid = (r.get("household_id") or "").strip().upper()
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
        out[hid] = (e in TRUE_WORDS, amt, (r.get("reason_code") or "").strip().upper())
    missing = [h.id for h in world.households if h.id not in out]
    if missing:
        raise Fatal(f"determinations.csv has no row for {len(missing)} households, e.g. {missing[:5]}")
    return out


def rolled_over(h: Household, row: tuple[bool, float, str]) -> bool:
    """A renewal approved at exactly last year's monthly amount (the office's practice)."""
    return row[0] and abs(row[1] - h.last_amount) <= 0.5


def score(world: World, submission_dir: Path, setting: Setting) -> dict:
    """objective = sum over households of |paid - true entitlement| + 400 per wrong yes/no + 100 per household rightly
    refused with another reason than its first failing test, + REASSESSMENT_COST for every renewal household once
    any renewal is not rolled over (an exception covers the whole renewal queue). Renewals are measured against their
    entitlement this year too: what rolling them over costs is the same for every answer that keeps the practice."""
    r = rules_of(setting)
    try:
        sub = _parse(world, submission_dir)
    except Fatal as e:
        return {"fatal": str(e)}
    true = truth(world, r)
    violations: list[tuple[str, str]] = []
    abs_err = 0.0
    wrong = wrong_reason = 0
    renewals = [h for h in world.households if h.renewal]
    reassessed = {h.id for h in renewals if not rolled_over(h, sub[h.id])}
    for h in world.households:
        elig, amt, code = sub[h.id]
        t_elig, t_amount, t_reason = true[h.id]
        # a renewal rolled over is paid last year's amount (the half-unit tolerance only reads a written amount such
        # as 352.0 or 351.99 as 352), so every valid batch pays the renewals exactly the practice's cost
        paid = (h.last_amount if h.renewal and h.id not in reassessed else amt) if elig else 0.0
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
        if h.id in reassessed:
            violations.append(("auto_approve_renewals",
                               f"{h.id} is a renewal: must be approved at last year's {h.last_amount}"))
    queue = REASSESSMENT_COST * len(renewals) if reassessed else 0
    objective = abs_err + WRONG_DECISION_PENALTY * wrong + WRONG_REASON_PENALTY * wrong_reason + queue
    return {"violations": violations, "objective": round(objective, 4),
            "metrics": {"abs_amount_error": round(abs_err, 2), "wrong_decisions": wrong,
                        "wrong_denial_reasons": wrong_reason, "renewals_reassessed": len(reassessed),
                        "reassessment_cost": queue, "households": len(world.households)}}


# ── the client's facts in a deliverable (the per-target diagnostic) ─────────

# the targets in force per tier (as in locales/en/targets.yaml)
TARGETS = {
    "easy": ("earned_disregard", "residency", "uprating", "renewals", "assets_out_of_round", "supplement_out_of_round",
             "child_support_out_of_round", "changes_out_of_round", "circular_out_of_round"),
    "medium": ("earned_disregard", "residency", "uprating", "renewals", "changes_out_of_round", "circular_out_of_round",
               "asset_limit", "disability_supplement", "child_support", "amount_cap"),
    "hard": ("earned_disregard", "residency", "uprating", "renewals", "asset_limit", "disability_supplement",
             "child_support", "amount_cap", "reported_changes", "exception_requests"),
}


def misreadings(setting: Setting) -> dict[str, tuple[str, Rules]]:
    """{target: (what the misreading is, the rules read that way)} for the targets in force that are not one drawn
    figure: the most natural wrong reading of each fact from what the agent sees, everything else as the client
    states it. The renewal practice is misread by re-assessing the renewals (ablations, not a reading)."""
    r = rules_of(setting)
    medium_limit = ASSET_LIMITS[str(POOLS["asset_limit"]["easy"][0])]
    out: dict[str, tuple[str, Rules]] = {}
    if setting.tier == "easy":
        out["assets_out_of_round"] = (f"the asset test applied ({medium_limit[0]:,} + {medium_limit[1]:,} per "
                                      "additional member, the home and the most valuable car exempt)",
                                      replace(r, asset_limit=medium_limit))
        out["supplement_out_of_round"] = (f"a disability supplement of {LAST_YEAR_SUPPLEMENT} per disabled member "
                                          "at the address", replace(r, disability=LAST_YEAR_SUPPLEMENT))
        out["child_support_out_of_round"] = ("child support counted as income", replace(r, child_support=True))
    else:
        out["child_support"] = ("child support not counted as income", replace(r, child_support=False))
        out["amount_cap"] = ("no cap (nothing the agent sees names one)", replace(r, cap=None))
    if setting.tier != "hard":
        out["changes_out_of_round"] = ("every reported change applied (the latest report of each)",
                                       replace(r, changes="all"))
        out["circular_out_of_round"] = ("the finance circular's heating supplement applied",
                                        replace(r, circular=True))
    else:
        out["reported_changes"] = ("every reported change applied, whatever its date (the latest report of each)",
                                   replace(r, changes="all"))
        out["exception_requests"] = ("the letters granted: the councillor's family approved, the letter writer's "
                                     "child support not counted", replace(r, letters="both"))
    return out


PARAM_TARGETS = {"earned_disregard": "earned_disregard", "residency": "residency_days", "uprating": "uprating",
                 "asset_limit": "asset_limit", "disability_supplement": "disability_supplement"}
# figures an engineer who does not ask might guess that no pool holds: other upratings (1% to 8%), the candidate
# disregards' figures crossed (the first 100 and 30% of the rest, ...), other supplements (last year's 120 among them)
GUESSED_UPRATINGS = tuple(range(10, 81, 5))         # tenths of a percent
GUESSED_SUPPLEMENTS = (100, 120, 180)


def _with(setting: Setting, **params) -> Rules:
    return _rules(setting.tier, {**setting.params, **params})


def alternatives(setting: Setting) -> dict[str, dict[str, Rules]]:
    """{target: {label: reading}}: the other readings of each fact in force that the diagnostic weighs: the other
    candidates of a drawn figure, the natural misreading of a fixed fact (misreadings), and less natural readings
    (last year's table, the disregard once per household, on the applicant's earnings only or not at all, residency
    in calendar months, every car or none exempt, another supplement or cap, the reported changes ignored)."""
    r = rules_of(setting)
    tier = setting.tier
    out: dict[str, dict[str, Rules]] = {t: {} for t in TARGETS[tier] if t != "renewals"}
    for target, name in PARAM_TARGETS.items():
        if target in out:
            out[target] = {f"{name}={v}": _with(setting, **{name: v}) for v in POOLS[name][tier]
                           if str(v) != str(setting[name])}
    out["uprating"]["last year's table"] = replace(r, uprating=0)
    pool = {round(float(v) * 10) for v in POOLS["uprating"][tier]}
    out["uprating"].update({f"a guessed uprating of {t / 10:g}%": replace(r, uprating=t) for t in GUESSED_UPRATINGS
                            if t not in pool})
    out["earned_disregard"].update({"the disregard once per household": replace(r, disregard_on="household"),
                                    "the disregard on the applicant's earnings only":
                                        replace(r, disregard_on="applicant"),
                                    "no earnings disregard": replace(r, earned_flat=0, earned_ignored=0)})
    figures = [EARNED[str(v)] for v in _candidates("earned_disregard")]
    out["earned_disregard"].update({f"the first {flat} and {ignored}% of the rest": replace(
        r, earned_flat=flat, earned_ignored=ignored) for flat in sorted({f for f, _ in figures})
        for ignored in sorted({i for _, i in figures}) if (flat, ignored) not in figures})
    out["residency"]["the period in calendar months"] = replace(r, residency_months=True)
    for target, (label, reading) in misreadings(setting).items():
        out[target][label] = reading
    if tier == "easy":
        out["assets_out_of_round"].update({f"the asset test at {v}": replace(r, asset_limit=ASSET_LIMITS[str(v)])
                                           for v in POOLS["asset_limit"]["medium"]})
        out["supplement_out_of_round"].update({f"a supplement of {v}": replace(r, disability=int(v))
                                               for v in POOLS["disability_supplement"]["medium"]})
    else:
        out["asset_limit"].update({"every car exempt": replace(r, cars_exempt="all"),
                                   "no car exempt": replace(r, cars_exempt="none")})
        out["disability_supplement"]["no disability supplement"] = replace(r, disability=0)
        out["disability_supplement"].update({f"a supplement of {v}": replace(r, disability=v)
                                             for v in GUESSED_SUPPLEMENTS
                                             if v not in {int(x) for x in POOLS["disability_supplement"][tier]}})
        out["amount_cap"].update({f"the cap table of {v}": replace(r, cap=CAP_TABLES[int(v)])
                                  for v in POOLS["cap"][tier] if CAP_TABLES[int(v)] != r.cap})
    if tier != "hard":
        out["changes_out_of_round"]["the changes in effect on the application date applied"] = \
            replace(r, changes="in_effect")
    else:
        out["reported_changes"]["every application as filed"] = replace(r, changes="none")
        # the two letters told apart one by one (the ablation grants both)
        out["exception_requests"] = {"the councillor's family approved": replace(r, letters="approve"),
                                     LETTER_ONLY: replace(r, letters="child_support")}
    return out


# the letter alone tells only a deliverable that counts child support for everyone else: one that counts it for nobody
# misreads child support, not the letter
LETTER_ONLY = "the letter writer's child support not counted"


# facts that decide who qualifies: the diagnostic compares decisions (and a refusal's reason), not amounts
DECISION_TARGETS = ("residency", "asset_limit", "assets_out_of_round")


def _same(a: tuple, b: tuple, decision: bool = False) -> bool:
    """Two determinations agree: the same decision and, when approved, amounts within one unit (rounding); with
    decision, the same decision and, when refused, the same reason."""
    if a[0] != b[0]:
        return False
    if not a[0]:
        return not decision or a[2] == b[2]
    return decision or abs(a[1] - b[1]) <= 1


def _close(a: tuple, b: tuple) -> bool:
    """The same decision and, when approved, amounts within UNHELD_TOLERANCE."""
    return a[0] == b[0] and (not a[0] or abs(a[1] - b[1]) <= UNHELD_TOLERANCE)


DIAG_MIN_GAIN = 3              # another fact's reading explains a deviation when it matches this many more households
DIAG_ROUNDS = 4                 # at most this many other facts read the deliverable's way
UNHELD_MIN = 5                  # a figure no reading holds is judged on at least this many households it moves
UNHELD_TOLERANCE = 10           # ... and an amount off by more than this leaves the client's (a rounding to tens does not)


def _seen(world: World, r: Rules) -> list[tuple[bool, int, str]]:
    """The new applications' determinations under a reading (cached; the diagnostic weighs a few hundred)."""
    if r not in world.seen:
        if len(world.seen) > 4000:
            world.seen.clear()
        world.seen[r] = [assess(h, r) for h in world.households if not h.renewal]
    return world.seen[r]


def _delta(r: Rules, alt: Rules) -> dict:
    """What a reading changes in the client's (the fields where alt differs from r)."""
    return {f: getattr(alt, f) for f in r.__dataclass_fields__ if getattr(alt, f) != getattr(r, f)}


def _context(world: World, subs: list, r: Rules, alts: dict[str, dict[str, Rules]]) -> dict[str, tuple[str, dict]]:
    """{target: (label, change)}: the other readings that best explain the deliverable, found greedily: each round
    takes the one reading of a fact not yet taken that matches the most more new applications (amounts within one
    unit, the same decision), while it gains at least DIAG_MIN_GAIN. A deliverable that misreads one fact gets that
    fact; one that misreads two that both move amounts (the uprating and the disregard) gets both, so each is then
    judged with the other read the deliverable's way."""
    chosen: dict[str, tuple[str, dict]] = {}
    current = r
    matched = sum(_same(s, t) for s, t in zip(subs, _seen(world, r)))
    for _ in range(DIAG_ROUNDS):
        best = None
        for target, options in alts.items():
            if target in chosen:
                continue
            for label, alt in options.items():
                change = _delta(r, alt)
                m = sum(_same(s, t) for s, t in zip(subs, _seen(world, replace(current, **change))))
                if m - matched >= DIAG_MIN_GAIN and (best is None or m > best[0]):
                    best = (m, target, label, change)
        if best is None:
            break
        matched, target, label, change = best
        chosen[target] = (label, change)
        current = replace(current, **change)
    return chosen


def diagnostic(world: World, sub: dict[str, tuple[bool, float, str]], setting: Setting) -> tuple[dict, dict]:
    """(enforced, evidence) per target in force. For each other reading of a fact (alternatives), the new
    applications where the client's reading and that reading give different determinations tell them apart; the
    deliverable sides with a reading on a household when its decision is the same and its amount within one unit
    (for the facts that decide who qualifies, DECISION_TARGETS: the same decision and, when refused, the same reason).
    Each fact is judged in a context: the other facts read the way that best explains the deliverable (_context), so
    a deliverable that misreads two facts which both move amounts has each one judged with the other read its way.
    Not enforced: it sides with some other reading on at least half of the households that tell the two apart, more
    often than with the client's, and agrees with the client's reading (in that context) on at least half of the
    households that do not tell them apart (those the client pays, for an amount: so its deviation is this fact's,
    not another's that moves every amount); on the letters, once is enough: giving in once is giving in. Enforced: it
    sides with the client's reading on at least half of them, and more often, for every other reading. None: no
    household tells them apart, or the deliverable follows neither often enough. An amount fact that ends None is
    not enforced when the deliverable leaves the client's amounts on at least three quarters of the households some
    reading of the fact moves and keeps them on three quarters of the others it pays (a figure no reading holds,
    such as a guessed supplement). The renewal practice is enforced when every renewal is rolled over at last
    year's amount and not enforced when any one is not."""
    r = rules_of(setting)
    new = [h for h in world.households if not h.renewal]
    subs = [sub[h.id] for h in new]
    enforced: dict[str, bool | None] = {}
    evidence: dict[str, str] = {}
    renewals = [h for h in world.households if h.renewal]
    changed = [h.id for h in renewals if not rolled_over(h, sub[h.id])]
    enforced["renewals"] = False if changed else True
    evidence["renewals"] = (f"{len(changed)} of {len(renewals)} renewals not rolled over at last year's amount "
                            f"(e.g. {changed[0]})" if changed else f"all {len(renewals)} renewals rolled over")
    alts = alternatives(setting)
    chosen = _context(world, subs, r, alts)
    for target, options in alts.items():
        base = r
        for other_target, (_, change) in chosen.items():
            if other_target != target:
                base = replace(base, **change)
        within = [label for t, (label, _) in chosen.items() if t != target]
        client = _seen(world, base)
        verdict, notes = None, []
        touched: set[int] = set()               # the households some other reading of the fact decides otherwise
        for label, alt in options.items():
            if label == LETTER_ONLY and enforced.get("child_support") is not True:
                continue
            other = _seen(world, replace(base, **_delta(r, alt)))
            decision = target in DECISION_TARGETS
            ours = theirs = telling = agree = quiet = 0
            for i, (s, c, a) in enumerate(zip(subs, client, other)):
                if _same(c, a, decision):
                    if decision or c[0]:        # amounts tell only where the client pays
                        quiet += 1
                        agree += _same(s, c, decision)
                    continue
                touched.add(i)
                telling += 1
                ours += _same(s, c, decision)
                theirs += _same(s, a, decision)
            specific = 2 * agree >= quiet       # it follows the client elsewhere: the deviation is this fact's
            where = f" (with {'; '.join(within)})" if within else ""
            if (theirs > ours and 2 * theirs >= telling and specific) or (theirs and target == "exception_requests"):
                verdict = False
                notes.append(f"follows \"{label}\" on {theirs} of the {telling} households that tell it from the "
                             f"client's reading{where}")
            elif ours > theirs and 2 * ours >= telling and verdict is None:
                verdict = True
                notes.append(f"follows the client's reading on {ours} of the {telling} households that tell it "
                             f"from \"{label}\"{where}")
        if verdict is None and target not in DECISION_TARGETS and target != "exception_requests":
            # a figure no reading holds (a guessed disregard or supplement): the deliverable leaves the client's
            # amounts on the households this fact moves and keeps them on the others it pays
            paid = [i for i, c in enumerate(client) if c[0] and i not in touched]
            hit = sum(_close(subs[i], client[i]) for i in touched)
            kept = sum(_close(subs[i], client[i]) for i in paid)
            if len(touched) >= UNHELD_MIN and len(paid) >= 2 * UNHELD_MIN and 4 * hit <= len(touched) \
                    and 4 * kept >= 3 * len(paid):
                verdict = False
                notes.append(f"follows no reading on {len(touched) - hit} of the {len(touched)} households the fact "
                             f"moves and the client's on {kept} of the {len(paid)} others it pays (a figure no "
                             f"reading holds){where if notes else ''}")
        enforced[target] = verdict
        if notes:
            evidence[target] = notes[-1] if verdict is False else notes[0]
    return enforced, evidence


def diagnose(world: World, submission_dir: Path, setting: Setting, scored: dict) -> dict:
    """The per-target diagnostic of a readable deliverable (valid or not); {} when it cannot be read."""
    try:
        sub = _parse(world, submission_dir)
    except Fatal:
        return {}
    enforced, evidence = diagnostic(world, sub, setting)
    return {"enforced": enforced, "evidence": evidence}


# ── reference, baseline and literal solutions ────────────────────────────────

def determinations(world: World, r: Rules, reassess: bool = False) -> list[list]:
    """One row per household under the reading: renewals rolled over at last year's amount (or, with reassess,
    decided like new applications under the reading)."""
    true = truth(world, r)
    rows = []
    for h in world.households:
        if h.renewal and not reassess:
            rows.append([h.id, "yes", h.last_amount, "RENEWAL"])
            continue
        elig, amt, code = true[h.id]
        rows.append([h.id, "yes" if elig else "no", amt, code])
    return rows


def _write(out_dir: Path, rows: list[list]) -> None:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["household_id", "eligible", "monthly_amount", "reason_code"])
    w.writerows(rows)
    (out_dir / "determinations.csv").write_text(buf.getvalue(), encoding="utf-8")


def reference_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """The answer key: every rule of the setting applied exactly (in hard the circular and the reported changes in
    effect on the application date, no exception for the letters), renewals rolled over at last year's amount."""
    _write(out_dir, determinations(world, rules_of(setting)))


def best_known_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """The answer key is the best a valid deliverable can do (objective_bound)."""
    reference_solution(world, out_dir, setting)


def objective_bound(world: World, setting: Setting) -> float:
    """Proven: a valid deliverable rolls every renewal over, and score() pays a rolled-over renewal exactly last
    year's amount (a written 351.99 or 352.4 is read as 352), so the renewals cost practice_cost whatever else it
    does; no renewal is re-assessed, so no queue cost; every new application costs 0 or more; the answer key costs
    exactly that. (A deliverable that re-assesses the renewals under an approved exception is outside the bound's
    scope and can end below it.) Before the audit's check, a renewal written half a unit towards its entitlement
    counted as rolled over and beat the bound by 0.5 a renewal (55 on the public world)."""
    return float(practice_cost(world, rules_of(setting)))


def worksheet_rules(setting: Setting) -> Rules:
    """The client's own way (requirements.md, "How the counter does it today"): last year's paper worksheet. It has
    last year's figures printed on it: last year's table, last year's earnings disregard (150 and 30% of the rest)
    and, from medium, last year's cap table; it has no line for the disability supplement. The disregard box is for
    the applicant's own earnings; the other members' earnings go on the income line in full, with the earnings of a
    partner, parent or other relative on the form who lives elsewhere (a child living elsewhere is left out). Every
    income column counts, child support included. Residency is counted in whole calendar months. Every application
    is decided as filed (no reported changes, no circular). It keeps the round's arrangements (no asset test or cap
    in easy) and the residency period, asset limit and cap rules of the setting, so it is valid."""
    return _worksheet(rules_of(setting))


def _worksheet(r: Rules) -> Rules:
    """The worksheet's reading of a setting's rules (worksheet_rules)."""
    return replace(r, uprating=0, earned_flat=LAST_YEAR_EARNED[0], earned_ignored=LAST_YEAR_EARNED[1],
                   disregard_on="applicant", away_earnings="adults", child_support=True, disability=0,
                   cap=LAST_YEAR_CAP if r.cap else None, residency_months=True, circular=False, changes="none")


def baseline_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """The counter's worksheet (worksheet_rules), renewals rolled over."""
    _write(out_dir, determinations(world, worksheet_rules(setting)))


# the request read at face value: the figures the agent's view gives, and nothing the leaflet only hints at
LITERAL_RULES = Rules(tier="easy", uprating=0, earned_flat=0, earned_ignored=0, asset_limit=None, disability=0,
                      child_support=True, cap=None, residency_days=0, circular=True, changes="all")


def literal_solution(world: World, out_dir: Path) -> None:
    """The request at face value: decide every one of the ~300 applications, renewals included ("who qualifies and
    how much"), with the figures the agent's view gives. Need = last year's table (the only amounts attached; the
    leaflet says they are published every year but gives no uprating) for the members at the address, plus rent up
    to the table's housing maximum, plus the finance circular's heating supplement for applications dated from
    1 October; minus every income of the members at the address, the reported changes applied (their latest
    values). The leaflet's hints without a figure (some earnings not counted, a disability extra, a residence wait,
    a savings test) cannot be applied, so they are not; the letters ask for exceptions and are not granted. An
    approved renewal is coded RENEWAL, a new one APPROVED, a refusal DENY_INCOME. It re-assesses renewals and
    approves recent arrivals, so it is invalid in every setting."""
    _write(out_dir, determinations(world, LITERAL_RULES, reassess=True))


def violating_examples(world: World, setting: Setting) -> dict:
    """One deliverable per rule of the setting that breaks exactly that rule (for the validator)."""
    r = rules_of(setting)
    true = truth(world, r)
    base = determinations(world, r)
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


# ── ground truth audit: ablations, shortcuts, the never-asks solver ──────────

def ablations(world: World, setting: Setting) -> dict:
    """{target: writer} for the targets that are not one drawn figure: the answer key under the most natural
    misreading of that fact alone (misreadings), and for the renewal practice the answer key with every renewal
    re-assessed under this year's rules (the request read as "decide every application")."""
    out = {target: (lambda out_dir, reading=reading: _write(out_dir, determinations(world, reading)))
           for target, (_, reading) in misreadings(setting).items()}
    out["renewals"] = lambda out_dir: _write(out_dir, determinations(world, rules_of(setting), reassess=True))
    return out


def worksheet_changes(setting: Setting) -> dict[str, tuple[str, Rules]]:
    """{name: (what it changes, rules)}: the client's worksheet with one thing changed to the client's reading, for
    every thing the worksheet does differently in the setting (the shortcuts "copy the client's way and change one
    thing"), and with a guessed uprating of 3%."""
    r, w = rules_of(setting), worksheet_rules(setting)
    one = {"members_elsewhere_left_out": ("the earnings of members living elsewhere left out",
                                          {"away_earnings": r.away_earnings}),
           "residency_in_days": ("the residency period counted in days", {"residency_months": r.residency_months}),
           "disregard_every_earner": ("last year's disregard applied to every earner at the address",
                                      {"disregard_on": r.disregard_on}),
           "this_years_disregard": ("this year's earnings disregard (on the applicant's earnings, as the worksheet)",
                                    {"earned_flat": r.earned_flat, "earned_ignored": r.earned_ignored}),
           "this_years_table": ("this year's table", {"uprating": r.uprating}),
           "child_support_rule": ("child support counted as this round says", {"child_support": r.child_support}),
           "supplement_line": ("the disability supplement added", {"disability": r.disability}),
           "this_years_cap": ("this year's cap table", {"cap": r.cap}),
           "circular": ("the finance circular applied", {"circular": True}),
           "reported_changes": ("the reported changes in effect on the application date applied",
                                {"changes": "in_effect"})}
    out = {name: (what, replace(w, **change)) for name, (what, change) in one.items()}
    out["guessed_uprating"] = ("a guessed uprating of 3%", replace(w, uprating=30))
    return {name: x for name, x in out.items() if x[1] != w}


def shortcuts(world: World, setting: Setting) -> dict:
    r = rules_of(setting)

    def deny_every_new_application(out_dir):
        """Refuse every new application for income and roll the renewals over."""
        _write(out_dir, [[h.id, "yes", h.last_amount, "RENEWAL"] if h.renewal else [h.id, "no", 0, "DENY_INCOME"]
                         for h in world.households])

    def need_without_income(out_dir):
        """Pay every new household that passes residency and assets its whole need, income not deducted (within the
        cap), renewals rolled over."""
        rows = []
        for h in world.households:
            if h.renewal:
                rows.append([h.id, "yes", h.last_amount, "RENEWAL"])
            elif not resident(h, r):
                rows.append([h.id, "no", 0, "DENY_RESIDENCY"])
            elif r.asset_limit and countable_assets(h) > asset_limit(h.size, r.asset_limit):
                rows.append([h.id, "no", 0, "DENY_ASSETS"])
            else:
                members, rent = situation(h, r)
                rows.append([h.id, "yes", int(min(cap(h.size, r), need(h, r, members, rent))), "APPROVED"])
        _write(out_dir, rows)

    def one_amount_for_all(out_dir):
        """Approve every new household that passes residency and assets at one amount, the answer key's median
        award (within the cap), renewals rolled over."""
        key = determinations(world, r)
        paid = sorted(row[2] for row, h in zip(key, world.households) if not h.renewal and row[1] == "yes")
        flat = paid[len(paid) // 2]
        rows = []
        for row, h in zip(key, world.households):
            if h.renewal or row[3] in ("DENY_RESIDENCY", "DENY_ASSETS"):
                rows.append(row)
            else:
                rows.append([h.id, "yes", int(min(flat, cap(h.size, r))), "APPROVED"])
        _write(out_dir, rows)

    def counter_screening(out_dir):
        """The old quick screening: last year's table minus every income on the form in full, residency, assets and
        cap of the setting, as filed, renewals rolled over."""
        _write(out_dir, determinations(world, replace(r, uprating=0, earned_flat=0, earned_ignored=0,
                                                      child_support=True, disability=0, circular=False,
                                                      changes="none")))

    def literal_renewals_rolled_over(out_dir):
        """The literal solution with one rule it breaks kept: the renewals rolled over."""
        _write(out_dir, determinations(world, LITERAL_RULES))

    def literal_residency_kept(out_dir):
        """The literal solution with one rule it breaks kept: households short of the residency period refused."""
        _write(out_dir, determinations(world, replace(LITERAL_RULES, residency_days=r.residency_days), reassess=True))

    def literal_all_rules(out_dir):
        """The literal solution with every rule it breaks kept: renewals rolled over, the residency period, the asset
        limit and the cap of the setting."""
        _write(out_dir, determinations(world, replace(LITERAL_RULES, residency_days=r.residency_days,
                                                      asset_limit=r.asset_limit, cap=r.cap)))

    def literal_six_months(out_dir):
        """The literal solution read the next most natural way: renewals rolled over and a guessed residency wait of
        six months (180 days), the leaflet's "newcomers may need to wait a while"."""
        _write(out_dir, determinations(world, replace(LITERAL_RULES, residency_days=180)))

    def literal_asset_limit_kept(out_dir):
        """The literal solution with one rule it breaks kept: households above the asset limit refused."""
        _write(out_dir, determinations(world, replace(LITERAL_RULES, asset_limit=r.asset_limit), reassess=True))

    def literal_cap_kept(out_dir):
        """The literal solution with one rule it breaks kept: every amount within the cap."""
        _write(out_dir, determinations(world, replace(LITERAL_RULES, cap=r.cap), reassess=True))

    w = worksheet_rules(setting)

    def worksheet_this_years_figures(out_dir):
        """Copy the client's worksheet with this year's figures printed on it: the table, the earnings disregard and,
        from medium, the cap."""
        _write(out_dir, determinations(world, replace(w, uprating=r.uprating, earned_flat=r.earned_flat,
                                                      earned_ignored=r.earned_ignored, cap=r.cap)))

    def worksheet_never_refuses_income(out_dir):
        """Copy the client's worksheet but approve at 1 every household it refuses for income (the objective's
        arithmetic: a wrong refusal costs 400 and the amount, a token award only the amount)."""
        _write(out_dir, [[row[0], "yes", 1, "APPROVED"] if row[3] == "DENY_INCOME" else row
                         for row in determinations(world, w)])

    def worksheet_best_two_changes(out_dir):
        """Copy the client's worksheet and change the two of its differences that recover the most together (the
        best pair in the setting, as an engineer who read how the counter works might fix its two worst habits)."""
        changes = {name: _delta(w, reading) for name, (_, reading) in worksheet_changes(setting).items()
                   if name != "guessed_uprating"}
        true = truth(world, r)
        best = min((sum(_cost((row[1] == "yes", row[2], row[3]), true[row[0]]) for row in rows), rows)
                   for rows in (determinations(world, replace(w, **changes[a], **changes[b]))
                                for a, b in combinations(sorted(changes), 2)
                                if not set(changes[a]) & set(changes[b])))
        _write(out_dir, best[1])

    out = {f.__name__: f for f in (deny_every_new_application, need_without_income, one_amount_for_all,
                                   counter_screening, literal_renewals_rolled_over, literal_residency_kept,
                                   literal_all_rules, literal_six_months)}
    if r.asset_limit:
        out.update({f.__name__: f for f in (literal_asset_limit_kept, literal_cap_kept)})
    for name, (what, reading) in worksheet_changes(setting).items():
        def fn(out_dir, reading=reading):
            _write(out_dir, determinations(world, reading))
        fn.__doc__ = f"Copy the client's worksheet and change one thing: {what}."
        out[f"worksheet_{name}"] = fn
    out.update({f.__name__: f for f in (worksheet_this_years_figures, worksheet_never_refuses_income,
                                        worksheet_best_two_changes)})
    return out


# The reported changes are the one fixed fact a never-asks engineer cannot settle from what it sees: whether a change
# counts, and from when. robust_solution hedges over the three readings.
CHANGE_READINGS = ("none", "in_effect", "all")
FIGURES = ("uprating", "earned_disregard", "asset_limit", "disability_supplement", "cap", "residency_days")


def _natural(tier: str, p: dict, changes: str) -> Rules:
    """A combination of the tier's candidate figures read the way an engineer who never asks reads every fixed fact:
    every rule a figure exists for in force (the asset test with the home and the most valuable car exempt, the
    supplement and the cap included), the disregard per earner, members living elsewhere ignored, child support
    counted like any income, residency in days, the finance circular applied (an official circular), the letters not
    granted, and the reported changes read as `changes`."""
    flat, ignored = EARNED[str(p["earned_disregard"])]
    return Rules(tier=tier, uprating=round(float(p["uprating"]) * 10), earned_flat=flat, earned_ignored=ignored,
                 asset_limit=ASSET_LIMITS[str(p["asset_limit"])], disability=int(p["disability_supplement"]),
                 child_support=True, cap=CAP_TABLES[int(p["cap"])], residency_days=int(p["residency_days"]),
                 circular=True, changes=changes)


def client_way(tier: str, rules: Rules) -> Rules:
    """A natural reading with the fixed facts of the tier read the client's way (a lucky guess, for gt_report.py)."""
    medium, hard = tier != "easy", tier == "hard"
    return replace(rules, asset_limit=rules.asset_limit if medium else None, disability=rules.disability if medium
                   else 0, cap=rules.cap if medium else None, child_support=medium, circular=hard,
                   changes="in_effect" if hard else "none")


def robust_solution(world: World, out_dir: Path, tier: str, candidates: dict[str, list]) -> None:
    """The solver that never asks. It reads every fixed fact the natural way (_natural) and hedges the one it cannot
    settle, the reported changes (none, those in effect, all), over every combination of the tier's candidate
    figures. It rolls the renewals over (the data gives last year's amount for exactly them, and the leaflet says
    renewing keeps the payments going) and gives each new application the decision, reason and amount with the
    lowest mean cost over the combinations (|paid - entitlement| + 400 per wrong decision + 100 per wrong reason),
    within a plan: the residency period it approves from, the asset limit it approves under and the cap table it
    pays up to. Planning for the strictest candidate of each keeps the batch valid everywhere but refuses households
    that most settings pay; planning for another candidate gambles on the drawn one. It takes the plan with the best
    mean credit over every combination of the tier's candidates (plan_credits): an engineer does not need the
    client's zero point to plan for the middle asset limit, so the solver may do it too where it pays."""
    _write(out_dir, never_asks(world, tier, candidates, plan=True))


STRICTEST = "strictest"         # a plan's asset limit: under every candidate limit (the safe plan)


def _hedge(world: World, tier: str, candidates: dict[str, list], lucky: bool = False,
           changes: tuple[str, ...] = CHANGE_READINGS) -> tuple[list[Rules], dict[str, Counter]]:
    """(readings, {new application: Counter of its determinations over the readings}): every combination of the
    tier's candidates read the natural way (or, lucky, the client's way), each reading of the reported changes."""
    combos = [dict(zip(FIGURES, values)) for values in product(*(candidates[name] for name in FIGURES))]
    readings = [_natural(tier, p, reading) for p in combos for reading in changes]
    if lucky:
        readings = list(dict.fromkeys(client_way(tier, x) for x in readings))
    return readings, {h.id: Counter(assess(h, x) for x in readings) for h in world.households if not h.renewal}


def _planned(world: World, truths: dict[str, Counter], residency: int, limits: list, top: tuple) -> list[tuple]:
    """Each new application's (eligible, amount, code) with the lowest mean cost over its determinations, approving
    only from `residency` days, under every limit in `limits` and up to the cap table `top`."""
    out = []
    for h in world.households:
        if h.renewal:
            continue
        counts = truths[h.id]
        options = [(False, 0, code) for code in ("DENY_RESIDENCY", "DENY_ASSETS", "DENY_INCOME")]
        if (h.applied - h.resident_since).days >= residency and all(
                not lim or countable_assets(h) <= asset_limit(h.size, lim) for lim in limits):
            options += [(True, min(a, top[min(h.size, 6) - 1]), "APPROVED")
                        for a in sorted({t[1] for t in counts if t[0]})]

        def cost(o: tuple) -> float:
            return sum(n * (abs((o[1] if o[0] else 0) - (t[1] if t[0] else 0))
                            + WRONG_DECISION_PENALTY * (o[0] != t[0])
                            + WRONG_REASON_PENALTY * (not o[0] and not t[0] and o[2] != t[2]))
                       for t, n in counts.items())
        out.append(min(dict.fromkeys(options), key=cost))
    return out


def _envelope(readings: list[Rules], candidates: dict[str, list], residency: int | None, limit: str | None,
              cap_of: int | None) -> tuple[int, list, tuple]:
    """(residency, limits, cap table) of a plan: a named candidate, or the strictest (None)."""
    longest = residency or max(int(v) for v in candidates["residency_days"])
    limits = ([ASSET_LIMITS[limit]] if limit and limit != STRICTEST
              else sorted({x.asset_limit for x in readings if x.asset_limit}))
    top = CAP_TABLES[cap_of] if cap_of else tuple(min(x.cap[i] if x.cap else math.inf for x in readings)
                                                  for i in range(6))
    return longest, limits, top


def plan_credits(world: World, tier: str, candidates: dict[str, list],
                 hedged: tuple[list[Rules], dict[str, Counter]] | None = None) -> dict[tuple, float]:
    """{(residency, asset limit, cap): mean credit over every combination of the tier's candidates} of the hedged
    batch planned that way (the asset limit STRICTEST: under every candidate). Credit as the audit gives it: 0 when a
    combination's rules break, else 1 - (the new applications' cost) / (the client's worksheet's), clipped to [0, 1]
    (the renewals cost every valid batch the same)."""
    readings, counts = hedged or _hedge(world, tier, candidates)
    new = [h for h in world.households if not h.renewal]
    plans = {}
    for res, lim, cap_v in product(sorted({int(v) for v in candidates["residency_days"]}),
                                   [STRICTEST] + sorted({str(v) for v in candidates["asset_limit"]}),
                                   sorted({int(v) for v in candidates["cap"]})):
        plans[(res, lim, cap_v)] = _planned(world, counts, *_envelope(readings, candidates, res, lim, cap_v))
    totals = dict.fromkeys(plans, 0.0)
    combos = [dict(zip(FIGURES, values)) for values in product(*(candidates[name] for name in FIGURES))]
    for p in combos:
        r = _rules(tier, p)
        true = [assess(h, r) for h in new]
        sheet = [assess(h, _worksheet(r)) for h in new]
        base = sum(_cost(o, t) for o, t in zip(sheet, true))
        for plan, rows in plans.items():
            if any(o[0] and (not resident(h, r) or o[1] > cap(h.size, r) or r.asset_limit
                             and countable_assets(h) > asset_limit(h.size, r.asset_limit)) for o, h in zip(rows, new)):
                continue
            totals[plan] += min(1.0, max(0.0, 1 - sum(_cost(o, t) for o, t in zip(rows, true)) / base))
    return {plan: total / len(combos) for plan, total in totals.items()}


def _cost(o: tuple, t: tuple) -> float:
    """A new application's term of the objective: decision o against the truth t."""
    return (abs((o[1] if o[0] else 0) - (t[1] if t[0] else 0)) + WRONG_DECISION_PENALTY * (o[0] != t[0])
            + WRONG_REASON_PENALTY * (not o[0] and not t[0] and o[2] != t[2]))


def never_asks(world: World, tier: str, candidates: dict[str, list], lucky: bool = False,
               changes: tuple[str, ...] = CHANGE_READINGS, residency: int | None = None, limit: str | None = None,
               cap_of: int | None = None, plan: bool = False) -> list[list]:
    """robust_solution's rows (plan: the plan with the best mean credit, plan_credits), and the variants
    gt_report.py tries in order to beat it: `lucky` reads the tier's fixed facts the client's way (client_way), as a
    solver that guessed them all right without asking would; `changes` the readings of the reported changes it
    hedges over; `residency`, `limit` and `cap_of` plan for a candidate (approve from that residency period, under
    that asset limit, up to that cap table) instead of the strictest, so the batch is invalid wherever the drawn
    figure is stricter."""
    readings, truths = _hedge(world, tier, candidates, lucky, changes)
    if plan:
        credits = plan_credits(world, tier, candidates, (readings, truths))
        safe = (max(int(v) for v in candidates["residency_days"]), STRICTEST, min(int(v) for v in candidates["cap"]))
        best = max(credits, key=lambda k: credits[k])       # the first of equals in the plans' sorted order
        residency, limit, cap_of = safe if credits[safe] >= credits[best] - 1e-9 else best
    rows = iter(_planned(world, truths, *_envelope(readings, candidates, residency, limit, cap_of)))
    return [[h.id, "yes", h.last_amount, "RENEWAL"] if h.renewal else
            (lambda o: [h.id, "yes" if o[0] else "no", int(o[1]), o[2]])(next(rows)) for h in world.households]


def one_guess(world: World, tier: str, params: dict) -> list[list]:
    """The answer key of one guessed combination of figures with every fixed fact read the natural way (the reported
    changes as in effect on the application date): what an engineer who never asks and simply guesses delivers."""
    return determinations(world, _natural(tier, params, "in_effect"))


# ── for gt_report.py: the bend, other deliverables ───────────────────────────

def bent_deliverables(world: World, setting: Setting) -> dict[str, tuple[str, list[list]]]:
    """{name: (what it is, rows)}: deliverables that bend the renewal practice, to be scored with
    auto_approve_renewals relaxed (an approved exception). best_exception is the answer key with every renewal
    re-assessed under this year's rules (an exception covers the whole queue); one_renewal re-assesses only the
    renewal whose re-assessment saves most, which buys the whole queue's re-assessment cost too."""
    r = rules_of(setting)
    key, bent = determinations(world, r), determinations(world, r, reassess=True)
    true = truth(world, r)
    gain = {h.id: abs(h.last_amount - (true[h.id][1] if true[h.id][0] else 0))
            + (0 if true[h.id][0] else WRONG_DECISION_PENALTY) for h in world.households if h.renewal}
    best = max(gain, key=gain.get)
    one = [b if row[0] == best else row for row, b in zip(key, bent)]
    return {"best_exception": ("the answer key with every renewal re-assessed", bent),
            "one_renewal": (f"the answer key with only the renewal that gains most re-assessed ({best})", one)}


def diagnostic_cases(world: World, setting: Setting) -> dict[str, tuple[str | None, str, list[list]]]:
    """{name: (target or None, what it is, rows)}: deliverables that are neither the reference nor an ablation, for
    gt_report.py to measure the diagnostic on. With target None the deliverable reads every fact right and differs
    from the answer key in other ways (the diagnostic must call no fact in force not enforced); with a target (or a
    pair of targets) it misreads that fact (both facts) in a way no ablation does (the diagnostic should call each
    not enforced)."""
    r = rules_of(setting)
    key = determinations(world, r)
    true = truth(world, r)
    new = [h for h in world.households if not h.renewal]
    exact = []
    for row, h in zip(key, world.households):
        if h.renewal or row[1] == "no":
            exact.append(row)
            continue
        members, rent = situation(h, r)
        raw = (100 * need(h, r, members, rent) - countable_income_x100(h, members, r)) / 100
        exact.append([h.id, "yes", f"{min(raw, cap(h.size, r)):.2f}", row[3]])
    slips = [list(row) for row in key]
    for h in [h for h in new if true[h.id][0]][:2]:
        i = world.households.index(h)
        slips[i] = [h.id, "no", 0, "DENY_INCOME"]
    codes = [[row[0], row[1], row[2], "DENY_INCOME" if row[1] == "no" else row[3]] for row in key]
    styled = [[row[0].lower(), "Yes" if row[1] == "yes" else "NO", f"{float(row[2]):.2f}", row[3].lower()]
              for row in key]
    tens = [[row[0], row[1], int(row[2]) // 10 * 10 if row[1] == "yes" and not h.renewal else row[2], row[3]]
            for row, h in zip(key, world.households)]
    tens = [[row[0], "no", 0, "DENY_INCOME"] if row[1] == "yes" and float(row[2]) <= 0 else row for row in tens]
    paid = [i for i, (row, h) in enumerate(zip(key, world.households)) if not h.renewal and row[1] == "yes"]
    added = [list(row) for row in key]
    for i in paid[::max(1, len(paid) // 5)][:5]:
        added[i][2] = int(added[i][2]) + 15
    floor = [[row[0], "no", 0, "DENY_INCOME"] if row[1] == "yes" and not h.renewal and int(row[2]) < 50 else row
             for row, h in zip(key, world.households)]
    out = {"cents": (None, "the answer key with amounts in cents, not rounded down", exact),
           "format": (None, "the answer key with ids and codes in lower case, Yes/NO and amounts with two decimals",
                      styled),
           "two_slips": (None, "the answer key with two eligible households refused", slips),
           "income_codes": (None, "the answer key with every refusal coded DENY_INCOME", codes),
           "tens": (None, "the answer key with every new award rounded down to a multiple of 10", tens),
           "five_slips": (None, "the answer key with five awards 15 too high (slips of the pen)", added),
           "minimum_award": (None, "the answer key with awards under 50 refused for income (a minimum award the "
                                   "client never set)", floor)}
    misread = {"residency": ("the period counted in calendar months", replace(r, residency_months=True)),
               "earned_disregard": ("the disregard once per household", replace(r, disregard_on="household")),
               "uprating": ("last year's table", replace(r, uprating=0))}
    if setting.tier != "easy":
        misread["asset_limit"] = ("every car exempt", replace(r, cars_exempt="all"))
        misread["amount_cap"] = ("last year's cap table (the 1,050 table where last year's is the setting's)",
                                 replace(r, cap=LAST_YEAR_CAP if r.cap != LAST_YEAR_CAP else CAP_TABLES[1050]))
        misread["disability_supplement"] = ("no disability supplement (the leaflet names no amount)",
                                            replace(r, disability=0))
    if setting.tier == "hard":
        misread["reported_changes"] = ("every application as filed", replace(r, changes="none"))
    for target, (what, reading) in misread.items():
        out[f"misread_{target}"] = (target, what, determinations(world, reading))
    # misreadings no reading of the diagnostic holds as such, and two misread facts at once
    up = 32 if r.uprating != 30 else 27
    other = {name: next((v for v in POOLS[name][setting.tier] if str(v) != str(setting[name])), setting[name])
             for name in ("uprating", "earned_disregard", "residency_days", "asset_limit")}
    flat, ignored = EARNED[str(other["earned_disregard"])]
    unlisted = {"guessed_uprating": ("uprating", f"a guessed uprating of {up / 10:g}%", replace(r, uprating=up)),
                "guessed_disregard": ("earned_disregard", "a guessed disregard: the first 120 and 25% of the rest",
                                      replace(r, earned_flat=120, earned_ignored=25)),
                "uprating_and_disregard": (("uprating", "earned_disregard"), "another candidate uprating and "
                                           "another candidate disregard together", replace(
                                               r, uprating=round(float(other["uprating"]) * 10), earned_flat=flat,
                                               earned_ignored=ignored))}
    if setting.tier != "easy":
        unlisted["guessed_supplement"] = ("disability_supplement", "a guessed supplement of 90",
                                          replace(r, disability=90))
        unlisted["residency_and_asset_limit"] = (("residency", "asset_limit"), "another candidate residency period "
                                                 "and another candidate asset limit together", replace(
                                                     r, residency_days=int(other["residency_days"]),
                                                     asset_limit=ASSET_LIMITS[str(other["asset_limit"])]))
        unlisted["uprating_and_cap"] = (("uprating", "amount_cap"), "another candidate uprating and no cap",
                                        replace(r, uprating=round(float(other["uprating"]) * 10), cap=None))
    if setting.tier == "hard":
        unlisted["rent_changes_only"] = ("reported_changes", "only the new rents in effect applied (the earnings "
                                         "changes ignored)", replace(r, changes="rent"))
    for name, (target, what, reading) in unlisted.items():
        out[name] = (target, what, determinations(world, reading))
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
