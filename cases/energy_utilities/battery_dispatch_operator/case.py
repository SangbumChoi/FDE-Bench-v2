"""Solar-plus-storage battery dispatch for one week (original FDE-Bench v2 case).

A grid-scale battery sits behind the same connection point as a solar farm.
The operator asks for next week's charge/discharge plan "to make the most
money". What decides validity and quality (per-direction efficiency, the
warranty state-of-charge window, start/end state of charge, an amended export
cap lower than the agreement on file, grid charging only off-peak, degradation
cost, 15-minute settlement against an hourly price file, a spring daylight-
saving change, the evening emergency reserve) is in the requirements and must
be asked for. Scoring settles the plan against true prices that differ from
the forecast; the reference only sees the forecast.
"""

from __future__ import annotations

import datetime as dt
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from fdebench2.casekit import Fatal, labels, number, read_csv, write_csv

# ── constants ────────────────────────────────────────────────────────────────

WEEK_START = dt.date(2027, 3, 22)       # Monday; clocks go 02:00 -> 03:00 on Sunday 2027-03-28
LOG_START = dt.date(2027, 3, 15)        # last week's dispatch log (no clock change)
DST_DAY = dt.date(2027, 3, 28)
DT_H = 0.25                             # settlement interval, hours
CAPACITY = 40.0                         # MWh
PMAX = 20.0                             # MW, charge and discharge
ETA = 0.92                              # one-way efficiency, applied on charge and on discharge
SOC_MIN, SOC_MAX = 0.10 * CAPACITY, 0.90 * CAPACITY
SOC_START = SOC_END = 0.50 * CAPACITY
EXPORT_CAP = 25.0                       # MW, amended (agreement on file says 30)
AGREEMENT_EXPORT = 30.0
IMPORT_CAP = 20.0
GRID_FROM, GRID_TO = 0, 6 * 60          # grid charging allowed for intervals starting 00:00-05:45 local
RESERVE = 0.20 * CAPACITY               # MWh held at every quarter boundary 17:00..21:00
RES_FROM, RES_TO = 17 * 60, 21 * 60
DEGRADATION = 5.0                       # EUR per MWh throughput (charge + discharge energy at the meter)
SOLAR_MW = 30.0
P_TOL, E_TOL = 1e-4, 0.02               # MW; MWh (0.05% of capacity: a plan rounded to 2-3 decimals stays valid)


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
    world.log_plan = _heuristic(log)
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
        (s["rte"], round(100 * ETA * ETA, 1), "%"), (s["socmin"], 5, "%"), (s["socmax"], 95, "%"),
        (s["solar"], SOLAR_MW, "MWp")])
    ch, dis = world.log_plan
    soc, rows = SOC_START, []
    for i in range(len(world.log.slots)):
        soc += DT_H * (ETA * ch[i] - dis[i] / ETA)
        rows.append((world.log.ts(i), round(ch[i], 3), round(dis[i], 3), round(100 * soc / CAPACITY, 2)))
    write_csv(data_dir / FILES["log"][lang], [c["ts"], c["charge"], c["discharge"], c["soc"]], rows)
    (data_dir / FILES["agreement"][lang]).write_text(
        AGREEMENT[lang].format(exp=int(AGREEMENT_EXPORT), imp=int(IMPORT_CAP)), encoding="utf-8")


# ── simulation and scoring ───────────────────────────────────────────────────

def _in_grid_window(m: int) -> bool:
    return GRID_FROM <= m < GRID_TO


def simulate(world: World, ch: list[float], dis: list[float], prices: list[float] | None = None):
    hz = world.week
    prices = hz.price_true if prices is None else prices
    viol: list[tuple[str, str]] = []

    def flag(rule: str, msg: str) -> None:
        if sum(1 for r, _ in viol if r == rule) < 5:     # first five messages per rule are enough
            viol.append((rule, msg))

    soc = SOC_START
    revenue = import_cost = baseline = deg = 0.0
    throughput = curtailed = 0.0
    min_soc, max_soc = soc, soc
    for i, (d, m) in enumerate(hz.slots):
        c, x, s, p = ch[i], dis[i], hz.solar[i], prices[i]
        ts = hz.ts(i)
        if c < -P_TOL or x < -P_TOL or c > PMAX + P_TOL or x > PMAX + P_TOL:
            flag("power_limits", f"{ts}: charge {c:g} / discharge {x:g} MW outside 0..{PMAX:g} MW")
        elif c > P_TOL and x > P_TOL:
            flag("power_limits", f"{ts}: charges and discharges in the same interval")
        net = s + x - c
        if x > P_TOL and net > EXPORT_CAP + P_TOL:
            flag("export_cap", f"{ts}: site export {net:.2f} MW > {EXPORT_CAP:g} MW while discharging")
        if net < -P_TOL and not _in_grid_window(m):
            flag("grid_charging_window", f"{ts}: imports {-net:.2f} MW from the grid outside 00:00-06:00")
        if net < -IMPORT_CAP - P_TOL:
            flag("power_limits", f"{ts}: imports {-net:.2f} MW > {IMPORT_CAP:g} MW")
        soc += DT_H * (ETA * c - x / ETA)
        min_soc, max_soc = min(min_soc, soc), max(max_soc, soc)
        if soc < SOC_MIN - E_TOL or soc > SOC_MAX + E_TOL:
            flag("soc_limits", f"after {ts}: SOC {100 * soc / CAPACITY:.2f}% outside 10%-90%")
        end_m = m + 15
        if RES_FROM <= end_m <= RES_TO and soc < RESERVE - E_TOL:
            flag("reserve_20pct", f"after {ts}: SOC {100 * soc / CAPACITY:.2f}% < 20% in the 17:00-21:00 reserve")
        export = min(max(net, 0.0), EXPORT_CAP)
        imp = max(-net, 0.0)
        curtailed += DT_H * max(0.0, net - EXPORT_CAP) if x <= P_TOL else 0.0
        revenue += p * DT_H * export
        import_cost += p * DT_H * imp
        baseline += p * DT_H * min(s, EXPORT_CAP)
        throughput += DT_H * (max(c, 0) + max(x, 0))
    if soc < SOC_END - E_TOL:
        flag("end_soc", f"week ends at SOC {100 * soc / CAPACITY:.2f}% < 50%")
    deg = DEGRADATION * throughput
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


