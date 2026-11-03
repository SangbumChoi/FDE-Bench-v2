"""Reference organizer for the multilingual corpus curator case (standard library only).

organize({"corpus_dir": ..., "out_dir": ...}) reads every file of the corpus (zip archives and catalog CSVs
included), groups the records that describe the same book, resolves each field by source precedence (embedded
metadata > title-page text > file name, a missing field from any other file of the book), maps every author to
the official romanization the drive gives for that person, and writes out_dir/library/..., out_dir/_review/...
and out_dir/manifest.csv. The client's library rules of the setting (layout, year basis, script, co-authors,
separator, length limit, the policy for books with no author and their fallback name) are in config.json next to
this file. It handles every exception the client describes, so on the hidden drive it files every book as the
client's catalogue does.

config.json may also carry switches the benchmark uses to build other deliverables from this one program:
"misread" (the reference misreading exactly one client fact, for the ground truth audit), "shortcut" (a
degenerate strategy), "robust" (a program that never asked the client: it does not know the reason codes, so it
sets aside the books it cannot file as skipped) and "break" (a deliberate rule break for the validator).
"""

import csv
import io
import json
import os
import re
import shutil
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "config.json"), encoding="utf-8") as _f:
    CONFIG = json.load(_f)

LAYOUTS = {"year/title/author": "{year}/{title}/{author}.txt", "year/author/title": "{year}/{author}/{title}.txt",
           "author/year_title": "{author}/{year}_{title}.txt"}
HEADINGS = {"内容简介", "内容紹介", "책 소개", "About this book", "Sinopsis"}
JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
GENERIC = re.compile(r"^((doc|scan|img|image|book|file|untitled|new)[\s_-]*\d*|\d{10,13})$", re.I)
FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
CJK_CHAR = re.compile(r"[぀-ヿ㐀-鿿가-힣豈-﫿]")
ONIX = "{http://ns.editeur.org/onix/3.0/reference}"
OPF = "{http://www.idpf.org/2007/opf}"
DC = "{http://purl.org/dc/elements/1.1/}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CATALOG_FIELDS = {
    "title": "title", "書名": "title", "title_latin": "title_latin", "書名ローマ字": "title_latin",
    "authors": "authors", "著者": "authors", "authors_latin": "authors_latin", "著者ローマ字": "authors_latin",
    "first_published": "first", "初版年": "first", "edition_year": "edition", "版年": "edition",
    "description": "desc", "内容紹介": "desc",
}


def nfkc(s):
    return unicodedata.normalize("NFKC", s)


# ── text helpers ─────────────────────────────────────────────────────────────

class Decoder:
    """Legacy encodings: pick the decoding whose characters look most like the UTF-8 files of the corpus."""

    def __init__(self):
        self.seen = {}

    def learn(self, text):
        for ch in text:
            if ord(ch) > 127:
                self.seen[ch] = self.seen.get(ch, 0) + 1

    def decode(self, raw, hint=None):
        if raw.startswith(b"\xef\xbb\xbf"):
            return raw[3:].decode("utf-8", "replace")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            pass
        if hint:
            try:
                return raw.decode(hint)
            except (LookupError, UnicodeDecodeError):
                pass
        best, best_score = raw.decode("cp1252", "replace"), -1.0
        for enc in ("cp949", "shift_jis", "gb18030", "cp1252"):
            try:
                text = raw.decode(enc)
            except UnicodeDecodeError:
                continue
            non = [c for c in text if ord(c) > 127]
            score = sum(1 for c in non if c in self.seen) / len(non) if non else 0.0
            if score > best_score:
                best, best_score = text, score
        return best


ROMAN = {"M": 1000, "D": 500, "C": 100, "L": 50, "X": 10, "V": 5, "I": 1}
HANZI = {c: str(k) for k, c in enumerate("〇一二三四五六七八九")}


def roman(s):
    total = 0
    for k, ch in enumerate(s):
        v = ROMAN[ch]
        total += -v if k + 1 < len(s) and ROMAN[s[k + 1]] > v else v
    return total


