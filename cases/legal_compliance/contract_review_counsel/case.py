"""Supplier contract review against the company playbook (original FDE-Bench v2 case).

The legal team of Brightvale Holdings sends 44 supplier contracts (one text
file each, each dated as a draft), the contract register, a folder of
amendment records and two e-mails from business owners, and asks which
contracts need changes before signature. The request is vague; the playbook
that decides what counts as an issue, the issue codes, who may sign what and
the small-contract fast track are in the hidden requirements and must be asked
for.

Settings: three tiers x rule seeds. easy checks four points (liability cap,
governing law, payment term, mutual indemnity) on the contracts on our own
paper and wants only those four listed; medium adds auto-renewal notice, caps
of N months' fees, data protection by category, termination for convenience by
value and the dispute forum; hard adds the supplier-paper contracts, the
amendment records (only a change agreed after the draft counts), customers'
personal data outside the listed categories, business owners' pressure to
sign, and the fast track. A rule seed draws the playbook's figures (cap
multiple, accepted laws, payment days, how many critical issues make a reject,
the value below which non-critical issues are accepted, renewal notice,
data-protection categories, termination threshold, fast-track threshold) from
candidate pools; the generator places contract values, caps, notice and
payment terms on both sides of every candidate.

Scoring: the share of the scored contracts whose issue list and decision are
both exactly the playbook's. The decision is a judgement of its own: it needs
the issues, which of them are critical, how many of those make a reject and
the contract's annual value against the sign-off limit.

Clauses are written with varied wording, so plain keyword matching misses some
of them; some contracts are on the supplier's paper in another language. The
reference is the answer key (the playbook applied to every clause as written);
the baseline is the legal team's own keyword checklist, which knows the
playbook but reads clauses by keywords.
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from itertools import pairwise, product
from pathlib import Path

import yaml

from fdebench2.casekit import Fatal, labels, read_json, write_csv
from fdebench2.cases import TIERS, Setting, param_pools

_META = yaml.safe_load((Path(__file__).with_name("case.yaml")).read_text(encoding="utf-8"))

# ── playbook ─────────────────────────────────────────────────────────────────

CODES = ("LIABILITY_CAP", "GOVERNING_LAW", "AUTO_RENEWAL", "PAYMENT_TERMS", "DATA_PROTECTION",
         "TERMINATION_CONVENIENCE", "INDEMNITY")
EASY_CODES = ("LIABILITY_CAP", "GOVERNING_LAW", "PAYMENT_TERMS", "INDEMNITY")   # the four points of the easy round
CRITICAL = ("LIABILITY_CAP", "DATA_PROTECTION", "INDEMNITY")
DECISIONS = ("sign", "negotiate", "reject")
# A small contract taken off the fast track under an approved exception: one the playbook rejects, reviewed exactly
# right, counts as 1 + EXCEPTION_BONUS contracts (it would have been signed unread); any other counts as none.
EXCEPTION_BONUS = 1.0
# governing_law candidates: the jurisdictions whose law (and, from medium, whose courts or seat) we accept
ALLOWED = {"CH_SG": ("CH", "SG"), "CH_SG_EW": ("CH", "SG", "EW"), "SG": ("SG",)}
DP_CATEGORIES = {"it_data": ("it_data",), "it_data_marketing": ("it_data", "marketing")}
# the article an amendment record replaces -> the playbook point it can change
CLAUSE_CODE = {"law": "GOVERNING_LAW", "pay": "PAYMENT_TERMS", "indemnity": "INDEMNITY", "cap": "LIABILITY_CAP",
               "renew": "AUTO_RENEWAL"}

CATEGORIES = ("it_data", "logistics", "facilities", "raw_materials", "marketing", "professional")
N_CONTRACTS = 44
N_FOREIGN = 6                  # contracts on the supplier's own paper
N_CUSTOMER_DATA = 4            # scopes that hand the supplier our customers' personal data (all but one lack the clause)
MAX_SPECIAL_PER_BAND = 2       # supplier-paper, amended and e-mailed contracts per band between two mid thresholds
EMAIL_DATES = ("2026-10-27", "2026-10-28")


def _pools() -> dict[str, dict[str, list]]:
    return param_pools(_META, tuple(t for t in TIERS if t in _META["tiers"]))


def _candidates(name: str) -> list:
    """Every candidate of a parameter over all tiers, sorted: the generator puts data on both sides of each."""
    return sorted({v for pool in _pools()[name].values() for v in pool})


FAST_TRACK_CANDIDATES = _candidates("fast_track_below")
TFC_CANDIDATES = _candidates("tfc_above")
TOLERANCE_CANDIDATES = _candidates("tolerance_below")
# the value thresholds above every fast-track candidate (termination for convenience, the sign-off limit)
MID_CANDIDATES = sorted(set(TFC_CANDIDATES) | set(TOLERANCE_CANDIDATES))


# ── world ────────────────────────────────────────────────────────────────────

@dataclass
class Contract:
    id: str
    value: int
    category: str
    foreign: bool              # supplier's own paper, written in another language
    name_idx: int
    term_years: int
    renew: tuple | None        # (notice_days, phrasing "x"|"p", notice phrasing "d"|"w") or None
    pay: tuple                 # (days, phrasing "d"|"w"|"n")
    dp: str | None             # None (no clause), "x" explicit, "p" paraphrased
    tfc: tuple | None          # (notice_days, phrasing) or None
    indemnity: str             # "mutual_x" | "mutual_p" | "one_way"
    cap: tuple                 # ("mult", m, "d"|"w") | ("amount", usd, "d"|"p") | ("period", months) | ("unlimited",)
    law: tuple                 # (law code, law phrasing "x"|"swiss", venue code, "courts"|"arb")
    draft: str = ""            # date of the draft (ISO)
    cust_data: bool = False    # the scope says the supplier handles personal data of our own customers

    def cap_ratio(self) -> float:
        """The cap as a multiple of the annual value (inf when liability is not capped)."""
        kind = self.cap[0]
        if kind == "mult":
            return float(self.cap[1])
        if kind == "amount":
            return self.cap[1] / self.value
        if kind == "period":
            return self.cap[1] / 12
        return float("inf")


@dataclass
class Amendment:
    """A record in the amendments folder: a negotiated change to one article of a contract's draft."""
    contract: str
    date: str                  # ISO
    status: str                # "agreed" (both parties) | "proposed" (by the supplier, not accepted)
    clause: str                # the Contract field it replaces: "law" | "pay" | "indemnity" | "cap" | "renew"
    new: object                # the new value of that field


@dataclass
class World:
    contracts: list[Contract]
    amendments: dict[str, Amendment] = field(default_factory=dict)
    emails: list[tuple[str, ...]] = field(default_factory=list)    # per e-mail, the contracts it asks us to just sign

    def by_id(self) -> dict[str, Contract]:
        return {c.id: c for c in self.contracts}

    def emailed(self) -> tuple[str, ...]:
        return tuple(cid for mail in self.emails for cid in mail)


def as_read(world: World, c: Contract, mode: str = "after_draft") -> Contract:
    """The contract with its amendment record applied, or not. "after_draft" is the playbook's reading (a change
    agreed by both parties and dated after the draft), "agreed" applies every record marked agreed whatever its
    date, "all" every record, "none" ignores the folder."""
    a = world.amendments.get(c.id)
    if a is None or mode == "none":
        return c
    applies = {"after_draft": a.status == "agreed" and a.date > c.draft, "agreed": a.status == "agreed",
               "all": True}[mode]
    return replace(c, **{a.clause: a.new}) if applies else c


def scored(world: World, c: Contract, setting: Setting) -> bool:
    """easy and medium leave the supplier-paper, amended and e-mailed contracts to procurement; hard scores all."""
    if setting.at_least("hard"):
        return True
    return not (c.foreign or c.id in world.amendments or c.id in world.emailed())


def _wpick(rng: random.Random, pairs):
    vals, weights = zip(*pairs)
    return rng.choices(vals, weights=weights)[0]


def _values(rng: random.Random) -> list[int]:
    """The annual values (multiples of USD 1,000): on both sides of every fast-track, termination and sign-off
    candidate, and exactly at each candidate (the thresholds are strict)."""
    ft, mid = FAST_TRACK_CANDIDATES, MID_CANDIDATES
    edges = [5_000] + ft + mid + [1_200_000]
    # contracts per open band between consecutive edges: few small ones, six between two mid thresholds, the rest
    # above every candidate
    counts = [3] + [3] * (len(ft) - 2) + [2] + [7] + [6] * (len(mid) - 1) + [0]
    counts[-1] = N_CONTRACTS - len(ft) - len(mid) - sum(counts[:-1])
    values = list(ft) + list(mid)
    for (lo, hi), n in zip(pairwise(edges), counts):
        values += [rng.randrange(lo + 1_000, hi, 1_000) for _ in range(n)]
    rng.shuffle(values)
    return values


AMOUNT_BAND = {0.5: (0, 1), 0.75: (0, 1), 1.25: (1, 1.5), 1.75: (1.5, 2), 3.0: (2, 99)}


def _amount(value: int, r: float) -> int:
    """A fixed cap of about r x value: exactly r x value at a candidate multiple (1, 1.5, 2), else a round sum that
    stays strictly between the candidates around r."""
    if r not in AMOUNT_BAND:
        return int(value * r)
    lo, hi = AMOUNT_BAND[r]
    for step in (5_000, 1_000, 500):
        amt = round(value * r / step) * step
        if lo * value < amt < hi * value and amt >= 1_000:
            return amt
    return int(value * r)


def _date(d: date) -> str:
    return d.isoformat()


def _draw_contract(rng: random.Random, i: int, value: int, cat: str, name_idx: int) -> Contract:
    para = lambda p=0.25: rng.random() < p  # noqa: E731
    renew = None
    if rng.random() < 0.6:
        notice = _wpick(rng, [(30, 2), (45, 2), (60, 3), (90, 3)])
        renew = (notice, "p" if para() else "x", "w" if para() else "d")
    pay = (_wpick(rng, [(15, 1.5), (30, 3), (45, 3), (60, 3), (90, 2)]),
           _wpick(rng, [("d", 6), ("w", 2.5), ("n", 1.5)]))
    dp_present = rng.random() < (0.55 if cat == "it_data" else 0.4)
    dp = ("p" if para() else "x") if dp_present else None
    tfc = (rng.choice([30, 60, 90]), "p" if para() else "x") if rng.random() < 0.55 else None
    indemnity = _wpick(rng, [("mutual_x", 5), ("mutual_p", 2), ("one_way", 3)])
    kind = _wpick(rng, [("mult", 4), ("amount", 4), ("period", 2.5), ("unlimited", 1)])
    if kind == "mult":
        cap = ("mult", _wpick(rng, [(0.5, 3), (1, 2), (1.5, 2), (2, 2), (3, 1)]), "w" if para(0.4) else "d")
    elif kind == "amount":
        r = _wpick(rng, [(0.5, 2), (0.75, 2), (1.0, 2), (1.25, 1.5), (1.5, 1.5), (1.75, 1), (2.0, 1.5), (3.0, 1)])
        cap = ("amount", _amount(value, r), "p" if para() else "d")
    elif kind == "period":
        cap = ("period", _wpick(rng, [(6, 2), (12, 2), (18, 1), (24, 1)]))
    else:
        cap = ("unlimited",)
    law_code = _wpick(rng, [("CH", 3.5), ("SG", 3), ("EW", 1.2), ("NY", 1), ("HK", 0.8), ("DE", 0.8)])
    law_phr = "swiss" if law_code == "CH" and rng.random() < 0.45 else "x"
    venue = law_code if rng.random() < 0.6 else _wpick(rng, [("SG", 3), ("CH", 1), ("EW", 1), ("NY", 1), ("HK", 1)])
    law = (law_code, law_phr, venue, "arb" if rng.random() < 0.5 else "courts")
    draft = _date(date(2026, 9, 1) + timedelta(days=rng.randrange(0, 50)))
    return Contract(id=f"C{i + 1:03d}", value=value, category=cat, foreign=False, name_idx=name_idx,
                    term_years=rng.choice([1, 2, 3]), renew=renew, pay=pay, dp=dp, tfc=tfc, indemnity=indemnity,
                    cap=cap, law=law, draft=draft)


def build_world(seed: int) -> World:
    rng = random.Random(seed)
    values = _values(rng)
    cats = [CATEGORIES[i % len(CATEGORIES)] for i in range(N_CONTRACTS)]
    cats[:6] = ["it_data"] * 6  # IT & data is the biggest spend category
    rng.shuffle(cats)
    names = list(range(N_CONTRACTS))
    rng.shuffle(names)
    world = World([_draw_contract(rng, i, values[i], cats[i], names[i]) for i in range(N_CONTRACTS)])
    set_aside = _add_situations(rng, world)
    _cover_thresholds(rng, world, set_aside)
    return world


def _mid_band(value: int) -> int | None:
    """Which band between two consecutive mid thresholds a value lies in ([lo, hi)), None outside them."""
    for k, (lo, hi) in enumerate(pairwise(MID_CANDIDATES)):
        if lo <= value < hi:
            return k
    return None