def score(world: World, submission_dir: Path) -> dict:
    try:
        ch, dis = _read_plan(world, submission_dir)
    except Fatal as e:
        return {"fatal": str(e)}
    viol, obj, metrics = simulate(world, ch, dis)
    return {"violations": viol, "objective": obj, "metrics": metrics}


# ── reference solution ───────────────────────────────────────────────────────

def _heuristic(hz: Horizon, reserve: bool = True) -> tuple[list[float], list[float]]:
    """Greedy two-cycles-a-day rule on forecast prices: fill up in the cheapest night quarters and sell into
    the morning peak; refill from solar in the cheapest daylight quarters (always soaking up clipped solar)
    and sell into the evening peak."""
    n = len(hz.slots)
    ch, dis = [0.0] * n, [0.0] * n
    soc = SOC_START
    days = sorted({d for d, _ in hz.slots})
    per_q = PMAX * DT_H
    k_sell = math.ceil((SOC_MAX - SOC_MIN) * ETA / per_q)
    for d in days:
        idx = [i for i in range(n) if hz.slots[i][0] == d]
        last = d == days[-1]
        m_of = {i: hz.slots[i][1] for i in idx}
        p = hz.price_fc

        def cheapest(cands, k):
            return sorted(cands, key=lambda i: (p[i], i))[:k]

        def dearest(cands, k, hurdle):
            return [i for i in sorted(cands, key=lambda i: (-p[i], i))[:k] if p[i] > hurdle]

        night = [i for i in idx if _in_grid_window(m_of[i])]
        q_night = math.ceil(max(0.0, SOC_MAX - soc) / (per_q * ETA) - 1e-9)
        buy1 = set(cheapest(night, q_night))
        h1 = (sum(p[i] for i in buy1) / len(buy1) if buy1 else 0.0) / (ETA * ETA) + 2 * DEGRADATION
        sell1 = set(dearest([i for i in idx if 6 * 60 <= m_of[i] < 11 * 60], k_sell, h1))
        sunny = [i for i in idx if 9 * 60 <= m_of[i] < 17 * 60 and hz.solar[i] >= 1.0]
        buy2 = set(cheapest(sunny, 16))
        h2 = (sum(p[i] for i in buy2) / len(buy2) if buy2 else 0.0) / (ETA * ETA) + 2 * DEGRADATION
        sell2 = set(dearest([i for i in idx if m_of[i] >= 15 * 60], k_sell, h2))
        refill = 0.8 * DT_H * ETA * sum(min(PMAX, hz.solar[i]) for i in buy2)
        for i in idx:
            m, s = m_of[i], hz.solar[i]
            room = max(0.0, (SOC_MAX - soc) / (DT_H * ETA))
            if i in buy1:
                ch[i] = min(PMAX, room)
            elif i in buy2 or s > EXPORT_CAP:
                ch[i] = min(PMAX, s if i in buy2 else s - EXPORT_CAP, room)
            elif i in sell1 or i in sell2:
                if last:
                    floor = max(RESERVE, SOC_END - refill) if i in sell1 else SOC_END
                elif reserve and m < RES_TO:
                    floor = RESERVE
                else:
                    floor = SOC_MIN
                dis[i] = max(0.0, min(PMAX, EXPORT_CAP - s, (soc - floor) * ETA / DT_H))
            ch[i], dis[i] = math.floor(ch[i] * 1e4) / 1e4, math.floor(dis[i] * 1e4) / 1e4
            soc += DT_H * (ETA * ch[i] - dis[i] / ETA)
    return ch, dis


def _write_plan(world: World, out_dir: Path, ch: list[float], dis: list[float]) -> None:
    hz = world.week
    write_csv(out_dir / "dispatch.csv", ["timestamp", "charge_mw", "discharge_mw"],
              [(hz.ts(i), round(ch[i], 4), round(dis[i], 4)) for i in range(len(hz.slots))])
    # write_csv adds a BOM; keep the reference plain ASCII
    p = out_dir / "dispatch.csv"
    p.write_bytes(p.read_bytes().removeprefix(b"\xef\xbb\xbf"))