def parse_year(s):
    if s is None:
        return None
    s = nfkc(str(s)).strip()
    if re.fullmatch(r"\d{4}", s):
        return int(s)
    if re.fullmatch(r"[MDCLXVI]+", s) and 1000 <= roman(s) <= 2100:
        return roman(s)
    m = re.fullmatch(r"([〇一二三四五六七八九]{4})\s*年?", s)
    if m:
        return int("".join(HANZI[c] for c in m.group(1)))
    m = re.search(r"(令和|平成|昭和)\s*(元|\d+)\s*年", s)
    if m:
        n = 1 if m.group(2) == "元" else int(m.group(2))
        return {"令和": 2018, "平成": 1988, "昭和": 1925}[m.group(1)] + n
    m = re.search(r"民[國国]\s*(\d+)\s*年", s)
    if m:
        return 1911 + int(m.group(1))
    m = re.search(r"단기\s*(\d+)\s*년", s)
    if m:
        return int(m.group(1)) - 2333
    m = re.search(r"(\d{4})\s*[年년]", s)
    if m:
        return int(m.group(1))
    m = re.fullmatch(r".*?\b(\d{4})\b.*", s)
    if m:
        return int(m.group(1))
    return None


def is_cjk(s):
    return bool(CJK_CHAR.search(s or ""))


def uninvert(name):
    name = " ".join(nfkc(name).split()) if not is_cjk(name) else name.strip()
    if "," in name and not is_cjk(name):
        family, _, given = name.partition(",")
        name = f"{given.strip()} {family.strip()}"
    return name


def person(orig=None, latin=None):
    """A name as {"orig", "latin"}; a lone Latin-script name is the Latin form only."""
    orig = (orig or "").strip() or None
    latin = (latin or "").strip() or None
    if orig and not latin and not is_cjk(orig):
        orig, latin = None, orig
    if latin:
        latin = uninvert(latin)
    return {"orig": orig, "latin": latin}


def name_key(name):
    toks = re.split(r"[\s,]+", nfkc(name).casefold().replace("-", ""))
    return tuple(sorted(t for t in toks if t))


def join_lines(lines):
    out = ""
    for line in lines:
        line = line.strip()
        if not out:
            out = line
        elif is_cjk(out[-1:]) or is_cjk(line[:1]):
            out += line
        else:
            out += " " + line
    return out


def parse_author_line(line):
    line = line.strip()
    for suffix in (" 著", " 지음"):
        if line.endswith(suffix):
            body = line[: -len(suffix)]
            parts = body.split("、") if suffix == " 著" else body.split(", ")
            out = []
            for p in parts:
                m = re.fullmatch(r"(.+?)[（(](.+?)[）)]", p.strip())
                out.append(person(m.group(1), m.group(2)) if m else person(p))
            return out
    if line.startswith("by "):
        return [person(p) for p in line[3:].split(" and ")]
    if line.startswith("por "):
        return [person(p) for p in line[4:].split(" y ")]
    return None


def parse_years_line(line):
    s = nfkc(line).strip()
    if not re.match(r"(初版|초판|First published|Primera edición)", s):
        return None
    parts = re.split(r"\s[·/]\s", s)
    first = parse_year(re.sub(r"^(初版|초판|First published|Primera edición:?)\s*", "", parts[0]))
    edition = None
    if len(parts) > 1:
        edition = parse_year(re.sub(r"^(本版|新版|개정판|This edition|Esta edición:?)\s*", "", parts[1]))
    return {"first": first, "edition": edition, "seen": True}


def title_page(lines):
    """Fields from title-page lines: title, Latin title, authors, years, description."""
    lines = [ln.rstrip() for ln in lines]
    head = next((k for k, ln in enumerate(lines) if ln.strip() in HEADINGS), None)
    top = [ln.strip() for ln in (lines if head is None else lines[:head]) if ln.strip()]
    rec = {}
    for k, ln in enumerate(top):
        authors = parse_author_line(ln)
        years = parse_years_line(ln)
        if authors is not None:
            rec["authors"] = authors
        elif years is not None:
            rec.update({k2: v for k2, v in years.items() if v is not None})
        elif ln.startswith("©"):
            m = re.match(r"©\s*(\d{4})", nfkc(ln))
            if m:
                rec["copyright"] = int(m.group(1))
        elif re.fullmatch(r"[(（].+[)）]", ln) and "title" in rec:
            rec["title_latin"] = ln[1:-1].strip()
        elif k == 0:
            rec["title"] = ln
    if head is not None:
        paras, cur = [], []
        for ln in lines[head + 1:]:
            if ln.strip():
                cur.append(ln)
            elif cur:
                paras.append(join_lines(cur))
                cur = []
        if cur:
            paras.append(join_lines(cur))
        rec["desc"] = paras
    return rec