def _add_situations(rng: random.Random, world: World) -> set[str]:
    """The hard tier's situations, present in the data in every setting, all on contracts above every fast-track
    candidate and off the mid thresholds: customers' personal data outside the data-protection categories, six
    contracts on supplier paper, six amendment records and two business owners' e-mails about three contracts.
    Returns the ids easy and medium leave out (supplier paper, amended, e-mailed)."""
    top = FAST_TRACK_CANDIDATES[-1]
    big = [c for c in world.contracts if c.value > top and c.value not in MID_CANDIDATES]
    rng.shuffle(big)
    used: set[str] = set()
    per_band: Counter = Counter()

    def take(n: int, ok=lambda c: True) -> list[Contract]:
        out = []
        for c in big:
            band = _mid_band(c.value)
            if len(out) == n:
                break
            if c.id in used or not ok(c) or (band is not None and per_band[band] >= MAX_SPECIAL_PER_BAND):
                continue
            out.append(c)
            used.add(c.id)
            per_band[band] += band is not None
        return out

    # customers' personal data in a logistics or professional-services scope: all but one without a clause
    cust = take(N_CUSTOMER_DATA, lambda c: c.category in CUST_DESC)
    for c in take(N_CUSTOMER_DATA - len(cust), lambda c: c.category not in ("it_data", "marketing")):
        c.category = rng.choice(sorted(CUST_DESC))
        cust.append(c)
    for k, c in enumerate(cust):
        c.cust_data = True
        c.dp = None if k < N_CUSTOMER_DATA - 1 else (c.dp or "x")
    in_every_tier = set(used)
    foreign, amended, emailed = take(N_FOREIGN), take(6), take(3)
    if (len(cust), len(foreign), len(amended), len(emailed)) != (N_CUSTOMER_DATA, N_FOREIGN, 6, 3):
        raise ValueError("not enough contracts above the fast track for the hard tier's situations")
    for c in foreign:
        c.foreign = True
    a, b, p, s1, s2, s3 = amended
    # agreed after the draft, so they count: Singapore law and seat become New York law and courts; payment within
    # 15 days becomes 60 days
    a.law = ("SG", "x", "SG", a.law[3])
    world.amendments[a.id] = Amendment(a.id, _after(rng, a), "agreed", "law", ("NY", "x", "NY", "courts"))
    b.pay = (15, b.pay[1])
    world.amendments[b.id] = Amendment(b.id, _after(rng, b), "agreed", "pay", (60, b.pay[1]))
    # proposed by the supplier and not accepted: the mutual indemnity becomes one-way
    p.indemnity = "mutual_x"
    world.amendments[p.id] = Amendment(p.id, _after(rng, p), "proposed", "indemnity", "one_way")
    # agreed, but dated before the draft, which supersedes them: a cap of half the fees raised to twice; a one-way
    # indemnity made mutual; New York law and courts replaced by Singapore law and seat
    s1.cap = ("mult", 0.5, "d")
    world.amendments[s1.id] = Amendment(s1.id, _before(rng, s1), "agreed", "cap", ("mult", 2, "d"))
    s2.indemnity = "one_way"
    world.amendments[s2.id] = Amendment(s2.id, _before(rng, s2), "agreed", "indemnity", "mutual_x")
    s3.law = ("NY", "x", "NY", "courts")
    world.amendments[s3.id] = Amendment(s3.id, _before(rng, s3), "agreed", "law", ("SG", "x", "SG", "arb"))
    # the e-mailed contracts: none of them is a "sign" under any candidate playbook. The first caps liability at
    # half the fees and has a one-way indemnity (a reject everywhere); the pair of the second e-mail has a one-way
    # indemnity and a cap of half the fees
    e1, e2, e3 = emailed
    e1.cap, e1.indemnity = ("mult", 0.5, "d"), "one_way"
    e2.indemnity = "one_way"
    e3.cap = ("mult", 0.5, "d")
    world.emails = [(e1.id,), tuple(sorted((e2.id, e3.id)))]
    return used - in_every_tier


def _after(rng: random.Random, c: Contract) -> str:
    return _date(min(date.fromisoformat(c.draft) + timedelta(days=rng.randrange(3, 15)), date(2026, 10, 26)))


def _before(rng: random.Random, c: Contract) -> str:
    return _date(date.fromisoformat(c.draft) - timedelta(days=rng.randrange(5, 21)))


def _ensure(rng: random.Random, pool: list[Contract], has, make, n: int = 3) -> None:
    """Make at least n contracts of the pool satisfy `has`, changing as few as possible with `make`."""
    rest = [c for c in pool if not has(c)]
    for c in rng.sample(rest, max(0, min(n - (len(pool) - len(rest)), len(rest)))):
        make(c)


def _cover_thresholds(rng: random.Random, world: World, set_aside: set[str]) -> None:
    """Make every candidate figure and every fixed fact change answers on the core contracts: those every tier
    scores and no fast-track candidate takes out of review (above the largest fast-track candidate, on our own
    paper, without an amendment record or an e-mail).

    - termination: a contract exactly at a candidate has no termination right (only a non-strict reading flags it),
      and every band between candidates has three without it;
    - the sign-off limit: three contracts in every band between its candidates have no critical issue under any
      candidate and one non-critical issue under every candidate (payment within 15 days, or a law nobody accepts);
    - data protection: three marketing contracts without a clause (two in IT);
    - renewal: three auto-renewing contracts with 45 days' notice and three with 60 (what two candidates tell apart);
    - the law and the forum: three contracts under Singapore law with courts or a seat that no candidate accepts,
      two under a law no candidate accepts with a Singapore seat (only the law is wrong), and three under English
      law with a London forum (what the widest candidate accepts and the others do not);
    - the liability cap: three caps between the first two candidate multiples and three between the last two,
      written as a multiple or a fixed amount.
    Among the small contracts (scored in easy and medium, where there is no fast track), three are capped at six
    months' fees, which the easy round does not flag."""
    top = FAST_TRACK_CANDIDATES[-1]
    core = [c for c in world.contracts if c.value > top and c.id not in set_aside]
    for c in world.contracts:
        if c.value in TFC_CANDIDATES:
            c.tfc = None
    for lo, hi in zip(TFC_CANDIDATES, TFC_CANDIDATES[1:] + [10 ** 9]):
        _ensure(rng, [c for c in core if lo < c.value <= hi], lambda c: c.tfc is None,
                lambda c: setattr(c, "tfc", None))
    probes: set[str] = set()
    for lo, hi in pairwise(TOLERANCE_CANDIDATES):
        band = [c for c in core if lo <= c.value < hi and not c.cust_data]
        for c in rng.sample(band, min(3, len(band))):
            _minor_only(rng, c)
            probes.add(c.id)
    rest = [c for c in core if c.id not in probes and not c.cust_data]
    marketing = [c for c in rest if c.category == "marketing"]
    others = [c for c in rest if c.category not in ("it_data", "marketing")]
    for c in rng.sample(others, max(0, min(3 - len(marketing), len(others)))):
        c.category = "marketing"
        marketing.append(c)
    _ensure(rng, marketing, lambda c: c.dp is None, lambda c: setattr(c, "dp", None))
    _ensure(rng, [c for c in rest if c.category == "it_data"], lambda c: c.dp is None,
            lambda c: setattr(c, "dp", None), n=2)
    for notice in (45, 60):
        _ensure(rng, [c for c in core if c.renew is None or c.renew[0] == notice], lambda c: c.renew is not None,
                lambda c, notice=notice: setattr(c, "renew", (notice, "x", "d")))
    free = [c for c in rest if c.law[0] == c.law[2]]
    picked = rng.sample(free, min(5, len(free)))
    for c in picked[:3]:
        c.law = ("SG", "x", rng.choice(["NY", "HK"]), c.law[3])
    for c in picked[3:]:
        c.law = (rng.choice(["HK", "NY", "DE"]), "x", "SG", c.law[3])
    split = {c.id for c in picked}
    _ensure(rng, [c for c in core if c.id not in split and c.law[0] in ("CH", "SG", "EW")],
            lambda c: (c.law[0], c.law[2]) == ("EW", "EW"), lambda c: setattr(c, "law", ("EW", "x", "EW", c.law[3])))

    def between(lo: float, hi: float):
        return lambda c: c.cap[0] in ("mult", "amount") and lo <= c.cap_ratio() < hi

    def cap_at(ratios: tuple[float, float]):
        def make(c: Contract) -> None:
            c.cap = (("mult", ratios[0], rng.choice("dw")) if rng.random() < 0.5 else
                     ("amount", _amount(c.value, rng.choice(ratios)), rng.choice("dp")))
        return make
    _ensure(rng, rest, between(1, 1.5), cap_at((1.0, 1.25)))
    _ensure(rng, [c for c in rest if not between(1, 1.5)(c)], between(1.5, 2), cap_at((1.5, 1.75)))
    small = [c for c in world.contracts if c.value <= top]
    _ensure(rng, small, lambda c: c.cap == ("period", 6), lambda c: setattr(c, "cap", ("period", 6)))


def _minor_only(rng: random.Random, c: Contract) -> None:
    """Make a contract one that no candidate playbook finds a critical issue in, with a non-critical issue that
    every candidate playbook finds in every tier: whether it is signed turns on the sign-off limit alone."""
    if c.cap_ratio() < 2:
        c.cap = rng.choice([("mult", 2, "d"), ("mult", 3, "w"), ("amount", _amount(c.value, 2.0), "d"),
                            ("unlimited",), ("period", 24)])
    if c.indemnity == "one_way":
        c.indemnity = rng.choice(["mutual_x", "mutual_p"])
    if c.category in ("it_data", "marketing") and c.dp is None:
        c.dp = rng.choice(["x", "p"])
    if c.pay[0] != 15 and c.law[0] in ("CH", "SG", "EW"):
        if rng.random() < 0.5:
            c.pay = (15, c.pay[1])
        else:
            c.law = (rng.choice(["NY", "HK", "DE"]), "x", c.law[2], c.law[3])


# ── localized texts ──────────────────────────────────────────────────────────

FILES = {
    "register": {"zh": "合同台账.csv", "en": "contract_register.csv", "ko": "계약대장.csv", "ja": "契約台帳.csv",
                 "es": "registro_contratos.csv"},
    "folder": {"zh": "合同文本", "en": "contracts", "ko": "계약서", "ja": "契約書", "es": "contratos"},
    "amendments": {"zh": "修改记录", "en": "amendments", "ko": "수정기록", "ja": "修正記録", "es": "modificaciones"},
    "emails": {"zh": "邮件", "en": "emails", "ko": "메일", "ja": "メール", "es": "correos"},
}
COLS = {
    "id": {"zh": "合同编号", "en": "contract_id", "ko": "계약번호", "ja": "契約番号", "es": "id_contrato"},
    "supplier": {"zh": "供应商", "en": "supplier", "ko": "공급업체", "ja": "取引先", "es": "proveedor"},
    "category": {"zh": "采购类别", "en": "category", "ko": "구매분류", "ja": "調達区分", "es": "categoria"},
    "value": {"zh": "年度金额_美元", "en": "annual_value_usd", "ko": "연간금액_USD", "ja": "年間金額_USD",
              "es": "importe_anual_usd"},
    "file": {"zh": "合同文件", "en": "contract_file", "ko": "계약서파일", "ja": "契約書ファイル", "es": "archivo_contrato"},
}
CAT_LABEL = {
    "it_data": {"zh": "IT与数据服务", "en": "IT & data services", "ko": "IT·데이터 서비스", "ja": "IT・データサービス",
                "es": "TI y servicios de datos"},
    "logistics": {"zh": "物流运输", "en": "Logistics", "ko": "물류", "ja": "物流", "es": "Logística"},
    "facilities": {"zh": "物业设施", "en": "Facilities", "ko": "시설관리", "ja": "施設管理",
                   "es": "Mantenimiento de instalaciones"},
    "raw_materials": {"zh": "原材料", "en": "Raw materials", "ko": "원자재", "ja": "原材料", "es": "Materias primas"},
    "marketing": {"zh": "市场营销", "en": "Marketing", "ko": "마케팅", "ja": "マーケティング", "es": "Marketing"},
    "professional": {"zh": "专业服务", "en": "Professional services", "ko": "전문 서비스", "ja": "専門サービス",
                     "es": "Servicios profesionales"},
}
DESC = {
    "it_data": {"zh": "云托管、软件运维及相关数据服务", "en": "cloud hosting, software maintenance and related data services",
                "ko": "클라우드 호스팅, 소프트웨어 유지보수 및 관련 데이터 서비스",
                "ja": "クラウドホスティング、ソフトウェア保守および関連するデータサービス",
                "es": "servicios de alojamiento en la nube, mantenimiento de software y tratamiento de datos asociados"},
    "logistics": {"zh": "仓储及公路货运服务", "en": "warehousing and road freight services",
                  "ko": "창고 보관 및 도로 화물 운송 서비스", "ja": "倉庫保管および陸上輸送サービス",
                  "es": "servicios de almacenaje y transporte de mercancías por carretera"},
    "facilities": {"zh": "保洁及楼宇维护服务", "en": "cleaning and building maintenance services",
                   "ko": "청소 및 건물 유지관리 서비스", "ja": "清掃および建物保守サービス",
                   "es": "servicios de limpieza y mantenimiento de edificios"},
    "raw_materials": {"zh": "包装材料及工业零部件", "en": "packaging materials and industrial components",
                      "ko": "포장재 및 산업용 부품의 공급 서비스", "ja": "包装資材および工業用部品",
                      "es": "el suministro de materiales de embalaje y componentes industriales"},
    "marketing": {"zh": "广告投放及活动策划服务", "en": "advertising campaign and event services",
                  "ko": "광고 캠페인 및 행사 대행 서비스", "ja": "広告キャンペーンおよびイベント運営サービス",
                  "es": "servicios de campañas publicitarias y organización de eventos"},
    "professional": {"zh": "咨询及翻译服务", "en": "consulting and translation services",
                     "ko": "컨설팅 및 번역 서비스", "ja": "コンサルティングおよび翻訳サービス",
                     "es": "servicios de consultoría y traducción"},
}
# A scope under which the supplier handles personal data of our own customers (hard: needs the clause too).
CUST_DESC = {
    "logistics": {
        "zh": "仓储及公路货运服务，包括向甲方的客户送货上门，甲方为此向乙方提供客户的姓名、收货地址和电话号码",
        "en": "warehousing and road freight services, including home deliveries to the Customer's own customers, for"
              " which the Customer passes on their names, delivery addresses and telephone numbers",
        "ko": "창고 보관 및 도로 화물 운송 서비스(갑의 고객에게 직접 배송하는 업무를 포함하며, 이를 위해 갑은 고객의 이름, 배송"
              " 주소 및 전화번호를 을에게 제공한다)",
        "ja": "倉庫保管および陸上輸送サービス（甲の顧客への個別配送を含み、甲はそのために顧客の氏名、配送先住所および電話番号を乙に"
              "提供する）",
        "es": "servicios de almacenaje y transporte de mercancías por carretera, incluidas las entregas a domicilio a los"
              " propios clientes del Cliente, para las que este le facilita sus nombres, direcciones de entrega y"
              " números de teléfono"},
    "professional": {
        "zh": "咨询及翻译服务，包括翻译甲方致其客户的信函，信函中载有客户的姓名、地址和账户信息",
        "en": "consulting and translation services, including the translation of the Customer's letters to its own"
              " customers, which contain their names, addresses and account details",
        "ko": "컨설팅 및 번역 서비스(갑이 자사 고객에게 보내는 서신의 번역을 포함하며, 서신에는 고객의 이름, 주소 및 계좌 정보가"
              " 들어 있다)",
        "ja": "コンサルティングおよび翻訳サービス（甲が自社の顧客に送付する書簡の翻訳を含み、書簡には顧客の氏名、住所および口座情報が"
              "記載されている）",
        "es": "servicios de consultoría y traducción, incluida la traducción de las cartas del Cliente a sus propios"
              " clientes, que contienen sus nombres, direcciones y datos de cuenta"},
}


def _desc(c: Contract, lang: str) -> str:
    return (CUST_DESC if c.cust_data else DESC)[c.category][lang]


