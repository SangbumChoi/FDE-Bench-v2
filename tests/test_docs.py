"""The documents' layout: each language's documents in docs/<lang>/ (README.md, REVIEW.md, explainer.html), a
generated index README.md at the case root, the catalog's pages in cases/docs/<lang>/. Every link a page or a
Markdown file makes resolves from where it is."""

import os
import re
from pathlib import Path
from urllib.parse import unquote

import pytest

from fdebench2.cli import main
from fdebench2.explain import (LANGS, PAGE, Anchors, build_case_readme, check_page, index_name, markdown, page_name,
                               write_index, write_page)
from fdebench2.validate import check_case

from conftest import REPO
from test_rule_seeds import make_toy

MD_LINK = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_LINK = re.compile(r'(?:href|src)="([^"]*)"')
SKIP = {"dataset", "runs", "site", "node_modules", "__pycache__"}       # generated, or not part of the repository


def _outside_code(text: str) -> str:
    """The text without fenced blocks and inline code spans: a link written inside code is an example."""
    text = re.sub(r"^```.*?^```[^\n]*$", "", text, flags=re.M | re.S)
    return re.sub(r"(`+)(?!`).*?(?<!`)\1(?!`)", "", text, flags=re.S)


def broken(path: Path, links: list[str]) -> list[str]:
    """The relative links among `links` (anchors dropped) that name no existing file or folder from `path`'s folder;
    absolute URLs, mailto: and in-page anchors are not checked."""
    out = []
    for href in links:
        if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", href) or href.startswith(("#", "/")):
            continue
        target = unquote(href.partition("#")[0])
        if target and not (path.parent / target).exists():
            out.append(href)
    return out


def markdown_files(root: Path) -> list[Path]:
    """Every Markdown file of the repository outside dataset/ (and hidden, generated or ignored folders)."""
    found = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP and not d.endswith(".egg-info"))
        found += [Path(folder) / f for f in sorted(files) if f.endswith(".md")]
    return found


def test_every_markdown_link_in_the_repository_resolves():
    files = markdown_files(REPO)
    assert len(files) > 100 and REPO / "cases" / "finance" / "loan_underwriting_specialist" / "docs" / "ko" / "README.md" \
        in files
    bad = {p.relative_to(REPO).as_posix(): links for p in files
           if (links := broken(p, MD_LINK.findall(_outside_code(p.read_text(encoding="utf-8")))))}
    assert bad == {}


def test_no_wrapped_line_starts_like_a_list_item():
    """A paragraph wrapped so that a line begins "2026. " or "1) " renders as a numbered list on GitHub and on
    the case pages. A numbered item directly under a prose line must be item 1 after a line that ends a sentence."""
    marker = re.compile(r"^(\d+)[.)] \S")
    listed = re.compile(r"^\s*(\d+[.)]|[-*+]) ")
    found = []
    for path in markdown_files(REPO):
        lines, fence = path.read_text(encoding="utf-8").split("\n"), False
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                fence = not fence
            m = marker.match(line)
            prev = lines[i - 1] if i else ""
            if fence or not m or not prev.strip() or listed.match(prev) or prev.startswith(("#", "|", ">", "<!--", " ")):
                continue
            if m.group(1) != "1" or not prev.rstrip().endswith((":", "：", ".", "。")):
                found.append(f"{path.relative_to(REPO)}:{i + 1}: {line[:50]}")
    assert found == []


def test_the_layout_of_every_case():
    for case in sorted(p.parent for p in (REPO / "cases").glob("*/*/case.yaml")):
        assert "README.md" in {p.name for p in case.glob("*.md")} <= {"README.md", "GT.md", "CLIENT_REVIEW.md"}, case
        assert not list(case.glob("*.html")), case
        assert {p.name for p in (case / "docs").iterdir()} == set(LANGS), case
        assert (case / "README.md").read_text(encoding="utf-8") == build_case_readme(case)
    assert all((REPO / "cases" / index_name(lang)).is_file() for lang in LANGS)
    assert not list((REPO / "cases").glob("index*.html")) and not list(REPO.glob("README.*.md"))
    assert all((REPO / "docs" / lang / "README.md").is_file() for lang in LANGS if lang != "en")


