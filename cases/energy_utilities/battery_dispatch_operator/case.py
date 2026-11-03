"""Solar-plus-storage battery dispatch for one week (original FDE-Bench v2 case).

A grid-scale battery sits behind the same connection point as a solar farm.
The operator asks for next week's charge/discharge plan "to make the most
money". What decides validity and quality (per-direction efficiency, the
warranty state-of-charge window, the end-of-week state of charge, an amended
export cap lower than the agreement on file, grid charging only off-peak, the
evening emergency reserve, degradation cost, 15-minute settlement against an
hourly price file, a spring daylight-saving change, dated grid notices) is in
the requirements and must be asked for. Scoring settles the plan against true
prices that differ from the forecast; the reference only sees the forecast.

The data is the same in every setting. A setting decides which rules apply and
their values:

  tiers
    easy    the core problem: SOC window, power, per-direction efficiency, end-of-week SOC, the amended
            export cap, the clock change; grid import at any hour, no evening reserve, no degradation charge
    medium  + the off-peak import window, the evening reserve and a degradation cost per MWh
    hard    + three dated notices (the substation works end early and the export cap returns to 30 MW; a
            DSO export limit on one evening; the battery offline 08:00-20:00 on one day for inverter
            maintenance) and the trading desk's push to spend the reserve
  rule seeds (case.yaml `params`; each parameter drawn on its own)
    soc_window       warranty SOC window, % (10-90, 15-85, 5-95)
    efficiency       one-way efficiency on charge / on discharge, % (92/92, 95/89, 90/94)
    end_soc          minimum SOC at the end of the week, % (50, 40, 30); the week starts at 50%
    export_cap       amended export limit while the substation works last, MW (18, 15, 12; below the 20 MW
                     battery, so it limits evening sales and clips solar)
    import_window    grid import only in quarters starting in this window (00-06, 01-05, 02-08; easy: any)
    reserve_pct      evening reserve, % (20, 30, 15; easy: 0)
    reserve_window   the reserve's hours (17-21, 18-22, 16-20; easy: none)
    degradation      EUR per MWh of charge plus discharge (5, 15, 25; easy: 0)
    works_end        hard: the day the works end, from 00:00 the agreement's 30 MW applies again
    dso_day, dso_mw  hard: the DSO limits site export to dso_mw MW (10, 5, 8) on dso_day 18:00-21:00
    outage_day       hard: inverter maintenance, the battery is offline on that day 08:00-20:00
  derive_params adds the values the texts state (MWh equivalents, efficiencies as decimals, window times);
  admissible rejects a reserve at or below the warranty floor.

Last week's dispatch log in the data was planned by last week's planner under last week's conventions
(LOG_RULES): 10-90%, 92% each way, 50% at the start and end, a 20% reserve 17:00-21:00, import 00:00-06:00,
a 25 MW cap. It is the same in every setting and stale evidence under every draw (the cap always differs).
"""

from __future__ import annotations

import datetime as dt
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from fdebench2.cases import Setting
from fdebench2.casekit import Fatal, labels, number, read_csv, write_csv

# ── constants ────────────────────────────────────────────────────────────────

WEEK_START = dt.date(2027, 3, 22)       # Monday; clocks go 02:00 -> 03:00 on Sunday 2027-03-28
LOG_START = dt.date(2027, 3, 15)        # last week's dispatch log (no clock change)
DST_DAY = dt.date(2027, 3, 28)
DT_H = 0.25                             # settlement interval, hours
CAPACITY = 40.0                         # MWh
PMAX = 20.0                             # MW, charge and discharge
SOC_START = 0.50 * CAPACITY             # the battery's state at Monday 00:00 (where last week's log ends)
AGREEMENT_EXPORT = 30.0                 # MW, the connection agreement on file
IMPORT_CAP = 20.0
DSO_FROM, DSO_TO = 18 * 60, 21 * 60     # hard: the DSO's export limit applies to quarters starting 18:00-20:45
OUTAGE_FROM, OUTAGE_TO = 8 * 60, 20 * 60    # hard: the battery is offline in quarters starting 08:00-19:45
NIGHT_TO = 6 * 60                       # the reference buys at night (before 06:00) when import is allowed any time
SOLAR_MW = 30.0
P_TOL, E_TOL = 1e-4, 0.02               # MW; MWh (0.05% of capacity: a plan rounded to 2-3 decimals stays valid)


@dataclass(frozen=True)
class Rules:
    """One setting's rules in model units (MWh, MW, minutes of the day)."""

    soc_min: float                      # MWh
    soc_max: float
    eta_c: float                        # one-way efficiency on charge
    eta_d: float                        # and on discharge
    soc_end: float                      # MWh, minimum after the last quarter
    export_cap: float                   # MW while the substation works last
    works_end: dt.date | None           # from this day 00:00 the agreement's 30 MW applies again
    import_window: tuple[int, int] | None   # grid import only in quarters starting in [from, to); None: any time
    reserve: float | None               # MWh held at every quarter boundary in [res_from, res_to]; None: no reserve
    res_from: int
    res_to: int
    degradation: float                  # EUR per MWh of charge plus discharge at the meter
    dso_day: dt.date | None             # the DSO's export limit on that day, DSO_FROM..DSO_TO
    dso_mw: float
    outage_day: dt.date | None          # the battery is offline on that day, OUTAGE_FROM..OUTAGE_TO

    def base_cap(self, d: dt.date) -> float:
        return AGREEMENT_EXPORT if self.works_end is not None and d >= self.works_end else self.export_cap

    def in_dso(self, d: dt.date, m: int) -> bool:
        return self.dso_day == d and DSO_FROM <= m < DSO_TO

    def cap(self, d: dt.date, m: int) -> float:
        """The site's export limit in that quarter (what the controller clips solar to)."""
        return min(self.base_cap(d), self.dso_mw) if self.in_dso(d, m) else self.base_cap(d)

    def can_import(self, m: int) -> bool:
        return self.import_window is None or self.import_window[0] <= m < self.import_window[1]

    def offline(self, d: dt.date, m: int) -> bool:
        return self.outage_day == d and OUTAGE_FROM <= m < OUTAGE_TO

    def in_reserve(self, m: int) -> bool:
        """The quarter starting at m ends inside the reserve hours, so its end state is checked."""
        return self.reserve is not None and self.res_from <= m + 15 <= self.res_to