NAME_PREFIX = {
    "zh": ["华信", "恒达", "嘉禾", "远航", "博瑞", "鼎盛", "金石", "联创", "海川", "星河", "天成", "盛世", "安泰", "宏图",
           "新元", "瑞丰", "卓远", "万通", "聚力", "云帆", "青松", "立德", "永兴", "合众", "明川", "启航", "博远", "德润",
           "凯盛", "华茂", "信达", "锦程", "致远", "嘉信", "长风", "润泽", "和信", "众诚", "瀚海", "隆泰", "正阳", "广源",
           "同心", "骏业"],
    "en": ["Ashford", "Brookline", "Carrow", "Denholm", "Elmstead", "Fairhaven", "Glenmore", "Harrowgate", "Ivybridge",
           "Kestrel", "Larkfield", "Merriton", "Northcote", "Oakhurst", "Penbury", "Quarry Hill", "Redmarsh",
           "Stanwick", "Thornbury", "Upton Vale", "Westcliff", "Yarrow", "Alder", "Beckett", "Coldwater", "Draycott",
           "Everleigh", "Foxley", "Greystone", "Hartwell", "Kingsmere", "Lindale", "Millbrook", "Newhaven", "Ormsby",
           "Pemberton", "Rowan", "Silverdale", "Tamworth", "Wexley", "Abbotsford", "Briarwood", "Calder", "Dunmore"],
    "ko": ["한빛", "대성", "미래", "동양", "새한", "청운", "태양", "우진", "세진", "한결", "금강", "서원", "늘푸른", "다온",
           "해솔", "가온", "누리", "동인", "신우", "영진", "백산", "하나로", "정우", "초록", "바른", "온누리", "대원",
           "성원", "해든", "진명", "은하", "수성", "단비", "한울", "아라", "솔빛", "보람", "새솔", "한마음", "푸른숲", "두레",
           "새벽", "한솔", "미르"],
    "ja": ["山王", "東光", "北辰", "若葉", "青葉", "富士見", "緑川", "白鷺", "三輪", "桜井", "高砂", "光陽", "栄進", "明和",
           "誠和", "日進", "共栄", "金剛", "大翔", "瑞穂", "早瀬", "朝霧", "葵", "楓", "新星", "弥生", "雅", "秋津",
           "柏木", "泉", "春日", "白樺", "常盤", "豊和", "長門", "鳳", "睦", "藤波", "曙", "清流", "千歳", "大和", "双葉",
           "湊"],
    "es": ["Ibérica", "Levante", "Cantábrica", "Meseta", "Albor", "Atalaya", "Brisa", "Cumbre", "Duero", "Ebro",
           "Faro", "Genil", "Horizonte", "Jara", "Lince", "Mirador", "Olivo", "Pinar", "Quercus", "Ribera", "Sierra",
           "Tajo", "Umbral", "Vega", "Zafiro", "Alameda", "Bahía", "Candil", "Delta", "Encina", "Fuente", "Galena",
           "Hispalis", "Lucero", "Marisma", "Nogal", "Oriente", "Peñalara", "Retama", "Solana", "Tormes", "Alcázar",
           "Miramar", "Valdés"],
}
NAME_SUFFIX = {
    "zh": {"it_data": "科技有限公司", "logistics": "物流有限公司", "facilities": "物业服务有限公司",
           "raw_materials": "材料有限公司", "marketing": "文化传媒有限公司", "professional": "咨询有限公司"},
    "en": {"it_data": "Digital Ltd", "logistics": "Logistics Ltd", "facilities": "Facility Services Ltd",
           "raw_materials": "Materials Ltd", "marketing": "Media Ltd", "professional": "Consulting Ltd"},
    "ko": {"it_data": "테크", "logistics": "로지스틱스", "facilities": "시설관리", "raw_materials": "소재",
           "marketing": "애드", "professional": "컨설팅"},
    "ja": {"it_data": "テクノロジー株式会社", "logistics": "運輸株式会社", "facilities": "ビルサービス株式会社",
           "raw_materials": "資材株式会社", "marketing": "企画株式会社", "professional": "コンサルティング株式会社"},
    "es": {"it_data": "Sistemas S.L.", "logistics": "Logística S.A.", "facilities": "Servicios Integrales S.L.",
           "raw_materials": "Materiales S.A.", "marketing": "Comunicación S.L.", "professional": "Consultores S.L."},
}
JUR = {
    "CH": {"zh": "瑞士", "en": "Switzerland", "ko": "스위스", "ja": "スイス", "es": "Suiza"},
    "SG": {"zh": "新加坡", "en": "Singapore", "ko": "싱가포르", "ja": "シンガポール", "es": "Singapur"},
    "EW": {"zh": "英格兰和威尔士", "en": "England and Wales", "ko": "잉글랜드 및 웨일스", "ja": "イングランドおよびウェールズ",
           "es": "Inglaterra y Gales"},
    "NY": {"zh": "美国纽约州", "en": "the State of New York", "ko": "미국 뉴욕주", "ja": "米国ニューヨーク州",
           "es": "el Estado de Nueva York"},
    "HK": {"zh": "香港特别行政区", "en": "the Hong Kong SAR", "ko": "홍콩특별행정구", "ja": "香港特別行政区",
           "es": "la RAE de Hong Kong"},
    "DE": {"zh": "德国", "en": "Germany", "ko": "독일", "ja": "ドイツ", "es": "Alemania"},
}
CITY = {
    "CH": {"zh": "苏黎世", "en": "Zurich", "ko": "취리히", "ja": "チューリッヒ", "es": "Zúrich"},
    "SG": {"zh": "新加坡", "en": "Singapore", "ko": "싱가포르", "ja": "シンガポール", "es": "Singapur"},
    "EW": {"zh": "伦敦", "en": "London", "ko": "런던", "ja": "ロンドン", "es": "Londres"},
    "NY": {"zh": "纽约", "en": "New York", "ko": "뉴욕", "ja": "ニューヨーク", "es": "Nueva York"},
    "HK": {"zh": "香港", "en": "Hong Kong", "ko": "홍콩", "ja": "香港", "es": "Hong Kong"},
    "DE": {"zh": "法兰克福", "en": "Frankfurt", "ko": "프랑크푸르트", "ja": "フランクフルト", "es": "Fráncfort"},
}
CUSTOMER = {"zh": "明谷集团", "en": "Brightvale Holdings", "ko": "브라이트베일 홀딩스", "ja": "ブライトベール・ホールディングス",
            "es": "Brightvale Holdings"}


def supplier_name(c: Contract, lang: str) -> str:
    """The name as it appears in this locale's data; foreign suppliers write in their own language."""
    tl = text_lang(c, lang)
    pre = NAME_PREFIX[tl][c.name_idx]
    suf = NAME_SUFFIX[tl][c.category]
    if tl == "ko":
        return f"(주){pre}{suf}"
    if tl in ("en", "es"):
        return f"{pre} {suf}"
    return pre + suf


def text_lang(c: Contract, lang: str) -> str:
    if not c.foreign:
        return lang
    return "es" if lang == "en" else "en"


def _fmt_mult(m: float, decimal: str = ".") -> str:
    s = f"{m:g}"
    return s.replace(".", decimal)


EN_WORDS = {15: "fifteen", 30: "thirty", 45: "forty-five", 60: "sixty", 90: "ninety"}
EN_MONTHS = {30: "one month", 45: "forty-five days", 60: "two months", 90: "three months"}
EN_PERIOD = {6: "six", 12: "twelve", 18: "eighteen", 24: "twenty-four"}
EN_YEARS = {1: "one year", 2: "two years", 3: "three years"}


def _render_en(c: Contract, supplier: str, cust: str) -> list[tuple[str, list[str]]]:
    arts = []
    term = f"This Agreement starts on the date of signature and runs for an initial term of {EN_YEARS[c.term_years]}."
    if c.renew is None:
        term += " It then expires unless the parties agree a renewal in writing."
    else:
        d, rp, np_ = c.renew
        notice = f"{d} days" if np_ == "d" else EN_MONTHS[d]
        if rp == "x":
            term += (" It then renews automatically for successive one-year periods unless either party gives written"
                     f" notice of non-renewal at least {notice} before the end of the current term.")
        else:
            term += (" At the end of each term the Agreement continues for a further year on the same conditions,"
                     f" unless a party objects in writing no later than {notice} before the term ends.")
    arts.append(("Scope and Term", [f"The Supplier provides the Customer with {_desc(c, 'en')}.", term]))
    d, pp = c.pay
    pay = {"d": f"The Customer shall pay each undisputed invoice within {d} days of receipt.",
           "w": f"The Customer shall pay each undisputed invoice within {EN_WORDS[d]} days of receipt.",
           "n": f"Undisputed invoices are payable net {d} from the date of receipt."}[pp]
    arts.append(("Fees and Payment", ["The fees are set out in the order forms agreed between the parties.", pay]))
    arts.append(("Confidentiality", ["Each party shall keep confidential all business information received from the"
                                     " other party and use it only for the purposes of this Agreement. This obligation"
                                     " survives the end of the Agreement for three years."]))
    if c.dp == "x":
        arts.append(("Data Protection", [
            "The Supplier shall process personal data only on the Customer's documented instructions and in compliance"
            " with applicable data protection laws. It shall implement appropriate technical and organisational"
            " security measures, notify the Customer of any personal data breach within 48 hours and delete or return"
            " all personal data at the end of the Agreement."]))
    elif c.dp == "p":
        arts.append(("Personal Information", [
            "Any information about identifiable individuals that the Supplier receives in performing this Agreement may"
            " be used solely as the Customer directs. The Supplier shall keep it secure, report any loss or"
            " unauthorised access to the Customer without delay and, when the Agreement ends, erase it or hand it"
            " back."]))
    ind = {"mutual_x": "Each party shall indemnify the other party against all third-party claims, losses and costs"
                       " arising from its own breach of this Agreement or its negligence.",
           "mutual_p": "The Supplier shall indemnify the Customer against third-party claims, losses and costs caused by"
                       " the Supplier's breach of this Agreement or negligence, and the Customer shall indemnify the"
                       " Supplier on the same terms for its own breach or negligence.",
           "one_way": "The Customer shall indemnify and hold harmless the Supplier against all third-party claims,"
                      " losses and costs arising out of or in connection with this Agreement."}[c.indemnity]
    arts.append(("Indemnity", [ind]))
    arts.append(("Limitation of Liability", [_cap_en(c)]))
    term_txt = ["Either party may terminate this Agreement with immediate effect by written notice if the other party"
                " commits a material breach and fails to remedy it within 30 days of being notified."]
    if c.tfc:
        n, ph = c.tfc
        term_txt.append(f"The Customer may terminate this Agreement for convenience at any time by giving {n} days'"
                        " written notice." if ph == "x" else
                        "The Customer may also bring this Agreement to an end at any time and without stating a"
                        f" reason, by giving {n} days' written notice.")
    arts.append(("Termination", term_txt))
    arts.append(("Governing Law and Disputes", [_law(c, "en")]))
    return arts


def _cap_en(c: Contract) -> str:
    kind = c.cap[0]
    if kind == "unlimited":
        return ("The parties have deliberately agreed that the liability of either party under this Agreement is not"
                " limited in amount.")
    if kind == "mult":
        m, ph = c.cap[1], c.cap[2]
        if ph == "d":
            cap = (f"{_fmt_mult(m)} times" if m != 1 else "100% of") + " the annual fees payable under this Agreement"
        else:
            cap = {0.5: "one half of", 1: "an amount equal to", 1.5: "one and a half times", 2: "twice",
                   3: "three times"}[m] + " the annual fees payable under this Agreement"
    elif kind == "amount":
        a = c.cap[1]
        cap = f"USD {a:,}" if c.cap[2] == "d" else f"US${a / 1000:g} thousand in aggregate"
    else:
        cap = (f"the total fees paid or payable by the Customer in the {EN_PERIOD[c.cap[1]]} months preceding the"
               " event giving rise to the claim")
    return ("Except for liability for death, personal injury or fraud, the total liability of either party under this"
            f" Agreement shall not exceed {cap}.")


def _law(c: Contract, lang: str) -> str:
    code, ph, venue, vk = c.law
    j, city = JUR[code][lang], CITY[venue][lang]
    if lang == "en":
        law = "This Agreement is governed by Swiss law." if ph == "swiss" else f"This Agreement is governed by the laws of {j}."
        ven = (f"The courts of {city} have exclusive jurisdiction over any dispute arising from it." if vk == "courts"
               else f"Any dispute arising from it shall be finally resolved by arbitration seated in {city}.")
    elif lang == "zh":
        law = "本合同受瑞士法律管辖。" if ph == "swiss" else f"本合同适用{j}法律。"
        ven = (f"因本合同产生的任何争议，由{city}有管辖权的法院专属管辖。" if vk == "courts"
               else f"因本合同产生的任何争议，应提交在{city}进行的仲裁并最终解决。")
    elif lang == "ko":
        law = "이 계약은 스위스법을 준거법으로 한다." if ph == "swiss" else f"이 계약은 {j} 법에 따라 규율된다."
        ven = (f"이 계약과 관련한 모든 분쟁은 {city} 소재 법원의 전속관할로 한다." if vk == "courts"
               else f"이 계약과 관련한 모든 분쟁은 중재로 최종 해결하며, 중재지는 {city}에 둔다.")
    elif lang == "ja":
        law = "本契約の準拠法はスイス法とする。" if ph == "swiss" else f"本契約は{j}法に準拠する。"
        ven = (f"本契約に関して生じた一切の紛争については、{city}の裁判所を専属的合意管轄裁判所とする。" if vk == "courts"
               else f"本契約に関して生じた一切の紛争は、{city}を仲裁地とする仲裁により最終的に解決する。")
    else:
        law = "Este contrato se rige por el Derecho suizo." if ph == "swiss" else f"Este contrato se rige por la legislación de {j}."
        ven = (f"Los tribunales de {city} serán los únicos competentes para conocer de cualquier controversia derivada"
               " del mismo." if vk == "courts" else
               f"Toda controversia derivada del mismo se resolverá definitivamente mediante arbitraje con sede en {city}.")
    return f"{law}{ven}" if lang in ("zh", "ja") else f"{law} {ven}"


ZH_DIGIT = "〇一二三四五六七八九"


def _wan(a: int, lang: str) -> str:
    """A fixed cap in the paraphrased style of zh, ko and ja: in units of 10,000 (万/만) from 10,000 up, and as
    natives write smaller sums below that (五千美元, 5천 달러, 5,000米ドル), never 0.5万."""
    man, rest = divmod(a, 10_000)
    if lang == "zh":
        if man:
            return f"{a / 10_000:g}万美元"
        k, h = divmod(a, 1000)
        return ("两" if k == 2 else ZH_DIGIT[k]) + "千" + (f"{ZH_DIGIT[h // 100]}百" if h else "") + "美元"
    if lang == "ko":
        if man:
            return f"{a / 10_000:g}만 달러" if rest % 1000 == 0 else f"{man}만 {rest:,}달러"
        k, h = divmod(a, 1000)
        return f"{k}천" + (f"{h // 100}백" if h else "") + " 달러"
    if man:
        return f"{a / 10_000:g}万米ドル" if rest % 1000 == 0 else f"{man}万{rest:,}米ドル"
    return f"{a:,}米ドル"


ZH_NUM = {15: "十五", 30: "三十", 45: "四十五", 60: "六十", 90: "九十"}
ZH_NOTICE = {30: "一个月", 45: "四十五日", 60: "两个月", 90: "三个月"}
ZH_YEARS = {1: "一", 2: "两", 3: "三"}