def _toy_with_docs(tmp_path: Path) -> Path:
    """The toy case with a README and a review in English, a Korean README, GT.md and a catalog, pages written."""
    root = make_toy(tmp_path)
    (tmp_path / "cases" / "README.md").write_text("# Cases\n", encoding="utf-8")
    (root / "GT.md").write_text("# Ground truth\n", encoding="utf-8")
    (root / "docs" / "en" / "README.md").write_text(
        "# Toy\n\nThe [catalog](../../../../README.md), the [review](REVIEW.md#findings), the stored "
        "[answers](../../dataset/answer/answers.csv), the [ground truth](../../GT.md) and [the data](#the-data).\n\n"
        "## The data\n", encoding="utf-8")
    (root / "docs" / "en" / "REVIEW.md").write_text(
        "# Findings\n\n- Back to the [README](README.md); [the data](#the-data).\n\n## The data\n", encoding="utf-8")
    (root / "docs" / "ko" / "README.md").write_text("# 장난감\n\n[정답](../../GT.md), [검토](../en/REVIEW.md)\n",
                                                    encoding="utf-8")
    write_page(root)
    write_index(tmp_path / "cases")
    return root


def test_every_link_of_the_generated_pages_resolves(tmp_path):
    root = _toy_with_docs(tmp_path)
    cases = tmp_path / "cases"
    assert check_page(root) == []
    pages = [root / page_name(lang) for lang in LANGS] + [cases / index_name(lang) for lang in LANGS]
    for page in pages:
        text = page.read_text(encoding="utf-8")
        links = HTML_LINK.findall(text)
        assert links and broken(page, links) == [], page
        # the language switcher: the same page in every language's folder
        assert all(f'../{lang}/{page.name}' in links for lang in LANGS)
        # every in-page link lands on an id of the page: a document's links to its own headings included
        ids = set(re.findall(r'\sid="([^"]*)"', text))
        assert [h for h in links if h.startswith("#") and unquote(h[1:]) not in ids] == [], page
    index = root / "README.md"
    links = MD_LINK.findall(index.read_text(encoding="utf-8"))
    assert broken(index, links) == [] and "GT.md" in links and "CLIENT_REVIEW.md" not in links
    assert {page_name(lang) for lang in LANGS} | {"docs/en/README.md", "docs/ko/README.md", "docs/en/REVIEW.md"} \
        <= set(links)
    # the stored answers: one table, one row per setting (tier x public rule seed), and the folder
    assert {"dataset/answer/answers.csv", "dataset/answer/"} <= set(links)
    assert "docs/ja/README.md" not in links and "docs/ko/REVIEW.md" not in links    # not translated yet: a dash
    # an English README shown on another language's page keeps its links working from there
    zh = (root / page_name("zh")).read_text(encoding="utf-8")
    assert 'href="../en/REVIEW.md#findings"' in zh and 'href="../../GT.md"' in zh
    en = (root / PAGE).read_text(encoding="utf-8")
    assert 'href="REVIEW.md#findings"' in en and 'href="../../dataset/answer/answers.csv"' in en
    # the README and the review on one page: the same heading, one id each, and each document's link finds its own
    assert '<h4 id="readme-the-data">' in en and '<h4 id="review-the-data">' in en
    assert 'href="#readme-the-data"' in en and 'href="#review-the-data"' in en
    # the data section lists every public setting in one table, from answers.csv
    assert en.count("<td><code>1</code></td>") == 3 and "s42" not in en
    assert f'href="../../logistics/toy_planner/{page_name("ja")}"' in (cases / index_name("ja")).read_text(encoding="utf-8")
    # a new translation makes the page that shows it stale, and the index that links it
    stale = "is out of date: run `fdebench2 explain-case` (or export-dataset)"
    (root / "docs" / "ko" / "REVIEW.md").write_text("# 발견 사항\n", encoding="utf-8")
    assert check_page(root) == [f"{page_name('ko')} {stale}", f"README.md {stale}"]
    write_page(root)
    (root / "docs" / "ja" / "REVIEW.md").write_text("# 指摘事項\n", encoding="utf-8")
    assert check_page(root) == [f"{page_name('ja')} {stale}", f"README.md {stale}"]


