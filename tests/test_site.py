"""build-site: every explainer becomes a page in every language, links into case files point at the repository."""

import re

from fdebench2.explain import LANGS, page_name
from fdebench2.site import build_site

from conftest import REPO

GITHUB = "https://github.com/example/FDE-Bench-v2"


def test_site_pages_and_links(tmp_path):
    out = tmp_path / "site"
    pages = build_site(REPO, out, github=GITHUB, ref="main")
    cases = sorted(p.parent.relative_to(REPO / "cases").as_posix() for p in (REPO / "cases").glob("*/*/explainer.html"))
    assert cases and {"index.html", "direction.html", "design.html", "catalog.html", ".nojekyll"} <= {
        p.name for p in out.iterdir()}
    expected = 3
    for lang in LANGS:
        root = out if lang == "en" else out / lang
        prefix = "" if lang == "en" else "../"
        home = (root / "index.html").read_text(encoding="utf-8")
        expected += 1
        assert all(f'href="{c}/index.html"' in home for c in cases)
        for c in cases:
            if not (REPO / "cases" / c / page_name(lang)).is_file():
                continue
            expected += 1
            html = (root / c / "index.html").read_text(encoding="utf-8")
            assert f'<nav class="site-nav"><a href="../../{prefix}{"" if lang == "en" else lang + "/"}index.html">' in html
            # the language switcher reaches the same case in every language
            for other in LANGS:
                target = f"{c}/index.html" if other == "en" else f"{other}/{c}/index.html"
                assert f'href="../../{prefix}{target}"' in html, (lang, other)
            # nothing relative is left except in-page anchors and the site's own pages
            for href in re.findall(r'href="([^"]*)"', html):
                assert href.startswith(("#", GITHUB + "/tree/main/cases/", "../")) or href == GITHUB, (c, href)
    assert len(pages) == expected
