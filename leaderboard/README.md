# Leaderboard submissions

One JSON file per system, written by `fdebench2 submit` and added by pull request. `fdebench2 build-site` turns
every `*.json` here into the leaderboard page of the site (`leaderboard.html`, and the same table in each language).
How to run, what to send and the rules: [docs/SUBMITTING.md](../docs/SUBMITTING.md).

- Ranked: submissions that ran a full round of `rounds.yaml` (every case and tier on the round's rule seeds, at
  least 3 trials), ordered by their mean final score within the round. `configs/experiments.leaderboard.yaml` is
  the current round's campaign.
- Development: any other submission (public rule seeds, fewer trials), shown unranked.
- Reference rows: [anchors-2026-11.json](anchors-2026-11.json) is not a model. It holds the cases' own anchors
  (the literal solution, the baseline and the reference) scored offline on the current round's tiers and rule
  seeds, as `fdebench2 try` scores them; the page shows them below the systems as reference rows.
- [rounds.yaml](rounds.yaml): the rounds and their rule seeds.
