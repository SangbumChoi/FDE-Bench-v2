"""Solar-plus-storage battery dispatch for one week (original FDE-Bench v2 case).

A grid-scale battery sits behind the same connection point as a solar farm.
The operator asks for next week's charge/discharge plan "to make the most
money". What decides validity and quality (per-direction efficiency, the
warranty state-of-charge window, the end-of-week state of charge, an amended
export cap lower than the agreement on file, grid charging only off-peak, the
evening emergency reserve, degradation cost, dated grid notices) is in the
requirements and must be asked for; what the data settles (quarter-hour
settlement against an hourly price file, the spring clock change, joint
metering, the 50% start) is context. A plan is scored by its expected profit:
every quarter settled at its hour's forecast price. The reference is the exact
optimum of that linear program (`optimum`, pure Python); the zero point is the
client's own planner (`_planner`), which made last week's log.

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
    soc_window       warranty SOC window, % (10-85, 15-85, 15-90: never the sheet's 5-95 nor the log's 10-90)
    efficiency       one-way efficiency on charge / on discharge, % (94/90, 95/89, 90/94: never the even 92/92)
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

Last week's dispatch log in the data was made by the client's planner under last week's conventions
(LOG_RULES): 10-90%, 92% each way, 50% at the start and end, a 20% reserve 17:00-21:00, import 00:00-06:00,
a 25 MW cap. It is the same in every setting and stale under every draw: the window, the split and the cap
always differ.
"""

from __future__ import annotations

import bisect
import csv
import datetime as dt
import io
import math
import random
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

import yaml

from fdebench2.cases import TIERS, Setting, value_text
from fdebench2.casekit import Fatal, labels, number, write_csv

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
NIGHT_TO = 6 * 60                       # the planner fills at night before 06:00 (in the import window if any)
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
    world.log_plan = _planner(log, LOG_RULES)
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
    """(violations, objective, metrics) of a plan under the rules r. The objective is the battery's expected profit:
    every quarter settled at the forecast price, the expected price of that hour (`prices` settles at others). What
    the plan would have made at the week's actual prices, one draw of the forecast's error, is a metric only."""
    hz = world.week
    prices = hz.price_fc if prices is None else prices
    viol: list[tuple[str, str]] = []

    def flag(rule: str, msg: str) -> None:
        if sum(1 for x, _ in viol if x == rule) < 5:     # first five messages per rule are enough
            viol.append((rule, msg))

    soc = SOC_START
    revenue = import_cost = baseline = actual = 0.0
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
        actual += hz.price_true[i] * DT_H * (export - imp - min(s, cap))
        throughput += DT_H * (max(c, 0) + max(x, 0))
    if soc < r.soc_end - E_TOL:
        flag("end_soc", f"week ends at SOC {100 * soc / CAPACITY:.2f}% < {100 * r.soc_end / CAPACITY:g}%")
    deg = r.degradation * throughput
    objective = revenue - import_cost - baseline - deg
    metrics = {"battery_profit_eur": round(objective, 2), "export_revenue_eur": round(revenue, 2),
               "grid_import_cost_eur": round(import_cost, 2), "solar_only_revenue_eur": round(baseline, 2),
               "degradation_eur": round(deg, 2), "throughput_mwh": round(throughput, 3),
               "end_soc_pct": round(100 * soc / CAPACITY, 3), "min_soc_pct": round(100 * min_soc / CAPACITY, 3),
               "max_soc_pct": round(100 * max_soc / CAPACITY, 3), "curtailed_mwh": round(curtailed, 3),
               "profit_at_actual_prices_eur": round(actual - deg, 2)}
    return viol, objective, metrics


# The plan as the client's systems read it. The request leaves the file's format open, so dispatch.csv is read by
# what its columns say rather than by their exact names: the time column under any of TIME_COLUMNS (else the first
# column that is neither power), the charge and discharge columns by a word of DIRECTION_WORDS in any of the five
# languages, comma or semicolon separated (decimal commas with semicolons), a timestamp as local "YYYY-MM-DD HH:MM"
# (seconds, a "T", a one-digit hour, a day-first or month-first date and a UTC offset or "Z" are understood; an
# offset is converted to local time), and a row at a
# clock time the spring change skips is ignored when the battery rests in it. A quarter without a row, or power at a
# clock time that does not exist, breaks the rule complete_plan (the plan must say what the battery does in each of
# the 668 quarters); a quarter given twice is fatal.
TIME_COLUMNS = ("timestamp", "time", "datetime", "date_time", "interval_start", "start", "time_local", "时间", "時間",
                "시각", "日時", "fecha_hora", "fecha", "hora")
DIRECTION_WORDS = {"discharge": ("discharg", "descarga", "放电", "방전", "放電"),
                   "charge": ("charg", "carga", "充电", "충전", "充電")}


def _columns(header: list[str]) -> dict[str, int]:
    names = [h.strip().lstrip("﻿").strip().lower() for h in header]
    out: dict[str, int] = {}
    for key in ("discharge", "charge"):
        hits = [k for k, h in enumerate(names) if any(w in h for w in DIRECTION_WORDS[key]) and k not in out.values()
                and (key == "discharge" or not any(w in h for w in DIRECTION_WORDS["discharge"]))
                and "soc" not in h and "state" not in h and "%" not in h and "pct" not in h]
        if len(hits) != 1:
            raise Fatal(f"dispatch.csv: needs one {key} column (e.g. {key}_mw), found {[header[k] for k in hits]}")
        out[key] = hits[0]
    timed = [k for k, h in enumerate(names) if h in TIME_COLUMNS and k not in out.values()]
    rest = [k for k in range(len(names)) if k not in out.values()]
    if not timed and not rest:
        raise Fatal("dispatch.csv: no timestamp column")
    out["ts"] = timed[0] if timed else rest[0]
    return out


DAY_FIRST = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}) (\d{1,2}):(\d{2})(?::\d{2})?")
YEAR_FIRST = re.compile(r"(\d{4})[/.-](\d{1,2})[/.-](\d{1,2}) (\d{1,2}):(\d{2})(?::\d{2})?")


def _local(text: str) -> str:
    """'YYYY-MM-DD HH:MM' in local time from a timestamp as written (one with an offset or Z converted to CET/CEST).
    A spreadsheet's "22/03/2027 0:00" (or "03/22/2027 0:00": the week's days are all above 12, so either order is
    unambiguous) and a one-digit hour are read too."""
    t = " ".join(str(text).strip().replace("T", " ").split())
    try:
        stamp = dt.datetime.fromisoformat(t.replace(" ", "T", 1).replace("Z", "+00:00"))
    except ValueError:
        if m := YEAR_FIRST.fullmatch(t):
            y, mo, d, h, mi = map(int, m.groups())
        elif (m := DAY_FIRST.fullmatch(t)) and max(int(m[1]), int(m[2])) > 12 >= min(int(m[1]), int(m[2])):
            a, b, y, h, mi = map(int, m.groups())
            d, mo = (a, b) if a > 12 else (b, a)
        else:
            return t[:16]
        return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}"
    if stamp.tzinfo is None:
        return stamp.strftime("%Y-%m-%d %H:%M")
    utc = stamp.astimezone(dt.timezone.utc).replace(tzinfo=None)
    summer = utc >= dt.datetime(2027, 3, 28, 1, 0)      # EU summer time from 01:00 UTC on the last Sunday of March
    return (utc + dt.timedelta(hours=2 if summer else 1)).strftime("%Y-%m-%d %H:%M")