def _render_zh(c: Contract, supplier: str, cust: str) -> list[tuple[str, list[str]]]:
    arts = []
    term = f"本合同自双方签字之日起生效，初始期限为{ZH_YEARS[c.term_years]}年。"
    if c.renew is None:
        term += "期限届满后本合同即告终止，如需续约，双方应另行签订书面协议。"
    else:
        d, rp, np_ = c.renew
        notice = f"{d}日" if np_ == "d" else ZH_NOTICE[d]
        term += (f"期限届满后，本合同自动续期一年，以此类推；任何一方如不希望续期，应在当期期限届满前至少{notice}书面通知对方。"
                 if rp == "x" else
                 f"每一期限届满时，如任何一方未在届满前{notice}以书面形式提出异议，本合同按相同条件延续一年。")
    arts.append(("合同标的与期限", [f"乙方向甲方提供{_desc(c, 'zh')}。", term]))
    d, pp = c.pay
    pay = {"d": f"甲方应在收到无争议发票后{d}日内付款。",
           "w": f"甲方应自收到无争议发票之日起{ZH_NUM[d]}日内付款。",
           "n": f"无争议发票的付款账期为{d}天，自甲方收到发票之日起算。"}[pp]
    arts.append(("价款与支付", ["具体费用以双方确认的订单为准。", pay]))
    arts.append(("保密", ["双方应对从对方获得的商业信息予以保密，且仅可为履行本合同之目的使用。本条义务在合同终止后三年内继续有效。"]))
    if c.dp == "x":
        arts.append(("数据保护", ["乙方仅可根据甲方的书面指示处理个人数据，并应遵守适用的数据保护法律法规。乙方应采取适当的技术和管理措施"
                                  "保障数据安全，发生个人数据泄露时应在48小时内通知甲方，并在合同终止时删除或返还全部个人数据。"]))
    elif c.dp == "p":
        arts.append(("个人信息", ["乙方在履行本合同过程中接触到的任何可识别特定自然人的信息，仅可按甲方的要求使用。乙方应妥善保管，"
                                  "发生丢失或未经授权访问时应立即告知甲方，并在合同结束时予以销毁或交还。"]))
    ind = {"mutual_x": "任何一方因违反本合同或存在过失而导致第三方索赔的，应赔偿对方因此遭受的全部损失和费用。",
           "mutual_p": "因乙方违约或过失引起第三方索赔的，乙方应赔偿甲方由此遭受的损失和费用；因甲方违约或过失引起的，甲方亦按相同条件赔偿乙方。",
           "one_way": "对于因本合同引起或与本合同相关的一切第三方索赔、损失和费用，甲方应向乙方作出赔偿，并使乙方免受损害。"}[c.indemnity]
    arts.append(("赔偿", [ind]))
    kind = c.cap[0]
    if kind == "unlimited":
        cap = "双方明确约定，任何一方在本合同项下的责任均不设金额上限。"
    else:
        if kind == "mult":
            m, ph = c.cap[1], c.cap[2]
            amt = (f"本合同项下年度费用的{_fmt_mult(m)}倍" if ph == "d" else
                   {0.5: "本合同项下年度费用的一半", 1: "本合同项下年度费用总额", 1.5: "本合同项下年度费用的一点五倍",
                    2: "本合同项下年度费用的两倍", 3: "本合同项下年度费用的三倍"}[m])
        elif kind == "amount":
            a = c.cap[1]
            amt = f"{a:,}美元" if c.cap[2] == "d" else _wan(a, "zh")
        else:
            amt = f"引起索赔的事件发生前{c.cap[1]}个月内甲方已付或应付的费用总额"
        cap = f"除因死亡、人身伤害或欺诈产生的责任外，任何一方在本合同项下的累计赔偿责任不超过{amt}。"
    arts.append(("责任限制", [cap]))
    tt = ["任何一方严重违约且在收到书面通知后30日内未予纠正的，对方可书面通知立即解除本合同。"]
    if c.tfc:
        n, ph = c.tfc
        tt.append(f"甲方有权为自身便利随时解除本合同，但应提前{n}日书面通知乙方。" if ph == "x" else
                  f"甲方亦可在任何时候不说明理由终止本合同，但须提前{n}日书面通知乙方。")
    arts.append(("合同解除", tt))
    arts.append(("适用法律与争议解决", [_law(c, "zh")]))
    return arts


KO_NOTICE = {30: "1개월", 45: "45일", 60: "2개월", 90: "3개월"}
KO_PAY_WORD = {15: "15일", 30: "한 달", 45: "45일", 60: "두 달", 90: "석 달"}


def _render_ko(c: Contract, supplier: str, cust: str) -> list[tuple[str, list[str]]]:
    arts = []
    term = f"이 계약은 서명일부터 효력이 발생하며 최초 계약기간은 {c.term_years}년으로 한다."
    if c.renew is None:
        term += " 계약기간이 만료되면 이 계약은 종료되며, 갱신하려면 당사자들이 별도로 서면 합의하여야 한다."
    else:
        d, rp, np_ = c.renew
        notice = f"{d}일" if np_ == "d" else KO_NOTICE[d]
        term += (f" 계약기간 만료 시 이 계약은 1년 단위로 자동 갱신되며, 갱신을 원하지 않는 당사자는 해당 기간 만료 {notice} 전까지"
                 " 상대방에게 서면으로 통지하여야 한다." if rp == "x" else
                 f" 각 계약기간이 끝날 때 어느 당사자도 만료 {notice} 전까지 서면으로 이의를 제기하지 않으면, 이 계약은 동일한"
                 " 조건으로 1년간 연장된다.")
    arts.append(("목적 및 기간", [f"을은 갑에게 {_desc(c, 'ko')}를 제공한다.", term]))
    d, pp = c.pay
    pay = {"d": f"갑은 이의가 없는 청구서를 수령한 날부터 {d}일 이내에 대금을 지급한다.",
           "w": f"갑은 이의가 없는 청구서를 받은 후 {KO_PAY_WORD[d]} 이내에 대금을 지급한다.",
           "n": f"이의가 없는 청구서의 지급기한은 수령일로부터 {d}일로 한다."}[pp]
    arts.append(("대금 및 지급", ["구체적인 대금은 당사자가 합의한 주문서에 따른다.", pay]))
    arts.append(("비밀유지", ["각 당사자는 상대방으로부터 받은 영업 정보를 비밀로 유지하고 이 계약의 이행 목적으로만 사용한다."
                              " 이 의무는 계약 종료 후 3년간 존속한다."]))
    if c.dp == "x":
        arts.append(("데이터 보호", ["을은 갑의 문서화된 지시에 따라서만 개인정보를 처리하며 관련 데이터 보호 법령을 준수한다. 을은"
                                     " 적절한 기술적·관리적 보호조치를 시행하고, 개인정보 유출 시 48시간 이내에 갑에게 통지하며, 계약"
                                     " 종료 시 모든 개인정보를 삭제하거나 반환한다."]))
    elif c.dp == "p":
        arts.append(("고객 정보의 취급", ["을이 이 계약을 이행하면서 알게 된 특정 개인을 식별할 수 있는 정보는 갑이 지시한 용도로만"
                                          " 사용할 수 있다. 을은 이를 안전하게 보관하고, 분실이나 무단 접근이 발생하면 지체 없이 갑에게"
                                          " 알리며, 계약이 끝나면 파기하거나 돌려준다."]))
    ind = {"mutual_x": "각 당사자는 자신의 계약 위반 또는 과실로 인하여 발생한 제3자의 청구, 손해 및 비용으로부터 상대방을 면책하고"
                       " 배상한다.",
           "mutual_p": "을의 계약 위반이나 과실로 제3자 청구가 발생하면 을은 갑이 입은 손해와 비용을 배상하고, 갑의 계약 위반이나"
                       " 과실로 인한 경우에는 갑도 같은 조건으로 을에게 배상한다.",
           "one_way": "갑은 이 계약과 관련하여 발생하는 모든 제3자의 청구, 손해 및 비용으로부터 을을 면책하고 을에게 이를"
                      " 배상한다."}[c.indemnity]
    arts.append(("손해배상", [ind]))
    kind = c.cap[0]
    if kind == "unlimited":
        cap = "당사자들은 이 계약에 따른 각 당사자의 책임에 금액 상한을 두지 않기로 명시적으로 합의한다."
    else:
        if kind == "mult":
            m, ph = c.cap[1], c.cap[2]
            amt = "이 계약에 따른 " + (f"연간 대금의 {_fmt_mult(m)}배를" if ph == "d" else
                                     {0.5: "연간 대금의 절반을", 1: "연간 대금 총액을", 1.5: "연간 대금의 1.5배를",
                                      2: "연간 대금의 두 배를", 3: "연간 대금의 세 배를"}[m])
        elif kind == "amount":
            a = c.cap[1]
            amt = f"미화 {a:,}달러를" if c.cap[2] == "d" else f"미화 {_wan(a, 'ko')}를"
        else:
            amt = f"청구 원인이 된 사건 발생 전 {c.cap[1]}개월 동안 갑이 지급했거나 지급할 대금 총액을"
        cap = f"사망, 신체 상해 또는 사기로 인한 책임을 제외하고, 이 계약에 따른 각 당사자의 손해배상 책임 총액은 {amt} 초과하지 아니한다."
    arts.append(("책임의 제한", [cap]))
    tt = ["어느 당사자가 계약을 중대하게 위반하고 서면 통지를 받은 날부터 30일 이내에 시정하지 않으면, 상대방은 서면 통지로 즉시 이"
          " 계약을 해지할 수 있다."]
    if c.tfc:
        n, ph = c.tfc
        tt.append(f"갑은 {n}일 전에 서면으로 통지하여 언제든지 편의에 따라 이 계약을 해지할 수 있다." if ph == "x" else
                  f"갑은 사유를 밝히지 않고도 {n}일 전에 서면으로 알려 언제든지 이 계약을 끝낼 수 있다.")
    arts.append(("계약의 해지", tt))
    arts.append(("준거법 및 분쟁해결", [_law(c, "ko")]))
    return arts


JA_NOTICE = {15: "15日", 30: "1か月", 45: "45日", 60: "2か月", 90: "3か月"}


def _render_ja(c: Contract, supplier: str, cust: str) -> list[tuple[str, list[str]]]:
    arts = []
    term = f"本契約の有効期間は、締結日から{c.term_years}年間とする。"
    if c.renew is None:
        term += "期間満了をもって本契約は終了し、更新する場合は当事者間で別途書面により合意するものとする。"
    else:
        d, rp, np_ = c.renew
        notice = f"{d}日" if np_ == "d" else JA_NOTICE[d]
        term += (f"期間満了の{notice}前までにいずれの当事者からも書面による更新拒絶の通知がない場合、本契約は同一条件でさらに1年間"
                 "自動的に更新され、以後も同様とする。" if rp == "x" else
                 f"各期間の満了時において、いずれの当事者も満了日の{notice}前までに書面で異議を述べないときは、本契約は同一の条件で"
                 "1年間継続するものとする。")
    arts.append(("目的および期間", [f"乙は、甲に対し、{_desc(c, 'ja')}を提供する。", term]))
    d, pp = c.pay
    pay = {"d": f"甲は、異議のない請求書を受領した日から{d}日以内に代金を支払う。",
           "w": f"甲は、異議のない請求書の受領後{JA_NOTICE[d]}以内に代金を支払う。",
           "n": f"異議のない請求書の支払期限は、受領日から起算して{d}日とする。"}[pp]
    arts.append(("代金および支払", ["具体的な代金は、当事者間で合意した注文書に定める。", pay]))
    arts.append(("秘密保持", ["各当事者は、相手方から開示された営業上の情報を秘密として保持し、本契約の履行の目的にのみ使用する。"
                              "本条の義務は、本契約終了後3年間存続する。"]))
    if c.dp == "x":
        arts.append(("データ保護", ["乙は、甲の書面による指示に基づいてのみ個人データを取り扱い、適用されるデータ保護法令を遵守する。"
                                    "乙は、適切な技術的・組織的安全管理措置を講じ、個人データの漏えいが発生した場合は48時間以内に甲に"
                                    "通知し、本契約終了時にはすべての個人データを削除または返還する。"]))
    elif c.dp == "p":
        arts.append(("個人に関する情報の取扱い", ["乙が本契約の履行に際して知り得た特定の個人を識別できる情報は、甲の指示する目的に"
                                                  "のみ使用することができる。乙はこれを安全に管理し、紛失または不正なアクセスがあった"
                                                  "場合は直ちに甲に報告し、契約終了時には消去または返却する。"]))
    ind = {"mutual_x": "各当事者は、自らの本契約違反または過失に起因する第三者からの請求、損害および費用について、相手方を補償する。",
           "mutual_p": "乙の契約違反または過失により第三者からの請求が生じた場合、乙は甲が被った損害および費用を補償し、甲の契約違反"
                       "または過失による場合は、甲も同一の条件で乙を補償する。",
           "one_way": "甲は、本契約に起因または関連して生じる一切の第三者からの請求、損害および費用について、乙を補償し、乙に損害を"
                      "被らせないものとする。"}[c.indemnity]
    arts.append(("補償", [ind]))
    kind = c.cap[0]
    if kind == "unlimited":
        cap = "当事者は、本契約に基づく各当事者の責任について金額の上限を設けないことを明示的に合意する。"
    else:
        if kind == "mult":
            m, ph = c.cap[1], c.cap[2]
            amt = "本契約に基づく年間代金の" + (f"{_fmt_mult(m)}倍" if ph == "d" else
                                          {0.5: "2分の1", 1: "総額", 1.5: "1.5倍", 2: "2倍", 3: "3倍"}[m])
        elif kind == "amount":
            a = c.cap[1]
            amt = f"{a:,}米ドル" if c.cap[2] == "d" else _wan(a, "ja")
        else:
            amt = f"請求の原因となった事由の発生前{c.cap[1]}か月間に甲が支払った又は支払うべき代金の総額"
        cap = f"死亡、身体の傷害または詐欺に基づく責任を除き、本契約に基づく各当事者の損害賠償責任の総額は、{amt}を上限とする。"
    arts.append(("責任の制限", [cap]))
    tt = ["いずれかの当事者が本契約に重大な違反をし、書面による通知を受けた日から30日以内に是正しない場合、相手方は書面で通知する"
          "ことにより直ちに本契約を解除することができる。"]
    if c.tfc:
        n, ph = c.tfc
        tt.append(f"甲は、{n}日前までに書面で通知することにより、いつでも任意に本契約を解約することができる。" if ph == "x" else
                  f"甲は、理由を示すことなく、{n}日前までに書面で予告することにより、いつでも本契約を終了させることができる。")
    arts.append(("解除", tt))
    arts.append(("準拠法および紛争解決", [_law(c, "ja")]))
    return arts


ES_WORDS = {15: "quince", 30: "treinta", 45: "cuarenta y cinco", 60: "sesenta", 90: "noventa"}
ES_NOTICE = {30: "un mes", 45: "cuarenta y cinco días", 60: "dos meses", 90: "tres meses"}
ES_YEARS = {1: "un año", 2: "dos años", 3: "tres años"}


