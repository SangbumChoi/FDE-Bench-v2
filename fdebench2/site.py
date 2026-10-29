"""`fdebench2 build-site`: the case explainers as a static web site (GitHub Pages).

The site is the stored pages, not a second renderer: cases/index.html becomes the home page, each case's
explainer.html becomes <field>/<role>/index.html, and the other languages' pages (index.<lang>.html,
explainer.<lang>.html) the same paths under <lang>/. DESIGN.md, docs/DIRECTION.md and the catalog
(cases/README.md) are rendered, in English, with the explainer's markdown renderer. A static host lists no
folders, so links into a case's files (dataset/gt/<setting>/, README.md, ...) point to the same path in the
GitHub repository at the published ref. Every page gets a small navigation bar in its language.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from .cases import discover
from .explain import LANGS, PAGE, _esc, _shell, _t, index_name, markdown, page_name

DOCS = {"direction.html": ("site_direction", "docs/DIRECTION.md"), "design.html": ("site_design", "DESIGN.md"),
        "catalog.html": ("site_catalog", "cases/README.md")}
NAV_CSS = (".site-nav{max-width:1100px;margin:0 auto;padding:12px 16px;font-size:14px;"
           "border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:4px 16px}"
           ".site-nav a{color:var(--accent);text-decoration:none}.site-nav a:hover{text-decoration:underline}")
LINK = re.compile(r'(href|src)="([^"#][^"]*)"')


def _git(repo: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def source_url(repo: Path) -> tuple[str, str]:
    """(https://github.com/<owner>/<repo>, ref): from the Actions environment, else from git."""
    if os.environ.get("GITHUB_REPOSITORY"):
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        return f"{server}/{os.environ['GITHUB_REPOSITORY']}", os.environ.get("GITHUB_REF_NAME", "main")
    url = _git(repo, "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    return (f"https://github.com/{m.group(1)}" if m else ""), (_git(repo, "rev-parse", "--abbrev-ref", "HEAD") or "main")


def _site_path(rel: str, lang: str) -> str:
    """A page's path on the site: English at the root, every other language under <lang>/."""
    return rel if lang == "en" else f"{lang}/{rel}"


def _nav(lang: str, up: str, github: str) -> str:
    english = "" if lang == "en" else " " + _t(lang, "site_english_only")
    links = [f'<a href="{up}{_site_path("index.html", lang)}">{_t(lang, "site_cases")}</a>'] + [
        f'<a href="{up}{page}">{_t(lang, key)}{english}</a>' for page, (key, _) in DOCS.items()]
    if github:
        links.append(f'<a href="{_esc(github)}">{_t(lang, "site_source")}</a>')
    return f'<nav class="site-nav">{"".join(links)}</nav>'


def _publish(html: str, *, page_dir: str, depth: int, lang: str, github: str, ref: str,
             local: dict[str, str]) -> str:
    """Rewrite one page's relative links for the site and add the navigation bar.

    `page_dir` is the page's folder in the repository, `depth` its folder depth on the site; `local` maps
    repository paths that exist on the site to their site URL (relative to the site root).
    """
    up = "../" * depth

    def fix(m: re.Match) -> str:
        attr, target = m.group(1), m.group(2)
        if re.match(r"[a-z]+:", target) or target.startswith("/"):
            return m.group(0)
        path, _, frag = target.partition("#")
        repo_path = os.path.normpath(os.path.join(page_dir, path)).replace(os.sep, "/")
        if repo_path in local:
            new = up + local[repo_path]
        elif github:
            new = f"{github}/tree/{ref}/{repo_path}"
        else:
            return m.group(0)
        return f'{attr}="{_esc(new)}{"#" + frag if frag else ""}"'

    html = LINK.sub(fix, html)
    html = html.replace("</style>", NAV_CSS + "</style>", 1)
    return html.replace("<body>", "<body>" + _nav(lang, up, github), 1)


def build_site(repo: Path, out: Path, github: str | None = None, ref: str | None = None) -> list[Path]:
    """Write the site into `out` (emptied first). Returns the pages written."""
    repo = Path(repo).resolve()
    found_url, found_ref = source_url(repo)
    github, ref = (github if github is not None else found_url).rstrip("/"), ref or found_ref
    cases_root = repo / "cases"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / ".nojekyll").write_text("", encoding="utf-8")

    cases = {cid: c for cid, c in discover(cases_root).items() if (c.root / PAGE).is_file()}
    langs = [l for l in LANGS if l == "en" or (cases_root / index_name(l)).is_file()]
    local = {f"cases/{cid}": f"{cid}/index.html" for cid in cases}
    for lang in langs:     # a case not yet translated links to its English page
        local |= {f"cases/{cid}/{page_name(lang)}": _site_path(f"{cid}/index.html", lang)
                  if (c.root / page_name(lang)).is_file() else f"{cid}/index.html" for cid, c in cases.items()}
        local[f"cases/{index_name(lang)}"] = _site_path("index.html", lang)
    local |= {src: page for page, (_, src) in DOCS.items() if (repo / src).is_file()}

    written = []

    def write(rel: str, html: str) -> None:
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        written.append(path)

    for lang in langs:
        extra = 0 if lang == "en" else 1
        index = (cases_root / index_name(lang)).read_text(encoding="utf-8")
        write(_site_path("index.html", lang), _publish(index, page_dir="cases", depth=extra, lang=lang,
                                                       github=github, ref=ref, local=local))
        for cid, case in cases.items():
            page = case.root / page_name(lang)
            if page.is_file():
                write(_site_path(f"{cid}/index.html", lang),
                      _publish(page.read_text(encoding="utf-8"), page_dir=f"cases/{cid}",
                               depth=cid.count("/") + 1 + extra, lang=lang, github=github, ref=ref, local=local))
    for page, (key, src) in DOCS.items():
        if (repo / src).is_file():
            text = (repo / src).read_text(encoding="utf-8")
            heading = text.splitlines()[0][2:].strip() if text.startswith("# ") else _t("en", key)
            if text.startswith("# "):
                text = text.split("\n", 1)[1] if "\n" in text else ""
            body = (f'<header><p class="eyebrow">FDE-Bench v2</p><h1>{_esc(heading)}</h1></header>'
                    f'<div class="doc">{markdown(text)}</div>')
            write(page, _publish(_shell(f"FDE-Bench v2 — {heading}", body, script=False),
                                 page_dir=str(Path(src).parent).replace(os.sep, "/"), depth=0, lang="en",
                                 github=github, ref=ref, local=local))
    return written