def _power(text: str, what: str, decimal_comma: bool) -> float:
    raw = str(text).strip()
    return number(raw.replace(",", ".") if decimal_comma else raw, what) if raw else 0.0


def _read_plan(world: World, submission_dir: Path) -> tuple[list[float], list[float], list[str]]:
    """(charge, discharge, what breaks complete_plan) of dispatch.csv. A quarter without a row rests and a row
    outside the week's quarters is left out of the simulation; both break complete_plan. Fatal: no file, an encoding
    or a number that cannot be read, no charge or discharge column, a quarter given twice."""
    path = Path(submission_dir) / "dispatch.csv"
    if not path.is_file():
        raise Fatal("missing dispatch.csv")
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "cp949", "shift_jis", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise Fatal("dispatch.csv: unknown text encoding")
    first = text.strip().splitlines()[0] if text.strip() else ""
    sep = ";" if first.count(";") > first.count(",") else ","
    rows = [r for r in csv.reader(io.StringIO(text.strip()), delimiter=sep) if any(x.strip() for x in r)]
    if not rows:
        raise Fatal("dispatch.csv is empty")
    col = _columns(rows[0])
    idx = world.index()
    n = len(world.week.slots)
    ch, dis, seen, gaps = [0.0] * n, [0.0] * n, set(), []
    for k, row in enumerate(rows[1:]):
        cell = lambda key: row[col[key]] if col[key] < len(row) else ""
        ts = _local(cell("ts"))
        c = _power(cell("charge"), f"{ts} charge", sep == ";")
        d = _power(cell("discharge"), f"{ts} discharge", sep == ";")
        if ts not in idx:
            if ts[:10] == DST_DAY.isoformat() and "02:00" <= ts[11:] < "03:00" and abs(c) <= P_TOL and abs(d) <= P_TOL:
                continue                # a clock time the change skips, and the battery rests in it
            gaps.append(f"row {k + 2}: {cell('ts')!r} is not a quarter of the week in local time (02:00-02:45 on 28 "
                        f"March does not exist) and moves the battery")
            continue
        if ts in seen:
            raise Fatal(f"dispatch.csv: timestamp {ts} appears more than once")
        seen.add(ts)
        ch[idx[ts]], dis[idx[ts]] = c, d
    if len(seen) != n:
        missing = [t for t in idx if t not in seen]
        gaps.insert(0, f"{len(missing)} of the week's {n} quarters have no row (e.g. {missing[:3]})")
    return ch, dis, gaps


def score(world: World, submission_dir: Path, setting: Setting) -> dict:
    try:
        ch, dis, gaps = _read_plan(world, submission_dir)
    except Fatal as e:
        return {"fatal": str(e)}
    viol, obj, metrics = simulate(world, rules_of(setting), ch, dis)
    return {"violations": [("complete_plan", g) for g in gaps[:5]] + viol, "objective": obj, "metrics": metrics}


# ── the client's planner (the baseline) ──────────────────────────────────────

PLANNER_BUFFER = 0.4                    # MWh (1% of capacity) the client's planner keeps inside the SOC limits


def _planner(hz: Horizon, r: Rules, room: bool = True, sell_reserve: bool = False,
             buffer: float = PLANNER_BUFFER, reserve_all_day: bool = True) -> tuple[list[float], list[float]]:
    """The client's own planner, which made last week's log (requirements.md, "How we run the battery today"): a
    greedy two-cycles-a-day rule on forecast prices. Fill up in the cheapest night quarters and sell into the
    morning peak; refill from solar in the cheapest daylight quarters (always soaking up clipped solar) and sell
    into the evening peak. Where grid import is allowed at any hour, the daylight refill tops up from the grid too.
    A quarter sells only above the cycle's buy price plus losses and degradation; offline quarters stay idle, and a
    quarter under the DSO's limit sells less, so the evening takes more quarters. The night fill leaves room for
    the daylight refill the morning sale will not make room for (`room`): always for clipped solar, which is free,
    and for the whole refill when it is cheaper than the night. It keeps `buffer` MWh inside the warranty window
    and above the reserve, and never sells below the reserve until the reserve hours are over, the morning sale
    included (so a cloudy afternoon or an outage cannot leave the evening short).

    Variants (shortcuts, and the base of the rule examples): room=False is the planner as it was before the export
    limit dropped, which fills up at night whatever the midday brings; sell_reserve=True also sells the reserve once
    its hours are over; buffer=0 plans to the limits themselves; reserve_all_day=False holds the reserve only through
    its hours, so the morning sale may go below it."""
    if buffer:
        r = replace(r, soc_min=r.soc_min + buffer, soc_max=r.soc_max - buffer,
                    reserve=None if r.reserve is None else r.reserve + buffer)
    n = len(hz.slots)
    ch, dis = [0.0] * n, [0.0] * n
    soc = SOC_START
    days = sorted({d for d, _ in hz.slots})
    per_q = PMAX * DT_H
    k_sell = math.ceil((r.soc_max - r.soc_min) * r.eta_d / per_q)
    eta2 = r.eta_c * r.eta_d
    night_to = min(r.import_window[1], NIGHT_TO) if r.import_window else NIGHT_TO     # before 06:00, in the window
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
        if room:
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
        if sell_reserve and r.reserve is not None:
            # once the reserve hours are over, the reserve itself can be sold too
            k_late = math.ceil((r.reserve - r.soc_min) * r.eta_d / per_q)
            sell2 |= set(dearest([i for i in live if m_of[i] >= r.res_to and i not in sell2], h2, k_late))
        refill = 0.8 * DT_H * r.eta_c * sum(PMAX if grid_top_up else min(PMAX, hz.solar[i]) for i in buy2)
        for i in idx:
            m, s = m_of[i], hz.solar[i]
            if r.offline(d, m):
                continue
            cap = r.cap(d, m)
            space = max(0.0, (r.soc_max - soc) / (DT_H * r.eta_c))
            if i in buy1:
                ch[i] = min(PMAX, space)
            elif i in buy2 or s > cap:
                if i in buy2:
                    ch[i] = min(PMAX, space) if grid_top_up else min(PMAX, s, space)
                else:
                    ch[i] = min(PMAX, s - cap, space)
            elif i in sell1 or i in sell2:
                floor = r.soc_min
                if r.reserve is not None and (r.in_reserve(m) if not reserve_all_day else m < r.res_to):
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


# ── the dispatch optimum (the reference) ─────────────────────────────────────

def _limits(hz: Horizon, r: Rules) -> list[tuple[float, float, float, float]]:
    """Per quarter (max charge MW, max discharge MW, MW of solar above the export limit, SOC floor after it in MWh):
    no power while offline; charge from the grid only in the import window (else at most the solar output);
    discharge only up to the quarter's export limit less solar, since site export may not pass it while the battery
    discharges; the warranty floor, or the reserve after a quarter that ends inside its hours."""
    out = []
    for i, (d, m) in enumerate(hz.slots):
        s, cap = hz.solar[i], r.cap(d, m)
        floor = max(r.soc_min, r.reserve) if r.in_reserve(m) else r.soc_min
        if r.offline(d, m):
            out.append((0.0, 0.0, 0.0, floor))
            continue
        cmax = PMAX if r.can_import(m) else min(PMAX, s)
        out.append((cmax, min(PMAX, max(0.0, cap - s)), min(cmax, max(0.0, s - cap)), floor))
    return out