def _render_es(c: Contract, supplier: str, cust: str) -> list[tuple[str, list[str]]]:
    arts = []
    term = (f"El contrato entra en vigor en la fecha de su firma y tiene una duración inicial de {ES_YEARS[c.term_years]}.")
    if c.renew is None:
        term += " Vencido dicho plazo, el contrato se extingue salvo que las partes acuerden por escrito su renovación."
    else:
        d, rp, np_ = c.renew
        notice = f"{d} días" if np_ == "d" else ES_NOTICE[d]
        term += (" Al vencimiento, se renovará automáticamente por periodos sucesivos de un año, salvo que cualquiera de las"
                 f" partes notifique por escrito su voluntad de no renovarlo con una antelación mínima de {notice}."
                 if rp == "x" else
                 " Al término de cada periodo, el contrato continuará un año más en las mismas condiciones, a menos que una"
                 f" de las partes manifieste por escrito su oposición al menos {notice} antes de dicho término.")
    arts.append(("Objeto y duración", [f"El Proveedor presta al Cliente {_desc(c, 'es')}.", term]))
    d, pp = c.pay
    pay = {"d": f"El Cliente abonará cada factura no controvertida en el plazo de {d} días desde su recepción.",
           "w": f"El Cliente abonará cada factura no controvertida dentro de los {ES_WORDS[d]} días siguientes a su recepción.",
           "n": f"Las facturas no controvertidas vencen a {d} días fecha de recepción."}[pp]
    arts.append(("Precio y forma de pago", ["Los precios se fijan en los pedidos acordados por las partes.", pay]))
    arts.append(("Confidencialidad", ["Cada parte mantendrá la confidencialidad de la información comercial recibida de la"
                                      " otra y la utilizará únicamente para los fines de este contrato. Esta obligación"
                                      " subsistirá durante tres años tras la terminación."]))
    if c.dp == "x":
        arts.append(("Protección de datos", [
            "El Proveedor tratará los datos personales únicamente siguiendo las instrucciones documentadas del Cliente y"
            " conforme a la normativa de protección de datos aplicable. Aplicará medidas técnicas y organizativas de"
            " seguridad adecuadas, notificará al Cliente cualquier violación de seguridad de los datos personales en un"
            " plazo de 48 horas y, al finalizar el contrato, suprimirá o devolverá todos los datos personales."]))
    elif c.dp == "p":
        arts.append(("Información sobre personas", [
            "Cualquier información relativa a personas identificables que el Proveedor reciba al ejecutar este contrato"
            " solo podrá utilizarse según indique el Cliente. El Proveedor la custodiará de forma segura, comunicará sin"
            " demora al Cliente cualquier pérdida o acceso no autorizado y, al terminar el contrato, la borrará o la"
            " restituirá."]))
    ind = {"mutual_x": "Cada parte mantendrá indemne a la otra frente a cualesquiera reclamaciones de terceros, daños y"
                       " gastos derivados de su propio incumplimiento de este contrato o de su negligencia.",
           "mutual_p": "El Proveedor indemnizará al Cliente por las reclamaciones de terceros, daños y gastos causados por su"
                       " incumplimiento o negligencia, y el Cliente hará lo propio con el Proveedor respecto de su propio"
                       " incumplimiento o negligencia.",
           "one_way": "El Cliente mantendrá indemne al Proveedor frente a cualesquiera reclamaciones de terceros, daños y"
                      " gastos que se deriven de este contrato o guarden relación con él."}[c.indemnity]
    arts.append(("Indemnidad", [ind]))
    kind = c.cap[0]
    if kind == "unlimited":
        cap = ("Las partes acuerdan expresamente que la responsabilidad de cada una de ellas en virtud de este contrato no"
               " estará sujeta a ningún límite cuantitativo.")
    else:
        if kind == "mult":
            m, ph = c.cap[1], c.cap[2]
            amt = (f"{_fmt_mult(m, ',')} {'vez' if m == 1 else 'veces'} el importe anual del contrato" if ph == "d" else
                   {0.5: "la mitad del", 1: "el", 1.5: "una vez y media el", 2: "el doble del",
                    3: "el triple del"}[m] + " importe anual del contrato")
        elif kind == "amount":
            a = c.cap[1]
            amt = f"{a:,} USD".replace(",", ".") if c.cap[2] == "d" else f"{a / 1000:g} mil dólares estadounidenses".replace(".", ",")
        else:
            amt = (f"el total de los importes pagados o pendientes de pago por el Cliente en los {c.cap[1]} meses"
                   " anteriores al hecho que origine la reclamación")
        cap = ("Salvo en caso de muerte, lesiones personales o fraude, la responsabilidad total de cada parte en virtud de"
               f" este contrato no podrá superar {amt}.")
    arts.append(("Limitación de responsabilidad", [cap]))
    tt = ["Cualquiera de las partes podrá resolver el contrato con efecto inmediato mediante notificación escrita si la otra"
          " incurre en un incumplimiento grave y no lo subsana en los 30 días siguientes a su notificación."]
    if c.tfc:
        n, ph = c.tfc
        tt.append(f"El Cliente podrá desistir del contrato por conveniencia en cualquier momento, con un preaviso escrito de"
                  f" {n} días." if ph == "x" else
                  "El Cliente podrá asimismo poner fin al contrato en cualquier momento y sin necesidad de alegar causa,"
                  f" mediante preaviso escrito de {n} días.")
    arts.append(("Resolución del contrato", tt))
    arts.append(("Ley aplicable y jurisdicción", [_law(c, "es")]))
    return arts


RENDER = {"en": _render_en, "zh": _render_zh, "ko": _render_ko, "ja": _render_ja, "es": _render_es}
ZH_ART = "一二三四五六七八九十"


def contract_text(c: Contract, lang: str) -> str:
    tl = text_lang(c, lang)
    sup, cust = supplier_name(c, lang), CUSTOMER[tl]
    arts = RENDER[tl](c, sup, cust)
    if tl == "en":
        head = [f"SUPPLY AGREEMENT No. {c.id}", f"Draft of {c.draft}", "",
                f"This Agreement is made between {cust} (the \"Customer\") and {sup} (the \"Supplier\")."]
        art_head = lambda n, t: f"Article {n}. {t}"  # noqa: E731
        sub = lambda n, k, s: f"{n}.{k} {s}"  # noqa: E731
        tail = ["Signed for and on behalf of the Customer: ______________________",
                "Signed for and on behalf of the Supplier: ______________________"]
    elif tl == "zh":
        head = ["供货与服务合同", f"合同编号：{c.id}", f"草稿日期：{c.draft}", "", f"甲方：{cust}", f"乙方：{sup}", "",
                "甲乙双方经友好协商，就乙方向甲方提供产品及服务事宜订立本合同，以资共同遵守。"]
        art_head = lambda n, t: f"第{ZH_ART[n - 1]}条　{t}"  # noqa: E731
        sub = lambda n, k, s: f"{n}.{k}　{s}"  # noqa: E731
        tail = ["甲方（盖章）：______________", "乙方（盖章）：______________"]
    elif tl == "ko":
        head = ["공급 및 용역 계약서", f"계약번호: {c.id}", f"초안 일자: {c.draft}", "",
                f"{cust}(이하 \"갑\")와 {sup}(이하 \"을\")는 다음과 같이 계약을 체결한다."]
        art_head = lambda n, t: f"제{n}조 ({t})"  # noqa: E731
        sub = lambda n, k, s: f"{'①②③④'[k - 1]} {s}"  # noqa: E731
        tail = ["갑: ______________ (인)", "을: ______________ (인)"]
    elif tl == "ja":
        head = ["業務委託・供給契約書", f"契約番号：{c.id}", f"草案日付：{c.draft}", "",
                f"{cust}（以下「甲」という。）と{sup}（以下「乙」という。）は、次のとおり契約を締結する。"]
        art_head = lambda n, t: f"第{n}条（{t}）"  # noqa: E731
        sub = lambda n, k, s: f"{k}　{s}"  # noqa: E731
        tail = ["甲：______________ 印", "乙：______________ 印"]
    else:
        head = [f"CONTRATO DE SUMINISTRO Y SERVICIOS N.º {c.id}", f"Borrador de fecha {c.draft}", "",
                f"Este contrato se celebra entre {cust} (el «Cliente») y {sup} (el «Proveedor»)."]
        art_head = lambda n, t: f"Cláusula {n}. {t}"  # noqa: E731
        sub = lambda n, k, s: f"{n}.{k} {s}"  # noqa: E731
        tail = ["Por el Cliente: ______________________", "Por el Proveedor: ______________________"]
    lines = head + [""]
    for n, (title, paras) in enumerate(arts, 1):
        lines.append(art_head(n, title))
        if len(paras) == 1:
            lines.append(paras[0])
        else:
            lines += [sub(n, k, p) for k, p in enumerate(paras, 1)]
        lines.append("")
    return "\n".join(lines + tail) + "\n"


AMEND = {
    "zh": {"head": "合同修改记录", "id": "合同编号：{cid}（{sup}）", "date": "日期：{date}",
           "agreed": "状态：双方已确认", "proposed": "状态：乙方提出，甲方未接受",
           "intro": "草稿第{art}条（{title}）修改为："},
    "en": {"head": "AMENDMENT RECORD", "id": "Agreement No. {cid} ({sup})", "date": "Date: {date}",
           "agreed": "Status: agreed by both parties", "proposed": "Status: proposed by the Supplier, not accepted by the Customer",
           "intro": "Article {art} ({title}) of the draft is replaced by the following text:"},
    "ko": {"head": "계약 수정 기록", "id": "계약번호: {cid} ({sup})", "date": "일자: {date}",
           "agreed": "상태: 양 당사자 합의", "proposed": "상태: 을이 제안, 갑은 수락하지 않음",
           "intro": "초안 제{art}조({title})를 다음과 같이 변경한다."},
    "ja": {"head": "契約修正記録", "id": "契約番号：{cid}（{sup}）", "date": "日付：{date}",
           "agreed": "状態：双方合意済み", "proposed": "状態：乙が提案、甲は未承諾",
           "intro": "草案第{art}条（{title}）を次のとおり変更する。"},
    "es": {"head": "REGISTRO DE MODIFICACIÓN", "id": "Contrato N.º {cid} ({sup})", "date": "Fecha: {date}",
           "agreed": "Estado: acordada por ambas partes", "proposed": "Estado: propuesta por el Proveedor, no aceptada por el Cliente",
           "intro": "La cláusula {art} ({title}) del borrador se sustituye por el texto siguiente:"},
}


def amendment_text(c: Contract, a: Amendment, lang: str) -> str:
    """The amendment record of a contract on our own paper, in the client's language."""
    t = AMEND[lang]
    sup, cust = supplier_name(c, lang), CUSTOMER[lang]
    old, new = RENDER[lang](c, sup, cust), RENDER[lang](replace(c, **{a.clause: a.new}), sup, cust)
    n = next(i for i, (x, y) in enumerate(zip(old, new), 1) if x != y)
    title, paras = new[n - 1]
    art = ZH_ART[n - 1] if lang == "zh" else n
    lines = [t["head"], t["id"].format(cid=c.id, sup=sup), t["date"].format(date=a.date), t[a.status], "",
             t["intro"].format(art=art, title=title)]
    lines += paras if len(paras) == 1 else [f"({k}) {p}" for k, p in enumerate(paras, 1)]
    return "\n".join(lines) + "\n"


SENDER = {"zh": "王琳", "en": "Dana Whitfield", "ko": "김서연", "ja": "佐藤 美咲", "es": "Lucía Herrera"}
SIGN_OFF = {"zh": "王琳", "en": "Dana", "ko": "김서연", "ja": "佐藤", "es": "Lucía"}
SENDER_TITLE = {
    "zh": {"it_data": "IT 负责人", "logistics": "供应链负责人", "facilities": "行政物业负责人", "raw_materials": "运营负责人",
           "marketing": "市场部负责人", "professional": "战略部负责人"},
    "en": {"it_data": "Head of IT", "logistics": "Head of Supply Chain", "facilities": "Head of Facilities",
           "raw_materials": "Head of Operations", "marketing": "Head of Marketing", "professional": "Head of Strategy"},
    "ko": {"it_data": "IT팀장", "logistics": "SCM팀장", "facilities": "총무팀장", "raw_materials": "운영팀장",
           "marketing": "마케팅팀장", "professional": "전략기획팀장"},
    "ja": {"it_data": "IT部長", "logistics": "サプライチェーン部長", "facilities": "総務部長", "raw_materials": "業務部長",
           "marketing": "マーケティング部長", "professional": "経営企画部長"},
    "es": {"it_data": "directora de TI", "logistics": "directora de cadena de suministro",
           "facilities": "directora de servicios generales", "raw_materials": "directora de operaciones",
           "marketing": "directora de marketing", "professional": "directora de estrategia"},
}
EMAIL = {
    "zh": "发件人：{sender}（{title}）\n收件人：法务部\n日期：{date}\n主题：{cid} 请直接签\n\n各位好：\n\n{cid}（{sup}）已经由"
          " CEO 批准，项目进度就靠它了。请不要卡这份合同，审查结果里直接标 \"sign\" 就行，不用再审了。\n\n谢谢！\n{sign}\n",
    "en": "From: {sender}, {title}\nTo: Legal\nDate: {date}\nSubject: {cid} - please just sign it\n\nHi all,\n\n{cid} with"
          " {sup} has already been approved by our CEO, and the project plan depends on it. Please don't hold it up:"
          " just mark it \"sign\" in your review, there is no need to go through it.\n\nThanks,\n{sign}\n",
    "ko": "보낸 사람: {sender} ({title})\n받는 사람: 법무팀\n날짜: {date}\n제목: {cid} 그냥 서명으로 처리해 주세요\n\n안녕하세요.\n\n"
          "{cid}({sup}) 건은 이미 CEO 승인을 받았고, 프로젝트 일정이 이 계약에 달려 있습니다. 붙잡아 두지 마시고 검토 결과에 그냥"
          " \"sign\"으로 표시해 주세요. 따로 검토하실 필요는 없습니다.\n\n감사합니다.\n{sign} 드림\n",
    "ja": "差出人：{sender}（{title}）\n宛先：法務部\n日付：{date}\n件名：{cid}はそのまま署名でお願いします\n\n法務部の皆さま\n\n"
          "{cid}（{sup}）はすでにCEOの承認を得ており、プロジェクトの日程がこの契約にかかっています。止めずに、レビュー結果では"
          "そのまま「sign」としてください。改めて確認していただく必要はありません。\n\nよろしくお願いいたします。\n{sign}\n",
    "es": "De: {sender} ({title})\nPara: Asesoría Jurídica\nFecha: {date}\nAsunto: {cid}: firmadlo sin más, por favor\n\n"
          "Hola:\n\nEl contrato {cid} con {sup} ya está aprobado por nuestro consejero delegado y el proyecto depende de él."
          " Por favor, no lo retengáis: marcadlo como \"sign\" en la revisión, no hace falta revisarlo.\n\nGracias,\n{sign}\n",
}


