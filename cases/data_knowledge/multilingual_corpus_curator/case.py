"""Multilingual corpus curator (original FDE-Bench v2 case).

A small publisher keeps the material of about a hundred books (Chinese, English,
Korean, Japanese, Spanish) in one messy shared folder: a book's title, authors,
publication years and description are spread over one to three files of mixed
formats (JSON, ONIX-like XML, EPUB, DOCX, PDF, HTML, Markdown, plain text,
catalog CSVs covering several books, zip archives, unreadable scans, junk). The
agent delivers a program `organize(task)` that builds a normalized library
(one description file per book), a manifest, and a review area for books that
cannot be placed. The program is scored on a hidden corpus of the same
distribution (another seed, same size), the same in every setting.

  easy    only well-formed books are scored (complete metadata, UTF-8, plain
          4-digit years, one file per book)
  medium  + every readable book: legacy encodings, era and other year
          notations, full-width / decomposed titles, forbidden path characters,
          author romanization variants, duplicates across formats, source
          precedence (embedded metadata > title page > file name)
  hard    + the exceptions: missing / recoverable authors, titles, years and
          descriptions, conflicting sources, scans, junk files, zip archives,
          multi-book catalog CSVs; each with a defined handling

Rule sets (A / B / C) change the library layout, the year basis (first
publication or this edition), the script of names (original or Latin), how
co-authors are written and the slug rules, so each gives a different library.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import re
import shutil
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from fdebench2.casekit import Fatal, run_program

ENTRYPOINT = "organize.py:organize"
HERE = Path(__file__).resolve().parent
REFERENCE = HERE / "reference" / "organize.py"
TIER_ORDER = ("easy", "medium", "hard")
REASONS = ("UNREADABLE", "NO_TITLE", "NO_AUTHOR", "NO_YEAR", "NO_DESCRIPTION", "CONFLICT")
NO_AUTHOR_REVIEW_CREDIT = 0.7          # a book without an author waiting in review: not on the shelf yet
EXTRA_PENALTY = 0.5                    # medium+: a library file that is no book
CJK = ("zh", "ko", "ja")
N_BOOKS = 100

# ── vocabulary (all invented) ────────────────────────────────────────────────

ZH_ADJ = [("沉默的", "Chenmo de"), ("遥远的", "Yaoyuan de"), ("最后的", "Zuihou de"), ("安静的", "Anjing de"),
          ("失落的", "Shiluo de"), ("漫长的", "Manchang de"), ("透明的", "Touming de"), ("迟到的", "Chidao de")]
ZH_NOUN = [("灯塔", "Dengta"), ("河流", "Heliu"), ("花园", "Huayuan"), ("信使", "Xinshi"), ("钟楼", "Zhonglou"),
           ("书店", "Shudian"), ("港口", "Gangkou"), ("列车", "Lieche"), ("地图", "Ditu"), ("群岛", "Qundao"),
           ("夏天", "Xiatian"), ("雨季", "Yuji")]
KO_ADJ = [("푸른", "Pureun"), ("조용한", "Joyonghan"), ("마지막", "Majimak"), ("먼", "Meon"), ("오래된", "Oraedoen"),
          ("하얀", "Hayan"), ("늦은", "Neujeun"), ("작은", "Jageun")]
KO_NOUN = [("등대", "Deungdae"), ("정원", "Jeongwon"), ("기차", "Gicha"), ("편지", "Pyeonji"), ("섬", "Seom"),
           ("서점", "Seojeom"), ("강", "Gang"), ("시계탑", "Sigyetap"), ("골목", "Golmok"), ("바다", "Bada"),
           ("여름", "Yeoreum"), ("지도", "Jido")]
JA_NOUN = [("雨", "Ame"), ("図書館", "Toshokan"), ("月", "Tsuki"), ("灯台", "Todai"), ("森", "Mori"), ("港", "Minato"),
           ("手紙", "Tegami"), ("庭", "Niwa"), ("時計", "Tokei"), ("旅人", "Tabibito"), ("硝子", "Garasu"), ("海", "Umi"),
           ("夏", "Natsu"), ("冬", "Fuyu"), ("坂道", "Sakamichi"), ("鳥", "Tori")]
JA_ADJ = [("静かな", "Shizukana"), ("遠い", "Toi"), ("青い", "Aoi"), ("最後の", "Saigo no"), ("小さな", "Chiisana")]
EN_ADJ = ["Silent", "Distant", "Last", "Quiet", "Lost", "Long", "Glass", "Late", "Hidden", "Northern"]
EN_NOUN = ["Lighthouse", "River", "Garden", "Messenger", "Clock Tower", "Bookshop", "Harbour", "Train", "Map",
           "Islands", "Summer", "Orchard"]
EN_PLACE = ["Aldermoor", "Saint Brennock", "Cape Halloway", "Westerley", "Fenwick Hollow", "Marrow Bay"]
EN_SUB = ["Stories from the Northern Coast and the Keepers Who Stayed Behind", "A Novel in Thirty-One Short Chapters",
          "Notes on Memory, Weather and the Families We Leave",
          "Three Generations, One House and a River That Would Not Stay"]
ES_NF = ["canción", "casa", "estación", "isla", "librería", "memoria", "playa"]
ES_NM = ["jardín", "río", "faro", "reloj", "mapa", "verano", "puerto"]
ES_ADJ = [("callada", "callado"), ("lejana", "lejano"), ("dormida", "dormido"), ("perdida", "perdido"),
          ("pequeña", "pequeño"), ("olvidada", "olvidado")]
ES_PLACE = ["Valdemora", "San Telmo del Mar", "Puerto Albéniz", "Almenara", "Castrillo de la Vega"]
ES_SUB = ["Relatos de la costa norte y de quienes se quedaron", "Una novela en treinta y un capítulos breves",
          "Notas sobre la memoria, el tiempo y las familias que dejamos"]

SURNAMES = {
    "zh": [("王", "Wang"), ("李", "Li"), ("陈", "Chen"), ("林", "Lin"), ("周", "Zhou"), ("赵", "Zhao"), ("吴", "Wu"),
           ("许", "Xu")],
    "ko": [("김", "Kim"), ("이", "Lee"), ("박", "Park"), ("최", "Choi"), ("정", "Jung"), ("강", "Kang"), ("윤", "Yoon"),
           ("한", "Han")],
    "ja": [("佐藤", "Sato"), ("鈴木", "Suzuki"), ("高橋", "Takahashi"), ("田中", "Tanaka"), ("渡辺", "Watanabe"),
           ("伊藤", "Ito"), ("中村", "Nakamura"), ("小林", "Kobayashi")],
    "en": ["Whitlock", "Ashdown", "Fairbairn", "Calloway", "Penrose", "Hartigan", "Elsworth", "Thorne"],
    "es": ["Ferrán", "Olmedo", "Barrachina", "Quiroga", "Echeverría", "Saldaña", "Montalbán", "Ribera"],
}
GIVEN = {   # CJK: (original, canonical Latin, other spelling)
    "zh": [("思远", "Siyuan", "Si-yuan"), ("明哲", "Mingzhe", "Ming-zhe"), ("晓雯", "Xiaowen", "Xiao-wen"),
           ("雨桐", "Yutong", "Yu-tong"), ("嘉怡", "Jiayi", "Jia-yi"), ("子涵", "Zihan", "Zi-han"),
           ("浩然", "Haoran", "Hao-ran"), ("若曦", "Ruoxi", "Ruo-xi")],
    "ko": [("민준", "Min-jun", "Minjun"), ("서연", "Seo-yeon", "Seoyeon"), ("지호", "Ji-ho", "Jiho"),
           ("하은", "Ha-eun", "Haeun"), ("도윤", "Do-yoon", "Doyoon"), ("수아", "Su-ah", "Suah"),
           ("예린", "Ye-rin", "Yerin"), ("현우", "Hyun-woo", "Hyunwoo")],
    "ja": [("遥", "Haruka", "Haruka"), ("蓮", "Ren", "Ren"), ("結衣", "Yui", "Yui"), ("大翔", "Hiroto", "Hiroto"),
           ("美咲", "Misaki", "Misaki"), ("湊", "Minato", "Minato"), ("葵", "Aoi", "Aoi"), ("悠真", "Yuma", "Yuma")],
    "en": ["Eleanor", "Marcus", "Priya", "Tobias", "Helena", "Owen", "Clara", "Jonah"],
    "es": ["Lucía", "Mateo", "Inés", "Álvaro", "Carmen", "Joaquín", "Marina", "Tomás"],
}

DESC = {
    "zh": dict(
        prot=["一位退休的地图绘制师", "一名年轻的渡轮驾驶员", "一对多年不说话的姐妹", "一位值夜班的图书管理员",
              "一名钟表学徒", "一位守寡的养蜂人", "一个刚搬来的邮递员", "一位失明的调音师"],
        place=["北方海岸的小渔镇", "被大雪封住的山村", "一条废弃铁路的终点站", "只有一家书店的小岛", "运河纵横的老城",
               "边境线上的茶园", "河口的旧码头", "高原上的气象站"],
        event=["一封迟到了四十年的信突然寄到", "河流在一夜之间改了道", "灯塔的灯第一次熄灭", "一个陌生人买下了同一本书的所有存货",
               "镇上的大钟停在了正午", "最后一班列车没有回来", "一场大火烧毁了档案馆", "候鸟提前一个月离开"],
        theme=["记忆与宽恕", "留下来的代价", "微小的善意", "家人之间没有说出口的话", "故乡与远方", "时间如何改变一个地方"],
        n=["十二", "十七", "二十", "三十一"],
        p1=["当{event}，住在{place}的{prot}不得不决定哪些东西值得留下。",
            "{prot}多年来一直回避{place}，直到{event}，一切又被重新翻了出来。",
            "故事从{place}开始：{event}，而{prot}是唯一记得原因的人。"],
        p2=["这是一部关于{theme}的安静小说。", "全书以一个冬天为线索，写{prot}和那些不肯离开的人。",
            "作者用{n}个短章在过去与现在之间来回，追问{theme}。"]),
    "ja": dict(
        prot=["引退した地図職人", "若いフェリーの操舵士", "口をきかなくなった二人の姉妹", "夜勤の図書館司書", "時計職人の見習い",
              "夫を亡くした養蜂家", "越してきたばかりの郵便配達人", "目の見えない調律師"],
        place=["北の海岸の小さな漁村", "雪に閉ざされた山あいの村", "廃線になった鉄道の終着駅", "書店がひとつしかない島",
               "運河の流れる古い町", "国境近くの茶畑", "河口の古い波止場", "高原の気象観測所"],
        event=["四十年遅れの手紙が届く", "川の流れが一夜で変わる", "灯台の灯りが初めて消える", "見知らぬ客が同じ本を買い占める",
               "町の時計が正午で止まる", "最終列車が戻らない", "火事で資料館が焼ける", "渡り鳥がひと月早く去る"],
        theme=["記憶と赦し", "とどまることの代償", "ささやかな優しさ", "家族が口にしなかったこと", "故郷と遠い場所",
               "時間が場所を変えていくこと"],
        n=["十二", "十七", "二十", "三十一"],
        p1=["{event}とき、{place}に住む{prot}は、何を残すべきかを決めなければならない。",
            "{prot}は長いあいだ{place}を避けてきた。だが{event}と、すべてがよみがえる。",
            "物語は{place}から始まる。{event}――その理由を覚えているのは{prot}だけだ。"],
        p2=["{theme}をめぐる静かな長編。", "ひと冬の出来事として、{prot}と、町を離れようとしない人々を描く。",
            "過去と現在を行き来する{n}の短い章で、{theme}を問いかける。"]),
    "ko": dict(
        prot=["은퇴한 지도 제작자", "젊은 여객선 조타수", "오랫동안 말을 끊은 두 자매", "야간 근무를 하는 사서", "시계공 견습생",
              "남편을 잃은 양봉가", "새로 온 우체부", "앞을 보지 못하는 조율사"],
        place=["북쪽 해안의 작은 어촌", "눈에 갇힌 산골 마을", "버려진 철길의 마지막 역", "서점이 하나뿐인 섬",
               "운하가 흐르는 오래된 도시", "국경 근처의 차밭", "강어귀의 낡은 부두", "고원의 기상 관측소"],
        event=["사십 년 늦은 편지가 도착하자", "강줄기가 하룻밤 사이에 바뀌자", "등대의 불이 처음으로 꺼지자",
               "낯선 사람이 같은 책을 모두 사 가자", "마을 시계가 정오에 멈추자", "마지막 기차가 돌아오지 않자",
               "화재로 기록 보관소가 불타자", "철새들이 한 달 일찍 떠나자"],
        theme=["기억과 용서", "남는다는 것의 대가", "작은 친절", "가족이 끝내 하지 못한 말", "고향과 먼 곳",
               "시간이 한 장소를 바꾸는 방식"],
        n=["12", "17", "20", "31"],
        p1=["{event}, {place}에 사는 {prot}{eun} 무엇을 남길지 결정해야 한다.",
            "{prot}{eun} 몇 해 동안 {place}{eul} 피해 왔다. 그러나 {event} 모든 것이 다시 떠오른다.",
            "이야기는 {place}에서 시작된다. {event} 그 이유를 기억하는 사람은 {prot}뿐이다."],
        p2=["{theme}에 관한 조용한 소설.", "한 겨울 동안의 이야기로, {prot}{wa} 떠나기를 거부하는 사람들을 따라간다.",
            "과거와 현재를 오가는 {n}개의 짧은 장으로 {theme}{eul2} 묻는다."]),
    "en": dict(
        prot=["a retired mapmaker", "a young ferry pilot", "two sisters who stopped speaking", "a night-shift librarian",
              "an apprentice clockmaker", "a widowed beekeeper", "a newly arrived postman", "a blind piano tuner"],
        place=["a fishing town on the northern coast", "a mountain village cut off by snow",
               "the last station of an abandoned railway", "an island with a single bookshop", "an old city of canals",
               "a tea garden on the border", "the old docks at the river mouth", "a weather station on the high plateau"],
        event=["a letter arrives forty years late", "the river changes course overnight",
               "the lighthouse goes dark for the first time", "a stranger buys every copy of the same book",
               "the town clock stops at noon", "the last train never comes back", "a fire destroys the archive",
               "the migrating birds leave a month early"],
        theme=["memory and forgiveness", "the price of staying", "small kindnesses", "what families leave unsaid",
               "home and elsewhere", "how time changes a place"],
        n=["twelve", "seventeen", "twenty", "thirty-one"],
        p1=["When {event}, {prot} in {place} has to decide what is worth keeping.",
            "For years {prot} has avoided {place}; then {event}, and everything comes back.",
            "It begins in {place}: {event}, and {prot} is the only one who remembers why."],
        p2=["A quiet novel about {theme}.", "Told over a single winter, it follows {prot} and the people who refuse to leave.",
            "In {n} short chapters that move between past and present, it asks about {theme}."]),
    "es": dict(
        prot=["una cartógrafa jubilada", "un joven piloto de transbordador", "dos hermanas que dejaron de hablarse",
              "un bibliotecario del turno de noche", "una aprendiz de relojera", "una apicultora viuda",
              "un cartero recién llegado", "un afinador de pianos ciego"],
        place=["un pueblo pesquero de la costa norte", "una aldea de montaña aislada por la nieve",
               "la última estación de un ferrocarril abandonado", "una isla con una sola librería",
               "una vieja ciudad de canales", "un jardín de té en la frontera", "los viejos muelles de la desembocadura",
               "una estación meteorológica en el altiplano"],
        event=["llega una carta con cuarenta años de retraso", "el río cambia de cauce en una sola noche",
               "el faro se apaga por primera vez", "un desconocido compra todos los ejemplares del mismo libro",
               "el reloj del pueblo se detiene al mediodía", "el último tren no regresa", "un incendio destruye el archivo",
               "las aves migratorias se marchan un mes antes"],
        theme=["la memoria y el perdón", "el precio de quedarse", "las pequeñas bondades", "lo que las familias no se dicen",
               "el hogar y la distancia", "cómo el tiempo cambia un lugar"],
        n=["doce", "diecisiete", "veinte", "treinta y uno"],
        p1=["Cuando {event}, {prot} de {place} debe decidir qué merece la pena conservar.",
            "Durante años, {prot} ha evitado {place}; entonces {event} y todo vuelve.",
            "Todo empieza en {place}: {event}, y {prot} es la única persona que recuerda por qué."],
        p2=["Una novela serena sobre {theme}.",
            "Contada a lo largo de un solo invierno, sigue a {prot} y a quienes se niegan a marcharse.",
            "En {n} capítulos breves que van del pasado al presente, se pregunta por {theme}."]),
}

HEADING = {"zh": "内容简介", "ja": "内容紹介", "ko": "책 소개", "en": "About this book", "es": "Sinopsis"}
OFFICE = {"zh": "北京办公室", "ko": "서울지사", "ja": "東京オフィス", "en": "london", "es": "madrid"}


def _batchim(word: str) -> bool:
    ch = word[-1]
    return "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 != 0


def _josa(word: str, with_final: str, without: str) -> str:
    return with_final if _batchim(word) else without


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def _title_key(t: str) -> str:
    """Two titles this close would be the same book to a reader: kept unique within a corpus."""
    return re.sub(r"[\W_]+", "", nfkc(t.split(" — ")[0]).casefold())


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


# ── the world ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Person:
    lang: str
    orig: str                 # canonical name in the book language's script
    latin: str                # canonical Latin form (= orig for en/es)
    variants: tuple           # other spellings found in the wild


@dataclass
class Book:
    bid: str
    lang: str
    kind: str
    scope: str
    title: str                # canonical (NFKC-stable)
    title_src: str            # as the sources print it (full-width, decomposed, ...)
    title_latin: str
    authors: list
    first: int | None
    edition: int | None       # None: a single year
    desc: list
    isbn: str
    review: str | None = None
    files: list = field(default_factory=list)    # source references (path, path!member, path#row)
    own: set = field(default_factory=set)        # real corpus files that belong to this book only

    @property
    def edition_year(self) -> int | None:
        return self.edition if self.edition is not None else self.first


@dataclass
class Corpus:
    books: list
    files: dict               # relative path -> bytes


@dataclass
class World:
    visible: Corpus
    hidden: Corpus
    _cache: dict = field(default_factory=dict)


@dataclass
class Src:
    fmt: str
    meta: dict                # see _meta
    name: str
    folder: str
    enc: str = "utf-8"
    text_meta: dict | None = None     # title-page text when it differs from the embedded metadata


KINDS = (
    [("easy", lang) for lang in ("zh", "en", "ko", "ja", "es") for _ in range(6)]
    + [("m_encoding", lang) for lang in ("zh", "ko", "ja", "es", "en", "ko", "ja")]
    + [("m_era", lang) for lang in ("ja", "zh", "ko", "en", "es", "zh")]
    + [("m_width", lang) for lang in ("en", "en", "es", "es")]
    + [("m_forbidden", lang) for lang in ("en", "es", "zh", "ja", "ko")]
    + [("m_variant", lang) for lang in ("zh", "ko", "ja", "ko", "en")]
    + [("m_dup", lang) for lang in ("zh", "ko", "ja", "en", "es", "ja")]
    + [("m_precedence", lang) for lang in ("en", "ko", "zh")]
    + [("h_author_recover", None)] * 3 + [("h_no_author", None)] * 2 + [("h_title_filename", "en"),
                                                                         ("h_title_filename", "es")]
    + [("h_no_title", None)] * 2 + [("h_desc_recover", None)] * 2 + [("h_no_desc", None)] * 2
    + [("h_year_copyright", None)] * 3 + [("h_no_year", None)] * 2 + [("h_conflict", None)] * 2
    + [("h_scan_only", None)] * 2 + [("h_scan_plus", None)] * 2 + [("h_zip", None)] * 4 + [("h_csv", None)] * 6
)
assert len(KINDS) == N_BOOKS
REVIEW_OF = {"h_no_author": "NO_AUTHOR", "h_no_title": "NO_TITLE", "h_no_desc": "NO_DESCRIPTION",
             "h_no_year": "NO_YEAR", "h_conflict": "CONFLICT", "h_scan_only": "UNREADABLE"}
ERA_STYLE = {"ja": "japanese_era", "ko": "dangi", "en": "roman", "es": "roman"}


def _title(rng: random.Random, lang: str) -> tuple[str, str]:
    if lang == "zh":
        if rng.random() < 0.7:
            (a, al), (n, nl) = rng.choice(ZH_ADJ), rng.choice(ZH_NOUN)
            return a + n, f"{al} {nl}"
        (a, al), (n, nl) = rng.sample(ZH_NOUN, 2)
        return f"{a}与{n}", f"{al} yu {nl}"
    if lang == "ko":
        if rng.random() < 0.7:
            (a, al), (n, nl) = rng.choice(KO_ADJ), rng.choice(KO_NOUN)
            return f"{a} {n}", f"{al} {nl}"
        (a, al), (n, nl) = rng.sample(KO_NOUN, 2)
        return f"{a}의 {n}", f"{al}-ui {nl}"
    if lang == "ja":
        if rng.random() < 0.7:
            (a, al), (n, nl) = rng.sample(JA_NOUN, 2)
            return f"{a}の{n}", f"{al} no {nl}"
        (a, al), (n, nl) = rng.choice(JA_ADJ), rng.choice(JA_NOUN)
        return a + n, f"{al} {nl}"
    if lang == "en":
        p = rng.random()
        if p < 0.55:
            t = f"The {rng.choice(EN_ADJ)} {rng.choice(EN_NOUN)}"
        elif p < 0.7:
            t = f"Letters from {rng.choice(EN_PLACE)}"
        elif p < 0.85:
            t = f"A Map of {rng.choice(EN_PLACE)}"
        else:
            t = f"The {rng.choice(EN_NOUN)} at {rng.choice(EN_PLACE)}"
        if rng.random() < 0.3:
            t += " — " + rng.choice(EN_SUB)
        return t, t
    p = rng.random()
    if p < 0.4:
        adj = rng.choice(ES_ADJ)
        t = f"La {rng.choice(ES_NF)} {adj[0]}"
    elif p < 0.7:
        adj = rng.choice(ES_ADJ)
        t = f"El {rng.choice(ES_NM)} {adj[1]}"
    elif p < 0.85:
        t = f"Cartas desde {rng.choice(ES_PLACE)}"
    else:
        t = f"El {rng.choice(ES_NM)} de {rng.choice(ES_PLACE)}"
    if rng.random() < 0.3:
        t += " — " + rng.choice(ES_SUB)
    return t, t


def _description(rng: random.Random, lang: str) -> list[str]:
    v = DESC[lang]
    slots = {k: rng.choice(v[k]) for k in ("prot", "place", "event", "theme", "n")}
    if lang == "ko":
        slots.update(eun=_josa(slots["prot"], "은", "는"), eul=_josa(slots["place"], "을", "를"),
                     wa=_josa(slots["prot"], "과", "와"), eul2=_josa(slots["theme"], "을", "를"))
    p1 = rng.choice(v["p1"]).format(**slots)
    p2 = rng.choice(v["p2"]).format(**slots)
    return [_cap(p1), _cap(p2)]


def _persons(rng: random.Random, lang: str, n: int) -> list[Person]:
    out, seen = [], set()
    while len(out) < n:
        s, g = rng.choice(SURNAMES[lang]), rng.choice(GIVEN[lang])
        if (str(s), str(g)) in seen:
            continue
        seen.add((str(s), str(g)))
        if lang in CJK:
            (so, sl), (go, gl, galt) = s, g
            canon = f"{sl} {gl}"
            variants = [f"{gl} {sl}", f"{sl.upper()} {galt}"]
            if galt != gl:
                variants.append(f"{sl} {galt}")
            out.append(Person(lang, so + go, canon, tuple(dict.fromkeys(v for v in variants if v != canon))))
        else:
            name = f"{g} {s}"
            out.append(Person(lang, name, name, (f"{s}, {g}",)))
    return out


def _isbn(rng: random.Random) -> str:
    digits = [9, 7, 9] + [rng.randrange(10) for _ in range(9)]
    check = (10 - sum(d * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits)) % 10) % 10
    return "".join(map(str, digits + [check]))


def build_corpus(seed: int) -> Corpus:
    rng = random.Random(seed)
    persons = {lang: _persons(rng, lang, 10) for lang in ("zh", "en", "ko", "ja", "es")}
    kinds = list(KINDS)
    books: list[Book] = []
    titles: set = set()
    descs: set = set()
    used_by_easy: dict = {lang: [] for lang in persons}
    for i, (kind, lang) in enumerate(kinds):
        lang = lang or rng.choice(("zh", "en", "ko", "ja", "es"))
        while True:
            title, latin = _title(rng, lang)
            if kind == "m_forbidden":
                title, latin = {
                    "en": (title.split(" — ")[0] + ": A Novel",) * 2,
                    "es": ("¿" + title.split(" — ")[0] + "?",) * 2,
                    "zh": (title + "？", latin + "?"), "ja": (title + "？", latin + "?"), "ko": (title + "?", latin + "?"),
                }[lang]
            elif kind in ("h_scan_plus", "h_title_filename", "h_conflict") and lang in ("en", "es"):
                title = latin = title.split(" — ")[0]
            keys = {_title_key(title), _title_key(latin)}
            if not keys & titles:
                titles.update(keys)
                break
        while True:
            desc = _description(rng, lang)
            if "".join(desc) not in descs:
                descs.add("".join(desc))
                break
        canon = nfkc(title)
        src_title = title
        if kind == "m_width" and lang == "en":
            src_title = "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else ("\u3000" if c == " " else c) for c in canon)
        elif kind == "m_width" and lang == "es":
            src_title = unicodedata.normalize("NFD", canon)
        first = rng.randrange(1962, 2024)
        edition = None
        if rng.random() < 0.4 and first <= 2020:
            edition = min(2025, first + rng.randrange(2, 16))
        if kind == "m_era" and lang == "ja":
            first, edition = rng.randrange(1975, 2012), rng.randrange(2019, 2025)
        if kind == "m_encoding" and lang == "en":
            edition = min(2025, first + 5)          # the "·" of the edition line is a CP1252 byte
        if kind in ("h_year_copyright", "h_no_year", "h_conflict"):
            edition = None
        pool = persons[lang]
        if kind == "m_variant" and used_by_easy[lang]:
            authors = [rng.choice(used_by_easy[lang])]
        elif kind == "h_no_author":
            authors = []
        else:
            authors = [rng.choice(pool)]
            if rng.random() < 0.18 and kind not in ("m_variant",):
                other = rng.choice([p for p in pool if p != authors[0]])
                authors.append(other)
        if kind == "easy" and lang in CJK:
            used_by_easy[lang].extend(authors)
        scope = "easy" if kind == "easy" else "medium" if kind.startswith("m_") else "hard"
        books.append(Book(bid=f"B{i + 1:03d}", lang=lang, kind=kind, scope=scope, title=canon, title_src=src_title,
                          title_latin=nfkc(latin), authors=authors, first=first, edition=edition, desc=desc,
                          isbn=_isbn(rng), review=REVIEW_OF.get(kind)))
    for b in books:
        if b.kind == "h_no_desc":
            b.desc = []
        if b.kind == "h_no_year":
            b.first = None
    files = _render_corpus(books, rng)
    return Corpus(books, files)


def build_world(seed: int) -> World:
    """The visible corpus (the agent's sample) and the hidden one the program is scored on: same recipe."""
    return World(visible=build_corpus(seed), hidden=build_corpus(seed + 7919))


# ── rendering the corpus ─────────────────────────────────────────────────────

def _roman(n: int) -> str:
    out = ""
    for v, s in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
                 (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out, n = out + s, n - v
    return out


def year_text(y: int, style: str, lang: str) -> str:
    if style == "digits":
        return str(y)
    if style == "default":
        return f"{y}年" if lang in ("zh", "ja") else f"{y}년" if lang == "ko" else str(y)
    if style == "japanese_era":
        era, n = ("令和", y - 2018) if y >= 2019 else ("平成", y - 1988) if y >= 1989 else ("昭和", y - 1925)
        return f"{era}{'元' if n == 1 else n}年"
    if style == "minguo":
        return f"民國{y - 1911}年"
    if style == "dangi":
        return f"단기 {y + 2333}년"
    if style == "roman":
        return _roman(y)
    if style == "hanzi":
        return "".join("〇一二三四五六七八九"[int(d)] for d in str(y)) + "年"
    raise ValueError(style)


def years_line(m: dict, lang: str) -> str | None:
    if m.get("first") is None:
        return None
    style = m.get("ystyle", "default")
    f = year_text(m["first"], style, lang)
    e = year_text(m["edition"], style, lang) if m.get("edition") is not None else None
    if lang == "zh":
        return f"初版 {f}" + (f" · 本版 {e}" if e else "")
    if lang == "ja":
        return f"初版 {f}" + (f" / 新版 {e}" if e else "")
    if lang == "ko":
        return f"초판 {f}" + (f" / 개정판 {e}" if e else "")
    if lang == "en":
        return f"First published {f}" + (f" · This edition {e}" if e else "")
    return f"Primera edición: {f}" + (f" · Esta edición: {e}" if e else "")


def author_line(authors: list, lang: str) -> str | None:
    if not authors:
        return None
    if lang in ("zh", "ja"):
        names = [f"{o}（{la}）" if o and la else (o or la) for o, la in authors]
        return "、".join(names) + " 著"
    if lang == "ko":
        names = [f"{o}({la})" if o and la else (o or la) for o, la in authors]
        return ", ".join(names) + " 지음"
    names = [o or la for o, la in authors]
    return ("by " + " and ".join(names)) if lang == "en" else ("por " + " y ".join(names))


def title_page(m: dict, lang: str) -> list[str]:
    """The lines of a book's title page and description, as text files, PDFs, DOCX bodies show them."""
    lines = []
    if m.get("title"):
        lines.append(m["title"])
        if m.get("title_latin") and lang in CJK:
            lines.append(f"({m['title_latin']})")
    for extra in (author_line(m.get("authors") or [], lang), years_line(m, lang)):
        if extra:
            lines.append(extra)
    if m.get("copyright"):
        names = m.get("authors") or []
        who = (names[0][0] or names[0][1]) if names else ""
        lines.append(f"© {m['copyright']} {who}".rstrip())
    lines += ["", HEADING[lang], ""]
    for k, p in enumerate(m.get("desc") or []):
        if k:
            lines.append("")
        lines.append(p)
    return lines


def _wrap(p: str, lang: str, width: int) -> list[str]:
    if lang in CJK:
        return [p[i:i + width // 2] for i in range(0, len(p), width // 2)] or [""]
    out, cur = [], ""
    for w in p.split(" "):
        if cur and len(cur) + 1 + len(w) > width:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    return out + [cur]


def _meta(b: Book, **over) -> dict:
    m = {"title": b.title_src, "title_latin": b.title_latin if b.lang in CJK else None,
         "authors": [(p.orig, p.latin) if b.lang in CJK else (p.orig, None) for p in b.authors],
         "first": b.first, "edition": b.edition, "desc": list(b.desc), "isbn": b.isbn, "ystyle": "default",
         "copyright": None}
    m.update(over)
    return m


def _json_year(m: dict, key: str):
    y = m.get(key)
    if y is None:
        return None
    return y if m.get("ystyle", "default") in ("default", "digits") else year_text(y, m["ystyle"], m["lang"])


def render_json(m: dict) -> bytes:
    doc = {"title": m.get("title"), "title_latin": m.get("title_latin")}
    doc["authors"] = [{"name": o, "name_latin": la} if la else {"name": o} for o, la in m.get("authors") or []]
    doc["first_published"] = _json_year(m, "first")
    if m.get("edition") is not None:
        doc["edition_year"] = _json_year(m, "edition")
    doc["description"] = "\n\n".join(m.get("desc") or [])
    doc["isbn"] = m.get("isbn")
    doc = {k: v for k, v in doc.items() if v is not None}
    return json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8")


def _x(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_onix(m: dict) -> bytes:
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<ONIXMessage xmlns="http://ns.editeur.org/onix/3.0/reference" release="3.0">',
           "  <Header><Sender><SenderName>Rights desk export</SenderName></Sender></Header>",
           "  <Product>", f"    <RecordReference>rec-{m['isbn'][-6:]}</RecordReference>",
           f"    <ProductIdentifier><ProductIDType>15</ProductIDType><IDValue>{m['isbn']}</IDValue></ProductIdentifier>",
           "    <DescriptiveDetail>"]
    if m.get("title"):
        out.append("      <TitleDetail><TitleType>01</TitleType><TitleElement><TitleElementLevel>01</TitleElementLevel>"
                   f"<TitleText>{_x(m['title'])}</TitleText></TitleElement></TitleDetail>")
    if m.get("title_latin"):
        out.append("      <TitleDetail><TitleType>01</TitleType><TitleElement><TitleElementLevel>01</TitleElementLevel>"
                   f'<TitleText textscript="Latn">{_x(m["title_latin"])}</TitleText></TitleElement></TitleDetail>')
    for k, (o, la) in enumerate(m.get("authors") or []):
        out.append(f"      <Contributor><SequenceNumber>{k + 1}</SequenceNumber><ContributorRole>A01</ContributorRole>"
                   f"<PersonName>{_x(o)}</PersonName>")
        if la:
            out.append(f'        <AlternativeName><NameType>01</NameType><PersonName textscript="Latn">{_x(la)}'
                       "</PersonName></AlternativeName>")
        elif " " in o and "," not in o:
            given, _, family = o.rpartition(" ")
            out.append(f"        <PersonNameInverted>{_x(family)}, {_x(given)}</PersonNameInverted>")
        out.append("      </Contributor>")
    out.append("    </DescriptiveDetail>")
    out.append("    <CollateralDetail><TextContent><TextType>03</TextType><ContentAudience>00</ContentAudience>"
               '<Text textformat="06">' + _x("\n\n".join(m.get("desc") or [])) + "</Text></TextContent></CollateralDetail>")
    out.append("    <PublishingDetail><PublishingStatus>04</PublishingStatus>")
    if m.get("edition") is not None:
        out.append(f"      <PublishingDate><PublishingDateRole>01</PublishingDateRole><Date dateformat=\"05\">"
                   f"{m['edition']}</Date></PublishingDate>")
    if m.get("first") is not None:
        role = "11" if m.get("edition") is not None else "01"
        out.append(f"      <PublishingDate><PublishingDateRole>{role}</PublishingDateRole><Date dateformat=\"05\">"
                   f"{m['first']}</Date></PublishingDate>")
    out += ["    </PublishingDetail>", "  </Product>", "</ONIXMessage>", ""]
    return "\n".join(out).encode("utf-8")


ZIP_TIME = (2024, 3, 1, 9, 0, 0)


def _zip(entries: list[tuple[str, bytes]], stored_first: bool = False) -> bytes:
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as z:
        for k, (name, body) in enumerate(entries):
            info = zipfile.ZipInfo(name, date_time=ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED if (stored_first and k == 0) else zipfile.ZIP_DEFLATED
            z.writestr(info, body)
    return raw.getvalue()


def render_epub(m: dict, lang: str) -> bytes:
    md = [f'    <dc:identifier id="uid">urn:isbn:{m["isbn"]}</dc:identifier>', f"    <dc:language>{lang}</dc:language>"]
    if m.get("title"):
        md.append(f'    <dc:title id="t1">{_x(m["title"])}</dc:title>')
        if m.get("title_latin"):
            md.append(f'    <meta refines="#t1" property="alternate-script" xml:lang="{lang}-Latn">'
                      f'{_x(m["title_latin"])}</meta>')
    for k, (o, la) in enumerate(m.get("authors") or []):
        md.append(f'    <dc:creator id="c{k + 1}">{_x(o)}</dc:creator>')
        md.append(f'    <meta refines="#c{k + 1}" property="role" scheme="marc:relators">aut</meta>')
        if la:
            md.append(f'    <meta refines="#c{k + 1}" property="alternate-script" xml:lang="{lang}-Latn">{_x(la)}</meta>')
        elif " " in o and "," not in o:
            given, _, family = o.rpartition(" ")
            md.append(f'    <meta refines="#c{k + 1}" property="file-as">{_x(family)}, {_x(given)}</meta>')
    if m.get("first") is not None:
        md.append(f"    <dc:date>{m['edition'] if m.get('edition') is not None else m['first']}</dc:date>")
        if m.get("edition") is not None:
            md.append(f'    <meta property="first-published">{m["first"]}</meta>')
    md.append("    <dc:description>" + _x("\n\n".join(m.get("desc") or [])) + "</dc:description>")
    md.append('    <meta property="dcterms:modified">2024-03-01T09:00:00Z</meta>')
    opf = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">\n'
           '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n' + "\n".join(md) + "\n  </metadata>\n"
           '  <manifest><item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/></manifest>\n'
           '  <spine><itemref idref="cover"/></spine>\n</package>\n')
    cover = ('<?xml version="1.0" encoding="UTF-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml"><head><title>cover'
             '</title></head><body><p>*</p></body></html>\n')
    container = ('<?xml version="1.0"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                 "</rootfiles></container>\n")
    return _zip([("mimetype", b"application/epub+zip"), ("META-INF/container.xml", container.encode()),
                 ("OEBPS/content.opf", opf.encode("utf-8")), ("OEBPS/cover.xhtml", cover.encode())], stored_first=True)


def _names_joined(m: dict) -> str:
    return "; ".join(o or la for o, la in m.get("authors") or [])


def render_docx(m: dict, text: dict, lang: str, rng: random.Random) -> bytes:
    paras = []
    for line in title_page(text, lang):
        if not line:
            paras.append("<w:p/>")
            continue
        cut = sorted({rng.randrange(1, len(line)) for _ in range(2)}) if len(line) > 8 else []
        pieces, last = [], 0
        for c in cut + [len(line)]:
            pieces.append(line[last:c])
            last = c
        runs = "".join(f'<w:r><w:t xml:space="preserve">{_x(p)}</w:t></w:r>' for p in pieces if p)
        paras.append(f"<w:p>{runs}</w:p>")
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + "".join(paras) + "</w:body></w:document>")
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>{_x(m.get('title') or '')}</dc:title><dc:creator>{_x(_names_joined(m))}</dc:creator>"
            "<cp:lastModifiedBy>rights-desk</cp:lastModifiedBy>"
            '<dcterms:created xsi:type="dcterms:W3CDTF">2023-05-17T10:22:00Z</dcterms:created>'
            '<dcterms:modified xsi:type="dcterms:W3CDTF">2024-02-02T08:15:00Z</dcterms:modified>'
            "</cp:coreProperties>")
    types = ('<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
             'content-types"><Default Extension="xml" ContentType="application/xml"/><Default Extension="rels" '
             'ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/'
             'document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main'
             '+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.'
             'core-properties+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/'
            '2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.'
            'openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            "</Relationships>")
    return _zip([("[Content_Types].xml", types.encode()), ("_rels/.rels", rels.encode()),
                 ("word/document.xml", doc.encode("utf-8")), ("docProps/core.xml", core.encode("utf-8"))])


def _pdf_str(s: str) -> str:
    return "<FEFF" + s.encode("utf-16-be").hex().upper() + ">"


def _pdf(objects: list[bytes], info: dict) -> bytes:
    """objects[0] is the catalog; an Info dictionary is appended as the last object."""
    info_obj = ("<< " + " ".join(f"/{k} {v}" for k, v in info.items()) + " >>").encode()
    objs = objects + [info_obj]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for k, body in enumerate(objs):
        offsets.append(out.tell())
        out.write(f"{k + 1} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info {len(objs)} 0 R >>\nstartxref\n{xref}\n%%EOF\n"
              .encode())
    return out.getvalue()


def _stream(body: bytes, extra: str = "") -> bytes:
    return f"<< /Length {len(body)}{extra} >>\nstream\n".encode() + body + b"\nendstream"


def render_pdf(m: dict, text: dict, lang: str) -> bytes:
    lines = []
    for line in title_page(text, lang):
        lines += _wrap(line, lang, 70) if line else [""]
    ops = ["BT", "/F1 11 Tf", "14 TL", "72 770 Td"]
    for line in lines:
        ops.append(f"{_pdf_str(line) if line else '()'} Tj T*")
    ops.append("ET")
    content = "\n".join(ops).encode("ascii")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> "
               b"/Contents 4 0 R >>",
               _stream(content),
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    info = {"Producer": "(Typeset 4.2)", "CreationDate": "(D:20230517102200Z)"}
    if m.get("title"):
        info["Title"] = _pdf_str(m["title"])
    if m.get("authors"):
        info["Author"] = _pdf_str(_names_joined(m))
    return _pdf(objects, info)


def render_scan(rng: random.Random) -> bytes:
    img = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + bytes(rng.randrange(256) for _ in range(1500)) + b"\xff\xd9"
    content = b"q 595 0 0 842 0 0 cm /Im1 Do Q"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /XObject << /Im1 5 0 R >> >> "
               b"/Contents 4 0 R >>",
               _stream(content),
               _stream(img, " /Type /XObject /Subtype /Image /Width 1240 /Height 1754 /ColorSpace /DeviceGray "
                            "/BitsPerComponent 8 /Filter /DCTDecode")]
    return _pdf(objects, {"Producer": "(ScanStation 2000)", "CreationDate": "(D:20220304111500Z)"})


def render_html(m: dict, text: dict, lang: str, enc: str) -> bytes:
    def h(s: str) -> str:
        s = _x(s).replace("—", "&mdash;")
        return s
    head = [f'<meta charset="{enc}">']
    if m.get("title"):
        head.append(f"<title>{h(m['title'])}</title>")
    if m.get("authors"):
        head.append(f'<meta name="author" content="{h(_names_joined(m))}">')
    body = []
    lines = title_page(text, lang)
    split = lines.index(HEADING[lang])
    top, desc = lines[:split], text.get("desc") or []
    classes = []
    if text.get("title"):
        classes.append(("h1", None))
        if text.get("title_latin") and lang in CJK:
            classes.append(("p", "latin"))
    if author_line(text.get("authors") or [], lang):
        classes.append(("p", "byline"))
    if years_line(text, lang):
        classes.append(("p", "edition"))
    if text.get("copyright"):
        classes.append(("p", "rights"))
    for (tag, cls), line in zip(classes, [x for x in top if x]):
        body.append(f"<{tag}{f' class={chr(34)}{cls}{chr(34)}' if cls else ''}>{h(line)}</{tag}>")
    body.append(f"<h2>{h(HEADING[lang])}</h2>")
    body.append('<div class="description">' + "".join(f"<p>{h(p)}</p>" for p in desc) + "</div>")
    doc = (f'<!DOCTYPE html>\n<html lang="{lang}">\n<head>\n' + "\n".join(head) + "\n</head>\n<body>\n"
           + "\n".join(body) + "\n</body>\n</html>\n")
    return doc.encode(enc)


def render_md(m: dict, text: dict, lang: str) -> str:
    fm = ["---"]
    if m.get("title"):
        fm.append(f"title: {m['title']}")
    if m.get("title_latin"):
        fm.append(f"title_latin: {m['title_latin']}")
    if m.get("authors"):
        fm.append(f"author: {_names_joined(m)}")
        if any(la for _, la in m["authors"]):
            fm.append("author_latin: " + "; ".join(la or o for o, la in m["authors"]))
    if m.get("first") is not None:
        style = m.get("ystyle", "default")
        fm.append(f"first_published: {m['first'] if style == 'default' else year_text(m['first'], style, lang)}")
        if m.get("edition") is not None:
            fm.append(f"edition: {m['edition'] if style == 'default' else year_text(m['edition'], style, lang)}")
    fm.append("---")
    lines = title_page(text, lang)
    top = [x for x in lines[:lines.index(HEADING[lang])] if x]
    body = []
    for k, line in enumerate(top):
        if k == 0 and text.get("title"):
            body.append(f"# {line}")
        elif k == 1 and text.get("title") and line.startswith("("):
            body.append(f"*{line[1:-1]}*")
        else:
            body.append(line)
    body.append(f"## {HEADING[lang]}")
    body += text.get("desc") or []
    return "\n".join(fm) + "\n\n" + "\n\n".join(body) + "\n"


def render_txt(text: dict, lang: str, wrap: bool) -> str:
    out = []
    for line in title_page(text, lang):
        out += _wrap(line, lang, 72) if (wrap and line and line in (text.get("desc") or [])) else [line]
    return "\n".join(out) + "\n"


CATALOG_HEADERS = {
    "en": ["isbn", "title", "title_latin", "authors", "authors_latin", "first_published", "edition_year", "description"],
    "ja": ["ISBN", "書名", "書名ローマ字", "著者", "著者ローマ字", "初版年", "版年", "内容紹介"],
}


def _safe_name(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|？]', "", s)
    return s.strip(" .") or "untitled"


NAME_BYTES = 255      # a file system's limit on one file name


def _fit(folder: str, stem: str, tail: str) -> str:
    """stem + tail, the stem cut so that the name, and its flattened copy "<folder>__<name>" in _review/, fit in
    NAME_BYTES (a long full-width title is a real name on a drive, but no longer than the drive allows)."""
    budget = NAME_BYTES - len(f"{folder}__".encode())
    if len((stem + tail).encode()) <= budget:
        return stem + tail
    while stem and len((stem + tail).encode()) > budget:
        stem = stem[:-1]
    return re.sub(r"[\s._]+$", "", stem) + tail          # no cut name ends in a space (also U+3000) or a dot


class _Names:
    def __init__(self):
        self.used: set = set()

    def take(self, folder: str, name: str) -> str:
        stem, dot, ext = name.rpartition(".")
        cand, k = _fit(folder, stem, f"{dot}{ext}"), 2
        while f"{folder}/{cand}".casefold() in self.used:
            cand = _fit(folder, stem, f" ({k}){dot}{ext}")
            k += 1
        self.used.add(f"{folder}/{cand}".casefold())
        return f"{folder}/{cand}"


def _file_name(b: Book, ext: str, rng: random.Random, n: int) -> str:
    p = rng.random()
    if p < 0.35:
        return f"{_safe_name(b.title_src)}.{ext}"
    if p < 0.55:
        return f"{b.isbn}.{ext}"
    if p < 0.75 and b.lang in CJK:
        return f"{_safe_name(b.title_latin).replace(' ', '_')}.{ext}"
    if p < 0.85:
        return f"{_safe_name(b.title_src).replace(' ', '_')}.{ext}"
    return f"book_{n:04d}.{ext}"


EMBEDDED_FORMATS = ("json", "onix", "epub")
SINGLE_FORMATS = ("json", "onix", "epub", "docx", "pdf", "html", "md", "txt")
LEGACY = {"zh": "gb18030", "ko": "cp949", "ja": "shift_jis", "es": "cp1252", "en": "cp1252"}


def _sources(b: Book, rng: random.Random, counter: list) -> list[Src]:
    """The book's files, chosen by its kind. Every value the ground truth needs is derivable from them."""
    lang, k = b.lang, b.kind

    def folder() -> str:
        p = rng.random()
        return OFFICE[lang] if p < 0.55 else "inbox" if p < 0.85 else "misc"

    def src(fmt: str, meta: dict, name: str | None = None, fold: str | None = None, **kw) -> Src:
        counter[0] += 1
        ext = {"onix": "xml"}.get(fmt, fmt)
        return Src(fmt, meta, name or _file_name(b, ext, rng, counter[0]), fold or folder(), **kw)

    m = _meta(b)
    if k == "easy":
        return [src(rng.choice(SINGLE_FORMATS), m)]
    if k == "m_encoding":
        fmt = rng.choice(("txt", "txt", "md", "html")) if lang in ("ko", "ja") else "txt"
        return [src(fmt, m, enc=LEGACY[lang])]
    if k == "m_era":
        style = {"zh": "minguo" if rng.random() < 0.5 else "hanzi"}.get(lang, ERA_STYLE.get(lang))
        return [src(rng.choice(("txt", "json", "md")), _meta(b, ystyle=style))]
    if k in ("m_width", "m_forbidden"):
        return [src(rng.choice(SINGLE_FORMATS), m)]
    if k == "m_variant":
        p = b.authors[0]
        form = p.variants[rng.randrange(len(p.variants))]
        mv = _meta(b, authors=[(form, None)])
        return [src(rng.choice(("docx", "pdf", "txt", "html")), mv)]
    if k == "m_dup":
        combo = rng.choice([("epub", "pdf"), ("json", "txt"), ("onix", "docx", "html"), ("md", "pdf"),
                            ("epub", "txt", "json")])
        out = []
        for fmt in combo:
            mm = m
            if fmt == "txt" and lang in CJK:
                p = b.authors[0]
                mm = _meta(b, authors=[(None, p.variants[0])] + [(q.orig, q.latin) for q in b.authors[1:]])
            out.append(src(fmt, mm))
        return out
    if k == "m_precedence":
        wrong = dict(m)
        if m["edition"] is not None:
            wrong["edition"] = m["edition"] + 1
        else:
            wrong["first"] = m["first"] - 1
        hi, lo = rng.choice([("json", "txt"), ("epub", "docx"), ("onix", "pdf")])
        return [src(hi, m), src(lo, wrong)]
    if k == "h_author_recover":
        hi, lo = rng.choice([("json", "txt"), ("epub", "pdf"), ("onix", "txt")])
        return [src(hi, _meta(b, authors=[])), src(lo, m)]
    if k == "h_no_author":
        return [src(rng.choice(("json", "txt", "docx")), m)]
    if k == "h_title_filename":
        return [src("txt", _meta(b, title=None), name=b.title.replace(" ", "_") + ".txt")]
    if k == "h_no_title":
        counter[0] += 1
        fmt = rng.choice(("txt", "docx"))
        return [src(fmt, _meta(b, title=None, title_latin=None), name=f"doc_{counter[0]:04d}.{fmt}")]
    if k == "h_desc_recover":
        return [src("json", _meta(b, desc=[])), src("txt", m)]
    if k == "h_no_desc":
        return [src(rng.choice(("json", "txt", "epub")), m)]
    if k == "h_year_copyright":
        return [src(rng.choice(("txt", "docx")), _meta(b, first=None, edition=None, copyright=b.first))]
    if k == "h_no_year":
        return [src(rng.choice(("txt", "docx", "json")), m)]
    if k == "h_conflict":
        other = b.first + rng.choice((-3, -2, 2, 3))
        return [src("json", m), src("onix", _meta(b, first=other))]
    if k == "h_scan_only":
        counter[0] += 1
        return [src("scan", {}, name=f"scan_{counter[0]:04d}.pdf", fold="scans")]
    if k == "h_scan_plus":
        return [src("scan", {}, name=f"{_safe_name(b.title_src)} (scan).pdf", fold="scans"),
                src(rng.choice(("json", "epub")), m)]
    if k == "h_zip":
        return [src(rng.choice(("json", "txt", "md")), m, fold="zip")]
    if k == "h_csv":
        return [src("csvrow", m, fold="csv")]
    raise ValueError(k)


def _render_file(s: Src, lang: str, rng: random.Random) -> bytes:
    m = dict(s.meta, lang=lang)
    text = dict(s.text_meta or m, lang=lang)
    if s.fmt == "json":
        return render_json(m)
    if s.fmt == "onix":
        return render_onix(m)
    if s.fmt == "epub":
        return render_epub(m, lang)
    if s.fmt == "docx":
        return render_docx(m, text, lang, rng)
    if s.fmt == "pdf":
        return render_pdf(m, text, lang)
    if s.fmt == "scan":
        return render_scan(rng)
    if s.fmt == "html":
        return render_html(m, text, lang, s.enc)
    if s.fmt == "md":
        return render_md(m, text, lang).encode(s.enc)
    if s.fmt == "txt":
        body = render_txt(text, lang, wrap=rng.random() < 0.5)
        if s.enc == "utf-8" and rng.random() < 0.2:
            body = body.replace("\n", "\r\n")
        return body.encode(s.enc)
    raise ValueError(s.fmt)


JUNK = [(".DS_Store", b"\x00\x00\x00\x01Bud1" + bytes(range(64)) * 4),
        ("Thumbs.db", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(200)),
        ("desktop.ini", b"[.ShellClassInfo]\r\nIconResource=C:\\Windows\\system32\\imageres.dll,-3\r\n")]


def _render_corpus(books: list[Book], rng: random.Random) -> dict:
    files: dict = {}
    names = _Names()
    counter = [0]
    zips: dict = {"archives/old_drive_backup.zip": [], "archives/handover_2021.zip": []}
    catalogs: dict = {"catalogs/rights_catalog_export.csv": ("en", []), "catalogs/東京_目録.csv": ("ja", [])}
    for b in books:
        for s in _sources(b, rng, counter):
            if s.fmt == "csvrow":
                cat = sorted(catalogs, key=lambda c: (len(catalogs[c][1]), c))[0]
                catalogs[cat][1].append((b, s.meta))
                b.files.append(f"{cat}#{len(catalogs[cat][1])}")
                continue
            if s.folder == "zip":
                z = sorted(zips, key=lambda c: (len(zips[c]), c))[0]
                inner = "backup" if "old" in z else "handover"
                stem, dot, ext = s.name.rpartition(".")
                member = f"{inner}/{_fit(inner, stem, dot + ext)}"
                zips[z].append((member, _render_file(s, b.lang, rng)))
                b.files.append(f"{z}!{member}")
                continue
            path = names.take(s.folder, s.name)
            files[path] = _render_file(s, b.lang, rng)
            b.files.append(path)
            b.own.add(path)
    for z, members in zips.items():
        members = list(members)
        members.insert(1, ("__MACOSX/._" + members[0][0].split("/")[-1], b"\x00\x05\x16\x07" + bytes(60)))
        files[z] = _zip(members)
    for cat, (hlang, rows) in catalogs.items():
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\r\n")
        w.writerow(CATALOG_HEADERS[hlang])
        for b, m in rows:
            w.writerow([m["isbn"], m["title"], m["title_latin"] or "", "; ".join(o for o, _ in m["authors"]),
                        "; ".join(la or o for o, la in m["authors"]), m["first"],
                        m["edition"] if m["edition"] is not None else "", "\n\n".join(m["desc"])])
        files[cat] = buf.getvalue().encode("utf-8-sig")
    # junk: system files, an editor lock file and empty files
    for folder in ("inbox", OFFICE["ja"], "misc"):
        name, body = JUNK[len(files) % len(JUNK)] if folder != "inbox" else JUNK[0]
        files[names.take(folder, name)] = body
    files[names.take(OFFICE["en"], "~$draft notes.docx")] = b"\x0bR\x00i\x00g\x00h\x00t\x00s" + bytes(150)
    files[names.take("inbox", "untitled.txt")] = b""
    files[names.take(OFFICE["zh"], "新建文本文档.txt")] = b""
    return dict(sorted(files.items()))


# ── data for the agent ───────────────────────────────────────────────────────

NOTES_FILE = {"zh": "整理说明.txt", "en": "archivist_notes.txt", "ko": "정리_메모.txt", "ja": "整理メモ.txt",
              "es": "notas_del_archivo.txt"}
NOTES = {
    "zh": "corpus/ 是我们共享盘的一个样本，原样拷贝，没有整理过。\n"
          "各地办公室、扫描组和版权组都往里面放过东西；也有一些旧的打包文件和目录导出。\n"
          "正式运行时，程序会拿到完整的共享盘，结构和这个样本一样。\n",
    "en": "corpus/ is a sample of our shared drive, copied as it is, nothing tidied.\n"
          "The regional offices, the scanning team and the rights desk have all put things there; there are also\n"
          "some old archives and catalog exports.\n"
          "For the real run the program gets the full drive, laid out like this sample.\n",
    "ko": "corpus/ 는 공유 드라이브의 샘플을 정리하지 않고 그대로 복사한 것입니다.\n"
          "각 지역 사무소, 스캔팀, 판권팀이 모두 파일을 넣어 왔고, 오래된 압축 파일과 목록 내보내기 파일도 있습니다.\n"
          "실제 실행 때 프로그램은 이 샘플과 같은 구조의 전체 드라이브를 받습니다.\n",
    "ja": "corpus/ は共有ドライブのサンプルを、整理せずにそのままコピーしたものです。\n"
          "各地のオフィス、スキャン担当、版権チームがそれぞれファイルを置いてきました。古いアーカイブや目録の書き出しもあります。\n"
          "本番では、このサンプルと同じ構成のドライブ全体をプログラムに渡します。\n",
    "es": "corpus/ es una muestra de nuestra unidad compartida, copiada tal cual, sin ordenar.\n"
          "Las oficinas regionales, el equipo de escaneo y el departamento de derechos han ido dejando archivos;\n"
          "también hay archivos comprimidos antiguos y exportaciones de catálogo.\n"
          "En la ejecución real el programa recibe la unidad completa, organizada como esta muestra.\n",
}


def write_data(world: World, data_dir: Path, lang: str) -> None:
    for rel, body in world.visible.files.items():
        p = data_dir / "corpus" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
    (data_dir / NOTES_FILE[lang]).write_text(NOTES[lang], encoding="utf-8")


# ── ground truth in one setting ──────────────────────────────────────────────

LAYOUTS = {"year/title/author": "{year}/{title}/{author}.txt", "year/author/title": "{year}/{author}/{title}.txt",
           "author/year_title": "{author}/{year}_{title}.txt"}
FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')


def slug(s: str, sep: str, max_len: int) -> str:
    """NFKC; forbidden characters become spaces; whitespace runs become one separator; cut; trim."""
    s = FORBIDDEN.sub(" ", nfkc(s))
    s = " ".join(s.split()).replace(" ", sep)[:max_len]
    return s.strip(" ." + sep)


def norm_text(s: str) -> str:
    return re.sub(r"\s+", "", nfkc(s))


def content_of(b: Book) -> str:
    return "\n\n".join(unicodedata.normalize("NFC", p) for p in b.desc) + "\n"


class _View:
    """One setting: its tier (which books are scored, which rules apply) and its rule-set parameters."""

    def __init__(self, setting):
        self.setting = setting
        self.tier = setting.tier
        self.medium, self.hard = setting.at_least("medium"), setting.at_least("hard")
        self.layout = setting["layout"]
        self.year_basis = setting["year_basis"]
        self.script = setting["script"]
        self.multi_author = setting["multi_author"]
        self.sep = setting["sep"]
        self.max_len = int(setting["max_len"])
        self.fallback = setting["fallback_author"]

    def in_scope(self, b: Book) -> bool:
        return TIER_ORDER.index(b.scope) <= TIER_ORDER.index(self.tier)

    def parts(self, b: Book) -> tuple | None:
        """(year, title, author) path components of the book, or None when it has no placement."""
        if b.first is None or not b.title:
            return None
        year = b.first if self.year_basis == "first" else b.edition_year
        title = b.title if self.script == "original" else b.title_latin
        names = [p.orig if self.script == "original" else p.latin for p in b.authors] or [self.fallback]
        author = names[0] if self.multi_author == "first" else " & ".join(names)
        return str(year), slug(title, self.sep, self.max_len), slug(author, self.sep, self.max_len)

    def path(self, b: Book) -> str | None:
        p = self.parts(b)
        if p is None:
            return None
        return "library/" + LAYOUTS[self.layout].format(year=p[0], title=p[1], author=p[2])

    def parse(self, rel: str) -> tuple | None:
        pat = re.escape(LAYOUTS[self.layout]).replace(r"\{year\}", r"(?P<year>[^/_]+)")
        pat = pat.replace(r"\{title\}", r"(?P<title>[^/]+)").replace(r"\{author\}", r"(?P<author>[^/]+)")
        m = re.fullmatch("library/" + pat, rel)
        return (m.group("year"), m.group("title"), m.group("author")) if m else None


def _decode(body: bytes) -> tuple[str, bool]:
    try:
        return body.decode("utf-8-sig"), True
    except UnicodeDecodeError:
        return body.decode("utf-8", "replace"), False


def _manifest(files: dict) -> list[dict]:
    text, _ = _decode(files["manifest.csv"])
    rows = list(csv.DictReader(io.StringIO(text)))
    if rows and not {"source", "status", "path", "reason"} <= set(k.strip() for k in rows[0] if k):
        raise Fatal("manifest.csv needs the columns source,status,path,reason")
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items() if isinstance(v, str) or v is None}
            for r in rows]


def _refs(source: str) -> set:
    out = set()
    for s in source.split(";"):
        s = re.split(r"[!#]", s.strip().replace("\\", "/"))[0]
        while s.startswith("./"):
            s = s[2:]
        if s:
            out.add(unicodedata.normalize("NFC", s))
    return out


def evaluate(corpus: Corpus, files: dict, v: _View) -> tuple[list, float, dict]:
    violations: list = []
    lib = {rel: body for rel, body in files.items() if rel.startswith("library/")}
    rows = _manifest(files)
    texts = {}
    for rel, body in sorted(lib.items()) + [("manifest.csv", files["manifest.csv"])]:
        texts[rel], ok = _decode(body)
        if not ok:
            violations.append(("utf8_output", f"{rel} is not valid UTF-8"))
    for rel in sorted(files):
        for comp in rel.split("/"):
            if FORBIDDEN.search(comp) or comp in (".", "..") or comp != comp.rstrip(" .") or len(comp.encode()) > 255:
                violations.append(("safe_names", f"{rel}: {comp!r} is not a safe file or folder name"))
                break

    # Which book each library file is: by its expected path, else by its description.
    by_path, by_content = {}, {}
    for b in corpus.books:
        p = v.path(b)
        if p and b.review in (None, "NO_AUTHOR", "NO_DESCRIPTION"):
            by_path.setdefault(p, b)
        if b.desc:
            by_content.setdefault(norm_text(content_of(b)), b)
    attributed: dict = {}
    extras = []
    for rel in sorted(lib):
        b = by_path.get(rel) or by_content.get(norm_text(texts[rel]))
        if b is None:
            extras.append(rel)
        else:
            attributed.setdefault(b.bid, []).append(rel)

    scope = [b for b in corpus.books if v.in_scope(b)]
    review_rows = [r for r in rows if r.get("status", "").lower() == "review"]
    for r in review_rows:
        if r.get("reason", "").upper() not in REASONS:
            violations.append(("review_reason", f"review row {r.get('source', '')[:60]!r} has reason "
                                                f"{r.get('reason', '')!r}, not one of {', '.join(REASONS)}"))
    credit, exact, review_ok, lost = 0.0, 0, 0, []
    for b in scope:
        mine = attributed.get(b.bid, [])
        if len(mine) > 1:
            violations.append(("one_file_per_book", f"{b.title[:40]}: {len(mine)} library files ({', '.join(mine[:3])})"))
        placed = 0.0
        if b.review in (None, "NO_AUTHOR"):
            exp, (y, t, a) = v.path(b), v.parts(b)
            want = norm_text(content_of(b))
            for rel in mine:
                ok = norm_text(texts[rel]) == want
                if rel == exp:
                    c = 1.0 if ok else 0.6
                elif ok:
                    got = v.parse(rel)
                    c = 0.4 + (0.2 * ((got[0] == y) + (got[1] == t) + (got[2] == a)) if got else 0.0)
                else:
                    c = 0.0
                placed = max(placed, c)
        reviewed = 0.0
        if b.review:
            base = NO_AUTHOR_REVIEW_CREDIT if b.review == "NO_AUTHOR" else 1.0
            for r in review_rows:
                if _refs(r.get("source", "")) & b.own:
                    reviewed = max(reviewed, base if r.get("reason", "").upper() == b.review else 0.4 * base)
            if v.hard and b.review == "NO_AUTHOR" and mine:
                violations.append(("missing_author_review", f"{b.title[:40]} has no author but was placed in the "
                                                            f"library ({mine[0]})"))
            if v.hard and b.review == "NO_DESCRIPTION" and mine:
                violations.append(("no_fabrication", f"{b.title[:40]} has no description in any source but has a "
                                                     f"library file ({mine[0]})"))
        c = placed if b.review is None else max(reviewed, placed if b.review == "NO_AUTHOR" else 0.0)
        credit += c
        exact += c == 1.0 and b.review is None
        review_ok += c >= NO_AUTHOR_REVIEW_CREDIT and b.review is not None
        if c == 0:
            lost.append(b.bid)
    if v.hard:
        for rel in sorted(lib):
            if not norm_text(texts[rel]):
                violations.append(("no_fabrication", f"{rel} is empty"))
    penalty = EXTRA_PENALTY * len(extras) if v.medium else 0.0
    objective = 100.0 * max(0.0, credit - penalty) / len(scope)
    metrics = {"books_scored": len(scope), "placed_exactly": exact, "reviewed_correctly": review_ok,
               "books_without_credit": len(lost), "extra_files": len(extras), "library_files": len(lib),
               "credit": round(credit, 3)}
    return violations, round(objective, 6), metrics


# ── running the delivered program ────────────────────────────────────────────

def _digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def run_on(corpus: Corpus, submission_dir: Path, cache: dict | None = None) -> dict:
    """Run organize() on a corpus; {"files": {relative path: bytes}, "error": str | None}."""
    prog = Path(submission_dir) / "program"
    if not prog.is_dir():
        raise Fatal("missing program/ directory")
    key = (id(corpus), _digest(prog))
    if cache is not None and key in cache:
        return cache[key]
    with tempfile.TemporaryDirectory(prefix="fdeb2-corpus-") as tmp:
        src, out = Path(tmp) / "corpus", Path(tmp) / "out"
        for rel, body in corpus.files.items():
            p = src / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body)
        res = run_program(Path(submission_dir), ENTRYPOINT, [{"corpus_dir": "$INPUT_DIR", "out_dir": "$OUTPUT_DIR"}],
                          per_call_timeout=300.0, total_timeout=600.0, input_dir=src, output_to=out)
        files = {}
        if out.is_dir():
            for p in sorted(out.rglob("*")):
                if p.is_file() and not p.is_symlink():
                    files[p.relative_to(out).as_posix()] = p.read_bytes()
    run = {"files": files, "error": res.errors[0] if res.errors else None}
    if cache is not None:
        cache[key] = run
    return run