def optimum(hz: Horizon, r: Rules, prices: list[float] | None = None) -> tuple[list[float], list[float], float]:
    """The plan of greatest profit at `prices` (the forecast by default) under the rules r, exactly: (charge,
    discharge, its profit before rounding to 4 decimals).

    The problem is a linear program with one state, the stored energy. A quarter's profit against a resting battery
    is a concave piecewise-linear function of the energy it moves: charging costs the price (the solar the site no
    longer exports, or grid power) plus degradation, except the solar above the export limit, which is free;
    discharging earns the price less degradation, up to the export limit; charging and discharging in one quarter
    never pays, so the either/or rule never binds. The best profit still to come is then a concave piecewise-linear
    function of the stored energy too, and a backward pass computes it exactly: each quarter's profit is added by
    merging its segments into the function's (a sup-convolution) and the SOC bounds after the quarter (warranty,
    reserve, the end of the week) cut its ends. A forward pass picks each quarter's move, on a tie the smallest."""
    p = hz.price_fc if prices is None else prices
    n = len(hz.slots)
    lim = _limits(hz, r)
    lo = [x[3] for x in lim]
    lo[-1] = max(lo[-1], r.soc_end)
    hi, ec, ed, deg = r.soc_max, r.eta_c, r.eta_d, r.degradation
    if lo[-1] > hi + 1e-9:
        raise ValueError("no plan meets the end-of-week level")
    # The function after quarter t: value fa at a, segments by slope, steepest first (neg holds the slopes negated,
    # ascending, for bisect), length total.
    a, fa, neg, lens = lo[-1], 0.0, [0.0], [hi - lo[-1]]
    total = hi - lo[-1]
    table: list[tuple[list[float], list[float]]] = [([], [])] * n

    def points() -> tuple[list[float], list[float]]:
        xs, vs = [a], [fa]
        for s, ln in zip(neg, lens):
            xs.append(xs[-1] + ln)
            vs.append(vs[-1] - s * ln)
        return xs, vs
    table[n - 1] = points()
    for t in range(n - 1, 0, -1):
        cmax, dmax, clip, _ = lim[t]
        ce = DT_H * ec * cmax
        a -= ce
        fa -= DT_H * p[t] * (cmax - clip) + DT_H * deg * cmax       # the quarter's profit when it charges cmax
        for slope, ln in (((p[t] + deg) / ec, DT_H * ec * (cmax - clip)), (deg / ec, DT_H * ec * clip),
                          ((p[t] - deg) * ed, DT_H * dmax / ed)):
            if ln > 1e-12:
                k = bisect.bisect_left(neg, -slope)
                if k < len(neg) and neg[k] == -slope:
                    lens[k] += ln
                else:
                    neg.insert(k, -slope)
                    lens.insert(k, ln)
                total += ln
        while a < lo[t - 1] - 1e-12 and neg:
            take = min(lens[0], lo[t - 1] - a)
            fa -= neg[0] * take
            a += take
            total -= take
            if lens[0] - take <= 1e-12:
                del neg[0], lens[0]
            else:
                lens[0] -= take
        while a + total > hi + 1e-12 and neg:
            cut = min(lens[-1], a + total - hi)
            total -= cut
            if lens[-1] - cut <= 1e-12:
                del neg[-1], lens[-1]
            else:
                lens[-1] -= cut
        if a < lo[t - 1] - 1e-9 or a > hi + 1e-9:
            raise ValueError(f"no plan meets the SOC bounds after {hz.ts(t - 1)}")
        table[t - 1] = points()

    ch, dis = [0.0] * n, [0.0] * n
    x, best_value = SOC_START, None
    for t in range(n):
        cmax, dmax, clip, _ = lim[t]
        xs, vs = table[t]
        ce, de = DT_H * ec * cmax, DT_H * dmax / ed

        def gain(y: float, x: float = x, t: int = t, clip: float = clip) -> float:
            delta = y - x
            if delta >= 0:
                c = delta / (DT_H * ec)
                own = -DT_H * p[t] * max(0.0, c - clip) - DT_H * deg * c
            else:
                own = DT_H * (p[t] - deg) * (-delta * ed / DT_H)
            k = min(max(bisect.bisect_right(xs, y) - 1, 0), len(xs) - 2)
            if len(xs) < 2 or xs[k + 1] <= xs[k]:
                return own + vs[min(k, len(vs) - 1)]
            return own + vs[k] + (vs[k + 1] - vs[k]) * (y - xs[k]) / (xs[k + 1] - xs[k])
        ylo, yhi = max(xs[0], x - de), min(xs[-1], x + ce)
        if ylo > yhi:                   # only after rounding drifted the state by a hair: stay as close as possible
            ylo = yhi = min(max(x, xs[0]), xs[-1])
        cands = {ylo, yhi} | {y for y in (x, x + DT_H * ec * clip) if ylo <= y <= yhi}
        cands |= set(xs[bisect.bisect_left(xs, ylo):bisect.bisect_right(xs, yhi)])
        y = max(sorted(cands), key=lambda y: (round(gain(y), 6), -abs(y - x)))
        if t == 0:
            best_value = gain(y)
        if y > x:
            ch[t] = min(cmax, round((y - x) / (DT_H * ec), 4))
        elif y < x:
            dis[t] = min(dmax, math.floor((x - y) * ed / DT_H * 1e4) / 1e4)
        x += DT_H * (ec * ch[t] - dis[t] / ed)
    return ch, dis, best_value


def reference_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """The plan of greatest expected profit under the setting's rules (optimum on the forecast)."""
    ch, dis, _ = optimum(world.week, rules_of(setting))
    _write_plan(world, out_dir, ch, dis)


def baseline_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """The client's own way: its planner, which made last week's log, run with this week's values (requirements.md,
    "How we run the battery today"). Valid in every setting it is given."""
    ch, dis = _planner(world.week, rules_of(setting))
    _write_plan(world, out_dir, ch, dis)


# The request at face value, from the files on hand: the spec sheet's manufacturer SOC window (5-95%) and its 84.6%
# round trip split evenly (92% each way), the connection agreement's 30 MW export and import at any hour, back at the
# 50% the week starts at, no reserve, no degradation charge and no notice the data does not hold.
LITERAL_RULES = Rules(soc_min=0.05 * CAPACITY, soc_max=0.95 * CAPACITY, eta_c=0.92, eta_d=0.92,
                      soc_end=0.50 * CAPACITY, export_cap=AGREEMENT_EXPORT, works_end=None, import_window=None,
                      reserve=None, res_from=0, res_to=0, degradation=0.0, dso_day=None, dso_mw=0.0,
                      outage_day=None)


def literal_solution(world: World, out_dir: Path) -> None:
    """The request done as written: the plan of greatest profit on the forecast under LITERAL_RULES (the same plan
    in every setting)."""
    ch, dis, _ = optimum(world.week, LITERAL_RULES)
    _write_plan(world, out_dir, ch, dis)


def violating_examples(world: World, setting: Setting) -> dict:
    """One plan per rule of the setting that breaks exactly that rule (for the validator)."""
    r = rules_of(setting)
    base_c, base_d = _planner(world.week, r, sell_reserve=True, buffer=0.0)
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
    out = {rule: search(rule, make()) for rule, make in makers.items() if applies.get(rule, True)}

    def clock_naive(out_dir: Path) -> None:
        # a valid plan with one more row: charging at 02:00 on 28 March, a clock time the change skips
        _write_plan(world, out_dir, base_c, base_d)
        path = out_dir / "dispatch.csv"
        path.write_text(path.read_text(encoding="utf-8") + f"{DST_DAY.isoformat()} 02:00,5.0,0.0\n", encoding="utf-8")
    return {"complete_plan": clock_naive, **out}


