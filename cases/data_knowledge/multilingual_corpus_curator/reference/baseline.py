"""Baseline organizer for the multilingual corpus curator case (standard library only).

What the client could script without an engineer: organize({"corpus_dir": ..., "out_dir": ...}) shelves only
the books that have a complete JSON export (UTF-8, a title, an author, a plain four-digit year and a
description), under the catalogue rules in config.json, and leaves every other file on the drive for the team.
No other format, no legacy encodings or era years, no merging of copies, no review area and no reason codes.
"""

import csv
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "config.json"), encoding="utf-8") as _f:
    CONFIG = json.load(_f)

LAYOUTS = {"year/title/author": "{year}/{title}/{author}.txt", "year/author/title": "{year}/{author}/{title}.txt",
           "author/year_title": "{author}/{year}_{title}.txt"}
FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')


def slug(s, sep, max_len):
    s = FORBIDDEN.sub(" ", unicodedata.normalize("NFKC", s))
    s = " ".join(s.split()).replace(" ", sep)[:max_len]
    return s.strip(" ." + sep)


def organize(task):
    corpus, out, cfg = task["corpus_dir"], task["out_dir"], CONFIG
    latin = cfg["script"] == "latin"
    sep, n = cfg["sep"], int(cfg["max_len"])
    os.makedirs(os.path.join(out, "library"), exist_ok=True)
    rows, taken = [], set()
    for root, dirs, files in os.walk(corpus):
        dirs.sort()
        for name in sorted(files):
            if not name.lower().endswith(".json"):
                continue
            src = os.path.join(root, name)
            try:
                with open(src, encoding="utf-8") as fh:
                    doc = json.load(fh)
            except (UnicodeDecodeError, ValueError):
                continue
            if not isinstance(doc, dict):
                continue
            title = (latin and doc.get("title_latin")) or doc.get("title")
            names = [(latin and a.get("name_latin")) or a.get("name") for a in doc.get("authors") or []
                     if isinstance(a, dict)]
            names = [x for x in names if x]
            first = str(doc.get("first_published") or "")
            year = first if cfg["year_basis"] == "first" else str(doc.get("edition_year") or first)
            desc = str(doc.get("description") or "").strip()
            if not (title and names and desc and re.fullmatch(r"\d{4}", year)):
                continue
            author = names[0] if cfg["multi_author"] == "first" else " & ".join(names)
            rel = "library/" + LAYOUTS[cfg["layout"]].format(year=year, title=slug(title, sep, n),
                                                             author=slug(author, sep, n))
            if rel in taken:
                continue
            taken.add(rel)
            dest = os.path.join(out, *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(desc + "\n")
            rows.append([os.path.relpath(src, corpus).replace(os.sep, "/"), "placed", rel, ""])
    with open(os.path.join(out, "manifest.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["source", "status", "path", "reason"])
        w.writerows(rows)
    return {"placed": len(rows)}