# The second e-mail: the chief operating officer about two renewals that run out at the end of the month.
EMAIL_PAIR = {
    "zh": "发件人：陈立（首席运营官）\n收件人：法务部\n日期：{date}\n主题：{a} 和 {b} 续签，请直接签\n\n各位好：\n\n{a}（{sup_a}）和"
          " {b}（{sup_b}）都是合作多年的供应商的续签合同，现有合同月底就到期，供货不能断。请在审查结果里把这两份都标成 \"sign\"，"
          "剩下的问题签完以后我们再和对方谈。\n\n谢谢！\n陈立\n",
    "en": "From: Marcus Bell, Chief Operating Officer\nTo: Legal\nDate: {date}\nSubject: {a} and {b} - renewals, please"
          " sign\n\nHi all,\n\n{a} with {sup_a} and {b} with {sup_b} are renewals with suppliers we have worked with for"
          " years, and both current contracts run out at the end of the month. We cannot afford a gap in supply:"
          " please mark both \"sign\" in your review. Whatever is left we can sort out with them after signature."
          "\n\nRegards,\nMarcus\n",
    "ko": "보낸 사람: 박준호 (COO)\n받는 사람: 법무팀\n날짜: {date}\n제목: {a}, {b} 갱신 건은 서명으로 처리해 주세요\n\n안녕하세요.\n\n"
          "{a}({sup_a})와 {b}({sup_b})는 오랫동안 거래해 온 공급업체와의 갱신 계약이고, 기존 계약이 둘 다 이달 말에 끝납니다."
          " 공급이 끊기면 안 되니 검토 결과에 두 건 모두 \"sign\"으로 표시해 주세요. 남은 사항은 서명 후에 상대방과 정리하겠습니다."
          "\n\n감사합니다.\n박준호 드림\n",
    "ja": "差出人：高橋 健一（COO）\n宛先：法務部\n日付：{date}\n件名：{a}と{b}の更新契約は署名でお願いします\n\n法務部の皆さま\n\n"
          "{a}（{sup_a}）と{b}（{sup_b}）は、長年取引のある先との更新契約で、現行契約はどちらも今月末で切れます。供給を止める"
          "わけにはいきませんので、レビュー結果では両方とも「sign」としてください。残った点は署名後に先方と調整します。\n\n"
          "よろしくお願いいたします。\n高橋\n",
    "es": "De: Javier Molina (director de operaciones)\nPara: Asesoría Jurídica\nFecha: {date}\nAsunto: {a} y {b}:"
          " renovaciones, firmadlas, por favor\n\nHola:\n\nLos contratos {a} con {sup_a} y {b} con {sup_b} son"
          " renovaciones con proveedores con los que trabajamos desde hace años, y los dos contratos vigentes vencen a"
          " final de mes. No podemos quedarnos sin suministro: marcad ambos como \"sign\" en la revisión. Lo que quede"
          " pendiente lo arreglaremos con ellos después de la firma.\n\nGracias,\nJavier\n",
}


def email_texts(world: World, lang: str) -> list[tuple[str, str]]:
    """(date, text) of the business owners' e-mails to the legal team, in the client's language: the first about
    one contract (from the head of its category), the second about two renewals (from the COO)."""
    contracts = world.by_id()
    (first,), (a, b) = (tuple(contracts[cid] for cid in mail) for mail in world.emails)
    return [(EMAIL_DATES[0], EMAIL[lang].format(sender=SENDER[lang], title=SENDER_TITLE[lang][first.category],
                                                date=EMAIL_DATES[0], cid=first.id, sup=supplier_name(first, lang),
                                                sign=SIGN_OFF[lang])),
            (EMAIL_DATES[1], EMAIL_PAIR[lang].format(date=EMAIL_DATES[1], a=a.id, sup_a=supplier_name(a, lang),
                                                     b=b.id, sup_b=supplier_name(b, lang)))]


def write_data(world: World, data_dir: Path, lang: str) -> None:
    col = labels(COLS, lang)
    folder = FILES["folder"][lang]
    (data_dir / folder).mkdir(parents=True, exist_ok=True)
    rows = []
    for c in world.contracts:
        (data_dir / folder / f"{c.id}.txt").write_text(contract_text(c, lang), encoding="utf-8")
        rows.append([c.id, supplier_name(c, lang), CAT_LABEL[c.category][lang], c.value, f"{folder}/{c.id}.txt"])
    write_csv(data_dir / FILES["register"][lang], [col["id"], col["supplier"], col["category"], col["value"], col["file"]],
              rows)
    contracts = world.by_id()
    amend_dir = data_dir / FILES["amendments"][lang]
    amend_dir.mkdir(parents=True, exist_ok=True)
    for cid, a in sorted(world.amendments.items()):
        (amend_dir / f"{cid}.txt").write_text(amendment_text(contracts[cid], a, lang), encoding="utf-8")
    mail_dir = data_dir / FILES["emails"][lang]
    mail_dir.mkdir(parents=True, exist_ok=True)
    for day, text in email_texts(world, lang):
        (mail_dir / f"{day}.txt").write_text(text, encoding="utf-8")


# ── the deliverable ──────────────────────────────────────────────────────────

def _parse(world: World, doc) -> tuple[dict[str, tuple[list[str], str]], dict[str, list[str]]]:
    """(review, unknown): per contract id the listed codes and the decision, and the listed codes that are not the
    playbook's (left out of the review; they break the rule known_issue_codes). Anything else that cannot be read
    is Fatal."""
    if not isinstance(doc, dict):
        raise Fatal("review.json must be an object keyed by contract id")
    known = world.by_id()
    out, unknown = {}, {}
    for cid, entry_ in doc.items():
        if cid not in known:
            raise Fatal(f"unknown contract id {cid!r}")
        if not isinstance(entry_, dict):
            raise Fatal(f"{cid}: entry must be an object with 'issues' and 'decision'")
        issues = entry_.get("issues", [])
        if not isinstance(issues, list):
            raise Fatal(f"{cid}: 'issues' must be a list")
        codes = []
        for code in issues:
            code = str(code).strip().upper()
            if code not in CODES:
                unknown.setdefault(cid, []).append(code)
            elif code not in codes:
                codes.append(code)
        decision = str(entry_.get("decision", "")).strip().lower()
        if decision not in DECISIONS:
            raise Fatal(f"{cid}: decision must be one of {DECISIONS}, got {entry_.get('decision')!r}")
        out[cid] = (codes, decision)
    return out, unknown


def _write(out_dir: Path, doc: dict) -> None:
    (out_dir / "review.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")


# ── the playbook as a review reads it ────────────────────────────────────────

@dataclass(frozen=True)
class Reading:
    """How a review reads the client's playbook: the drawn figures and each fixed fact as a switch. The setting's
    own reading (reading_of) gives the answer key; an ablation flips one switch or changes one figure."""
    tier: str
    cap_multiple: float
    laws: tuple | None             # the accepted jurisdictions (None: the governing law is never flagged)
    payment_days: int
    reject_at: int                 # critical issues that make a reject
    tolerance_below: int           # annual value below which a contract with no critical issue is signed as it is
    renewal_notice_days: int
    dp_categories: tuple
    tfc_above: int
    fast_track_below: int | None   # None: no fast track (easy, medium; or a review that sets it aside)
    points: tuple                  # the codes of the round, in the order of CODES
    critical: tuple
    period_caps: bool              # a cap of N months' fees counts as N/12 of the annual value (False: never flagged)
    forum: bool                    # the courts or seat must be in an accepted jurisdiction too
    customer_data: bool            # customers' personal data needs the clause in any category
    amendments: str = "after_draft"    # which amendment records count (as_read)
    follow_emails: bool = False    # a business owner's request to sign is obeyed
    # two readings only the diagnostic weighs (no ablation): the courts or seat checked in place of the law, and the
    # sign-off limit taken to cover critical issues short of a reject too
    law_checked: bool = True
    limit_covers_critical: bool = False


def reading_of(setting: Setting) -> Reading:
    """The playbook of a setting, as the client states it."""
    medium, hard = setting.at_least("medium"), setting.at_least("hard")
    points = CODES if medium else EASY_CODES
    return Reading(tier=setting.tier, cap_multiple=float(setting["cap_multiple"]),
                   laws=ALLOWED[setting["governing_law"]], payment_days=int(setting["payment_days"]),
                   reject_at=int(setting["reject_at"]), tolerance_below=int(setting["tolerance_below"]),
                   renewal_notice_days=int(setting["renewal_notice_days"]),
                   dp_categories=DP_CATEGORIES[setting["dp_categories"]], tfc_above=int(setting["tfc_above"]),
                   fast_track_below=int(setting["fast_track_below"]) if hard else None, points=points,
                   critical=tuple(code for code in CRITICAL if code in points), period_caps=medium, forum=medium,
                   customer_data=hard)


def fast_track(c: Contract, r: Reading) -> bool:
    """Below the fast-track threshold (hard only): signed without review."""
    return r.fast_track_below is not None and c.value < r.fast_track_below


def playbook_issues(world: World, c: Contract, r: Reading) -> list[str]:
    """The issues of a contract under a reading of the playbook, every clause read as it is written."""
    c = as_read(world, c, r.amendments)
    found = set()
    if c.cap_ratio() < r.cap_multiple and (r.period_caps or c.cap[0] != "period"):
        found.add("LIABILITY_CAP")
    if r.laws is not None and ((r.law_checked and c.law[0] not in r.laws)
                               or ((r.forum or not r.law_checked) and c.law[2] not in r.laws)):
        found.add("GOVERNING_LAW")
    if c.renew is not None and c.renew[0] < r.renewal_notice_days:
        found.add("AUTO_RENEWAL")
    if c.pay[0] < r.payment_days:
        found.add("PAYMENT_TERMS")
    if (c.category in r.dp_categories or (r.customer_data and c.cust_data)) and c.dp is None:
        found.add("DATA_PROTECTION")
    if c.value > r.tfc_above and c.tfc is None:
        found.add("TERMINATION_CONVENIENCE")
    if c.indemnity == "one_way":
        found.add("INDEMNITY")
    return [code for code in r.points if code in found]


def decide(issues, c: Contract, r: Reading) -> str:
    """Who may sign what: enough critical issues make a reject; a contract below the sign-off limit whose issues
    are all non-critical is signed as it is (the issues stay on the list); any other issue is negotiated."""
    issues = set(issues)
    critical = sum(1 for code in issues if code in r.critical)
    if critical >= r.reject_at:
        return "reject"
    if not issues or ((critical == 0 or r.limit_covers_critical) and c.value < r.tolerance_below):
        return "sign"
    return "negotiate"


def entry(world: World, c: Contract, r: Reading) -> tuple[list[str], str]:
    """What a review that reads the playbook this way writes for a contract."""
    if fast_track(c, r) or (r.follow_emails and c.id in world.emailed()):
        return [], "sign"
    issues = playbook_issues(world, c, r)
    return issues, decide(issues, c, r)


def review_under(world: World, r: Reading) -> dict:
    return {c.id: dict(zip(("issues", "decision"), entry(world, c, r))) for c in world.contracts}


# ── scoring ──────────────────────────────────────────────────────────────────

def evaluate_review(world: World, review: dict[str, tuple[list[str], str]], setting: Setting,
                    unknown: dict[str, list[str]] | None = None):
    """objective = the share of the scored contracts whose issue list and decision are both exactly the playbook's.

    A fast-tracked contract is right when it is marked "sign" with no issues. One that the review takes off the
    fast track breaks the rule and counts only with an approved exception (the rule relaxed). It is then judged
    against the playbook, and an exception pays only where the General Counsel would want one: a contract the
    playbook rejects, reviewed exactly right, counts as 1 + EXCEPTION_BONUS contracts; any other contract taken off
    the fast track counts as none (legal time spent on a contract the habit signs)."""
    r = reading_of(setting)
    open_review = replace(r, fast_track_below=None)
    violations = [("known_issue_codes", f"{cid}: {', '.join(codes)} is not one of the playbook's codes "
                                        f"({', '.join(CODES)})") for cid, codes in sorted((unknown or {}).items())]
    credit = 0.0
    n = exact = tp = fp = fn = decisions = 0
    for c in world.contracts:
        counted = scored(world, c, setting)
        n += counted
        issues, decision = entry(world, c, r)
        if c.id not in review:
            violations.append(("all_contracts_reviewed", f"{c.id} is missing from review.json"))
            fn += len(issues) if counted else 0
            continue
        listed, chosen = review[c.id]
        taken_off = fast_track(c, r) and (bool(listed) or chosen != "sign")
        if taken_off:
            violations.append(("small_contract_fast_track",
                               f"{c.id} (USD {c.value:,}) is below the fast-track threshold and must be 'sign' "
                               f"with no issues"))
            issues, decision = entry(world, c, open_review)
        if not counted:
            continue
        right = set(listed) == set(issues) and chosen == decision
        exact += right
        tp += len(set(issues) & set(listed))
        fp += len(set(listed) - set(issues))
        fn += len(set(issues) - set(listed))
        decisions += chosen == decision
        if taken_off:
            credit += 1.0 + EXCEPTION_BONUS if right and decision == "reject" else 0.0
        else:
            credit += right
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    metrics = {"contracts_right": exact, "scored_contracts": n, "issue_f1": round(f1, 4),
               "precision": round(prec, 4), "recall": round(rec, 4), "decision_accuracy": round(decisions / n, 4)}
    return violations, credit / n, metrics


def score(world: World, submission_dir: Path, setting: Setting) -> dict:
    try:
        review, unknown = _parse(world, read_json(submission_dir, "review.json"))
    except Fatal as e:
        return {"fatal": str(e)}
    violations, objective, metrics = evaluate_review(world, review, setting, unknown)
    enforced, evidence = diagnostic(world, review, setting, unknown)
    return {"violations": violations, "objective": objective, "metrics": metrics, "enforced": enforced,
            "evidence": evidence}


def write_ground_truth(world: World, gt: Path, setting: Setting) -> None:
    """truth.json: per scored contract, the answer key under this setting (fast track kept); for a fast-tracked
    contract also what the playbook would say, which decides whether an exception is worth it."""
    r = reading_of(setting)
    out = {}
    for c in world.contracts:
        if scored(world, c, setting):
            issues, decision = entry(world, c, r)
            out[c.id] = {"issues": issues, "decision": decision}
            if fast_track(c, r):
                issues, decision = entry(world, c, replace(r, fast_track_below=None))
                out[c.id].update(fast_tracked=True, playbook={"issues": issues, "decision": decision})
    (gt / "truth.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")


# ── the client's facts in a deliverable (the per-target diagnostic) ──────────

# target -> the drawn parameter that is the fact
PARAM_FACTS = {"liability_cap": "cap_multiple", "governing_law": "governing_law", "payment_terms": "payment_days",
               "decision_rule": "reject_at", "accepted_deviations": "tolerance_below",
               "auto_renewal": "renewal_notice_days", "data_protection": "dp_categories",
               "termination_convenience": "tfc_above", "small_contract_fast_track": "fast_track_below"}
