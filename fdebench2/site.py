"""`fdebench2 build-site`: the case explainers as a static web site (GitHub Pages).

The site is the stored pages, not a second renderer: cases/index.html becomes the home page, each case's
explainer.html becomes <field>/<role>/index.html, and DESIGN.md, docs/DIRECTION.md and the catalog
(cases/README.md) are rendered with the explainer's markdown renderer. A static host lists no folders, so
links into a case's files (dataset/gt/<setting>/, README.md, ...) point to the same path in the GitHub
repository at the published ref. Every page gets a small navigation bar.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from .cases import discover
from .explain import PAGE, _esc, _shell, build_index, markdown

DOCS = {"direction.html": ("Direction", "docs/DIRECTION.md"), "design.html": ("Design", "DESIGN.md"),
        "catalog.html": ("Catalog", "cases/README.md")}
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


def _nav(depth: int, github: str) -> str:
    up = "../" * depth
    links = [f'<a href="{up}index.html">All cases</a>'] + [
        f'<a href="{up}{page}">{title}</a>' for page, (title, _) in DOCS.items()]
    if github:
        links.append(f'<a href="{_esc(github)}">Source on GitHub</a>')
    return f'<nav class="site-nav">{"".join(links)}</nav>'


def _publish(html: str, *, page_dir: str, depth: int, github: str, ref: str, local: dict[str, str]) -> str:
    """Rewrite one page's relative links for the site and add the navigation bar.

    `page_dir` is the page's folder in the repository; `local` maps repository paths that exist on the site
    to their site URL (relative to the site root).
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
    return html.replace("<body>", "<body>" + _nav(depth, github), 1)


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
    local = {f"cases/{cid}/{PAGE}": f"{cid}/index.html" for cid in cases}
    local |= {f"cases/{cid}": f"{cid}/index.html" for cid in cases}
    local |= {src: page for page, (_, src) in DOCS.items() if (repo / src).is_file()}
    local["cases/index.html"] = "index.html"

    written = []

    def write(rel: str, html: str) -> None:
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        written.append(path)

    write("index.html", _publish(build_index(cases_root), page_dir="cases", depth=0, github=github, ref=ref,
                                 local=local))
    for cid, case in cases.items():
        html = (case.root / PAGE).read_text(encoding="utf-8")
        write(f"{cid}/index.html", _publish(html, page_dir=f"cases/{cid}", depth=cid.count("/") + 1,
                                            github=github, ref=ref, local=local))
    for page, (title, src) in DOCS.items():
        if (repo / src).is_file():
            text = (repo / src).read_text(encoding="utf-8")
            heading = text.splitlines()[0][2:].strip() if text.startswith("# ") else title
            if text.startswith("# "):
                text = text.split("\n", 1)[1] if "\n" in text else ""
            body = (f'<header><p class="eyebrow">FDE-Bench v2</p><h1>{_esc(heading)}</h1></header>'
                    f'<div class="doc">{markdown(text)}</div>')
            write(page, _publish(_shell(f"FDE-Bench v2 — {title}", body, script=False),
                                 page_dir=str(Path(src).parent).replace(os.sep, "/"), depth=0, github=github,
                                 ref=ref, local=local))
    return written
