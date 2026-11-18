## What this changes

<!-- One topic: a case, a translation, a set of client-answer verdicts, a fix. Say what changed and why. -->

Type: new case / translation or native review / client-answer review / bug fix / other

Cases touched: <!-- e.g. finance/loan_underwriting_specialist -->

## Checklist

See CONTRIBUTING.md for the full bar.

- [ ] One topic per pull request.
- [ ] `fdebench2 validate-case` passes for every case touched.
- [ ] `fdebench2 export-dataset` was re-run after any change to a case's code or texts, and `dataset/` is committed.
- [ ] Audited cases: `fdebench2 audit-case` was re-run when the case's sources changed, and `dataset/audit.json` is fresh.
- [ ] New case: quality span ≥ 5%, literal solution ≤ 0.2 and the agent view identical in every setting.
- [ ] All five locales (zh, en, ko, ja, es) updated together; native wording checked where possible.
- [ ] No real personal data; original content only.
- [ ] The catalog and home pages regenerated (`fdebench2 explain-case`) when a case was added or renamed.
- [ ] `python -m pytest -q` passes.
- [ ] Commit messages are plain: what changed and why.
