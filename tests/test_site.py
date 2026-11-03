"""build-site: every explainer becomes a page in every language, links into case files point at the repository."""

import re

from fdebench2.cases import discover
from fdebench2.explain import LANGS, PAGE, page_name
from fdebench2.site import build_site

from conftest import REPO

GITHUB = "https://github.com/example/FDE-Bench-v2"


def test_site_pages_and_links(tmp_path):
    out = tmp_path / "site"
    pages = build_site(REPO, out, github=GITHUB, ref="main")
    cases = sorted(cid for cid, c in discover(REPO / "cases").items() if (c.root / PAGE).is_file())
    assert cases and {"index.html", "direction.html", "design.html", "catalog.html", ".nojekyll"} <= {
        p.name for p in out.iterdir()}
    expected = 3
    for lang in LANGS:
        root = out if lang == "en" else out / lang
        prefix = "" if lang == "en" else "../"
        home = (root / "index.html").read_text(encoding="utf-8")
        expected += 1
        assert all(f'href="{prefix}{"" if lang == "en" else lang + "/"}{c}/index.html"' in home for c in cases)
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
            # every link into the repository, resolved from the page's folder docs/<lang>/, names a path that exists
            # (the stored answers, GT.md, the catalog's other cases, ...)
            tree = GITHUB + "/tree/main/"
            files = [h[len(tree):].partition("#")[0] for h in re.findall(r'href="([^"]*)"', html) if h.startswith(tree)]
            assert any(f.startswith(f"cases/{c}/dataset/") for f in files), c
            assert [f for f in files if not (REPO / f).exists()] == [], (lang, c)
    assert len(pages) == expected
