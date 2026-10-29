"""build-site: every explainer becomes a page, links into case files point at the repository."""

import re

from fdebench2.site import build_site

from conftest import REPO

GITHUB = "https://github.com/example/FDE-Bench-v2"


def test_site_pages_and_links(tmp_path):
    out = tmp_path / "site"
    pages = build_site(REPO, out, github=GITHUB, ref="main")
    cases = sorted(p.parent.relative_to(REPO / "cases").as_posix() for p in (REPO / "cases").glob("*/*/explainer.html"))
    assert cases and all((out / c / "index.html").is_file() for c in cases)
    assert {"index.html", "direction.html", "design.html", "catalog.html", ".nojekyll"} <= {p.name for p in out.iterdir()}
    assert len(pages) == len(cases) + 4
    home = (out / "index.html").read_text(encoding="utf-8")
    assert all(f'href="{c}/index.html"' in home for c in cases)
    for c in cases:
        html = (out / c / "index.html").read_text(encoding="utf-8")
        assert '<nav class="site-nav"><a href="../../index.html">All cases</a>' in html
        # nothing relative is left except in-page anchors and the site's own pages
        for target in re.findall(r'href="([^"]*)"', html):
            assert (target.startswith(("#", GITHUB + "/tree/main/cases/", "../../"))
                    or target == GITHUB), (c, target)
