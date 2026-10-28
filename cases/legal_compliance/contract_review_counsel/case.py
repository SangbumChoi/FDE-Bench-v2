"""Supplier contract review against the company playbook (original FDE-Bench v2 case).

The legal team of Brightvale Holdings sends 40 supplier contracts (one text
file each) plus the contract register and asks which ones need changes before
signature. The request is vague; the playbook that decides what counts as an
issue (liability cap vs annual value, allowed governing laws, renewal notice,
payment terms, data-protection clause for IT & data suppliers, termination for
convenience above a value, mutual indemnity), the issue codes, the decision
logic and the small-contract fast track are in the requirements and must be
asked for. Clauses are written with varied wording, so plain keyword matching
misses some of them; some contracts are on the supplier's paper in another
language.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from fdebench2.casekit import Fatal, labels, read_json, write_csv

# ── playbook ─────────────────────────────────────────────────────────────────

ALLOWED_LAW = ("CH", "SG")
MIN_RENEWAL_NOTICE = 60       # days; a month counts as 30 days
MIN_PAYMENT_DAYS = 45
DP_CATEGORIES = ("it_data",)
TFC_ABOVE = 150_000           # USD annual value: termination for convenience required above this
FAST_TRACK_BELOW = 20_000     # USD annual value: signed without review below this
CODES = ("LIABILITY_CAP", "GOVERNING_LAW", "AUTO_RENEWAL", "PAYMENT_TERMS", "DATA_PROTECTION",
         "TERMINATION_CONVENIENCE", "INDEMNITY")
CRITICAL = ("LIABILITY_CAP", "DATA_PROTECTION", "INDEMNITY")
DECISIONS = ("sign", "negotiate", "reject")
F1_WEIGHT, DECISION_WEIGHT = 0.7, 0.3

CATEGORIES = ("it_data", "logistics", "facilities", "raw_materials", "marketing", "professional")
N_CONTRACTS = 40


def decide(issues) -> str:
    crit = sum(1 for i in set(issues) if i in CRITICAL)
    if crit >= 2:
        return "reject"
    return "negotiate" if issues else "sign"


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
    truth: list[str] = field(default_factory=list)

    def cap_usd(self) -> float:
        kind = self.cap[0]
        if kind == "mult":
            return self.cap[1] * self.value
        if kind == "amount":
            return float(self.cap[1])
        if kind == "period":
            return self.cap[1] / 12 * self.value
        return float("inf")


@dataclass
class World:
    contracts: list[Contract]

    def by_id(self) -> dict[str, Contract]:
        return {c.id: c for c in self.contracts}


def true_issues(c: Contract) -> list[str]:
    out = []
    if c.cap_usd() < c.value:
        out.append("LIABILITY_CAP")
    if c.law[0] not in ALLOWED_LAW:
        out.append("GOVERNING_LAW")
    if c.renew is not None and c.renew[0] < MIN_RENEWAL_NOTICE:
        out.append("AUTO_RENEWAL")
    if c.pay[0] < MIN_PAYMENT_DAYS:
        out.append("PAYMENT_TERMS")
    if c.category in DP_CATEGORIES and c.dp is None:
        out.append("DATA_PROTECTION")
    if c.value > TFC_ABOVE and c.tfc is None:
        out.append("TERMINATION_CONVENIENCE")
    if c.indemnity == "one_way":
        out.append("INDEMNITY")
    return out


def _wpick(rng: random.Random, pairs):
    vals, weights = zip(*pairs)
    return rng.choices(vals, weights=weights)[0]


def build_world(seed: int) -> World:
    rng = random.Random(seed)
    values = ([rng.randrange(6_000, 19_500, 500) for _ in range(8)]
              + [rng.randrange(25_000, 150_000, 500) for _ in range(14)]
              + [rng.randrange(160_000, 1_200_000, 500) for _ in range(18)])
    rng.shuffle(values)
    cats = [CATEGORIES[i % len(CATEGORIES)] for i in range(N_CONTRACTS)]
    cats[:6] = ["it_data"] * 6  # IT & data is the biggest spend category
    rng.shuffle(cats)
    foreign = set(rng.sample(range(N_CONTRACTS), 6))
    names = list(range(N_CONTRACTS))
    rng.shuffle(names)
    contracts = []
    for i in range(N_CONTRACTS):
        value, cat = values[i], cats[i]
        para = lambda p=0.25: rng.random() < p  # noqa: E731
        renew = None
        if rng.random() < 0.6:
            notice = _wpick(rng, [(30, 2), (45, 2), (60, 3), (90, 3)])
            renew = (notice, "p" if para() else "x", "w" if para() else "d")
        pay = (_wpick(rng, [(30, 3), (45, 3), (60, 3), (90, 2)]), _wpick(rng, [("d", 6), ("w", 2.5), ("n", 1.5)]))
        dp_present = rng.random() < (0.55 if cat == "it_data" else 0.4)
        dp = ("p" if para() else "x") if dp_present else None
        tfc = (rng.choice([30, 60, 90]), "p" if para() else "x") if rng.random() < 0.55 else None
        indemnity = _wpick(rng, [("mutual_x", 5), ("mutual_p", 2), ("one_way", 3)])
        kind = _wpick(rng, [("mult", 4), ("amount", 4), ("period", 2.5), ("unlimited", 1)])
        if kind == "mult":
            cap = ("mult", _wpick(rng, [(0.5, 3), (1, 2), (1.5, 2), (2, 2), (3, 1)]), "w" if para(0.4) else "d")
        elif kind == "amount":
            r = _wpick(rng, [(0.5, 2), (0.75, 2), (1.0, 2), (1.25, 1), (2.0, 2)])
            amt = value if r == 1.0 else (int(value * r // 5000) * 5000 if r < 1 else -(-int(value * r) // 5000) * 5000)
            amt = max(amt, 5000) if r >= 1 else max(min(amt, value - 500), 2000)
            cap = ("amount", amt, "p" if para() else "d")
        elif kind == "period":
            cap = ("period", _wpick(rng, [(6, 2), (12, 2), (24, 1)]))
        else:
            cap = ("unlimited",)
        law_code = _wpick(rng, [("CH", 3.5), ("SG", 3), ("EW", 1.2), ("NY", 1), ("HK", 0.8), ("DE", 0.8)])
        law_phr = "swiss" if law_code == "CH" and rng.random() < 0.45 else "x"
        venue = law_code if rng.random() < 0.6 else _wpick(rng, [("SG", 3), ("CH", 1), ("EW", 1), ("NY", 1), ("HK", 1)])
        law = (law_code, law_phr, venue, "arb" if rng.random() < 0.5 else "courts")
        c = Contract(id=f"C{i + 1:03d}", value=value, category=cat, foreign=i in foreign, name_idx=names[i],
                     term_years=rng.choice([1, 2, 3]), renew=renew, pay=pay, dp=dp, tfc=tfc, indemnity=indemnity,
                     cap=cap, law=law)
        c.truth = true_issues(c)
        contracts.append(c)
    return World(contracts)


# ── localized texts ──────────────────────────────────────────────────────────

FILES = {
    "register": {"zh": "合同台账.csv", "en": "contract_register.csv", "ko": "계약대장.csv", "ja": "契約台帳.csv",
                 "es": "registro_contratos.csv"},
    "folder": {"zh": "合同文本", "en": "contracts", "ko": "계약서", "ja": "契約書", "es": "contratos"},
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
NAME_PREFIX = {
    "zh": ["华信", "恒达", "嘉禾", "远航", "博瑞", "鼎盛", "金石", "联创", "海川", "星河", "天成", "盛世", "安泰", "宏图",
           "新元", "瑞丰", "卓远", "万通", "聚力", "云帆", "青松", "立德", "永兴", "合众", "明川", "启航", "博远", "德润",
           "凯盛", "华茂", "信达", "锦程", "致远", "嘉信", "长风", "润泽", "和信", "众诚", "瀚海", "隆泰"],
    "en": ["Ashford", "Brookline", "Carrow", "Denholm", "Elmstead", "Fairhaven", "Glenmore", "Harrowgate", "Ivybridge",
           "Kestrel", "Larkfield", "Merriton", "Northcote", "Oakhurst", "Penbury", "Quarry Hill", "Redmarsh",
           "Stanwick", "Thornbury", "Upton Vale", "Westcliff", "Yarrow", "Alder", "Beckett", "Coldwater", "Draycott",
           "Everleigh", "Foxley", "Greystone", "Hartwell", "Kingsmere", "Lindale", "Millbrook", "Newhaven", "Ormsby",
           "Pemberton", "Rowan", "Silverdale", "Tamworth", "Wexley"],
    "ko": ["한빛", "대성", "미래", "동양", "새한", "청운", "태양", "우진", "세진", "한결", "금강", "서원", "늘푸른", "다온",
           "해솔", "가온", "누리", "동인", "신우", "영진", "백산", "하나로", "정우", "초록", "바른", "온누리", "대원",
           "성원", "해든", "진명", "은하", "수성", "단비", "한울", "아라", "솔빛", "보람", "새솔", "한마음", "푸른숲"],
    "ja": ["山王", "東光", "北辰", "若葉", "青葉", "富士見", "緑川", "白鷺", "三輪", "桜井", "高砂", "光陽", "栄進", "明和",
           "誠和", "日進", "共栄", "金剛", "大翔", "瑞穂", "早瀬", "朝霧", "葵", "楓", "新星", "弥生", "雅", "秋津",
           "柏木", "泉", "春日", "白樺", "常盤", "豊和", "長門", "鳳", "睦", "藤波", "曙", "清流"],
    "es": ["Ibérica", "Levante", "Cantábrica", "Meseta", "Albor", "Atalaya", "Brisa", "Cumbre", "Duero", "Ebro",
           "Faro", "Genil", "Horizonte", "Jara", "Lince", "Mirador", "Olivo", "Pinar", "Quercus", "Ribera", "Sierra",
           "Tajo", "Umbral", "Vega", "Zafiro", "Alameda", "Bahía", "Candil", "Delta", "Encina", "Fuente", "Galena",
           "Hispalis", "Lucero", "Marisma", "Nogal", "Oriente", "Peñalara", "Retama", "Solana"],
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


EN_WORDS = {30: "thirty", 45: "forty-five", 60: "sixty", 90: "ninety"}
EN_MONTHS = {30: "one month", 45: "forty-five days", 60: "two months", 90: "three months"}
EN_PERIOD = {6: "six", 12: "twelve", 24: "twenty-four"}
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
    arts.append(("Scope and Term", [f"The Supplier provides the Customer with {DESC[c.category]['en']}.", term]))
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


ZH_NUM = {30: "三十", 45: "四十五", 60: "六十", 90: "九十"}
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
    arts.append(("合同标的与期限", [f"乙方向甲方提供{DESC[c.category]['zh']}。", term]))
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
            amt = f"{a:,}美元" if c.cap[2] == "d" else f"{a / 10000:g}万美元"
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
KO_PAY_WORD = {30: "한 달", 45: "45일", 60: "두 달", 90: "석 달"}


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
    arts.append(("목적 및 기간", [f"을은 갑에게 {DESC[c.category]['ko']}를 제공한다.", term]))
    d, pp = c.pay
    pay = {"d": f"갑은 이의가 없는 세금계산서를 수령한 날부터 {d}일 이내에 대금을 지급한다.",
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
            amt = f"미화 {a:,}달러를" if c.cap[2] == "d" else f"미화 {a / 10000:g}만 달러를"
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


JA_NOTICE = {30: "1か月", 45: "45日", 60: "2か月", 90: "3か月"}


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
    arts.append(("目的および期間", [f"乙は、甲に対し、{DESC[c.category]['ja']}を提供する。", term]))
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
            amt = f"{a:,}米ドル" if c.cap[2] == "d" else f"{a / 10000:g}万米ドル"
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


ES_WORDS = {30: "treinta", 45: "cuarenta y cinco", 60: "sesenta", 90: "noventa"}
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
    arts.append(("Objeto y duración", [f"El Proveedor presta al Cliente {DESC[c.category]['es']}.", term]))
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
        head = [f"SUPPLY AGREEMENT No. {c.id}", "",
                f"This Agreement is made between {cust} (the \"Customer\") and {sup} (the \"Supplier\")."]
        art_head = lambda n, t: f"Article {n}. {t}"  # noqa: E731
        sub = lambda n, k, s: f"{n}.{k} {s}"  # noqa: E731
        tail = ["Signed for and on behalf of the Customer: ______________________",
                "Signed for and on behalf of the Supplier: ______________________"]
    elif tl == "zh":
        head = ["供货与服务合同", f"合同编号：{c.id}", "", f"甲方：{cust}", f"乙方：{sup}", "",
                "甲乙双方经友好协商，就乙方向甲方提供产品及服务事宜订立本合同，以资共同遵守。"]
        art_head = lambda n, t: f"第{ZH_ART[n - 1]}条　{t}"  # noqa: E731
        sub = lambda n, k, s: f"{n}.{k}　{s}"  # noqa: E731
        tail = ["甲方（盖章）：______________", "乙方（盖章）：______________"]
    elif tl == "ko":
        head = ["공급 및 용역 계약서", f"계약번호: {c.id}", "",
                f"{cust}(이하 \"갑\")와 {sup}(이하 \"을\")는 다음과 같이 계약을 체결한다."]
        art_head = lambda n, t: f"제{n}조 ({t})"  # noqa: E731
        sub = lambda n, k, s: f"{'①②③④'[k - 1]} {s}"  # noqa: E731
        tail = ["갑: ______________ (인)", "을: ______________ (인)"]
    elif tl == "ja":
        head = ["業務委託・供給契約書", f"契約番号：{c.id}", "",
                f"{cust}（以下「甲」という。）と{sup}（以下「乙」という。）は、次のとおり契約を締結する。"]
        art_head = lambda n, t: f"第{n}条（{t}）"  # noqa: E731
        sub = lambda n, k, s: f"{k}　{s}"  # noqa: E731
        tail = ["甲：______________ 印", "乙：______________ 印"]
    else:
        head = [f"CONTRATO DE SUMINISTRO Y SERVICIOS N.º {c.id}", "",
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


# ── scoring ──────────────────────────────────────────────────────────────────

def _parse(world: World, doc) -> dict[str, tuple[list[str], str]]:
    if not isinstance(doc, dict):
        raise Fatal("review.json must be an object keyed by contract id")
    known = world.by_id()
    out = {}
    for cid, entry in doc.items():
        if cid not in known:
            raise Fatal(f"unknown contract id {cid!r}")
        if not isinstance(entry, dict):
            raise Fatal(f"{cid}: entry must be an object with 'issues' and 'decision'")
        issues = entry.get("issues", [])
        if not isinstance(issues, list):
            raise Fatal(f"{cid}: 'issues' must be a list")
        codes = []
        for code in issues:
            code = str(code).strip().upper()
            if code not in CODES:
                raise Fatal(f"{cid}: unknown issue code {code!r}; allowed: {', '.join(CODES)}")
            if code not in codes:
                codes.append(code)
        decision = str(entry.get("decision", "")).strip().lower()
        if decision not in DECISIONS:
            raise Fatal(f"{cid}: decision must be one of {DECISIONS}, got {entry.get('decision')!r}")
        out[cid] = (codes, decision)
    return out


def evaluate_review(world: World, review: dict[str, tuple[list[str], str]]):
    violations = []
    tp = fp = fn = correct = 0
    for c in world.contracts:
        if c.id not in review:
            violations.append(("all_contracts_reviewed", f"{c.id} is missing from review.json"))
            fn += len(c.truth)
            continue
        issues, decision = review[c.id]
        if decision != decide(issues):
            violations.append(("decision_consistency",
                               f"{c.id}: issues {issues} call for '{decide(issues)}', not '{decision}'"))
        if c.value < FAST_TRACK_BELOW and (decision != "sign" or issues):
            violations.append(("small_contract_fast_track",
                               f"{c.id} (USD {c.value:,}) is below the fast-track threshold and must be 'sign' with no issues"))
        truth = set(c.truth)
        tp += len(truth & set(issues))
        fp += len(set(issues) - truth)
        fn += len(truth - set(issues))
        correct += decision == decide(c.truth)
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    acc = correct / len(world.contracts)
    objective = F1_WEIGHT * f1 + DECISION_WEIGHT * acc
    metrics = {"issue_f1": round(f1, 4), "precision": round(prec, 4), "recall": round(rec, 4),
               "decision_accuracy": round(acc, 4), "tp": tp, "fp": fp, "fn": fn}
    return violations, objective, metrics


def score(world: World, submission_dir: Path) -> dict:
    try:
        review = _parse(world, read_json(submission_dir, "review.json"))
    except Fatal as e:
        return {"fatal": str(e)}
    violations, objective, metrics = evaluate_review(world, review)
    return {"violations": violations, "objective": objective, "metrics": metrics}


# ── reference solution: keyword rules on the English wording ─────────────────

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


def keyword_issues(c: Contract) -> list[str]:
    """What a careful but literal keyword checklist finds in the English version of the contract."""
    text = "\n".join(f"Article {n}. {t}\n" + "\n".join(p) for n, (t, p) in
                     enumerate(_render_en(c, "", CUSTOMER["en"]), 1))
    sec = _sections(text)
    found = []
    cap = sec.get("limitation of liability", "")
    m = re.search(r"(\d+(?:\.\d+)?) times", cap)
    a = re.search(r"USD ([\d,]+)", cap)
    if "one half of" in cap or (m and float(m.group(1)) < 1):
        found.append("LIABILITY_CAP")
    elif not m and a and int(a.group(1).replace(",", "")) < c.value:
        found.append("LIABILITY_CAP")
    law = sec.get("governing law and disputes", "")
    if not re.search(r"Switzerland|Swiss|Singapore", law):
        found.append("GOVERNING_LAW")
    scope = sec.get("scope and term", "")
    if "automatically" in scope:
        n = re.search(r"(\d+) days", scope)
        if n and int(n.group(1)) < MIN_RENEWAL_NOTICE:
            found.append("AUTO_RENEWAL")
    pay_txt = sec.get("fees and payment", "")
    for n, word in EN_WORDS.items():
        pay_txt = pay_txt.replace(f"{word} days", f"{n} days")
    pay = re.search(r"(\d+) days", pay_txt)
    if pay and int(pay.group(1)) < MIN_PAYMENT_DAYS:
        found.append("PAYMENT_TERMS")
    if c.category in DP_CATEGORIES and "data protection" not in text.lower():
        found.append("DATA_PROTECTION")
    if c.value > TFC_ABOVE and "convenience" not in sec.get("termination", ""):
        found.append("TERMINATION_CONVENIENCE")
    if "each party" not in sec.get("indemnity", "").lower():
        found.append("INDEMNITY")
    return [code for code in CODES if code in found]


def _reference(world: World, fast_track: bool = True) -> dict:
    out = {}
    for c in world.contracts:
        issues = [] if fast_track and c.value < FAST_TRACK_BELOW else keyword_issues(c)
        out[c.id] = {"issues": issues, "decision": decide(issues)}
    return out


def _write(out_dir: Path, doc: dict) -> None:
    (out_dir / "review.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")


def reference_solution(world: World, out_dir: Path) -> None:
    _write(out_dir, _reference(world))


def violating_examples(world: World) -> dict:
    ref = _reference(world)

    def mutate(fn):
        doc = json.loads(json.dumps(ref))
        fn(doc)
        return lambda out: _write(out, doc)

    def drop(doc):
        cid = next(c.id for c in world.contracts if c.value >= FAST_TRACK_BELOW)
        del doc[cid]

    def inconsistent(doc):
        cid = next(k for k, v in doc.items() if v["decision"] == "negotiate")
        doc[cid]["decision"] = "sign"

    def review_small(doc):
        c = next(c for c in world.contracts if c.value < FAST_TRACK_BELOW and c.truth)
        doc[c.id] = {"issues": list(c.truth), "decision": decide(c.truth)}

    return {"all_contracts_reviewed": mutate(drop), "decision_consistency": mutate(inconsistent),
            "small_contract_fast_track": mutate(review_small)}