def paragraphs(text):
    return [join_lines(p.splitlines()) for p in re.split(r"\n\s*\n", text.replace("\r\n", "\n")) if p.strip()]


# ── readers: each returns (embedded, title_page) dicts ───────────────────────

def read_json(raw, dec):
    doc = json.loads(dec.decode(raw))
    emb = {"title": doc.get("title"), "title_latin": doc.get("title_latin"),
           "authors": [person(a.get("name"), a.get("name_latin")) for a in doc.get("authors") or []],
           "first": parse_year(doc.get("first_published")), "edition": parse_year(doc.get("edition_year")),
           "desc": paragraphs(doc.get("description") or "")}
    return emb, {}


def read_onix(raw, dec):
    root = ET.fromstring(raw)
    emb = {"authors": []}
    for t in root.iter(ONIX + "TitleText"):
        emb["title_latin" if t.get("textscript") == "Latn" else "title"] = t.text
    for c in root.iter(ONIX + "Contributor"):
        name = c.findtext(ONIX + "PersonName")
        alt = c.find(ONIX + "AlternativeName")
        latin = alt.findtext(ONIX + "PersonName") if alt is not None else None
        emb["authors"].append(person(name, latin))
    for d in root.iter(ONIX + "PublishingDate"):
        role, year = d.findtext(ONIX + "PublishingDateRole"), parse_year(d.findtext(ONIX + "Date"))
        emb["first" if role == "11" else "edition"] = year
    if "first" not in emb and "edition" in emb:
        emb["first"] = emb.pop("edition")
    text = root.find(f".//{ONIX}TextContent/{ONIX}Text")
    emb["desc"] = paragraphs(text.text or "") if text is not None else []
    return emb, {}


def read_epub(raw, dec):
    z = zipfile.ZipFile(io.BytesIO(raw))
    container = ET.fromstring(z.read("META-INF/container.xml"))
    opf_path = next(e.get("full-path") for e in container.iter() if e.tag.endswith("rootfile"))
    meta = ET.fromstring(z.read(opf_path)).find(OPF + "metadata")
    refines = {}
    for m in meta.iter(OPF + "meta"):
        if m.get("refines"):
            refines.setdefault(m.get("refines")[1:], {})[m.get("property")] = m.text
    emb = {"authors": []}
    t = meta.find(DC + "title")
    if t is not None:
        emb["title"] = t.text
        emb["title_latin"] = refines.get(t.get("id"), {}).get("alternate-script")
    for c in meta.iter(DC + "creator"):
        emb["authors"].append(person(c.text, refines.get(c.get("id"), {}).get("alternate-script")))
    first = next((m.text for m in meta.iter(OPF + "meta") if m.get("property") == "first-published"), None)
    date = meta.findtext(DC + "date")
    emb["first"] = parse_year(first or date)
    emb["edition"] = parse_year(date) if first else None
    emb["desc"] = paragraphs(meta.findtext(DC + "description") or "")
    return emb, {}


def read_docx(raw, dec):
    z = zipfile.ZipFile(io.BytesIO(raw))
    core = ET.fromstring(z.read("docProps/core.xml"))
    emb = {"title": core.findtext(DC + "title") or None,
           "authors": [person(n) for n in (core.findtext(DC + "creator") or "").split(";") if n.strip()]}
    body = ET.fromstring(z.read("word/document.xml"))
    lines = ["".join(t.text or "" for t in p.iter(W + "t")) for p in body.iter(W + "p")]
    return emb, title_page(lines)


def _pdf_string(tok):
    if tok.startswith("<"):
        data = bytes.fromhex(tok[1:-1])
        return data[2:].decode("utf-16-be") if data.startswith(b"\xfe\xff") else data.decode("latin-1")
    body = tok[1:-1]
    return re.sub(r"\\(.)", r"\1", body)