# ── ground truth audit hooks (fdebench2.audit, GT.md) ────────────────────────

_META = yaml.safe_load((Path(__file__).parent / "case.yaml").read_text(encoding="utf-8"))
POOLS = {name: spec["values"] if isinstance(spec["values"], dict) else {t: spec["values"] for t in TIERS}
         for name, spec in _META["params"].items()}
SHEET_SPLIT = "92/92"           # the spec sheet's 84.6% split evenly, and last week's planner
ONE_SIDED = {"84.6/100": (0.846, 1.0), "100/84.6": (1.0, 0.846)}    # the sheet's round trip all on one side
DOC_WINDOWS = ("5-95", "10-90")  # the spec sheet's window, and last week's
PIN = 0.01                      # MWh or MW: a plan "pinned" at a value sits within this of it
DIAG_TOL = 2 * E_TOL            # MWh: a SOC this far past a limit breaks it
NEAR = 0.005                    # a plan within this share of a misread value's optimum is that value's plan


def ablations(world: World, setting: Setting) -> dict:
    """Every client fact is one drawn parameter (`param:` in en/targets.yaml), which the audit ablates itself with
    the reference of each other candidate. The one hook covers a setting where no other candidate is admissible:
    the warranty window 10-85% under a 15% reserve (15-85% and 15-90% would put the reserve on the floor). There
    the window is misread the way the files suggest, as the spec sheet's manufacturer window, 5-95%. In easy the
    import window, the reserve and degradation have one candidate each (none of them applies) and are not targets:
    the natural reading of the agent's view (the agreement's 20 MW at any hour, no reserve, no wear cost) is already
    the client's."""
    r = rules_of(setting)

    def soc_window(out: Path) -> None:
        """The spec sheet's manufacturer window, 5-95%, taken for the warranty's."""
        _write_plan(world, out, *optimum(world.week, replace(r, soc_min=LITERAL_RULES.soc_min,
                                                              soc_max=LITERAL_RULES.soc_max))[:2])
    return {"soc_window": soc_window}


def shortcuts(world: World, setting: Setting) -> dict:
    """Plans a lazy or gaming agent might hand in; each must be invalid or score at most 0.5."""
    r = rules_of(setting)
    hz = world.week
    n = len(hz.slots)

    def solved(rules: Rules) -> Callable[[Path], None]:
        return lambda out: _write_plan(world, out, *optimum(hz, rules)[:2])

    # The literal plan with one rule it breaks satisfied: that rule's facts as the client gives them, the rest read
    # from the files (LITERAL_RULES).
    facts = {"soc_limits": dict(soc_min=r.soc_min, soc_max=r.soc_max, eta_c=r.eta_c, eta_d=r.eta_d),
             "export_cap": dict(export_cap=r.export_cap, works_end=r.works_end),
             "end_soc": dict(soc_end=r.soc_end),
             "grid_charging_window": dict(import_window=r.import_window),
             "evening_reserve": dict(reserve=r.reserve, res_from=r.res_from, res_to=r.res_to),
             "dso_limit": dict(dso_day=r.dso_day, dso_mw=r.dso_mw),
             "maintenance_outage": dict(outage_day=r.outage_day)}
    lit = optimum(hz, LITERAL_RULES)[:2]
    broken = {x for x, _ in simulate(world, r, *lit)[0]}
    out: dict[str, Callable[[Path], None]] = {}
    for rule, fix in facts.items():
        if rule in broken:
            fn = solved(replace(LITERAL_RULES, **fix))
            fn.__doc__ = f"The literal plan with the one rule it breaks, {rule}, kept: that fact asked, the rest " \
                         f"read from the files."
            out[f"literal_plus_{rule}"] = fn

    def last_week_settings(out_dir: Path) -> None:
        """Plan with last week's settings, which made the log: 10-90%, 92% each way, 50% at the end, a 20% reserve
        17:00-21:00, import 00:00-06:00 and a 25 MW cap."""
        solved(LOG_RULES)(out_dir)

    def last_week_settings_plus_cap(out_dir: Path) -> None:
        """Last week's settings with the one fact the documents flag as stale asked: this week's export limit."""
        solved(replace(LOG_RULES, export_cap=r.export_cap, works_end=r.works_end))(out_dir)

    def copy_last_week(out_dir: Path) -> None:
        """Copy the data through: last week's plan repeated quarter by quarter, the same weekday and clock time."""
        last = {(d.weekday(), m): i for i, (d, m) in enumerate(world.log.slots)}
        ch, dis = world.log_plan
        pick = [last[(d.weekday(), m)] for d, m in hz.slots]
        _write_plan(world, out_dir, [ch[k] for k in pick], [dis[k] for k in pick])

    def planner_before_the_cut(out_dir: Path) -> None:
        """Copy the client's way and change one thing: its planner as it ran before the export limit dropped
        (the night fill leaves no room for the midday solar)."""
        _write_plan(world, out_dir, *_planner(hz, r, room=False))

    def planner_without_buffer(out_dir: Path) -> None:
        """Copy the client's way and change one thing: its planner without the 1% buffer inside the SOC limits."""
        _write_plan(world, out_dir, *_planner(hz, r, buffer=0.0))

    def planner_sells_reserve(out_dir: Path) -> None:
        """Copy the client's way and change one thing: its planner also sells the reserve once its hours are over."""
        _write_plan(world, out_dir, *_planner(hz, r, sell_reserve=True))

    def planner_reserve_in_hours(out_dir: Path) -> None:
        """Copy the client's way and change one thing: the reserve held only through its hours, not all day.

        The morning sale may then go below it (the planner's all-day habit kept it there)."""
        _write_plan(world, out_dir, *_planner(hz, r, reserve_all_day=False))

    def planner_two_changes(out_dir: Path) -> None:
        """Copy the client's way and drop its two most costly habits: the 1% buffer and the all-day reserve.

        Open where the morning sale into the reserve pays most (validate.OPEN_AUDIT_FINDINGS)."""
        _write_plan(world, out_dir, *_planner(hz, r, buffer=0.0, reserve_all_day=False))

    def solar_surplus_only(out_dir: Path) -> None:
        """Do the minimum: store only the solar the controller would clip, sell it in the dearest evening quarters.

        Every fact right; it sells in the twelve dearest quarters from 15:00 on."""
        ch, dis, soc = [0.0] * n, [0.0] * n, SOC_START
        days = sorted({d for d, _ in hz.slots})
        for d in days:
            live = [i for i, (day, m) in enumerate(hz.slots) if day == d and not r.offline(day, m)]
            for i in live:
                m = hz.slots[i][1]
                if m < 15 * 60 and hz.solar[i] > r.cap(d, m):
                    room_mw = max(0.0, (r.soc_max - soc) / (DT_H * r.eta_c))
                    ch[i] = math.floor(min(PMAX, hz.solar[i] - r.cap(d, m), room_mw) * 1e4) / 1e4
                    soc += DT_H * r.eta_c * ch[i]
            evening = sorted((i for i in live if hz.slots[i][1] >= 15 * 60), key=lambda i: (-hz.price_fc[i], i))[:12]
            for i in sorted(evening):
                m = hz.slots[i][1]
                floor = max(r.soc_min, r.reserve if r.reserve is not None and m < r.res_to else 0.0,
                            r.soc_end if d == days[-1] else 0.0)
                mw = min(PMAX, r.cap(d, m) - hz.solar[i], (soc - floor) * r.eta_d / DT_H)
                dis[i] = math.floor(max(0.0, mw) * 1e4) / 1e4
                soc -= DT_H * dis[i] / r.eta_d
        _write_plan(world, out_dir, ch, dis)

    def same_day_every_day(out_dir: Path) -> None:
        """Output a constant: the best plan's Tuesday repeated on every day of the week, clock time by clock time."""
        ch, dis, _ = optimum(hz, r)
        tuesday = {m: (ch[i], dis[i]) for i, (d, m) in enumerate(hz.slots) if d.weekday() == 1}
        _write_plan(world, out_dir, [tuesday[m][0] for _, m in hz.slots], [tuesday[m][1] for _, m in hz.slots])

    def idle(out_dir: Path) -> None:
        """Do nothing: the battery rests at 50% all week and the farm sells its solar alone."""
        _write_plan(world, out_dir, [0.0] * n, [0.0] * n)

    def solar_only(out_dir: Path) -> None:
        """Never draw from the grid: every other fact right, the best plan that charges from solar only.

        Open where the night cycle does not pay (validate.OPEN_AUDIT_FINDINGS): there it is the optimum itself."""
        solved(replace(r, import_window=(0, 0)))(out_dir)

    def no_end_target(out_dir: Path) -> None:
        """Sell everything by the end of the week: the best plan with every fact right but no end-of-week level."""
        solved(replace(r, soc_end=r.soc_min))(out_dir)

    def stale_agreement(out_dir: Path) -> None:
        """Trust the documents on the export limit: every other fact right, the agreement's 30 MW all week."""
        solved(replace(r, export_cap=AGREEMENT_EXPORT, works_end=None))(out_dir)

    def clock_naive(out_dir: Path) -> None:
        """Ignore the clock change: the best plan on a 672-quarter clock, charging through 02:00-02:45 on Sunday."""
        ch, dis, _ = optimum(hz, r)
        _write_plan(world, out_dir, ch, dis)
        path = out_dir / "dispatch.csv"
        night = [i for i, (d, m) in enumerate(hz.slots) if d == DST_DAY and m < 120][-4:]
        extra = "".join(f"{DST_DAY.isoformat()} 02:{15 * k:02d},{max(ch[i], 5.0)},0.0\n" for k, i in enumerate(night))
        path.write_text(path.read_text(encoding="utf-8") + extra, encoding="utf-8")

    made = [last_week_settings, last_week_settings_plus_cap, copy_last_week, planner_before_the_cut,
            planner_without_buffer, idle, solar_only, no_end_target, stale_agreement, clock_naive, solar_surplus_only,
            same_day_every_day]
    if r.reserve is not None:
        made[6:6] = [planner_sells_reserve, planner_reserve_in_hours, planner_two_changes]
    return {**out, **{f.__name__: f for f in made}}


