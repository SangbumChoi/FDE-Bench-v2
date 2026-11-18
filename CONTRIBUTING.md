# Contributing to FDE-Bench v2

[English](CONTRIBUTING.md) · [中文](docs/zh/CONTRIBUTING.md) · [한국어](docs/ko/CONTRIBUTING.md) · [日本語](docs/ja/CONTRIBUTING.md) · [Español](docs/es/CONTRIBUTING.md)

Thank you for helping. This page says what you can contribute, how a new case is built, the bar it must pass and
what a pull request needs. Background: [README.md](README.md), the case format in [DESIGN.md](DESIGN.md) §3, the
catalog in [cases/README.md](cases/README.md) and the design rules for new cases in
[docs/DIRECTION.md](docs/DIRECTION.md) §5.

## What you can contribute

| Contribution | What it is | Start with |
|---|---|---|
| **A new case** | A role from the catalog ([cases/README.md](cases/README.md), specs in [docs/specs/](docs/specs/README.md)) built to the case contract | An issue with the *Case proposal* template, then the workflow below |
| **A translation or native review** | Fixing or reviewing a locale's texts: `locales/<lang>/` (request, requirements, targets, summary, explainer.yaml), `docs/<lang>/README.md` and `REVIEW.md`, `fdebench2/prompts/*.yaml`, `docs/<lang>/` | A pull request for the locale you read natively; say which files you reviewed |
| **A client-answer review** | A verdict in an audited case's `CLIENT_REVIEW.md`: does the passage each locale's client answers from answer the natural question, correctly and no more? | The section below |
| **A bug report** | Wrong scoring, a validator gap, a crash, a broken page, a client that leaks or invents a rule | An issue with the *Bug report* template |
| **A result submission** | Runs of a model or harness on the benchmark | [docs/SUBMITTING.md](docs/SUBMITTING.md) |

### Client-answer reviews

Each audited case (`audited: true` in case.yaml) has a `CLIENT_REVIEW.md` next to its case.yaml. For every fact it
gives the question an engineer would ask, the line of `requirements.md` each locale's client answers from, and a
machine pre-check. Every `Reviewer verdict:` line is still empty.

- Read the passages in the locales you read natively.
- On the `Reviewer verdict:` line write `OK` or `Problem`, the locales you checked, and for a problem what is
  wrong: a wrong or missing number, an ambiguous answer, or a passage that answers more than was asked.
- `CLIENT_REVIEW.md` is generated (`make_client_review.py` rewrites it). Send verdicts in a pull request of their
  own and do not regenerate the file in it. A fix to the requirements themselves is a separate pull request.

## The case workflow

```bash
fdebench2 new-case <field>/<role>             # add --program when the deliverable is code run on hidden inputs
# write case.yaml and case.py, then every text in all five locales (zh, en, ko, ja, es)
fdebench2 export-dataset cases/<field>/<role> # store data and answers in dataset/; also writes the explainer pages
fdebench2 validate-case cases/<field>/<role>  # the case contract, on the public world and world seeds 1-3
fdebench2 audit-case cases/<field>/<role>     # the ground truth audit, stored in dataset/audit.json
python -m pytest -q                           # the repository's tests
```

1. **Propose.** Open a *Case proposal* issue: the role, the client, the deliverable, the hidden facts and how each
   changes the answer. Pick a role from the catalog or say which field it belongs to (`cases/fields.yaml`).
2. **Scaffold.** `fdebench2 new-case` writes case.yaml, case.py, the five locales and the README in every
   language, every required part marked TODO. Copy patterns from the built cases its docstring names
   (`fdebench2/scaffold.py`).
3. **Write the world and the scorer** in case.py: `build_world`, `write_data`, `reference_solution`,
   `baseline_solution`, `literal_solution`, `score`, `violating_examples`; for an audit also `ablations`,
   `shortcuts`, `robust_solution`, `best_known_solution` or `objective_bound` ([DESIGN.md](DESIGN.md) §3).
4. **Write the texts in five locales:** `locales/<lang>/request.md`, `requirements.md`, `targets.yaml`,
   `summary.yaml`, `explainer.yaml` (not en) and `docs/<lang>/README.md`. Write each language natively, not as a
   word-for-word gloss, with the same target ids, `{{param}}` placeholders and setting markers in every locale.
5. **Export** with `fdebench2 export-dataset`, then **validate** with `fdebench2 validate-case` until it reports
   no problem. Fix warnings or explain them in the case's `docs/en/REVIEW.md`.
6. **Audit** with `fdebench2 audit-case` (10 to 40 minutes). When the case passes it, set `audited: true` and
   run `validate-case` again: an audited case fails when its audit is missing or stale.
7. **Add the case to the catalog** ([cases/README.md](cases/README.md)), regenerate the home pages
   (`fdebench2 explain-case cases/<field>/<role>`), run the tests and open a pull request.

## The bar a case must pass

- `fdebench2 validate-case` reports no problem, on the public world and world seeds 1-3.
- The quality scale is at least 5% wide in every public setting: |reference − baseline| / |reference| ≥ 0.05.
- The literal solution (the request done exactly as written, from the agent's view only) is invalid or scores
  at most 0.2 in every public setting.
- The agent's view (request and files) is byte-identical in every setting; only the client's facts differ.
- Every rule has a class, and exactly one business rule is the bendable habit.
- For an audited case: every client fact bites (misreading only it makes the deliverable invalid or costs at least
  0.10 quality in each tier where it is in force), every shortcut is closed (invalid or at most 0.5), and asking
  is worth at least 0.10 per tier.
- No real personal data: every person, company, address and number is generated.
- Original content only: nothing copied from another benchmark, dataset or document whose terms do not allow it.
  FDE-Bench v2 shares no code or data with other benchmarks.

## Pull request checklist

- [ ] One topic per pull request (a case, a translation, a set of verdicts, a fix).
- [ ] `fdebench2 validate-case` passes for every case touched.
- [ ] `fdebench2 export-dataset` was re-run after any change to a case's code or texts, and `dataset/` is committed.
- [ ] Audited cases: `fdebench2 audit-case` was re-run when the case's sources changed, and `dataset/audit.json` is fresh.
- [ ] New case: quality span ≥ 5%, literal solution ≤ 0.2 and the agent view identical in every setting.
- [ ] All five locales updated together; native wording checked where you can.
- [ ] No real personal data; original content only.
- [ ] The catalog and home pages regenerated (`fdebench2 explain-case`) when a case was added or renamed.
- [ ] `python -m pytest -q` passes.
- [ ] Commit messages are plain: what changed and why.