def read_pdf(raw, dec):
    text = raw.decode("latin-1")
    emb = {}
    info = re.search(r"/Info (\d+) 0 R", text)
    if info:
        obj = re.search(rf"\n{info.group(1)} 0 obj\n(.*?)\nendobj", text, re.S)
        if obj:
            for key, field in (("Title", "title"), ("Author", "authors")):
                m = re.search(rf"/{key} (<[0-9A-Fa-f]*>|\((?:\\.|[^\\)])*\))", obj.group(1))
                if m:
                    val = _pdf_string(m.group(1))
                    emb[field] = [person(n) for n in val.split(";") if n.strip()] if field == "authors" else val
    lines = []
    for stream in re.findall(r"stream\r?\n(.*?)\r?\nendstream", text, re.S):
        if not re.match(r"\s*BT\b", stream):
            continue                                   # not a text stream (an image, a font)
        for m in re.finditer(r"(<[0-9A-Fa-f]*>|\((?:\\.|[^\\)])*\))\s*Tj", stream):
            lines.append(_pdf_string(m.group(1)))
    if not lines and not emb.get("title"):
        return None                                    # an image-only scan
    return emb, title_page(lines)


class _Html(HTMLParser):
    BLOCKS = {"h1", "h2", "h3", "p", "li", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.cur, self.meta, self.title, self.in_block = [], [], {}, None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("name"):
            self.meta[a["name"].lower()] = a.get("content", "")
        if tag in self.BLOCKS:
            self.in_block, self.cur = tag, []

    def handle_endtag(self, tag):
        if tag == self.in_block:
            text = " ".join("".join(self.cur).split())
            if tag == "title":
                self.title = text
            else:
                self.lines += [text, ""]
            self.in_block = None

    def handle_data(self, data):
        if self.in_block:
            self.cur.append(data)


def read_html(raw, dec):
    head = raw[:300].decode("ascii", "replace")
    m = re.search(r'charset="?([\w-]+)', head)
    p = _Html()
    p.feed(dec.decode(raw, m.group(1) if m else None))
    emb = {"title": p.title, "authors": [person(n) for n in p.meta.get("author", "").split(";") if n.strip()]}
    return emb, title_page(p.lines)


def read_md(raw, dec):
    text = dec.decode(raw).replace("\r\n", "\n")
    emb = {}
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if m:
        fm = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
        fm = {k.strip(): v.strip() for k, v in fm.items()}
        names = [n.strip() for n in fm.get("author", "").split(";") if n.strip()]
        latins = [n.strip() for n in fm.get("author_latin", "").split(";") if n.strip()]
        emb = {"title": fm.get("title"), "title_latin": fm.get("title_latin"),
               "authors": [person(n, latins[k] if k < len(latins) and is_cjk(n) else None) for k, n in enumerate(names)],
               "first": parse_year(fm.get("first_published")), "edition": parse_year(fm.get("edition"))}
        text = text[m.end():]
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"^#+\s*", "", line)
        if re.fullmatch(r"\*(.+)\*", line.strip()):
            line = "(" + line.strip()[1:-1] + ")"
        lines.append(line)
    return emb, title_page(lines)


def read_txt(raw, dec):
    return {}, title_page(dec.decode(raw).replace("\r\n", "\n").split("\n"))


def read_catalog(raw, dec):
    rows = list(csv.reader(io.StringIO(dec.decode(raw))))
    fields = [CATALOG_FIELDS.get(h.strip()) for h in rows[0]]
    out = []
    for row in rows[1:]:
        d = {f: v for f, v in zip(fields, row) if f}
        names = [n.strip() for n in d.get("authors", "").split(";") if n.strip()]
        latins = [n.strip() for n in d.get("authors_latin", "").split(";") if n.strip()]
        emb = {"title": d.get("title"), "title_latin": d.get("title_latin") or None,
               "authors": [person(n, latins[k] if k < len(latins) and is_cjk(n) else None) for k, n in enumerate(names)],
               "first": parse_year(d.get("first")), "edition": parse_year(d.get("edition") or None),
               "desc": paragraphs(d.get("desc") or "")}
        out.append(emb)
    return out


READERS = {".json": read_json, ".xml": read_onix, ".epub": read_epub, ".docx": read_docx, ".pdf": read_pdf,
           ".html": read_html, ".htm": read_html, ".md": read_md, ".txt": read_txt}


def filename_title(rel, generic_ok=False):
    """A title from a meaningful file name (underscores stand for spaces); generic names are not titles."""
    stem = os.path.splitext(os.path.basename(rel))[0]
    stem = re.sub(r"\s*\(scan\)$", "", stem, flags=re.I)
    if GENERIC.match(stem) and not generic_ok:
        return None
    return stem.replace("_", " ").strip() or None