def score(world: World, submission_dir: Path, setting) -> dict:
    try:
        run = run_on(world.hidden, Path(submission_dir), world._cache.setdefault("runs", {}))
        if "manifest.csv" not in run["files"]:
            why = f" (organize failed: {run['error'][:300]})" if run["error"] else ""
            raise Fatal("the program wrote no manifest.csv" + why)
        violations, objective, metrics = evaluate(world.hidden, run["files"], _View(setting))
    except Fatal as e:
        return {"fatal": str(e)}
    metrics["program_error"] = (run["error"] or "")[:300]
    return {"violations": violations, "objective": objective, "metrics": metrics}


# ── reference solution and rule-breaking examples ────────────────────────────

PARAMS = ("layout", "year_basis", "script", "multi_author", "sep", "max_len", "fallback_author")


def write_program(out_dir: Path, setting, brk: str | None = None) -> None:
    prog = Path(out_dir) / "program"
    prog.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REFERENCE, prog / "organize.py")
    cfg = {k: setting[k] for k in PARAMS}
    cfg["break"] = brk
    (prog / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def reference_solution(world: World, out_dir: Path, setting) -> None:
    write_program(out_dir, setting)


def violating_examples(world: World, setting) -> dict:
    """One program per rule of the setting that breaks exactly that rule (for the validator)."""
    breaks = {"utf8_output": "utf8", "safe_names": "names", "one_file_per_book": "dup", "review_reason": "reason"}
    if setting.at_least("hard"):
        breaks.update(no_fabrication="fabricate", missing_author_review="bend")
    return {rule: (lambda d, b=b: write_program(d, setting, b)) for rule, b in breaks.items()}


# ── stored dataset (fdebench2 export-dataset) ────────────────────────────────

def write_hidden(world: World, out_dir: Path) -> None:
    """hidden/corpus/...: the hidden drive exactly as the program receives it (same in every setting)."""
    for rel, body in world.hidden.files.items():
        p = Path(out_dir) / "corpus" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)