def test_headings_get_githubs_ids():
    text = ("# Rule seeds (the client's parameters)\n\nSee [the data](#data), [the next one](#data-1) and "
            "[the review](REVIEW.md#data).\n\n## Data\n\n## Data\n\n## データ（規則）\n\n### F3 — `answer/` **moved**\n")
    page = markdown(text, link=lambda href: "../en/" + href, anchors=Anchors("readme-"))
    assert re.findall(r'<h\d id="([^"]*)"', page) == ["readme-rule-seeds-the-clients-parameters", "readme-data",
                                                      "readme-data-1", "readme-データ規則", "readme-f3--answer-moved"]
    assert 'href="#readme-data"' in page and 'href="#readme-data-1"' in page and 'href="../en/REVIEW.md#data"' in page
    plain = markdown(text)                                    # without anchors: no ids, the links as written
    assert " id=" not in plain and 'href="#data"' in plain and 'href="REVIEW.md#data"' in plain


def test_documents_in_the_old_layout_are_a_problem(tmp_path):
    root = _toy_with_docs(tmp_path / "a")
    (root / "docs" / "ko" / "README.md").rename(root / "README.ko.md")
    (root / "docs" / "en" / "REVIEW.md").rename(root / "REVIEW.md")
    (root / page_name("es")).rename(root / "explainer.es.html")
    problems = check_case(root).problems
    assert "README.ko.md: each language's documents are in docs/<lang>/ now: move it to docs/ko/README.md " \
           "(git mv README.ko.md docs/ko/README.md)" in problems
    assert "REVIEW.md: each language's documents are in docs/<lang>/ now: move it to docs/en/REVIEW.md " \
           "(git mv REVIEW.md docs/en/REVIEW.md)" in problems
    assert "explainer.es.html: the explainer pages are docs/<lang>/ now: delete it, `fdebench2 explain-case` writes " \
           "docs/es/explainer.html" in problems
    # the case README itself at the root, with nothing in docs/en/
    other = _toy_with_docs(tmp_path / "b")
    (other / "docs" / "en" / "README.md").replace(other / "README.md")
    assert any(p.startswith("README.md: the case README is docs/en/README.md now and README.md the index")
               for p in check_case(other).problems)


def test_a_review_needs_its_translations(tmp_path):
    root = _toy_with_docs(tmp_path)
    problems = check_case(root).problems
    assert "docs/zh/REVIEW.md is missing (the translation of docs/en/REVIEW.md)" in problems
    assert "docs/ja/README.md is missing (the translation of docs/en/README.md)" in problems
    assert "docs/ko/README.md is missing (the translation of docs/en/README.md)" not in problems


def test_the_cases_glob_skips_the_catalog_pages(tmp_path, capsys):
    root = _toy_with_docs(tmp_path)
    cases = tmp_path / "cases"
    main(["explain-case", str(root), str(cases / "docs" / "en")])
    out, err = capsys.readouterr()
    assert f"{cases / 'docs' / 'en'}: skipped, the catalog's pages (not a case)" in err
    assert str(root / PAGE) in out and check_page(root) == []
    with pytest.raises(SystemExit) as done:
        main(["validate-case", str(cases / "docs" / "ko")])
    assert done.value.code == 2 and "validate-case: no case directory given" in capsys.readouterr().err


def test_the_home_page_links_each_readmes_what_is_different_section():
    from fdebench2.explain import UI, build_index, heading_id
    for lang in LANGS:
        page = REPO / "cases" / index_name(lang)
        assert page.read_text(encoding="utf-8") == build_index(REPO / "cases", lang)      # regenerated
        hrefs = [h for h in HTML_LINK.findall(page.read_text(encoding="utf-8")) if "README.md#" in h]
        assert len(hrefs) == 1 and broken(page, hrefs) == [], lang
        path, _, frag = hrefs[0].partition("#")
        lines = (page.parent / path).read_text(encoding="utf-8").splitlines()
        assert "## " + UI[lang]["diff_heading"] in lines, lang
        assert unquote(frag) in {heading_id(line[3:].strip()) for line in lines if line.startswith("## ")}, lang