# ── the never-asks solver ────────────────────────────────────────────────────

def _hedged(world: World, tier: str, candidates: dict, degradation: float | None = None) -> tuple[list, list]:
    """The plan of greatest expected profit that is valid under every combination of the tier's candidates: one
    linear program (scipy) over charge and discharge with a state of charge for every candidate efficiency split.
    Each SOC stays inside every candidate window and above every candidate reserve in every candidate's hours, and
    ends at the highest candidate level; the battery discharges only up to the lowest candidate export limit (30 MW
    once every candidate's works have ended), the lowest DSO limit on every candidate day, and rests through every
    candidate outage; it imports only where every candidate window allows. Charging is priced at its expected cost
    over the candidate limits (solar above the limit is free), degradation at the pool's mean."""
    import numpy as np
    from scipy.optimize import linprog
    from scipy.sparse import coo_matrix

    hz = world.week
    n = len(hz.slots)
    uniq = lambda name: list(dict.fromkeys(value_text(v) for v in candidates[name]))
    splits = [tuple(int(x) / 100 for x in _pair(e, "/")) for e in uniq("efficiency")]
    wins = [_pair(w, "-") for w in uniq("soc_window")]
    lo, hi = max(a for a, _ in wins) * CAPACITY / 100, min(b for _, b in wins) * CAPACITY / 100
    end = max(float(v) for v in uniq("end_soc")) * CAPACITY / 100
    caps = [float(v) for v in uniq("export_cap")]
    works = [_day(v) for v in uniq("works_end")]
    imports = [None if w == "any" else tuple(60 * h for h in _pair(w, "-")) for w in uniq("import_window")]
    hours = [tuple(60 * h for h in _pair(w, "-")) for w in uniq("reserve_window") if w != "none"]
    reserve = max(float(v) for v in uniq("reserve_pct")) * CAPACITY / 100 if hours else None
    degs = [float(v) for v in uniq("degradation")]
    deg = sum(degs) / len(degs) if degradation is None else degradation
    dso_days = [d for d in map(_day, uniq("dso_day")) if d]
    dso_mw = min((float(v) for v in uniq("dso_mw") if v != "none"), default=0.0)
    outages = [d for d in map(_day, uniq("outage_day")) if d]
    last_works = None if None in works else max(works)
    p = hz.price_fc
    scen = [(c, w) for c in caps for w in works]          # (export cap, works end), equally likely
    segs, cidx, didx, nvar = [], [], [], 0
    for i, (d, m) in enumerate(hz.slots):
        s = hz.solar[i]
        offline = d in outages and OUTAGE_FROM <= m < OUTAGE_TO
        cmax = 0.0 if offline else PMAX if all(w is None or w[0] <= m < w[1] for w in imports) else min(PMAX, s)
        clips = [min(cmax, max(0.0, s - (AGREEMENT_EXPORT if w and d >= w else c))) for c, w in scen]
        levels = sorted(set(clips) | {0.0, cmax})
        segs.append([(b - a, DT_H * (p[i] * sum(x <= a + 1e-12 for x in clips) / len(clips) + deg))
                     for a, b in zip(levels, levels[1:])])
        cidx.append(list(range(nvar, nvar + len(segs[-1]))))
        nvar += len(segs[-1])
        didx.append(nvar)
        nvar += 1
    soc = [[nvar + k * n + i for i in range(n)] for k in range(len(splits))]
    nvar += len(splits) * n
    cost, lb, ub = np.zeros(nvar), np.zeros(nvar), np.zeros(nvar)
    for i, (d, m) in enumerate(hz.slots):
        s = hz.solar[i]
        for j, (length, c) in zip(cidx[i], segs[i]):
            ub[j], cost[j] = length, c
        cap = AGREEMENT_EXPORT if last_works and d >= last_works else min(caps)
        if d in dso_days and DSO_FROM <= m < DSO_TO:
            cap = min(cap, dso_mw)
        offline = d in outages and OUTAGE_FROM <= m < OUTAGE_TO
        ub[didx[i]] = 0.0 if offline else min(PMAX, max(0.0, cap - s))
        cost[didx[i]] = -DT_H * (p[i] - deg)
        floor = max(lo, reserve) if reserve is not None and any(a <= m + 15 <= b for a, b in hours) else lo
        for k in range(len(splits)):
            lb[soc[k][i]], ub[soc[k][i]] = floor, hi
    for k in range(len(splits)):
        lb[soc[k][-1]] = max(lb[soc[k][-1]], end)
    rows, cols, vals, rhs = [], [], [], []
    for k, (ec, ed) in enumerate(splits):
        for i in range(n):
            row = len(rhs)
            entries = [(soc[k][i], 1.0), (didx[i], DT_H / ed)] + [(j, -DT_H * ec) for j in cidx[i]]
            if i:
                entries.append((soc[k][i - 1], -1.0))
            for col, val in entries:
                rows.append(row)
                cols.append(col)
                vals.append(val)
            rhs.append(SOC_START if i == 0 else 0.0)
    res = linprog(cost, A_eq=coo_matrix((vals, (rows, cols)), shape=(len(rhs), nvar)).tocsr(), b_eq=np.array(rhs),
                  bounds=list(zip(lb, ub)), method="highs")
    if res.status != 0:
        raise RuntimeError(f"the hedged plan has no solution: {res.message}")
    ch = [round(max(0.0, sum(res.x[j] for j in cidx[i])), 4) for i in range(n)]
    dis = [math.floor(max(0.0, res.x[didx[i]]) * 1e4) / 1e4 for i in range(n)]
    for i in range(n):          # a quarter that does both never pays; keep the larger move
        if ch[i] > 0 and dis[i] > 0:
            ch[i], dis[i] = (ch[i] - dis[i], 0.0) if ch[i] >= dis[i] else (0.0, dis[i] - ch[i])
    return ch, dis


