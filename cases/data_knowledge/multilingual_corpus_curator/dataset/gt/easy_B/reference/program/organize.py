"""Reference organizer for the multilingual corpus curator case (standard library only).

organize({"corpus_dir": ..., "out_dir": ...}) reads every file of the corpus, groups the records that
describe the same book, resolves each field by source precedence (embedded metadata > title-page text >
file name) and writes out_dir/library/..., out_dir/_review/... and out_dir/manifest.csv. The client's
rule-set parameters are in config.json next to this file.

Deliberate gaps (the headroom an agent can win back): it does not open zip archives, does not read
Roman-numeral or Chinese-numeral years, does not recover a year from a copyright line, does not detect two
sources of the same rank that disagree on the year (it takes the first), and resolves a romanized author
name only from the book's own files (no corpus-wide name map).
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


def parse_year(s):
    if s is None:
        return None
    s = nfkc(str(s)).strip()
    if re.fullmatch(r"\d{4}", s):
        return int(s)
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
            continue                       # copyright line: not read by the reference
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


def filename_title(rel):
    stem = os.path.splitext(os.path.basename(rel))[0]
    stem = re.sub(r"\s*\(scan\)$", "", stem, flags=re.I)
    if GENERIC.match(stem):
        return None
    return stem.replace("_", " ").strip() or None


# ── organizing ───────────────────────────────────────────────────────────────

def slug(s, sep, max_len):
    s = FORBIDDEN.sub(" ", nfkc(s))
    s = " ".join(s.split()).replace(" ", sep)[:max_len]
    return s.strip(" ." + sep)


def title_key(t):
    return re.sub(r"[\W_]+", "", nfkc(t).casefold())


def resolve(recs):
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
    first = pick("first")
    edition = pick("edition") or first
    return {"title": pick("title"), "title_latin": pick("title_latin"), "authors": authors, "first": first,
            "edition": edition, "desc": pick("desc")}


def organize(task):
    corpus, out = task["corpus_dir"], task["out_dir"]
    cfg = CONFIG
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
    for rel, raw in raws.items():                       # learn the corpus's characters from its UTF-8 files
        if rel.lower().endswith((".txt", ".md", ".html", ".json", ".csv", ".xml")):
            try:
                dec.learn(raw.decode("utf-8"))
            except UnicodeDecodeError:
                pass
    manifest, records = [], []
    for rel in paths:
        name, raw = os.path.basename(rel), raws[rel]
        ext = os.path.splitext(name)[1].lower()
        if name.lower() in JUNK_NAMES or name.startswith(("~$", "._")) or not raw:
            manifest.append([rel, "skipped", "", "JUNK"])
            continue
        if ext == ".zip":
            manifest.append([rel, "skipped", "", "ARCHIVE_NOT_READ"])
            continue
        if ext == ".csv":
            try:
                for k, emb in enumerate(read_catalog(raw, dec)):
                    records.append({"src": f"{rel}#{k + 1}", "real": None, "emb": emb, "text": {}, "fname": {},
                                    "unreadable": False})
            except Exception:
                manifest.append([rel, "skipped", "", "UNKNOWN_FORMAT"])
            continue
        reader = READERS.get(ext)
        if reader is None:
            manifest.append([rel, "skipped", "", "UNKNOWN_FORMAT"])
            continue
        try:
            got = reader(raw, dec)
        except Exception:
            got = None
        fname = {"title": filename_title(rel)}
        if got is None:
            records.append({"src": rel, "real": rel, "emb": {}, "text": {}, "fname": fname, "unreadable": True})
            continue
        emb, text = got
        records.append({"src": rel, "real": rel, "emb": emb, "text": text, "fname": fname, "unreadable": False})

    groups, order = {}, []
    for r in records:
        title = next((r[lv].get("title") for lv in ("emb", "text", "fname") if r[lv].get("title")), None)
        key = title_key(title) if title else f"untitled:{r['src']}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)

    layout = LAYOUTS[cfg["layout"]]
    os.makedirs(os.path.join(out, "library"), exist_ok=True)
    taken = set()
    for key in order:
        recs = groups[key]
        readable = [r for r in recs if not r["unreadable"]]
        sources = ";".join(r["src"] for r in recs)
        if not readable:
            reason = "UNREADABLE"
            book = None
        else:
            book = resolve(readable)
            reason = None
            if not book["title"]:
                reason = "NO_TITLE"
            elif not book["authors"] and cfg.get("break") != "bend":
                reason = "NO_AUTHOR"
            elif not book["first"]:
                reason = "NO_YEAR"
            elif not book["desc"] and cfg.get("break") != "fabricate":
                reason = "NO_DESCRIPTION"
        if reason:
            for r in recs:
                if r["real"]:
                    dest = os.path.join(out, "_review", reason, r["real"].replace("/", "__"))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copyfile(os.path.join(corpus, r["real"]), dest)
            manifest.append([sources, "review", "", reason])
            continue
        original = cfg["script"] == "original"
        title = book["title"] if original else (book["title_latin"] or book["title"])
        names = [(a["orig"] or a["latin"]) if original else (a["latin"] or a["orig"]) for a in book["authors"]]
        if not names:
            names = [cfg["fallback_author"]]
        author = names[0] if cfg["multi_author"] == "first" else " & ".join(names)
        year = book["first"] if cfg["year_basis"] == "first" else book["edition"]
        sep, n = cfg["sep"], int(cfg["max_len"])
        rel = "library/" + layout.format(year=year, title=slug(title, sep, n), author=slug(author, sep, n))
        if rel in taken:
            manifest.append([sources, "review", "", "CONFLICT"])
            continue
        taken.add(rel)
        desc = book["desc"] or ["No description available."]
        body = "\n\n".join(unicodedata.normalize("NFC", p) for p in desc) + "\n"
        dest = os.path.join(out, *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        manifest.append([sources, "placed", rel, ""])

    _break(out, manifest, cfg.get("break"))
    with open(os.path.join(out, "manifest.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["source", "status", "path", "reason"])
        w.writerows(manifest)
    return {"placed": sum(1 for m in manifest if m[1] == "placed"),
            "review": sum(1 for m in manifest if m[1] == "review")}


def _break(out, manifest, mode):
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
    elif mode == "dup":
        os.makedirs(os.path.join(out, "library", "_copies"), exist_ok=True)
        for k, rel in enumerate(lib):
            shutil.copyfile(os.path.join(out, *rel.split("/")), os.path.join(out, "library", "_copies", f"{k}.txt"))
    elif mode == "reason":
        for m in manifest:
            if m[1] == "review":
                m[3] = ""
                break