def reference_solution(world: World, out_dir: Path) -> None:
    ch, dis = _heuristic(world.week)
    _write_plan(world, out_dir, ch, dis)


def baseline_solution(world: World, out_dir: Path) -> None:
    """The site without a dispatch plan: the battery rests at 50% all week and the farm sells solar alone
    (battery profit 0; nothing to break, since export, import and reserve rules only bite when it moves)."""
    n = len(world.week.slots)
    _write_plan(world, out_dir, [0.0] * n, [0.0] * n)


def violating_examples(world: World) -> dict:
    """One plan per rule that breaks exactly that rule (for the validator)."""
    base_c, base_d = _heuristic(world.week)
    hz = world.week
    n = len(hz.slots)

    def only(rule: str, c: list[float], d: list[float]) -> bool:
        return {r for r, _ in simulate(world, c, d)[0]} == {rule}

    def search(rule: str, candidates):
        for c, d in candidates:
            if only(rule, c, d):
                return lambda out, c=c, d=d: _write_plan(world, out, c, d)
        raise AssertionError(f"no clean example for {rule}")

    m_of = lambda i: hz.slots[i][1]
    idle = lambda i: base_c[i] == 0 and base_d[i] == 0

    def over_power():
        for i in range(n):
            if base_d[i] > 0 and hz.solar[i] == 0:
                for j in range(i + 1, n):
                    if base_d[j] >= 1.0:
                        c, d = base_c[:], base_d[:]
                        extra = PMAX + 1.0 - d[i]
                        if d[j] < extra:
                            continue
                        d[i] += extra
                        d[j] -= extra
                        yield c, d

    def end_low():
        for a in (2.0, 4.0, 8.0, 12.0, 16.0):
            c, d = base_c[:], base_d[:]
            k = n - 1
            c[k] = 0.0
            d[k] = a
            yield c, d

    def grid_outside():
        # charge from the grid at 22:00-23:45 and charge that much less in the next night
        for i in range(n):
            if not (22 * 60 <= m_of(i) and idle(i) and hz.solar[i] == 0):
                continue
            for j in range(i + 1, n):
                if base_c[j] >= 4.0 and _in_grid_window(m_of(j)):
                    c, d = base_c[:], base_d[:]
                    c[i] += 4.0
                    c[j] -= 4.0
                    yield c, d

    def export_over():
        for i in range(n):
            if not (idle(i) and 8.0 < hz.solar[i] < EXPORT_CAP - 1.0):
                continue
            for j in range(i + 1, n):
                a = EXPORT_CAP - hz.solar[i] + 2.0
                if base_d[j] >= a:
                    c, d = base_c[:], base_d[:]
                    d[i] += a
                    d[j] -= a
                    yield c, d

    def reserve_ex():
        # dip into the evening reserve (but not below 10%), taken back from the next discharge
        for i in range(n):
            if not (base_c[i] == 0 and RES_FROM <= m_of(i) < RES_TO and hz.solar[i] < 5.0):
                continue
            for a in (4.0, 8.0, 12.0):
                if base_d[i] + a > PMAX:
                    continue
                j = next((j for j in range(i + 1, n) if base_d[j] >= a and m_of(j) < RES_FROM or
                          base_d[j] >= a and m_of(j) >= RES_TO), None)
                if j is not None:
                    c, d = base_c[:], base_d[:]
                    d[i] += a
                    d[j] -= a
                    yield c, d

    def soc_low():
        # an extra full-power quarter late in the evening, taken back from the next discharge
        for i in range(n):
            if not (idle(i) and m_of(i) >= RES_TO and hz.solar[i] == 0):
                continue
            for a in (PMAX, 16.0, 12.0):
                j = next((j for j in range(i + 1, n) if base_d[j] >= a), None)
                if j is not None:
                    c, d = base_c[:], base_d[:]
                    d[i] += a
                    d[j] -= a
                    yield c, d

    def soc_high():
        for i in range(n):
            if idle(i) and _in_grid_window(m_of(i)):
                for a in (8.0, 12.0, 16.0, 20.0):
                    c, d = base_c[:], base_d[:]
                    c[i] = a
                    # compensate later with extra discharge outside the reserve window and below the cap
                    need = a * ETA * ETA
                    for j in range(i + 1, n):
                        if base_d[j] > 0 and base_d[j] + need <= PMAX and m_of(j) >= RES_TO \
                                and hz.solar[j] + base_d[j] + need <= EXPORT_CAP:
                            d[j] += need
                            yield c, d
                            break

    return {
        "power_limits": search("power_limits", over_power()),
        "soc_limits": search("soc_limits", (x for g in (soc_low(), soc_high()) for x in g)),
        "export_cap": search("export_cap", export_over()),
        "grid_charging_window": search("grid_charging_window", grid_outside()),
        "end_soc": search("end_soc", end_low()),
        "reserve_20pct": search("reserve_20pct", reserve_ex()),
    }