def robust_solution(world: World, out_dir: Path, tier: str, candidates: dict) -> None:
    """The strongest plan that never asks: the hedged optimum over the tier's pools (_hedged), from the forecast,
    the solar forecast and the spec sheet. Fixed facts at their natural reading, which is the client's: quarter-hour
    settlement against the hourly price, the clock change, the agreement's joint metering (site export is solar +
    discharge - charge) and the 50% start the log ends at. It is valid in every setting of the tier.

    Other plans were tried (GT.md, part 4): any subset of each parameter's candidates instead of all of them (a
    single one is a guess, valid only where it is right), degradation at the pool's lowest or highest value, and
    every measured setting's own reference (a full guess). Over all 81 easy combinations none earns more; in medium
    a single change (a 40% end level, or a 20% reserve) earns up to 0.04 more on the audit's settings; in hard
    nothing earns more than 0.005."""
    _write_plan(world, out_dir, *_hedged(world, tier, candidates))


# ── reference and bounds ─────────────────────────────────────────────────────

def best_known_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """The optimum, which the reference already is: no valid plan earns more at the forecast prices
    (objective_bound); an agent with the client's facts and a linear program reaches it."""
    reference_solution(world, out_dir, setting)


def objective_bound(world: World, setting: Setting) -> float:
    """A proven upper bound on the expected profit, and the optimum: the value of the linear program `optimum` solves
    exactly (before its plan is rounded to 4 decimals). The program allows every plan the rules allow, and more
    (charging and discharging in one quarter), so no valid plan earns more."""
    return optimum(world.week, rules_of(setting))[2]


# ── the per-target diagnostic: does the plan implement each client fact? ─────

def _path(ch: list[float], dis: list[float], ec: float, ed: float) -> list[float]:
    out, soc = [], SOC_START
    for c, d in zip(ch, dis):
        soc += DT_H * (ec * c - d / ed)
        out.append(soc)
    return out


def _others(setting: Setting, name: str) -> list[str]:
    """The other candidates of a parameter in the setting's tier, as text."""
    own = value_text(setting.params[name])
    return [v for v in dict.fromkeys(value_text(x) for x in POOLS[name][setting.tier]) if v != own]