# ── organizing ───────────────────────────────────────────────────────────────

REASONS = ("UNREADABLE", "NO_TITLE", "NO_AUTHOR", "NO_YEAR", "NO_DESCRIPTION", "CONFLICT")
FREE_REASONS = {"UNREADABLE": "unreadable scan", "NO_TITLE": "title missing", "NO_AUTHOR": "author missing",
                "NO_YEAR": "year missing", "NO_DESCRIPTION": "description missing",
                "CONFLICT": "years disagree"}
PLACEHOLDER = "No description available."


def slug(s, sep, max_len):
    s = FORBIDDEN.sub(" ", nfkc(s))
    s = " ".join(s.split()).replace(" ", sep)[:max_len]
    return s.strip(" ." + sep)


def title_key(t):
    return re.sub(r"[\W_]+", "", nfkc(t).casefold())


def resolve(recs, official, misread=None):
    """One book from its records: each field from the highest rank that has it (any file of the book), the
    official romanization of every author, the year from a copyright line when no source gives one, and whether
    two sources of the same rank (embedded metadata) disagree on a year."""
    def pick(field):
        for level in ("emb", "text", "fname"):
            for r in recs:
                v = r[level].get(field)
                if v not in (None, "", []):
                    return v
        return None
    authors = [dict(a) for a in (pick("authors") or [])]
    pool = [a for r in recs for level in ("emb", "text") for a in r[level].get("authors") or []]
    for a in authors:
        for b in pool:
            if a["orig"] and b["orig"] == a["orig"] and b["latin"] and not a["latin"]:
                a["latin"] = b["latin"]
            if a["latin"] and b["latin"] and name_key(b["latin"]) == name_key(a["latin"]) and b["orig"] and not a["orig"]:
                a["orig"] = b["orig"]
        pair = official.get(name_key(a["latin"])) if a["latin"] else None
        if pair and (not a["orig"] or a["orig"] == pair[0]):
            a["orig"], a["latin"] = pair                 # the drive's official pair for this person
    first = pick("first") or pick("copyright")
    edition = pick("edition") or first
    conflict = misread != "first_source" and any(
        len({r["emb"][f] for r in recs if r["emb"].get(f) is not None}) > 1 for f in ("first", "edition"))
    return {"title": pick("title"), "title_latin": pick("title_latin"), "authors": authors, "first": first,
            "edition": edition, "desc": pick("desc"), "conflict": conflict}


def _entries(paths, raws):
    """(source reference, name, bytes, corpus path or None): every file of the drive, with the members of zip
    archives as files of their own (`archive.zip!path/inside`)."""
    out = []
    for rel in paths:
        raw = raws[rel]
        if rel.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    members = [(i.filename, z.read(i)) for i in z.infolist() if not i.is_dir()]
                out += [(f"{rel}!{name}", name, body, None) for name, body in members]
                continue
            except (zipfile.BadZipFile, OSError):
                pass
        out.append((rel, rel, raw, rel))
    return out