# Last week's conventions: the dispatch log in the data was planned under these (the case without settings).
LOG_RULES = Rules(soc_min=4.0, soc_max=36.0, eta_c=0.92, eta_d=0.92, soc_end=20.0, export_cap=25.0, works_end=None,
                  import_window=(0, 6 * 60), reserve=8.0, res_from=17 * 60, res_to=21 * 60, degradation=5.0,
                  dso_day=None, dso_mw=0.0, outage_day=None)


def _pair(text: str, sep: str) -> tuple[int, int]:
    a, b = str(text).split(sep)
    return int(a), int(b)


def _day(value) -> dt.date | None:
    return None if str(value) == "none" else dt.date.fromisoformat(str(value))


def rules_of(setting: Setting) -> Rules:
    p = setting.params
    lo, hi = _pair(p["soc_window"], "-")
    ec, ed = _pair(p["efficiency"], "/")
    window = None if p["import_window"] == "any" else tuple(60 * h for h in _pair(p["import_window"], "-"))
    reserve = float(p["reserve_pct"]) * CAPACITY / 100 if p["reserve_window"] != "none" else None
    r_from, r_to = (60 * h for h in _pair(p["reserve_window"], "-")) if reserve is not None else (0, 0)
    return Rules(soc_min=lo * CAPACITY / 100, soc_max=hi * CAPACITY / 100, eta_c=ec / 100, eta_d=ed / 100,
                 soc_end=float(p["end_soc"]) * CAPACITY / 100, export_cap=float(p["export_cap"]),
                 works_end=_day(p["works_end"]), import_window=window, reserve=reserve, res_from=r_from,
                 res_to=r_to, degradation=float(p["degradation"]), dso_day=_day(p["dso_day"]),
                 dso_mw=0.0 if p["dso_mw"] == "none" else float(p["dso_mw"]), outage_day=_day(p["outage_day"]))


# ── rule seeds: derived values and admissible combinations ───────────────────

def _decimal(pct: int) -> dict:
    text = f"{pct / 100:.2f}"
    return {"zh": text, "en": text, "ko": text, "ja": text, "es": text.replace(".", ",")}


def derive_params(params: dict, tier: str) -> dict:
    """The numbers the requirements state, from the drawn values: MWh equivalents of the percentages, the
    efficiencies as decimals (decimal comma in es) and the first and last quarter of each window."""
    lo, hi = _pair(params["soc_window"], "-")
    ec, ed = _pair(params["efficiency"], "/")
    mwh = lambda pct: int(pct) * int(CAPACITY) // 100      # every candidate is a whole number of MWh
    if params["import_window"] == "any":
        import_from, import_last = "00:00", "23:45"
    else:
        a, b = _pair(params["import_window"], "-")
        import_from, import_last = f"{a:02d}:00", f"{b - 1:02d}:45"
    if params["reserve_window"] == "none":
        reserve_from = reserve_to = "-"
    else:
        a, b = _pair(params["reserve_window"], "-")
        reserve_from, reserve_to = f"{a:02d}:00", f"{b:02d}:00"
    return {"soc_min": lo, "soc_max": hi, "soc_min_mwh": mwh(lo), "soc_max_mwh": mwh(hi),
            "eta_charge_pct": ec, "eta_discharge_pct": ed, "eta_charge": _decimal(ec), "eta_discharge": _decimal(ed),
            "end_soc_mwh": mwh(params["end_soc"]), "reserve_mwh": mwh(params["reserve_pct"]),
            "import_from": import_from, "import_last": import_last,
            "reserve_from": reserve_from, "reserve_to": reserve_to}


def admissible(params: dict, tier: str) -> bool:
    """A reserve sits above the warranty floor (a 15% reserve under a 15-85% window would be no rule at all)."""
    return params["reserve_window"] == "none" or int(params["reserve_pct"]) > int(params["soc_min"])


# ── world ────────────────────────────────────────────────────────────────────

@dataclass
class Horizon:
    slots: list[tuple[dt.date, int]]    # (local date, minute of day) of each 15-minute interval start
    solar: list[float]                  # MW average over the interval
    price_fc: list[float]               # EUR/MWh forecast (hourly value repeated over its quarters)
    price_true: list[float] = field(default_factory=list)

    def ts(self, i: int) -> str:
        d, m = self.slots[i]
        return f"{d.isoformat()} {m // 60:02d}:{m % 60:02d}"


@dataclass
class World:
    week: Horizon
    log: Horizon
    log_plan: tuple[list[float], list[float]]
    _index: dict = field(default_factory=dict)

    def index(self) -> dict[str, int]:
        if not self._index:
            self._index.update({self.week.ts(i): i for i in range(len(self.week.slots))})
        return self._index


def _slots(start: dt.date) -> list[tuple[dt.date, int]]:
    out = []
    for k in range(7):
        d = start + dt.timedelta(days=k)
        for m in range(0, 1440, 15):
            if d == DST_DAY and 120 <= m < 180:
                continue                # 02:00-02:59 does not exist on the clock-change night
            out.append((d, m))
    return out