def diagnose(world: World, submission_dir: Path, setting: Setting, scored: dict) -> dict:
    """{"enforced": {target: True | False | None}, "evidence": {target: text}} for the targets in force, read from
    the plan's own numbers against the facts: a limit the plan breaks that another candidate would explain is that
    candidate's (False); a stricter candidate the plan sits exactly on (within PIN) while the optimum uses the room
    the client's value gives is a misreading too (False; for the reserve hours, a window floor at the reserve's level
    and the range last week's log runs in only when the plan also earns within NEAR of that reading's optimum, since
    a planner that keeps the reserve all day or stops selling at its end sits there too: None); otherwise True, or
    None where the plan shows nothing either way. GT.md, part 5, lists each test."""
    try:
        ch, dis, _ = _read_plan(world, submission_dir)
    except Fatal:
        return {}
    r = rules_of(setting)
    hz = world.week
    n = len(hz.slots)
    ref_c, ref_d, _ = optimum(hz, r)
    own_profit = simulate(world, r, ch, dis)[1]

    def near(other: Rules) -> bool:
        """The plan earns within NEAR of the optimum under `other` (a misread value with every other fact right):
        sitting on that value is then evidence of the misreading, not of a habit or a heuristic that happens to
        stop there."""
        best = optimum(hz, other)[2]
        return best - own_profit <= NEAR * abs(best)
    enforced: dict[str, bool | None] = {}
    evidence: dict[str, str] = {}
    tier = setting.tier

    def say(target: str, value: bool | None, text: str) -> None:
        enforced[target], evidence[target] = value, text

    def soc_trouble(path: list[float]) -> int:
        """Quarters where the SOC breaks the window or the reserve, plus one for a short end of the week."""
        bad = sum(1 for i, x in enumerate(path) if x < r.soc_min - DIAG_TOL or x > r.soc_max + DIAG_TOL
                  or (r.in_reserve(hz.slots[i][1]) and x < r.reserve - DIAG_TOL))
        return bad + (path[-1] < r.soc_end - DIAG_TOL)

    # ── efficiency: the split under which the plan's SOC keeps the client's limits ──
    def pins(p: list[float]) -> int:
        """Days whose highest SOC sits on the warranty ceiling, plus days whose lowest sits on its floor."""
        days: dict = {}
        for i, (day, _) in enumerate(hz.slots):
            lo_, hi_ = days.get(day, (9e9, -9e9))
            days[day] = (min(lo_, p[i]), max(hi_, p[i]))
        return sum((abs(b - r.soc_max) <= PIN) + (abs(a - r.soc_min) <= PIN) for a, b in days.values())

    split = (r.eta_c, r.eta_d)
    path = _path(ch, dis, *split)
    own = soc_trouble(path)
    # the other candidates, the sheet's 84.6% split evenly (and last week's 92/92), all on one side, or the client's
    # applied the wrong way round on discharge
    splits = {e: tuple(int(x) / 100 for x in _pair(e, "/")) for e in _others(setting, "efficiency") + [SHEET_SPLIT]}
    splits.update(ONE_SIDED)
    splits["the discharge efficiency multiplied"] = (r.eta_c, 1 / r.eta_d)     # discharging P removes 0.25*P*eta
    if own == 0:
        # a plan made for another split can stay inside the limits and fall short of them every day: under the
        # split it was made for, it sits on the ceiling and the floor
        tight = [e for e, x in splits.items() if pins(path) <= 1
                 and soc_trouble(p := _path(ch, dis, *x)) == 0 and pins(p) >= 3]
        if tight:
            split = splits[tight[0]]
            path = _path(ch, dis, *split)
            say("efficiency", False, f"the SOC never reaches the warranty limits with the client's split; with "
                                     f"{tight[0]} it sits on them on {pins(path)} day-ends")
        else:
            say("efficiency", True, f"with {round(100 * r.eta_c)}/{round(100 * r.eta_d)} the plan's SOC keeps the "
                                    f"window, reserve and end level")
    else:
        # another split explains the breaks when under it the SOC keeps every limit and sits on the warranty's
        # ceiling or floor on three or more day-ends, as a plan made for that split does
        fits = [e for e, x in splits.items() if soc_trouble(p := _path(ch, dis, *x)) == 0 and pins(p) >= 3]
        if fits:
            split = splits[fits[0]]
            path = _path(ch, dis, *split)
            say("efficiency", False, f"the SOC leaves the limits in {own} quarters with the client's split, none with "
                                     f"{fits[0]}")
        else:
            say("efficiency", None, f"the SOC leaves the limits in {own} quarters under every split")
    ref_path = _path(ref_c, ref_d, r.eta_c, r.eta_d)

    # ── the warranty window (on the plan's own split) ──
    low, high = min(path), max(path)
    pct = lambda x: f"{100 * x / CAPACITY:.2f}%"
    if low < r.soc_min - DIAG_TOL or high > r.soc_max + DIAG_TOL:
        wider = [w for w in _others(setting, "soc_window") + list(DOC_WINDOWS)
                 if low >= _pair(w, "-")[0] * CAPACITY / 100 - DIAG_TOL
                 and high <= _pair(w, "-")[1] * CAPACITY / 100 + DIAG_TOL]
        say("soc_window", False if wider else None,
            f"the SOC runs {pct(low)}-{pct(high)}" + (f", inside {wider[0]}" if wider else ""))
    else:
        # the other candidates, and the range last week's log runs in (the planner's buffer and all-day reserve
        # under last week's settings), which a plan read off the log keeps
        stricter = {w: tuple(x * CAPACITY / 100 for x in _pair(w, "-")) for w in _others(setting, "soc_window")}
        log_path = _path(*world.log_plan, LOG_RULES.eta_c, LOG_RULES.eta_d)
        stricter[f"log's {pct(min(log_path))}-{pct(max(log_path))}"] = (min(log_path), max(log_path))
        pinned, habit = [], []
        for w, (a, b) in stricter.items():
            if low < a - PIN or high > b + PIN:
                continue                # a plan made for that window stays inside it
            on = [f"floor {w}"] if a > r.soc_min + PIN and min(ref_path) < a - 0.1 and abs(low - a) <= PIN else []
            on += [f"ceiling {w}"] if b < r.soc_max - PIN and max(ref_path) > b + 0.1 and abs(high - b) <= PIN else []
            if not on:
                continue
            # a candidate's bound the plan stops at is its reading, unless the reserve explains it (a floor at the
            # reserve's level, held all day); the log's range only for a plan near that range's best plan
            explained = r.reserve is not None and abs(a - r.reserve) <= PIN and not on[-1].startswith("ceiling")
            if near(replace(r, soc_min=max(a, r.soc_min), soc_max=min(b, r.soc_max))) or (
                    w in _others(setting, "soc_window") and not explained):
                pinned.extend(on)
            else:
                habit.extend(on)
        say("soc_window", False if pinned else None if habit else True, f"the SOC runs {pct(low)}-{pct(high)}"
            + (f", stopping exactly at the {pinned[0]}" if pinned else "")
            + (f", stopping at the {habit[0]}, which the reserve or a margin explains as well" if habit and not pinned
               else ""))

    # ── the end of the week ──
    final = path[-1]
    if final < r.soc_end - DIAG_TOL:
        say("end_soc", False, f"the week ends at {pct(final)}, below {pct(r.soc_end)}")
    else:
        kept = [v for v in _others(setting, "end_soc") if float(v) * CAPACITY / 100 > r.soc_end + PIN
                and ref_path[-1] < float(v) * CAPACITY / 100 - 0.1 and abs(final - float(v) * CAPACITY / 100) <= PIN]
        say("end_soc", not kept, f"the week ends at {pct(final)}" + (f", exactly at {kept[0]}%" if kept else ""))

    # ── the export limit, the works' end and the DSO evening ──
    def peaks(c: list[float], d: list[float], days) -> list[float]:
        """Site export in the quarters that discharge on these days, outside the DSO's hours."""
        return [hz.solar[i] + d[i] - c[i] for i, (day, m) in enumerate(hz.slots)
                if d[i] > P_TOL and day in days and not r.in_dso(day, m)]
    week = sorted({day for day, _ in hz.slots})
    works = [w for w in map(_day, _others(setting, "works_end")) if w]
    early = min(works + ([r.works_end] if r.works_end else []), default=None)
    before = [day for day in week if early is None or day < early]
    mine, theirs = peaks(ch, dis, before), peaks(ref_c, ref_d, before)
    if any(x > r.export_cap + P_TOL for x in mine):
        say("export_cap", False, f"site export reaches {max(mine):.2f} MW while discharging, above {r.export_cap:g}")
    else:
        low_caps = [float(v) for v in _others(setting, "export_cap") if float(v) < r.export_cap]
        pinned = [c for c in low_caps if theirs and max(theirs) > c + 0.05 and mine
                  and abs(max(mine) - c) <= PIN and sum(abs(x - c) <= PIN for x in mine) >= 3]
        say("export_cap", not pinned, f"site export while discharging peaks at {max(mine, default=0.0):.2f} MW"
            + (f", held at {pinned[0]:g} MW" if pinned else ""))
    if r.works_end is not None:
        gap = [day for day in week if day < r.works_end and (early is None or day >= early)]
        over = [x for x in peaks(ch, dis, gap) if x > r.export_cap + P_TOL]
        # a later candidate end, or none this week: the plan keeps the amended limit up to it, where the best plan
        # does not
        kept = []
        for w in sorted(w for w in works if w > r.works_end) + [week[-1] + dt.timedelta(days=1)]:
            span = [day for day in week if r.works_end <= day < w]
            after, ref_after = peaks(ch, dis, span), peaks(ref_c, ref_d, span)
            if ref_after and max(ref_after) > r.export_cap + 0.05 and max(after, default=0.0) <= r.export_cap + PIN:
                kept.append(w)
        after = peaks(ch, dis, [day for day in week if day >= r.works_end])
        if any(x > r.export_cap + P_TOL for x in mine):
            say("works_end", None, "the plan passes the amended limit before any candidate end of the works")
        elif over:
            say("works_end", False, f"site export reaches {max(over):.2f} MW before {r.works_end}, as if the works "
                                    f"had ended earlier")
        elif kept:
            say("works_end", False, f"from {r.works_end} until {min(kept)} the plan still keeps site export within "
                                    f"{r.export_cap:g} MW")
        else:
            say("works_end", True, f"site export from {r.works_end} peaks at {max(after, default=0.0):.2f} MW")
    if r.dso_day is not None:
        top = max((float(v) for v in POOLS["dso_mw"][tier] if value_text(v) != "none"), default=r.dso_mw)
        evening = lambda c, d: [hz.solar[i] + d[i] - c[i] for i, (day, m) in enumerate(hz.slots)
                                if d[i] > P_TOL and r.in_dso(day, m)]
        mine_d, ref_dso = evening(ch, dis), evening(ref_c, ref_d)
        m_d = max(mine_d, default=0.0)
        if m_d > top + P_TOL:
            say("dso_day", False, f"on {r.dso_day} 18:00-21:00 site export reaches {m_d:.2f} MW: no DSO limit that evening")
            say("dso_limit", None, "the plan applies no DSO limit on the DSO's day")
        else:
            say("dso_day", True, f"on {r.dso_day} 18:00-21:00 site export stays within {m_d:.2f} MW")
            lower = [float(v) for v in _others(setting, "dso_mw") if float(v) < r.dso_mw]
            pinned = [v for v in lower if max(ref_dso, default=0.0) > v + 0.05 and abs(m_d - v) <= PIN
                      and sum(abs(x - v) <= PIN for x in mine_d) >= 2]
            if m_d > r.dso_mw + P_TOL:
                say("dso_limit", False, f"site export reaches {m_d:.2f} MW, above the DSO's {r.dso_mw:g}")
            else:
                say("dso_limit", not pinned, f"site export peaks at {m_d:.2f} MW in the DSO's hours"
                    + (f", held at {pinned[0]:g} MW" if pinned else ""))
    if r.outage_day is not None:
        moves = sum(1 for i, (day, m) in enumerate(hz.slots) if r.offline(day, m) and (ch[i] > P_TOL or dis[i] > P_TOL))
        say("maintenance_outage", moves == 0, f"the battery moves in {moves} quarters of the outage")

    # ── the import window: no import outside it, and no cheaper allowed quarter skipped for a stricter window ──
    if r.import_window is not None:
        draws = [i for i in range(n) if hz.solar[i] + dis[i] - ch[i] < -P_TOL]
        outside = [i for i in draws if not r.can_import(hz.slots[i][1])]
        if outside:
            say("grid_charging", False, f"the plan draws from the grid in {len(outside)} quarters outside the window "
                                        f"(e.g. {hz.ts(outside[0])})")
        else:
            ref_draws = [i for i in range(n) if hz.solar[i] + ref_d[i] - ref_c[i] < -P_TOL]
            stricter = []
            for w in _others(setting, "import_window"):
                a, b = (60 * h for h in _pair(w, "-"))
                spare = lambda i, a=a, b=b: r.can_import(hz.slots[i][1]) and not a <= hz.slots[i][1] < b
                if not draws or any(spare(i) for i in draws) or not any(spare(i) for i in ref_draws):
                    continue
                nights = set()
                for i in draws:            # a night that draws at a dearer quarter while a cheaper spare one rests
                    day = hz.slots[i][0]
                    if any(spare(j) and hz.slots[j][0] == day and hz.price_fc[j] < hz.price_fc[i] - 0.5
                           and ch[j] <= P_TOL for j in range(n)):
                        nights.add(day)
                if len(nights) >= 2:
                    stricter.append(w)
            say("grid_charging", not stricter, f"the plan draws from the grid in {len(draws)} quarters, all inside "
                f"the window" + (f", never outside {stricter[0]} although cheaper quarters there rest"
                                 if stricter else ""))

    # ── the reserve: its level and its hours, on the plan's own split ──
    if r.reserve is not None:
        def lowest(p: list[float], hours: tuple[int, int]) -> list[float]:
            """Per day, the lowest SOC after a quarter that ends inside these hours (and after none of `but`)."""
            out = {}
            for i, (day, m) in enumerate(hz.slots):
                if hours[0] <= m + 15 <= hours[1]:
                    out[day] = min(out.get(day, 9e9), p[i])
            return [out[day] for day in sorted(out)]

        def beyond(p: list[float], hours: tuple[int, int]) -> list[float]:
            """Per day, the lowest SOC after a quarter that ends inside these hours but outside the client's."""
            out = {}
            for i, (day, m) in enumerate(hz.slots):
                if hours[0] <= m + 15 <= hours[1] and not r.in_reserve(m):
                    out[day] = min(out.get(day, 9e9), p[i])
            return [out[day] for day in sorted(out)]
        hours = {w: tuple(60 * h for h in _pair(w, "-")) for w in _others(setting, "reserve_window")}
        level = lambda v: float(v) * CAPACITY / 100
        mine_r, ref_r = lowest(path, (r.res_from, r.res_to)), lowest(ref_path, (r.res_from, r.res_to))
        held = min(mine_r)
        if held < r.reserve - DIAG_TOL:
            # broken: by the hours (the reserve held through another candidate's hours and broken only outside
            # them) or by the level (a lower admissible candidate held through the client's hours). Where both
            # explain it, the one the plan sits on (within 0.1 MWh) on more days.
            dips = {m for i, (day, m) in enumerate(hz.slots) if r.in_reserve(m) and path[i] < r.reserve - DIAG_TOL}
            other_hours = {w: sum(abs(x - r.reserve) <= 0.1 for x in lowest(path, h)) for w, h in hours.items()
                           if min(lowest(path, h)) >= r.reserve - DIAG_TOL
                           and not any(h[0] <= m + 15 <= h[1] for m in dips)}
            lower = {v: sum(abs(x - level(v)) <= 0.1 for x in mine_r) for v in _others(setting, "reserve_pct")
                     if r.soc_min < level(v) < r.reserve and held >= level(v) - DIAG_TOL}
            by_hours, by_level = max(other_hours.values(), default=-1), max(lower.values(), default=-1)
            hours_wrong = bool(other_hours) and by_hours >= by_level
            level_wrong = bool(lower) and by_level >= by_hours
            say("reserve_hours", False if hours_wrong else None, f"the SOC falls to {pct(held)} in the reserve hours"
                + (f" but holds the reserve through {max(other_hours, key=other_hours.get)}" if hours_wrong else ""))
            say("reserve_level", False if level_wrong else None, f"the SOC falls to {pct(held)} in the reserve hours"
                + (f", holding {max(lower, key=lower.get)}%" if level_wrong else ""))
        else:
            # kept: through another candidate's extra hours too, sitting exactly on the reserve there, where the
            # best plan sells below it
            sits = [w for w, h in hours.items() if beyond(path, h) and min(beyond(path, h)) >= r.reserve - DIAG_TOL
                    and abs(min(lowest(path, h)) - r.reserve) <= PIN
                    and min(beyond(ref_path, h)) < r.reserve - 0.1]
            extra = [w for w in sits if near(replace(r, res_from=hours[w][0], res_to=hours[w][1]))]
            say("reserve_hours", False if extra else None if sits else True,
                f"the SOC holds {pct(held)} or more in the reserve hours"
                + (f", and the reserve through {extra[0]} too" if extra else "")
                + (f", and the reserve through {sits[0]} too, but far from that window's best plan"
                   if sits and not extra else ""))
            higher = [v for v in _others(setting, "reserve_pct") if level(v) > r.reserve + PIN
                      and min(ref_r) < level(v) - 0.1 and sum(abs(x - level(v)) <= PIN for x in mine_r) >= 2
                      and held >= level(v) - PIN]
            say("reserve_level", not higher, f"the SOC holds {pct(held)} or more in the reserve hours"
                + (f", exactly {higher[0]}% on several days" if higher else ""))

    # ── degradation: the cost (a candidate, or none at all) for which the plan comes closest to the best plan; read
    #    only from a plan that keeps every rule, since a broken limit can earn what no valid plan can ──
    if r.degradation and len(set(POOLS["degradation"][tier])) > 1:
        flow = DT_H * sum(max(c, 0.0) + max(d, 0.0) for c, d in zip(ch, dis))
        broken, gross, _ = simulate(world, replace(r, degradation=0.0), ch, dis)
        regret = {}
        for v in dict.fromkeys([0.0] + [float(x) for x in POOLS["degradation"][tier]]):
            best = optimum(hz, replace(r, degradation=v))[2]
            regret[v] = (best - (gross - v * flow)) / abs(best)
        near = min(regret, key=regret.get)
        text = f"{flow:.0f} MWh through the battery; short of the best plan by " + ", ".join(
            f"{100 * x:.2f}% at {v:g} EUR/MWh" for v, x in regret.items())
        if broken:
            say("degradation", None, f"the plan breaks {broken[0][0]}; {text}")
        else:
            say("degradation", True if near == r.degradation else False if regret[near] < 0.003 else None, text)
    return {"enforced": enforced, "evidence": evidence}