def _skipped(corpus: Corpus) -> list:
    """Corpus files and archive members that belong to no book (junk), as manifest sources."""
    refs = {re.split(r"[!#]", f)[0] for b in corpus.books for f in b.files}
    members = {f for b in corpus.books for f in b.files if "!" in f}
    out = []
    for rel, body in corpus.files.items():
        if rel not in refs:
            out.append(rel)
        elif rel.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                out += [f"{rel}!{m}" for m in z.namelist() if f"{rel}!{m}" not in members]
    return out


def expected_output(corpus: Corpus, v: _View) -> tuple[dict, list]:
    """The correct out_dir for the books scored in this setting: ({relative path: bytes}, per-book key rows)."""
    files, manifest, key, taken = {}, [], [], {}
    for b in corpus.books:
        scored = v.in_scope(b)
        review = b.review if b.review != "NO_AUTHOR" or v.hard else None
        path = None if review else v.path(b)
        if scored:
            if review:
                for rel in sorted(b.own):
                    files[f"_review/{review}/{rel.replace('/', '__')}"] = corpus.files[rel]
                manifest.append([";".join(b.files), "review", "", review])
            else:
                assert path not in taken, (path, b.bid, taken.get(path))
                taken[path] = b.bid
                files[path] = content_of(b).encode("utf-8")
                manifest.append([";".join(b.files), "placed", path, ""])
        key.append([b.bid, b.lang, b.kind, b.scope, int(scored), "review" if review else "placed", path or "",
                    review or "", b.title, b.title_latin, "; ".join(p.orig for p in b.authors),
                    "; ".join(p.latin for p in b.authors), b.first or "", b.edition_year or "", ";".join(b.files)])
    if v.hard:
        manifest += [[rel, "skipped", "", "JUNK"] for rel in _skipped(corpus)]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["source", "status", "path", "reason"])
    w.writerows(manifest)
    files["manifest.csv"] = buf.getvalue().encode("utf-8")
    return files, key


