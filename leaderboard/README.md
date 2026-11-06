# Leaderboard submissions

One JSON file per system, written by `fdebench2 submit` and added by pull request. `fdebench2 build-site` turns
every `*.json` here into the leaderboard page of the site (`leaderboard.html`, and the same table in each language).
How to run, what to send and the rules: [docs/SUBMITTING.md](../docs/SUBMITTING.md).

- Ranked: submissions on private rule seeds with at least 3 trials, ordered by their mean final score.
- Development: any other submission (public rule seeds, fewer trials), shown unranked.
- Reference rows: [EXAMPLE-anchors.json](EXAMPLE-anchors.json) is an **example**, not a model. It holds the cases'
  own anchors (the literal solution, the baseline and the reference) scored offline on the public rule seeds, as
  `fdebench2 try` scores them; the page shows them below the systems as reference rows.