def organize(task):
    corpus, out = task["corpus_dir"], task["out_dir"]
    cfg = CONFIG
    misread, shortcut, brk, robust = cfg.get("misread"), cfg.get("shortcut"), cfg.get("break"), cfg.get("robust")
    dec = Decoder()
    paths = []
    for root, dirs, files in os.walk(corpus):
        dirs.sort()
        for f in sorted(files):
            paths.append(os.path.relpath(os.path.join(root, f), corpus).replace(os.sep, "/"))
    raws = {}
    for rel in paths:
        with open(os.path.join(corpus, rel), "rb") as fh:
            raws[rel] = fh.read()
    entries = _entries(paths, raws)
    for ref, name, raw, real in entries:                # learn the corpus's characters from its UTF-8 files
        if name.lower().endswith((".txt", ".md", ".html", ".json", ".csv", ".xml")):
            try:
                dec.learn(raw.decode("utf-8"))
            except UnicodeDecodeError:
                pass
    manifest, records = [], []
    for ref, name, raw, real in entries:
        base = os.path.basename(name)
        ext = os.path.splitext(base)[1].lower()
        if base.lower() in JUNK_NAMES or base.startswith(("~$", "._")) or "__MACOSX/" in name or not raw:
            manifest.append([ref, "skipped", "", "JUNK"])
            continue
        if ext == ".csv":
            try:
                for k, emb in enumerate(read_catalog(raw, dec)):
                    records.append({"src": f"{ref}#{k + 1}", "real": None, "emb": emb, "text": {}, "fname": {},
                                    "unreadable": False, "raw": raw})
            except Exception:
                manifest.append([ref, "skipped", "", "UNKNOWN_FORMAT"])
            continue
        reader = READERS.get(ext)
        if reader is None:
            manifest.append([ref, "skipped", "", "UNKNOWN_FORMAT"])
            continue
        try:
            got = reader(raw, dec)
        except Exception:
            got = None
        fname = {"title": filename_title(name, misread == "filename_titles")}
        if got is None:
            records.append({"src": ref, "real": real, "emb": {}, "text": {}, "fname": fname, "unreadable": True,
                            "raw": raw})
            continue
        emb, text = got
        records.append({"src": ref, "real": real, "emb": emb, "text": text, "fname": fname, "unreadable": False,
                        "raw": raw})

    official = {}                                       # the drive's official name pairs, by person
    for r in records:
        for level in ("emb", "text"):
            for a in r[level].get("authors") or []:
                if a["orig"] and a["latin"]:
                    official.setdefault(name_key(a["latin"]), (a["orig"], a["latin"]))

    groups, order = {}, []
    for r in records:
        title = next((r[lv].get("title") for lv in ("emb", "text", "fname") if r[lv].get("title")), None)
        key = title_key(title) if title else f"untitled:{r['src']}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)

    layouts = list(LAYOUTS.values()) if shortcut == "all_layouts" else [LAYOUTS[cfg["layout"]]]
    os.makedirs(os.path.join(out, "library"), exist_ok=True)
    taken, copies_skipped, plain = set(), False, []
    for key in order:
        recs = groups[key]
        readable = [r for r in recs if not r["unreadable"]]
        sources = ";".join(r["src"] for r in recs)
        if not readable:
            reason = "UNREADABLE"
            book = None
        else:
            book = resolve(readable, official, misread)
            reason = None
            if not book["title"]:
                reason = "NO_TITLE"
            elif not book["authors"] and (cfg["no_author"] == "review" or brk == "noshelve") and brk != "bend":
                reason = "NO_AUTHOR"
            elif not book["first"]:
                reason = "NO_YEAR"
            elif not book["desc"] and brk != "fabricate" and misread != "placeholder":
                reason = "NO_DESCRIPTION"
            elif book["conflict"] and brk != "guess":
                reason = "CONFLICT"
        if shortcut == "review_all":
            reason = reason or "UNREADABLE"
        if reason and robust:                           # no reason codes known: set the book aside, unfiled
            manifest.append([sources, "skipped", "", ""])
            continue
        if reason:
            skip_copies = shortcut == "no_review_copies" or (brk == "copies" and not copies_skipped
                                                              and any(r["real"] for r in recs))
            copies_skipped = copies_skipped or skip_copies
            for r in recs:
                if r["real"] and not skip_copies:
                    dest = os.path.join(out, "_review", reason, r["real"].replace("/", "__"))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copyfile(os.path.join(corpus, r["real"]), dest)
            manifest.append([sources, "review", "", FREE_REASONS[reason] if misread == "free_reasons" else reason])
            continue
        original = cfg["script"] == "original"
        title = book["title"] if original else (book["title_latin"] or book["title"])
        names = [(a["orig"] or a["latin"]) if original else (a["latin"] or a["orig"]) for a in book["authors"]]
        if not names:
            names = [cfg["fallback_author"]]
        author = names[0] if cfg["multi_author"] == "first" else " & ".join(names)
        year = book["first"] if cfg["year_basis"] == "first" else book["edition"]
        sep, n = cfg["sep"], int(cfg["max_len"])
        desc = book["desc"] or [PLACEHOLDER]
        body = "\n\n".join(unicodedata.normalize("NFC", p) for p in desc) + "\n"
        if misread == "card":                           # a catalogue card: title, author and year above the blurb
            body = f"{title}\n{' & '.join(names)}\n{year}\n\n" + body
        elif shortcut == "placeholder_text":
            body = "x\n"
        elif shortcut == "whole_text":
            body = dec.decode(readable[0]["raw"]).replace("\r\n", "\n")
        if shortcut == "flat_titles":
            rels = ["library/" + slug(title, sep, n) + ".txt"]
        else:
            rels = ["library/" + lay.format(year=year, title=slug(title, sep, n), author=slug(author, sep, n))
                    for lay in layouts]
        if rels[0] in taken:
            manifest.append([sources, "review", "", "CONFLICT"])
            continue
        for rel in rels:
            taken.add(rel)
            dest = os.path.join(out, *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body)
        manifest.append([sources, "placed", rels[0], ""])
        if brk == "dup" and _plain(recs, book):
            plain.append(rels[0])

    if shortcut == "copy_through":
        manifest = _copy_through(corpus, out, paths)
    if shortcut in ("sourceless_manifest", "path_as_source"):     # the index without the drive side
        for m in manifest:
            if m[1] == "placed":
                m[0] = "" if shortcut == "sourceless_manifest" else m[2]
    if shortcut == "spam":                              # six review rows, one per code, for every source
        for ref, name, raw, real in entries:
            for code in REASONS:
                manifest.append([ref, "review", "", code])
            if real:
                dest = os.path.join(out, "_review", "ALL", real.replace("/", "__"))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copyfile(os.path.join(corpus, real), dest)
    _break(out, manifest, brk, plain)
    with open(os.path.join(out, "manifest.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["source", "status", "path", "reason"])
        if shortcut != "header_only":
            w.writerows(manifest)
    return {"placed": sum(1 for m in manifest if m[1] == "placed"),
            "review": sum(1 for m in manifest if m[1] == "review")}


def _copy_through(corpus, out, paths):
    """Shortcut: every file of the drive copied into library/ as it is, one placed row each."""
    shutil.rmtree(os.path.join(out, "library"), ignore_errors=True)
    rows = []
    for rel in paths:
        dest = os.path.join(out, "library", *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(os.path.join(corpus, rel), dest)
        rows.append([rel, "placed", f"library/{rel}", ""])
    return rows


def _plain(recs, book):
    """Whether a placed book looks well-formed: one readable UTF-8 file of the drive giving every field above
    the file name, a plain four-digit year and a title that needs no normalizing (the "dup" break copies such
    books, which every tier scores)."""
    if len(recs) != 1 or not recs[0]["real"]:
        return False
    try:
        text = recs[0]["raw"].decode("utf-8")
    except UnicodeDecodeError:
        return False
    fields = dict(recs[0]["text"])
    fields.update({k: v for k, v in recs[0]["emb"].items() if v not in (None, "", [])})
    title = fields.get("title") or ""
    return bool(title and fields.get("authors") and fields.get("first") and fields.get("desc")) \
        and str(book["first"]) in text and nfkc(title) == title and not FORBIDDEN.search(title)


def _break(out, manifest, mode, plain=()):
    """Deliberate rule breaks, used only by the benchmark's validator (config "break")."""
    lib = sorted(m[2] for m in manifest if m[1] == "placed")
    if mode == "utf8":
        for rel in lib:
            p = os.path.join(out, *rel.split("/"))
            with open(p, encoding="utf-8") as fh:
                body = fh.read()
            with open(p, "wb") as fh:
                fh.write(body.encode("utf-16"))
    elif mode == "names" and lib:
        p = os.path.join(out, *lib[0].split("/"))
        os.rename(p, p[:-4] + "?.txt")
        for m in manifest:
            if m[1] == "placed" and m[2] == lib[0]:
                m[2] = lib[0][:-4] + "?.txt"
    elif mode == "dup":     # a second library file for well-formed books, each with its own row naming a junk file
        junk = [m for m in manifest if m[1] == "skipped" and m[3] == "JUNK"]
        os.makedirs(os.path.join(out, "library", "_copies"), exist_ok=True)
        for k, (rel, m) in enumerate(zip(plain, junk)):
            shutil.copyfile(os.path.join(out, *rel.split("/")), os.path.join(out, "library", "_copies", f"{k}.txt"))
            m[1:] = ["placed", f"library/_copies/{k}.txt", ""]
    elif mode == "reason":
        for m in manifest:
            if m[1] == "review":
                m[3] = ""
                break
    elif mode == "manifest":                            # a library file without its placed row
        for k, m in enumerate(manifest):
            if m[1] == "placed":
                del manifest[k]
                break