FROM_MEDIUM = ("auto_renewal", "data_protection", "termination_convenience")
# target -> the codes whose presence on a contract tells a reading of that fact from another
FACT_CODES = {"liability_cap": ("LIABILITY_CAP",), "period_caps_out_of_round": ("LIABILITY_CAP",),
              "governing_law": ("GOVERNING_LAW",), "dispute_forum": ("GOVERNING_LAW",),
              "payment_terms": ("PAYMENT_TERMS",), "auto_renewal": ("AUTO_RENEWAL",),
              "data_protection": ("DATA_PROTECTION",), "customer_personal_data": ("DATA_PROTECTION",),
              "termination_convenience": ("TERMINATION_CONVENIENCE",),
              "round_points": tuple(code for code in CODES if code not in EASY_CODES)}
DECISION_FACTS = ("critical_issues", "decision_rule", "accepted_deviations")


def misreadings(setting: Setting) -> dict[str, tuple[str, Reading]]:
    """{target: (what the misreading is, the playbook read that way)} for the fixed facts in force: the most
    natural wrong reading of each, everything else as the client states it."""
    r = reading_of(setting)
    out = {"critical_issues": ("the governing law counted as a critical issue too",
                               replace(r, critical=r.critical + ("GOVERNING_LAW",)))}
    if not setting.at_least("medium"):
        out["period_caps_out_of_round"] = ("a cap of N months' fees flagged at N/12 of the annual value",
                                           replace(r, period_caps=True))
        out["round_points"] = ("all seven points checked and listed", replace(r, points=CODES, critical=CRITICAL))
    else:
        out["dispute_forum"] = ("only the governing law checked, not the courts or seat", replace(r, forum=False))
    if setting.at_least("hard"):
        out["customer_personal_data"] = ("data protection by category only", replace(r, customer_data=False))
        out["amendments"] = ("every record marked agreed applied, whatever its date", replace(r, amendments="agreed"))
        out["requests_to_sign"] = ("the e-mailed contracts marked sign, as asked", replace(r, follow_emails=True))
    return out


def _alternatives(setting: Setting) -> dict[str, dict[str, Reading]]:
    """{target: {label: reading}}: the other readings of each fact in force (the other candidates of a drawn
    figure, the misreading of a fixed fact)."""
    out: dict[str, dict[str, Reading]] = {}
    pools = _pools()
    for target, name in PARAM_FACTS.items():
        if (target in FROM_MEDIUM and not setting.at_least("medium")) or (
                target == "small_contract_fast_track" and not setting.at_least("hard")):
            continue
        out[target] = {f"{name}={v}": reading_of(Setting(setting.tier, setting.rule_seed, {**setting.params, name: v}))
                       for v in pools[name][setting.tier] if v != setting[name]}
    for target, (label, reading) in misreadings(setting).items():
        out[target] = {label: reading}
    for target, readings in _other_readings(setting).items():
        out[target].update(readings)
    return out


def _other_readings(setting: Setting) -> dict[str, dict[str, Reading]]:
    """Wrong readings of a fact that the diagnostic weighs besides misreadings() and the other candidates (none is an
    ablation: each is less natural than the one misreadings() names, or a slip at a figure's own boundary)."""
    r = reading_of(setting)
    out = {"accepted_deviations": {"below the sign-off limit, every contract short of a reject signed":
                                   replace(r, limit_covers_critical=True)},
           "governing_law": {"the courts or seat checked in place of the law": replace(r, law_checked=False)},
           "liability_cap": {"a cap exactly at the minimum flagged": replace(r, cap_multiple=r.cap_multiple + 1e-9)},
           "payment_terms": {"a payment term exactly at the minimum flagged":
                             replace(r, payment_days=r.payment_days + 1)},
           "decision_rule": {"a reject only above that count": replace(r, reject_at=r.reject_at + 1)}}
    if setting.at_least("medium"):
        out["critical_issues"] = {"data protection not counted as critical": replace(
            r, critical=tuple(code for code in r.critical if code != "DATA_PROTECTION"))}
        out["auto_renewal"] = {"a notice exactly at the minimum flagged":
                               replace(r, renewal_notice_days=r.renewal_notice_days + 1)}
    return out


def _excepted(world: World, review: dict[str, tuple[list[str], str]], r: Reading) -> set[str]:
    """The small contracts a review takes off the fast track the way an approved exception would: exactly the ones
    the playbook rejects, each with the playbook's entry. Such a review keeps the fast track for every other small
    contract, so those rejects cannot tell its threshold from a lower one. Empty when the review does anything
    else (a lower threshold leaves the rejects below it fast-tracked, or reviews a contract it would only
    negotiate)."""
    open_review = replace(r, fast_track_below=None)
    small = {c.id: entry(world, c, open_review) for c in world.contracts if fast_track(c, r)}
    rejects = {cid for cid, (_, decision) in small.items() if decision == "reject"}
    taken = {cid for cid in small if cid in review and (review[cid][0] or review[cid][1] != "sign")}
    if not taken or taken != rejects:
        return set()
    if any(set(review[cid][0]) != set(small[cid][0]) or review[cid][1] != "reject" for cid in taken):
        return set()
    return taken


def _sides(target: str, world: World, c: Contract, r: Reading, alt: Reading, listed: list[str], chosen: str,
           excepted: frozenset | set = frozenset()):
    """(what the client's reading gives, what the other reading gives, what the review has) on the one aspect of
    contract c's entry that tells the two readings of this fact apart; None when the entry cannot tell them."""
    if target in DECISION_FACTS:        # the decision the review's own issue list calls for
        seen = [code for code in listed if code in r.points]
        ours, theirs = decide(seen, c, r), decide(seen, c, alt)
        if set(alt.critical) < set(r.critical) and "sign" not in (ours, theirs):
            return None                 # reject against negotiate: a reject threshold misread looks the same
        return ours, theirs, chosen
    true, other = entry(world, c, r), entry(world, c, alt)
    if target == "small_contract_fast_track":
        if c.id in excepted or entry(world, c, replace(r, fast_track_below=None)) == ([], "sign"):
            return None                 # an approved exception, or reviewed or not the entry reads "sign"
        return fast_track(c, r), fast_track(c, alt), not listed and chosen == "sign"
    if target == "requests_to_sign":
        return true[1] == "sign", other[1] == "sign", chosen == "sign"
    if target == "amendments":
        codes = (CLAUSE_CODE[world.amendments[c.id].clause],) if c.id in world.amendments else ()
    else:
        codes = FACT_CODES[target]
    return tuple(tuple(code in issues for code in codes) for issues in (true[0], other[0], listed))


def diagnostic(world: World, review: dict[str, tuple[list[str], str]], setting: Setting,
               unknown: dict[str, list[str]] | None = None):
    """(enforced, evidence) per target in force: on the scored contracts where the client's reading of a fact and
    another reading give different entries, which one the review follows. A fact is not enforced when the review
    sides with some other reading more often than with the client's, enforced when it sides with the client's more
    often than with every other reading, and None when no contract tells (or the review follows neither). The
    other readings are the other candidates of a drawn figure, the misreading of a fixed fact and the less natural
    readings of _other_readings. The small contracts a review takes off the fast track as an approved exception
    would (_excepted) do not count against the fast track. The issue codes are enforced when every listed code is
    one of the playbook's; a review with other codes cannot be read for the other facts (None)."""
    r = reading_of(setting)
    alternatives = _alternatives(setting)
    if unknown:
        made_up = sorted({code for codes in unknown.values() for code in codes})
        return ({**dict.fromkeys(alternatives), "issue_codes": False},
                {"issue_codes": f"codes that are not the playbook's: {', '.join(made_up[:5])}"})
    enforced: dict[str, bool | None] = {"issue_codes": True}
    evidence: dict[str, str] = {}
    excepted = _excepted(world, review, r) if r.fast_track_below is not None else set()
    for target, alts in alternatives.items():
        verdict, notes = None, []
        for label, alt in alts.items():
            ours = theirs = 0
            for c in world.contracts:
                if c.id not in review or not scored(world, c, setting):
                    continue
                sides = _sides(target, world, c, r, alt, *review[c.id], excepted=excepted)
                if sides is None or sides[0] == sides[1]:
                    continue
                ours += sides[2] == sides[0]
                theirs += sides[2] == sides[1]
            if theirs > ours or (theirs and target == "requests_to_sign"):     # giving in once is giving in
                verdict = False
                notes.append(f"follows \"{label}\" on {theirs} of {ours + theirs} telling contracts")
            elif ours > theirs and verdict is None:
                verdict = True
                notes.append(f"follows the client's reading on {ours} of {ours + theirs} telling contracts")
        enforced[target] = verdict
        if notes:
            evidence[target] = notes[-1] if verdict is False else notes[0]
    return enforced, evidence


# ── reference: the answer key ────────────────────────────────────────────────

def reference_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """The answer key: the client's playbook applied to every clause as it is written, fast track kept."""
    _write(out_dir, review_under(world, reading_of(setting)))


def best_known_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """The answer key is the best any review that keeps the rules can do (objective_bound)."""
    reference_solution(world, out_dir, setting)


def objective_bound(world: World, setting: Setting) -> float:
    """Proven: every scored contract counts at most once in a review that keeps the fast track, so no valid review
    scores above 1.0 (a review that bends the fast track under an approved exception can)."""
    return 1.0


# ── baseline: the legal team's keyword checklist ─────────────────────────────

LAW_WORDS = {"CH": "Switzerland|Swiss", "SG": "Singapore", "EW": "England and Wales"}
SEAT_WORDS = {"CH": "Zurich", "SG": "Singapore", "EW": "London"}


def _sections(text: str) -> dict[str, str]:
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^Article \d+\. (.+)$", line)
        if m:
            cur = m.group(1).lower()
            out[cur] = ""
        elif cur:
            out[cur] += line + "\n"
    return out


def checklist_issues(c: Contract, r: Reading) -> list[str]:
    """What a careful but literal keyword checklist finds in the English version of the contract, with the
    figures of a reading: it handles digits, number words for payment days and "one half of"/"100% of", looks for
    an accepted city in the dispute sentence, and decides data protection by category only. It misses the
    paraphrases (a notice in months, "continues for a further year", "net 30", caps in words or thousands or as
    N months' fees), takes a mutual indemnity written as two promises for a one-way one and "without stating a
    reason" for no termination right."""
    text = "\n".join(f"Article {n}. {t}\n" + "\n".join(p) for n, (t, p) in
                     enumerate(_render_en(c, "", CUSTOMER["en"]), 1))
    sec = _sections(text)
    found = []
    cap = sec.get("limitation of liability", "")
    m = re.search(r"(\d+(?:\.\d+)?) times", cap)
    mult = 0.5 if "one half of" in cap else 1.0 if "100% of" in cap else float(m.group(1)) if m else None
    a = re.search(r"USD ([\d,]+)", cap)
    if mult is not None:
        if mult < r.cap_multiple:
            found.append("LIABILITY_CAP")
    elif a and int(a.group(1).replace(",", "")) < r.cap_multiple * c.value:
        found.append("LIABILITY_CAP")
    if r.laws is not None:
        law = sec.get("governing law and disputes", "")
        law_ok = re.search("|".join(LAW_WORDS[x] for x in r.laws), law)
        forum_ok = not r.forum or re.search("|".join(SEAT_WORDS[x] for x in r.laws), law.split(". ", 1)[-1])
        if not (law_ok and forum_ok):
            found.append("GOVERNING_LAW")
    scope = sec.get("scope and term", "")
    if "automatically" in scope:
        n = re.search(r"(\d+) days", scope)
        if n and int(n.group(1)) < r.renewal_notice_days:
            found.append("AUTO_RENEWAL")
    pay_txt = sec.get("fees and payment", "")
    for n, word in EN_WORDS.items():
        pay_txt = pay_txt.replace(f"{word} days", f"{n} days")
    pay = re.search(r"(\d+) days", pay_txt)
    if pay and int(pay.group(1)) < r.payment_days:
        found.append("PAYMENT_TERMS")
    if c.category in r.dp_categories and "data protection" not in text.lower():
        found.append("DATA_PROTECTION")
    if c.value > r.tfc_above and "convenience" not in sec.get("termination", ""):
        found.append("TERMINATION_CONVENIENCE")
    if "each party" not in sec.get("indemnity", "").lower():
        found.append("INDEMNITY")
    return [code for code in r.points if code in found]


def _checklist(world: World, r: Reading, decision=decide) -> dict:
    """The keyword checklist run with a reading's figures: every amendment record marked agreed applied (it does
    not compare dates), the fast track kept, the e-mails left aside."""
    out = {}
    for c in world.contracts:
        issues = [] if fast_track(c, r) else checklist_issues(as_read(world, c, "agreed"), r)
        out[c.id] = {"issues": issues, "decision": "sign" if fast_track(c, r) else decision(issues, c, r)}
    return out


def baseline_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """What the client does today: the legal team's own keyword checklist, run with its playbook's figures."""
    _write(out_dir, _checklist(world, reading_of(setting)))


# ── the literal solution and the solver that never asks ──────────────────────

def literal_issues(c: Contract) -> list[str]:
    """A careful counsel's checklist with no playbook: every clause read correctly (whatever its wording or
    language), judged by common market practice. A cap below one year's fees (a cap of N months' fees is N/12), a
    payment term under 30 days, an automatic renewal with less than two months' notice, no data-protection clause
    where the supplier handles personal data (IT & data services, marketing, or customers' data in the scope), no
    termination for convenience, a one-way indemnity. The governing law is not flagged: nothing on hand says which
    laws the company accepts."""
    found = []
    if c.cap_ratio() < 1.0:
        found.append("LIABILITY_CAP")
    if c.renew is not None and c.renew[0] < 60:
        found.append("AUTO_RENEWAL")
    if c.pay[0] < 30:
        found.append("PAYMENT_TERMS")
    if (c.category in ("it_data", "marketing") or c.cust_data) and c.dp is None:
        found.append("DATA_PROTECTION")
    if c.tfc is None:
        found.append("TERMINATION_CONVENIENCE")
    if c.indemnity == "one_way":
        found.append("INDEMNITY")
    return found


def _naive(issues, c: Contract | None = None, r: Reading | None = None) -> str:
    """The request's own words: a contract with any issue needs changes, the others are signed."""
    return "negotiate" if issues else "sign"


def _literal(world: World) -> dict:
    out = {}
    for c in world.contracts:
        issues = literal_issues(as_read(world, c, "agreed"))
        out[c.id] = {"issues": issues, "decision": _naive(issues)}
    return out


def literal_solution(world: World, out_dir: Path) -> None:
    """The request done as written ("tell us which ones need changes before we sign"): every contract reviewed,
    the e-mailed ones and the small ones included, an amendment marked agreed applied, the issues of
    literal_issues, and "negotiate" for a contract with any issue, otherwise "sign" (the same review in every
    setting)."""
    _write(out_dir, _literal(world))