BOOK_KEY_HEADER = ["book", "lang", "kind", "tier", "scored", "status", "path", "reason", "title", "title_latin",
                   "authors", "authors_latin", "first_published", "edition_year", "sources"]


def _write_tree(root: Path, files: dict) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)


def write_ground_truth(world: World, gt_dir: Path, setting) -> None:
    """For the hidden corpus (the one the program is scored on): expected_output/ (the correct out_dir for the
    scored books), books.csv (every book with its expected status, path and reason), expected_score.json, and
    reference_output/ (what the reference program writes)."""
    gt_dir, v = Path(gt_dir), _View(setting)
    files, key = expected_output(world.hidden, v)
    _write_tree(gt_dir / "expected_output", files)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(BOOK_KEY_HEADER)
    w.writerows(key)
    (gt_dir / "books.csv").write_bytes(buf.getvalue().encode("utf-8-sig"))
    violations, objective, metrics = evaluate(world.hidden, files, v)
    score = {"objective": objective, "violations": violations, "metrics": metrics}
    (gt_dir / "expected_score.json").write_text(json.dumps(score, ensure_ascii=False, indent=2, sort_keys=True)
                                                + "\n", encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="fdeb2-ref-") as tmp:
        write_program(Path(tmp), setting)
        run = run_on(world.hidden, Path(tmp), world._cache.setdefault("runs", {}))
    _write_tree(gt_dir / "reference_output", run["files"])