def _bell(x: float, mu: float, sd: float) -> float:
    return math.exp(-0.5 * ((x - mu) / sd) ** 2)


def _horizon(rng: random.Random, start: dt.date, sun: list[float], true_noise: bool) -> Horizon:
    slots = _slots(start)
    hour_fc: dict[tuple[dt.date, int], float] = {}
    hour_true: dict[tuple[dt.date, int], float] = {}
    for k in range(7):
        d = start + dt.timedelta(days=k)
        shift = 1.0 if d >= DST_DAY else 0.0          # summer time: the sun (and the price dip) an hour later
        weekend = 0.86 if d.weekday() >= 5 else 1.0
        level = rng.uniform(0.93, 1.08)
        bias = rng.gauss(0, 4.0)
        for h in range(24):
            x = h + 0.5
            p = (40 + 12 * _bell(x, 8.5, 1.3) + 26 * _bell(x, 8.5, 1.0)
                 - 46 * sun[k] * _bell(x, 13.0 + shift, 2.3)
                 + 92 * _bell(x, 19.5, 1.4) + 14 * _bell(x, 22.5, 1.2))
            p = max(3.0, p * weekend * level + rng.gauss(0, 3.0))
            hour_fc[(d, h)] = round(p, 2)
            hour_true[(d, h)] = round(max(0.0, p + bias + rng.gauss(0, 7.0)), 2) if true_noise else round(p, 2)
    solar = []
    for d, m in slots:
        k = (d - start).days
        shift = 60 if d >= DST_DAY else 0
        t = (m + 7.5 - (6 * 60 + 45 + shift)) / (12 * 60)
        base = math.sin(math.pi * t) ** 1.3 if 0 < t < 1 else 0.0
        cloud = 1.0 if sun[k] > 0.85 else rng.uniform(0.7, 1.05)
        solar.append(round(min(SOLAR_MW, SOLAR_MW * sun[k] * base * cloud * 1.04), 2) if base > 0 else 0.0)
    pf = [hour_fc[(d, m // 60)] for d, m in slots]
    pt = [hour_true[(d, m // 60)] for d, m in slots]
    return Horizon(slots, solar, pf, pt)


def build_world(seed: int) -> World:
    rng = random.Random(seed)
    sun_week = [round(min(1.0, s + rng.uniform(-0.04, 0.04)), 3) for s in (0.92, 1.0, 0.5, 0.32, 0.85, 1.0, 0.98)]
    week = _horizon(rng, WEEK_START, sun_week, true_noise=True)
    sun_log = [round(min(1.0, s + rng.uniform(-0.04, 0.04)), 3) for s in (0.6, 0.9, 1.0, 0.4, 0.7, 0.95, 0.55)]
    log = _horizon(rng, LOG_START, sun_log, true_noise=False)
    world = World(week, log, ([], []))
    world.log_plan = _heuristic(log, LOG_RULES, last_week=True)
    return world


# ── data rendering ───────────────────────────────────────────────────────────

FILES = {
    "price": {"zh": "电价预测.csv", "en": "price_forecast.csv", "ko": "가격예측.csv", "ja": "価格予測.csv",
              "es": "prevision_precios.csv"},
    "solar": {"zh": "光伏出力预测.csv", "en": "solar_forecast.csv", "ko": "태양광예측.csv", "ja": "太陽光予測.csv",
              "es": "prevision_solar.csv"},
    "spec": {"zh": "电池规格.csv", "en": "battery_spec.csv", "ko": "배터리사양.csv", "ja": "蓄電池仕様.csv",
             "es": "ficha_bateria.csv"},
    "log": {"zh": "上周调度记录.csv", "en": "dispatch_log_last_week.csv", "ko": "지난주운전기록.csv",
            "ja": "先週運転記録.csv", "es": "registro_despacho_semana_pasada.csv"},
    "agreement": {"zh": "并网协议.md", "en": "connection_agreement.md", "ko": "계통연계계약.md", "ja": "系統連系契約.md",
                  "es": "contrato_conexion.md"},
}
COLS = {
    "ts": {"zh": "时间", "en": "timestamp", "ko": "시각", "ja": "日時", "es": "fecha_hora"},
    "price": {"zh": "日前电价_欧元每MWh", "en": "day_ahead_price_eur_mwh", "ko": "하루전가격_EUR_MWh",
              "ja": "前日価格_EUR_MWh", "es": "precio_diario_eur_mwh"},
    "solar": {"zh": "光伏出力_MW", "en": "solar_mw", "ko": "태양광출력_MW", "ja": "太陽光出力_MW", "es": "solar_mw"},
    "param": {"zh": "参数", "en": "parameter", "ko": "항목", "ja": "項目", "es": "parametro"},
    "value": {"zh": "数值", "en": "value", "ko": "값", "ja": "値", "es": "valor"},
    "unit": {"zh": "单位", "en": "unit", "ko": "단위", "ja": "単位", "es": "unidad"},
    "charge": {"zh": "充电_MW", "en": "charge_mw", "ko": "충전_MW", "ja": "充電_MW", "es": "carga_mw"},
    "discharge": {"zh": "放电_MW", "en": "discharge_mw", "ko": "방전_MW", "ja": "放電_MW", "es": "descarga_mw"},
    "soc": {"zh": "荷电状态_百分比", "en": "soc_pct", "ko": "충전상태_퍼센트", "ja": "充電率_パーセント",
            "es": "estado_carga_pct"},
}
SPEC = {
    "energy": {"zh": "额定容量", "en": "Rated energy", "ko": "정격 용량", "ja": "定格容量", "es": "Energía nominal"},
    "pch": {"zh": "最大充电功率", "en": "Max charge power", "ko": "최대 충전 출력", "ja": "最大充電出力",
            "es": "Potencia máxima de carga"},
    "pdis": {"zh": "最大放电功率", "en": "Max discharge power", "ko": "최대 방전 출력", "ja": "最大放電出力",
             "es": "Potencia máxima de descarga"},
    "rte": {"zh": "往返效率", "en": "Round-trip efficiency", "ko": "왕복 효율", "ja": "往復効率",
            "es": "Eficiencia de ida y vuelta"},
    "socmin": {"zh": "厂家允许最低荷电状态", "en": "Manufacturer minimum SOC", "ko": "제조사 최저 충전상태",
               "ja": "メーカー許容最低充電率", "es": "SOC mínimo del fabricante"},
    "socmax": {"zh": "厂家允许最高荷电状态", "en": "Manufacturer maximum SOC", "ko": "제조사 최고 충전상태",
               "ja": "メーカー許容最高充電率", "es": "SOC máximo del fabricante"},
    "solar": {"zh": "同站光伏装机容量", "en": "Co-located solar capacity", "ko": "동일 부지 태양광 설비용량",
              "ja": "併設太陽光の設備容量", "es": "Potencia solar en el mismo emplazamiento"},
}
AGREEMENT = {
    "en": """# Connection agreement (summary of the signed agreement, 2024)

Site: Llano Verde solar and storage park (Spain), one shared point of connection.

- Maximum export capacity at the point of connection: {exp} MW.
- Maximum import capacity at the point of connection: {imp} MW.
- The solar farm and the battery are metered together at the point of connection; export means net injection of the site into the grid.
- The site controller curtails the solar inverters automatically whenever the site would exceed the export capacity.
- Clock: all schedules exchanged under this agreement use local time.
""",
    "es": """# Contrato de conexión (resumen del contrato firmado, 2024)

Emplazamiento: parque solar con almacenamiento Llano Verde (España), un único punto de conexión compartido.

- Capacidad máxima de vertido en el punto de conexión: {exp} MW.
- Capacidad máxima de consumo desde la red en el punto de conexión: {imp} MW.
- La planta solar y la batería se miden juntas en el punto de conexión; vertido significa inyección neta del emplazamiento a la red.
- El controlador de la planta limita automáticamente los inversores solares cuando el emplazamiento superaría la capacidad de vertido.
- Horario: todos los programas intercambiados bajo este contrato usan la hora local.
""",
    "zh": """# 并网协议（2024 年签署协议摘要）

场站：利亚诺韦尔德光储电站（西班牙），光伏与储能共用一个并网点。

- 并网点最大上网容量：{exp} MW。
- 并网点最大下网（从电网取电）容量：{imp} MW。
- 光伏与电池在并网点合并计量；上网指整个场站向电网的净送电。
- 场站将要超过上网容量时，场站控制器会自动对光伏逆变器限发。
- 时间：本协议下交换的所有计划均使用当地时间。
""",
    "ko": """# 계통연계계약 (2024년 체결 계약 요약)

사업장: 야노베르데 태양광·ESS 발전소(스페인), 공용 연계점 1개.

- 연계점 최대 송전(역송) 용량: {exp} MW.
- 연계점 최대 수전 용량: {imp} MW.
- 태양광과 배터리는 연계점에서 합산 계량하며, 송전은 사업장 전체가 계통으로 보내는 순 송전량을 뜻합니다.
- 사업장이 송전 용량을 넘게 되면 사업장 제어기가 태양광 인버터 출력을 자동으로 제한합니다.
- 시각: 이 계약에 따라 주고받는 모든 계획은 현지 시각을 사용합니다.
""",
    "ja": """# 系統連系契約（2024年締結契約の要約）

サイト：リャノ・ベルデ太陽光・蓄電所（スペイン）、共用の連系点が1か所です。

- 連系点での最大逆潮流（送電）容量：{exp} MW
- 連系点での最大受電容量：{imp} MW
- 太陽光と蓄電池は連系点でまとめて計量されます。送電とはサイト全体から系統への正味の送電を指します。
- サイトが送電容量を超えそうになると、サイトコントローラーが太陽光インバーターを自動的に出力抑制します。
- 時刻：本契約に基づいてやり取りする計画はすべて現地時刻を使用します。
""",
}


def write_data(world: World, data_dir: Path, lang: str) -> None:
    c, s = labels(COLS, lang), labels(SPEC, lang)
    wk = world.week
    hourly = [(wk.ts(i), wk.price_fc[i]) for i in range(len(wk.slots)) if wk.slots[i][1] % 60 == 0]
    write_csv(data_dir / FILES["price"][lang], [c["ts"], c["price"]], hourly)
    write_csv(data_dir / FILES["solar"][lang], [c["ts"], c["solar"]],
              [(wk.ts(i), wk.solar[i]) for i in range(len(wk.slots))])
    write_csv(data_dir / FILES["spec"][lang], [c["param"], c["value"], c["unit"]], [
        (s["energy"], CAPACITY, "MWh"), (s["pch"], PMAX, "MW"), (s["pdis"], PMAX, "MW"),
        (s["rte"], round(100 * LOG_RULES.eta_c * LOG_RULES.eta_d, 1), "%"), (s["socmin"], 5, "%"), (s["socmax"], 95, "%"),
        (s["solar"], SOLAR_MW, "MWp")])
    ch, dis = world.log_plan
    soc, rows = SOC_START, []
    for i in range(len(world.log.slots)):
        soc += DT_H * (LOG_RULES.eta_c * ch[i] - dis[i] / LOG_RULES.eta_d)
        rows.append((world.log.ts(i), round(ch[i], 3), round(dis[i], 3), round(100 * soc / CAPACITY, 2)))
    write_csv(data_dir / FILES["log"][lang], [c["ts"], c["charge"], c["discharge"], c["soc"]], rows)
    (data_dir / FILES["agreement"][lang]).write_text(
        AGREEMENT[lang].format(exp=int(AGREEMENT_EXPORT), imp=int(IMPORT_CAP)), encoding="utf-8")


# ── simulation and scoring ───────────────────────────────────────────────────

def _hm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def simulate(world: World, r: Rules, ch: list[float], dis: list[float], prices: list[float] | None = None):
    hz = world.week
    prices = hz.price_true if prices is None else prices
    viol: list[tuple[str, str]] = []

    def flag(rule: str, msg: str) -> None:
        if sum(1 for x, _ in viol if x == rule) < 5:     # first five messages per rule are enough
            viol.append((rule, msg))

    soc = SOC_START
    revenue = import_cost = baseline = 0.0
    throughput = curtailed = 0.0
    min_soc, max_soc = soc, soc
    lo, hi = 100 * r.soc_min / CAPACITY, 100 * r.soc_max / CAPACITY
    for i, (d, m) in enumerate(hz.slots):
        c, x, s, p = ch[i], dis[i], hz.solar[i], prices[i]
        ts = hz.ts(i)
        if c < -P_TOL or x < -P_TOL or c > PMAX + P_TOL or x > PMAX + P_TOL:
            flag("power_limits", f"{ts}: charge {c:g} / discharge {x:g} MW outside 0..{PMAX:g} MW")
        elif c > P_TOL and x > P_TOL:
            flag("power_limits", f"{ts}: charges and discharges in the same interval")
        if r.offline(d, m) and (abs(c) > P_TOL or abs(x) > P_TOL):
            flag("maintenance_outage", f"{ts}: the battery is offline for maintenance "
                                       f"({_hm(OUTAGE_FROM)}-{_hm(OUTAGE_TO)}) but the plan moves it")
        net = s + x - c
        cap = r.cap(d, m)
        if x > P_TOL and net > r.base_cap(d) + P_TOL:
            flag("export_cap", f"{ts}: site export {net:.2f} MW > {r.base_cap(d):g} MW while discharging")
        if x > P_TOL and r.in_dso(d, m) and net > r.dso_mw + P_TOL:
            flag("dso_limit", f"{ts}: site export {net:.2f} MW > the DSO's {r.dso_mw:g} MW while discharging")
        if net < -P_TOL and not r.can_import(m):
            w = r.import_window
            flag("grid_charging_window", f"{ts}: imports {-net:.2f} MW from the grid outside "
                                         f"{_hm(w[0])}-{_hm(w[1])}")
        if net < -IMPORT_CAP - P_TOL:
            flag("power_limits", f"{ts}: imports {-net:.2f} MW > {IMPORT_CAP:g} MW")
        soc += DT_H * (r.eta_c * c - x / r.eta_d)
        min_soc, max_soc = min(min_soc, soc), max(max_soc, soc)
        if soc < r.soc_min - E_TOL or soc > r.soc_max + E_TOL:
            flag("soc_limits", f"after {ts}: SOC {100 * soc / CAPACITY:.2f}% outside {lo:g}%-{hi:g}%")
        if r.in_reserve(m) and soc < r.reserve - E_TOL:
            flag("evening_reserve", f"after {ts}: SOC {100 * soc / CAPACITY:.2f}% < {100 * r.reserve / CAPACITY:g}% "
                                    f"in the {_hm(r.res_from)}-{_hm(r.res_to)} reserve")
        export = min(max(net, 0.0), cap)
        imp = max(-net, 0.0)
        curtailed += DT_H * max(0.0, net - cap) if x <= P_TOL else 0.0
        revenue += p * DT_H * export
        import_cost += p * DT_H * imp
        baseline += p * DT_H * min(s, cap)
        throughput += DT_H * (max(c, 0) + max(x, 0))
    if soc < r.soc_end - E_TOL:
        flag("end_soc", f"week ends at SOC {100 * soc / CAPACITY:.2f}% < {100 * r.soc_end / CAPACITY:g}%")
    deg = r.degradation * throughput
    objective = revenue - import_cost - baseline - deg
    metrics = {"battery_profit_eur": round(objective, 2), "export_revenue_eur": round(revenue, 2),
               "grid_import_cost_eur": round(import_cost, 2), "solar_only_revenue_eur": round(baseline, 2),
               "degradation_eur": round(deg, 2), "throughput_mwh": round(throughput, 3),
               "end_soc_pct": round(100 * soc / CAPACITY, 3), "min_soc_pct": round(100 * min_soc / CAPACITY, 3),
               "max_soc_pct": round(100 * max_soc / CAPACITY, 3), "curtailed_mwh": round(curtailed, 3)}
    return viol, objective, metrics


def _read_plan(world: World, submission_dir: Path) -> tuple[list[float], list[float]]:
    rows = read_csv(submission_dir, "dispatch.csv", ["timestamp", "charge_mw", "discharge_mw"])
    idx = world.index()
    n = len(world.week.slots)
    ch, dis, seen = [0.0] * n, [0.0] * n, set()
    for k, r in enumerate(rows):
        ts = " ".join(str(r.get("timestamp", "")).strip().replace("T", " ").split())[:16]
        if ts not in idx:
            raise Fatal(f"dispatch.csv row {k + 2}: timestamp {r.get('timestamp')!r} is not a 15-minute interval "
                        f"start of the week (local time, YYYY-MM-DD HH:MM)")
        if ts in seen:
            raise Fatal(f"dispatch.csv: timestamp {ts} appears more than once")
        seen.add(ts)
        ch[idx[ts]] = number(r.get("charge_mw"), f"{ts} charge_mw")
        dis[idx[ts]] = number(r.get("discharge_mw"), f"{ts} discharge_mw")
    if len(seen) != n:
        missing = [t for t in idx if t not in seen]
        raise Fatal(f"dispatch.csv covers {len(seen)} of {n} intervals; missing e.g. {missing[:3]}")
    return ch, dis


def score(world: World, submission_dir: Path, setting: Setting) -> dict:
    try:
        ch, dis = _read_plan(world, submission_dir)
    except Fatal as e:
        return {"fatal": str(e)}
    viol, obj, metrics = simulate(world, rules_of(setting), ch, dis)
    return {"violations": viol, "objective": obj, "metrics": metrics}


# ── reference solution ───────────────────────────────────────────────────────

def _heuristic(hz: Horizon, r: Rules, last_week: bool = False) -> tuple[list[float], list[float]]:
    """Greedy two-cycles-a-day rule on forecast prices: fill up in the cheapest night quarters and sell into
    the morning peak; refill from solar in the cheapest daylight quarters (always soaking up clipped solar)
    and sell into the evening peak. Where grid import is allowed at any hour, the daylight refill tops up from
    the grid too. A quarter sells only above the cycle's buy price plus losses and degradation; offline
    quarters stay idle, and a quarter under the DSO's limit sells less, so the evening takes more quarters.

    Two refinements over last week's planner (last_week=True, which made the dispatch log in the data):
    the night fill leaves room for the daylight refill the morning sale will not make room for, when that
    refill is cheaper than the night (clipped solar is free); and once the reserve hours are over, the
    reserve itself is sold too."""
    n = len(hz.slots)
    ch, dis = [0.0] * n, [0.0] * n
    soc = SOC_START
    days = sorted({d for d, _ in hz.slots})
    per_q = PMAX * DT_H
    k_sell = math.ceil((r.soc_max - r.soc_min) * r.eta_d / per_q)
    eta2 = r.eta_c * r.eta_d
    night_to = r.import_window[1] if r.import_window else NIGHT_TO
    grid_top_up = r.import_window is None
    p = hz.price_fc
    for d in days:
        idx = [i for i in range(n) if hz.slots[i][0] == d]
        live = [i for i in idx if not r.offline(d, hz.slots[i][1])]
        last = d == days[-1]
        m_of = {i: hz.slots[i][1] for i in idx}

        def cheapest(cands, k):
            return sorted(cands, key=lambda i: (p[i], i))[:k]

        def dearest(cands, hurdle, k=k_sell):
            """The dearest quarters until they can deliver k full-power quarters (fewer MW in a quarter whose
            export limit is below the battery's power), those above the hurdle."""
            out, power = [], 0.0
            for i in sorted(cands, key=lambda i: (-p[i], i)):
                if power >= k * PMAX - 1e-9:
                    break
                out.append(i)
                power += min(PMAX, r.cap(d, m_of[i]))
            return [i for i in out if p[i] > hurdle]

        def avg(quarters):
            return sum(p[i] for i in quarters) / len(quarters) if quarters else 0.0

        night = [i for i in live if m_of[i] < night_to and r.can_import(m_of[i])]
        q_night = math.ceil(max(0.0, r.soc_max - soc) / (per_q * r.eta_c) - 1e-9)
        buy1 = set(cheapest(night, q_night))
        h1 = avg(buy1) / eta2 + 2 * r.degradation
        sell1 = set(dearest([i for i in live if 6 * 60 <= m_of[i] < 11 * 60 and i not in buy1], h1))
        sunny = [i for i in live if 9 * 60 <= m_of[i] < 17 * 60 and hz.solar[i] >= 1.0]
        buy2 = set(cheapest(sunny, 16))
        if not last_week:
            # Room for the daylight refill: clipped solar always (it is free), the whole refill when it is
            # cheaper than the night; less whatever the morning sale frees anyway.
            clipped = [i for i in live if hz.solar[i] > r.cap(d, m_of[i]) and i not in buy2]
            intake = DT_H * r.eta_c * (sum(PMAX if grid_top_up else min(PMAX, hz.solar[i]) for i in buy2)
                                       + sum(min(PMAX, hz.solar[i] - r.cap(d, m_of[i])) for i in clipped))
            free = DT_H * r.eta_c * sum(min(PMAX, hz.solar[i] - r.cap(d, m_of[i])) for i in live
                                        if hz.solar[i] > r.cap(d, m_of[i]))
            wanted = intake if buy1 and avg(buy2) < avg(buy1) else free
            low = r.reserve if r.reserve is not None else r.soc_min
            morning = min(r.soc_max - low, DT_H / r.eta_d * sum(
                max(0.0, min(PMAX, r.cap(d, m_of[i]) - hz.solar[i])) for i in sell1))
            keep_room = min(wanted, r.soc_max - r.soc_min) - morning
            if keep_room > 0:
                # the night may stay below the reserve (and the end target) by what the daylight refill
                # brings before the reserve hours, counted at 80%
                before = r.res_from if r.reserve is not None else 24 * 60
                early = 0.8 * DT_H * r.eta_c * sum(
                    (PMAX if grid_top_up else min(PMAX, hz.solar[i])) if i in buy2
                    else min(PMAX, hz.solar[i] - r.cap(d, m_of[i]))
                    for i in set(buy2) | set(clipped) if m_of[i] + 15 <= before)
                target = max(r.soc_max - keep_room, r.soc_min + 2 * E_TOL, low - early,
                             r.soc_end - early if last else r.soc_min)
                q_night = math.ceil(max(0.0, target - soc) / (per_q * r.eta_c) - 1e-9)
                buy1 = set(cheapest(night, q_night))
        h2 = avg(buy2) / eta2 + 2 * r.degradation
        sell2 = set(dearest([i for i in live if m_of[i] >= 15 * 60], h2))
        if not last_week and r.reserve is not None:
            # once the reserve hours are over, the reserve itself can be sold too
            k_late = math.ceil((r.reserve - r.soc_min) * r.eta_d / per_q)
            sell2 |= set(dearest([i for i in live if m_of[i] >= r.res_to and i not in sell2], h2, k_late))
        refill = 0.8 * DT_H * r.eta_c * sum(PMAX if grid_top_up else min(PMAX, hz.solar[i]) for i in buy2)
        for i in idx:
            m, s = m_of[i], hz.solar[i]
            if r.offline(d, m):
                continue
            cap = r.cap(d, m)
            room = max(0.0, (r.soc_max - soc) / (DT_H * r.eta_c))
            if i in buy1:
                ch[i] = min(PMAX, room)
            elif i in buy2 or s > cap:
                if i in buy2:
                    ch[i] = min(PMAX, room) if grid_top_up else min(PMAX, s, room)
                else:
                    ch[i] = min(PMAX, s - cap, room)
            elif i in sell1 or i in sell2:
                floor = r.soc_min
                if r.reserve is not None and m < r.res_to:
                    floor = max(floor, r.reserve)
                if last:
                    floor = max(floor, r.soc_end - refill if i in sell1 else r.soc_end)
                dis[i] = max(0.0, min(PMAX, cap - s, (soc - floor) * r.eta_d / DT_H))
            ch[i], dis[i] = math.floor(ch[i] * 1e4) / 1e4, math.floor(dis[i] * 1e4) / 1e4
            soc += DT_H * (r.eta_c * ch[i] - dis[i] / r.eta_d)
    return ch, dis


def _write_plan(world: World, out_dir: Path, ch: list[float], dis: list[float]) -> None:
    hz = world.week
    write_csv(out_dir / "dispatch.csv", ["timestamp", "charge_mw", "discharge_mw"],
              [(hz.ts(i), round(ch[i], 4), round(dis[i], 4)) for i in range(len(hz.slots))])
    # write_csv adds a BOM; keep the reference plain ASCII
    p = out_dir / "dispatch.csv"
    p.write_bytes(p.read_bytes().removeprefix(b"\xef\xbb\xbf"))


def reference_solution(world: World, out_dir: Path, setting: Setting) -> None:
    ch, dis = _heuristic(world.week, rules_of(setting))
    _write_plan(world, out_dir, ch, dis)


def baseline_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """The site without a dispatch plan: the battery rests at 50% all week and the farm sells solar alone
    (battery profit 0). Valid in every setting: export, import, reserve, DSO and outage rules only bite when
    the battery moves, every SOC window holds 50%, and no end-of-week target is above 50%."""
    n = len(world.week.slots)
    _write_plan(world, out_dir, [0.0] * n, [0.0] * n)


def violating_examples(world: World, setting: Setting) -> dict:
    """One plan per rule of the setting that breaks exactly that rule (for the validator)."""
    r = rules_of(setting)
    base_c, base_d = _heuristic(world.week, r)
    hz = world.week
    n = len(hz.slots)

    def only(rule: str, c: list[float], d: list[float]) -> bool:
        return {x for x, _ in simulate(world, r, c, d)[0]} == {rule}

    def search(rule: str, candidates):
        for c, d in candidates:
            if only(rule, c, d):
                return lambda out, c=c, d=d: _write_plan(world, out, c, d)
        raise AssertionError(f"no clean example for {rule} ({setting.label})")

    day = lambda i: hz.slots[i][0]
    m_of = lambda i: hz.slots[i][1]
    idle = lambda i: base_c[i] == 0 and base_d[i] == 0
    late = r.res_to if r.reserve is not None else 21 * 60

    def moved(i: int, j: int, a: float):
        """a MW more discharge in quarter i, taken back from quarter j (before or after it)."""
        c, d = base_c[:], base_d[:]
        d[i] += a
        d[j] -= a
        return c, d

    def over_power():
        # charge and discharge in the same quarter, with the state of charge where the reference has it
        for i in range(n):
            if base_d[i] > 0 and base_c[i] == 0:
                c, d = base_c[:], base_d[:]
                c[i] = 1.0
                d[i] += 1.0 * r.eta_c * r.eta_d
                yield c, d
        # more than 20 MW in one quarter
        for i in range(n):
            if base_d[i] > 0 and hz.solar[i] == 0:
                for j in range(i + 1, n):
                    extra = PMAX + 1.0 - base_d[i]
                    if base_d[j] >= max(1.0, extra):
                        yield moved(i, j, extra)

    def soc_path(c: list[float], d: list[float]) -> list[float]:
        out, soc = [], SOC_START
        for i in range(n):
            soc += DT_H * (r.eta_c * c[i] - d[i] / r.eta_d)
            out.append(soc)
        return out

    ref_soc = soc_path(base_c, base_d)

    def can_add_charge(c: list[float], d: list[float], j: int) -> float:
        """MW of charge quarter j can take without touching another rule (from solar, or from the grid inside
        the import window), 0 where it discharges or is offline."""
        if d[j] > 0 or r.offline(day(j), m_of(j)):
            return 0.0
        limit = PMAX if r.can_import(m_of(j)) else hz.solar[j]
        return max(0.0, min(PMAX, limit) - c[j])

    def repay(c: list[float], d: list[float], start: int, deficit: float):
        """Take a SOC deficit (MWh) back from quarter `start` on: cut later discharges, then charge in quarters
        that may (the SOC never rises above the reference's). None if the week ends before it is repaid."""
        for j in range(start, n):
            if deficit <= 1e-9:
                return c, d
            if d[j] > 0:
                cut = min(d[j], deficit * r.eta_d / DT_H)
                d[j] -= cut
                deficit -= cut * DT_H / r.eta_d
            else:
                add = min(can_add_charge(c, d, j), deficit / (DT_H * r.eta_c))
                c[j] += add
                deficit -= add * DT_H * r.eta_c
        return (c, d) if deficit <= 1e-9 else None

    def dip(quarters: list[int], target: float):
        """Extra discharge in consecutive quarters (no charging, within PMAX and the export limits) until the
        SOC after one of them is at `target`; returns (c, d, last quarter, deficit) or None."""
        c, d = base_c[:], base_d[:]
        deficit = 0.0
        for k in quarters:
            if c[k] > 0 or r.offline(day(k), m_of(k)):
                return None
            room = min(PMAX - d[k], r.cap(day(k), m_of(k)) - hz.solar[k] - d[k])
            want = (ref_soc[k] - deficit - target) * r.eta_d / DT_H
            a = max(0.0, min(room, want))
            d[k] += a
            deficit += a * DT_H / r.eta_d
            if ref_soc[k] - deficit <= target + 1e-6:
                return c, d, k, deficit
        return None

    def end_low():
        # sell more in the last evening quarters (after the reserve hours) so the week ends below the target
        tail = [i for i in range(n) if day(i) == day(n - 1) and m_of(i) >= late and hz.solar[i] == 0]
        target = max(r.soc_min + 0.5, r.soc_end - 1.0)
        for start in range(len(tail)):
            out = dip(tail[start:], target)
            if out:
                c, d, k, _ = out
                yield c, d

    def grid_outside():
        # charge from the grid late in the evening and charge that much less in the next import window
        for i in range(n):
            if not (22 * 60 <= m_of(i) and idle(i) and hz.solar[i] == 0 and not r.can_import(m_of(i))):
                continue
            for j in range(i + 1, n):
                if base_c[j] >= 4.0 and r.can_import(m_of(j)):
                    c, d = base_c[:], base_d[:]
                    c[i] += 4.0
                    c[j] -= 4.0
                    yield c, d

    def export_over():
        for i in range(n):
            cap = r.base_cap(day(i))
            if not (idle(i) and 8.0 < hz.solar[i] < cap - 1.0 and not r.offline(day(i), m_of(i))):
                continue
            a = cap - hz.solar[i] + 2.0
            for j in range(i + 1, n):
                if base_d[j] >= a:
                    yield moved(i, j, a)

    def reserve_ex():
        # dip below the evening reserve (not below the warranty floor), repaid from later discharges and charges
        target = (r.reserve + r.soc_min) / 2
        for d0 in sorted({day(i) for i in range(n)})[:-1]:
            window = [i for i in range(n) if day(i) == d0 and r.in_reserve(m_of(i))]
            for start in range(len(window)):
                out = dip(window[start:], target)
                if out:
                    c, d, k, deficit = out
                    paid = repay(c, d, k + 1, deficit)
                    if paid:
                        yield paid

    def soc_high():
        # charge more where it is allowed: the surplus stays, so the SOC passes the ceiling at the next fill
        for i in range(n):
            if base_d[i] == 0 and not r.offline(day(i), m_of(i)):
                a = can_add_charge(base_c, base_d, i)
                if max(ref_soc[i:]) + a * DT_H * r.eta_c > r.soc_max + 4 * E_TOL:
                    c, d = base_c[:], base_d[:]
                    c[i] += a
                    yield c, d

    def soc_low():
        # sell down below the floor late in the evening, repaid from later discharges and charges
        target = r.soc_min - 0.5
        for d0 in sorted({day(i) for i in range(n)})[:-1]:
            evening = [i for i in range(n) if day(i) == d0 and m_of(i) >= late and hz.solar[i] == 0]
            for start in range(len(evening)):
                out = dip(evening[start:], target)
                if out:
                    c, d, k, deficit = out
                    paid = repay(c, d, k + 1, deficit)
                    if paid:
                        yield paid

    def dso_over():
        # sell above the DSO's limit (but within the export cap), taken from the nearest other discharge
        for i in range(n):
            if not (r.in_dso(day(i), m_of(i)) and base_c[i] == 0):
                continue
            s = hz.solar[i]
            a = r.dso_mw - s - base_d[i] + 1.0
            if a <= 0 or base_d[i] + a > PMAX or s + base_d[i] + a > r.base_cap(day(i)):
                continue
            for j in sorted(range(n), key=lambda j: abs(j - i)):
                if j != i and base_d[j] >= a:
                    yield moved(i, j, a)

    def outage_move():
        # move the battery while it is offline, taken from another discharge
        for i in range(n):
            if not r.offline(day(i), m_of(i)) or hz.solar[i] > r.cap(day(i), m_of(i)) - 3.0:
                continue
            for j in sorted(range(n), key=lambda j: abs(j - i)):
                if base_d[j] >= 2.0 and not r.offline(day(j), m_of(j)):
                    yield moved(i, j, 2.0)

    makers = {
        "power_limits": over_power,
        "soc_limits": lambda: (x for g in (soc_high(), soc_low()) for x in g),
        "export_cap": export_over,
        "grid_charging_window": grid_outside,
        "end_soc": end_low,
        "evening_reserve": reserve_ex,
        "dso_limit": dso_over,
        "maintenance_outage": outage_move,
    }
    applies = {"grid_charging_window": r.import_window is not None, "evening_reserve": r.reserve is not None,
               "dso_limit": r.dso_day is not None, "maintenance_outage": r.outage_day is not None}
    return {rule: search(rule, make()) for rule, make in makers.items() if applies.get(rule, True)}