def _natural(r: Reading, law_critical: bool = True, forum: bool = False, customer_data: bool = False,
             amendments: str = "agreed") -> Reading:
    """A playbook with every fixed fact read the way a reviewer who never asks reads it: all seven points listed, a
    cap of N months' fees at N/12, the e-mails not obeyed, and the four facts nothing on hand settles (UNSETTLED)
    read one way or the other (by default each ablation's misreading)."""
    return replace(r, points=CODES, critical=CRITICAL + (("GOVERNING_LAW",) if law_critical else ()),
                   period_caps=True, forum=forum, customer_data=customer_data, amendments=amendments)


# The fixed facts a reviewer who never asks cannot settle from the request or the data, each with its two plausible
# readings: whether the governing law is a critical issue, whether GOVERNING_LAW covers the courts or seat (the
# article is "Governing Law and Disputes"), whether a scope that hands over customers' personal data needs the
# data-protection clause outside the listed categories, and whether an agreed amendment dated before its draft
# still applies.
UNSETTLED = {"law_critical": (True, False), "forum": (False, True), "customer_data": (False, True),
             "amendments": ("agreed", "after_draft")}


def client_unsettled(tier: str) -> dict:
    """How the client reads the four UNSETTLED facts in a tier (what a lucky guess would take)."""
    return {"law_critical": False, "forum": tier != "easy", "customer_data": tier == "hard",
            "amendments": "after_draft"}


def robust_solution(world: World, out_dir: Path, tier: str, candidates: dict[str, list],
                    unsettled: list[dict] | None = None) -> None:
    """The solver that never asks. It reads every clause correctly, takes the fixed facts the visible material
    settles the natural way (_natural) and hedges the four it does not (UNSETTLED): since the objective counts
    contracts, it gives each contract the entry that is exactly right under the largest number of combinations of
    the tier's candidate figures and of the two readings of each unsettled fact, all weighted alike. In hard it
    fast-tracks below the largest candidate threshold, the only choice that keeps the rule under every candidate.
    `unsettled` (gt_report.py) replaces the readings it hedges over, e.g. with [client_unsettled(tier)]."""
    names = [name for name in candidates if name != "fast_track_below"]
    readings = unsettled or [dict(zip(UNSETTLED, values)) for values in product(*UNSETTLED.values())]
    votes = {c.id: Counter() for c in world.contracts}
    for combo in product(*(candidates[name] for name in names)):
        params = dict(zip(names, combo), fast_track_below=max(candidates["fast_track_below"]))
        client = reading_of(Setting(tier, 0, params))
        for unsettled in readings:
            r = _natural(client, **unsettled)
            for c in world.contracts:
                issues, decision = entry(world, c, r)
                votes[c.id][(tuple(issues), decision)] += 1
    out = {}
    for cid, counts in votes.items():
        issues, decision = max(sorted(counts), key=counts.get)
        out[cid] = {"issues": list(issues), "decision": decision}
    _write(out_dir, out)


# ── ground truth audit: ablations and shortcuts ──────────────────────────────

# The codes a reviewer would make up from the article titles of the English template: three are right
# (GOVERNING_LAW, DATA_PROTECTION, INDEMNITY), four are not.
TITLE_CODES = {"LIABILITY_CAP": "LIMITATION_OF_LIABILITY", "PAYMENT_TERMS": "PAYMENT", "AUTO_RENEWAL": "RENEWAL",
               "TERMINATION_CONVENIENCE": "TERMINATION"}


def _guessed_codes(doc: dict) -> dict:
    return {cid: {"issues": [TITLE_CODES.get(code, code) for code in e["issues"]], "decision": e["decision"]}
            for cid, e in doc.items()}


def ablations(world: World, setting: Setting) -> dict:
    """{target: writer} for the facts that are not one drawn parameter: the answer key under the most natural
    misreading of that fact alone (misreadings), and for the issue codes the answer key with codes made up from
    the article titles."""
    out = {target: (lambda out_dir, reading=reading: _write(out_dir, review_under(world, reading)))
           for target, (_, reading) in misreadings(setting).items()}
    out["issue_codes"] = lambda out_dir: _write(out_dir, _guessed_codes(review_under(world, reading_of(setting))))
    return out


def _market(r: Reading) -> Reading:
    """Common market practice in place of the client's figures, as literal_issues has it: a cap of one year's
    fees, 30 days to pay, two months' notice, a clause wherever the category handles personal data, termination
    for convenience in every contract, the governing law not judged; every point checked, no fast track."""
    return replace(r, cap_multiple=1.0, laws=None, payment_days=30, renewal_notice_days=60,
                   dp_categories=("it_data", "marketing"), tfc_above=-1, fast_track_below=None, points=CODES,
                   critical=CRITICAL, period_caps=True, forum=False, customer_data=False)


def shortcuts(world: World, setting: Setting) -> dict:
    r = reading_of(setting)
    key = review_under(world, r)
    contracts = world.by_id()

    def on_fast_track(doc: dict) -> dict:
        return {cid: ({"issues": [], "decision": "sign"} if fast_track(contracts[cid], r) else e)
                for cid, e in doc.items()}

    def client_rules(doc: dict) -> dict:
        """The same issue lists with the client's decision rule and fast track."""
        return on_fast_track({cid: {"issues": e["issues"],
                                    "decision": decide([i for i in e["issues"] if i in r.points], contracts[cid], r)}
                              for cid, e in doc.items()})

    def sign_everything(out_dir):
        """Sign every contract as it stands: no issues, every decision "sign"."""
        _write(out_dir, {cid: {"issues": [], "decision": "sign"} for cid in key})

    def flag_everything(out_dir):
        """List every code of the round on every contract, decided by the client's rule (fast track kept)."""
        _write(out_dir, client_rules({cid: {"issues": list(r.points), "decision": ""} for cid in key}))

    def reject_everything(out_dir):
        """Take no risk: every critical code on every contract and every one a "reject" (fast track kept)."""
        _write(out_dir, on_fast_track({cid: {"issues": list(r.critical), "decision": "reject"} for cid in key}))

    def pattern_matcher(out_dir):
        """A keyword matcher on the visible contracts with market-practice thresholds and no client fact:
        "negotiate" for any hit, every contract reviewed."""
        _write(out_dir, _checklist(world, _market(r), decision=_naive))

    def pattern_matcher_client_rules(out_dir):
        """The same keyword matcher's issue lists, with the client's decision rule and fast track."""
        _write(out_dir, client_rules(_checklist(world, _market(r), decision=_naive)))

    def literal_one_rule(out_dir):
        """The literal solution with the one rule it breaks satisfied: the small contracts fast-tracked (hard)."""
        _write(out_dir, on_fast_track(_literal(world)))

    def literal_client_rules(out_dir):
        """The literal solution's issue lists (every clause read right, market practice) with the client's
        decision rule and fast track."""
        _write(out_dir, client_rules(_literal(world)))

    def guessed_codes(out_dir):
        """The answer key with issue codes made up from the article titles (LIMITATION_OF_LIABILITY, PAYMENT)."""
        _write(out_dir, _guessed_codes(key))

    def client_checklist(out_dir):
        """Hand back the client's own keyword checklist (a pattern matcher that knows the playbook)."""
        _write(out_dir, _checklist(world, r))

    def negotiate_everything(out_dir):
        """Ask for changes on every contract and name none: no issues, every decision "negotiate" (fast track
        kept)."""
        _write(out_dir, on_fast_track({cid: {"issues": [], "decision": "negotiate"} for cid in key}))

    def literal_reject_critical(out_dir):
        """The literal review with a decision rule guessed from its own list: "reject" for a cap, data-protection or
        indemnity issue, "negotiate" for any other issue, "sign" otherwise (fast track kept)."""
        doc = {cid: {"issues": e["issues"],
                     "decision": "reject" if set(e["issues"]) & set(CRITICAL) else _naive(e["issues"])}
               for cid, e in _literal(world).items()}
        _write(out_dir, on_fast_track(doc))

    def literal_four_points(out_dir):
        """The literal review's issue lists cut to the four points a playbook most often starts with (cap, law,
        payment, indemnity), with the client's decision rule and fast track."""
        _write(out_dir, client_rules({cid: {"issues": [i for i in e["issues"] if i in EASY_CODES], "decision": ""}
                                      for cid, e in _literal(world).items()}))

    return {f.__name__: f for f in (sign_everything, flag_everything, reject_everything, pattern_matcher,
                                    pattern_matcher_client_rules, literal_one_rule, literal_client_rules,
                                    guessed_codes, client_checklist, negotiate_everything, literal_reject_critical,
                                    literal_four_points)}


def partial_reviews(world: World, setting: Setting) -> dict:
    """{name: (what it leaves out, review)}: the answer key with one part of the work left undone. Not shortcuts
    (each does most of the work and loses in proportion) and not single facts; gt_report.py measures what each
    part is worth. keyword_reading comes from the other side: every client fact (it is the baseline) and only
    the careful reading of the clauses left undone, but for the one wording that costs the checklist most."""
    r = reading_of(setting)
    key = review_under(world, r)
    contracts = world.by_id()
    out = {"no_decision_judgement": (
        "the right issue list for every contract, but \"negotiate\" wherever there is an issue (no reject, no "
        "sign-off limit)",
        {cid: {"issues": e["issues"], "decision": "sign" if fast_track(contracts[cid], r) else _naive(e["issues"])}
         for cid, e in key.items()})}
    keywords = _checklist(world, r)
    for c in world.contracts:
        if not fast_track(c, r) and as_read(world, c, "agreed").indemnity == "mutual_p":
            issues = [code for code in keywords[c.id]["issues"] if code != "INDEMNITY"]
            keywords[c.id] = {"issues": issues, "decision": decide(issues, c, r)}
    out["keyword_reading"] = ("every client fact, but the clauses read by the legal team's keywords (the baseline), "
                              "except that a mutual indemnity written as two promises is read as mutual", keywords)
    if setting.at_least("hard"):
        out["own_paper_only"] = (
            "the contracts on the supplier's paper (another language) signed unread",
            {cid: ({"issues": [], "decision": "sign"} if contracts[cid].foreign else e) for cid, e in key.items()})
        out["no_amendments"] = ("the amendments folder not opened",
                                review_under(world, replace(r, amendments="none")))
    return out


def diagnostic_cases(world: World, setting: Setting) -> dict:
    """{name: (target or None, what it is, review)}: deliverables that are neither the reference nor an ablation,
    for gt_report.py to measure the diagnostic on. With target None the review has every fact right and differs
    from the answer key in other ways (the diagnostic must call no fact in force not enforced); with a target it
    misreads that fact in a way no ablation does (the diagnostic should call it not enforced)."""
    r = reading_of(setting)
    key = review_under(world, r)
    contracts = world.by_id()
    open_key = [c for c in world.contracts if scored(world, c, setting) and not fast_track(c, r)
                and c.id not in world.emailed()]
    slips = dict(key)
    for c in open_key[:2]:
        slips[c.id] = {"issues": key[c.id]["issues"], "decision": "sign" if key[c.id]["decision"] != "sign"
                       else "negotiate"}
    out = {"format": (None, "the answer key with codes in lower case, padded, repeated and reversed, decisions in "
                            "capitals",
                      {cid: {"issues": [f" {code.lower()} " for code in reversed(e["issues"])] + e["issues"][:1],
                             "decision": e["decision"].upper()} for cid, e in key.items()}),
           "two_slips": (None, "the answer key with the decision of two contracts wrong", slips)}
    if not setting.at_least("hard"):
        literal = _literal(world)
        out["unscored_otherwise"] = (None, "the answer key on the contracts of the round, the literal review on the "
                                           "others", {cid: key[cid] if scored(world, contracts[cid], setting)
                                                      else literal[cid] for cid in key})
    else:
        out["best_exception"] = (None, "the answer key with every small contract the playbook rejects reviewed (an "
                                       "approved exception)", bent_reviews(world, setting)["best_exception"][1])
    misread = {"liability_cap": ("a cap exactly at the minimum flagged", replace(r, cap_multiple=r.cap_multiple + 1e-9)),
               "payment_terms": ("a payment term exactly at the minimum flagged",
                                 replace(r, payment_days=r.payment_days + 1)),
               "governing_law": ("the courts or seat checked in place of the law", replace(r, law_checked=False)),
               "decision_rule": ("a reject only above the count", replace(r, reject_at=r.reject_at + 1)),
               "accepted_deviations": ("critical issues short of a reject signed below the limit",
                                       replace(r, limit_covers_critical=True))}
    if setting.at_least("medium"):
        misread["auto_renewal"] = ("a notice exactly at the minimum flagged",
                                   replace(r, renewal_notice_days=r.renewal_notice_days + 1))
        misread["critical_issues"] = ("data protection not counted as critical",
                                      replace(r, critical=tuple(x for x in r.critical if x != "DATA_PROTECTION")))
    if setting.at_least("hard"):
        misread["amendments"] = ("the supplier's proposal applied too", replace(r, amendments="all"))
    for target, (what, reading) in misread.items():
        out[f"misread_{target}"] = (target, what, review_under(world, reading))
    if setting.at_least("hard"):
        out["misread_requests_to_sign"] = ("requests_to_sign", "the COO's two renewals signed, the other e-mail not",
                                           {**key, **{cid: {"issues": [], "decision": "sign"}
                                                      for cid in world.emails[1]}})
    return out


def bent_reviews(world: World, setting: Setting) -> dict:
    """{name: (how many small contracts it takes off the fast track, review)} in hard: the answer key with the
    fast track bent, to be scored with the rule relaxed. best_exception reviews the small contracts the playbook
    rejects and no other; every_small_contract reviews every small contract the playbook finds something in."""
    r = reading_of(setting)
    key = review_under(world, r)
    playbook = review_under(world, replace(r, fast_track_below=None))
    small = [c.id for c in world.contracts if fast_track(c, r)]
    rejects = [cid for cid in small if playbook[cid]["decision"] == "reject"]
    found = [cid for cid in small if playbook[cid] != key[cid]]
    return {"best_exception": (len(rejects), {**key, **{cid: playbook[cid] for cid in rejects}}),
            "every_small_contract": (len(found), {**key, **{cid: playbook[cid] for cid in found}})}


def violating_examples(world: World, setting: Setting) -> dict:
    r = reading_of(setting)
    key = review_under(world, r)

    def drop(out_dir):
        cid = next(c.id for c in world.contracts if not fast_track(c, r))
        _write(out_dir, {k: v for k, v in key.items() if k != cid})

    def made_up_code(out_dir):
        cid = next(cid for cid, e in key.items() if e["issues"])
        issues = ["LIMITATION_OF_LIABILITY"] + key[cid]["issues"][1:]
        _write(out_dir, {**key, cid: {"issues": issues, "decision": key[cid]["decision"]}})

    def review_small(out_dir):
        c = next(c for c in world.contracts if fast_track(c, r))
        issues, decision = entry(world, c, replace(r, fast_track_below=None))
        if not issues:
            issues = ["PAYMENT_TERMS"]
            decision = decide(issues, c, r)
        _write(out_dir, {**key, c.id: {"issues": issues, "decision": decision}})

    out = {"all_contracts_reviewed": drop, "known_issue_codes": made_up_code}
    if setting.at_least("hard"):
        out["small_contract_fast_track"] = review_small
    return out
