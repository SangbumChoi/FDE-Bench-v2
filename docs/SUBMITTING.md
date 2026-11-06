# Submitting results to the leaderboard

Anyone can put a system (a model with a harness) on the FDE-Bench v2 leaderboard: run a campaign, package its
results with `fdebench2 submit`, and open a pull request that adds one file, `leaderboard/<name>.json`. The site
(`fdebench2 build-site`) shows every file in [leaderboard/](../leaderboard/) as a row of the leaderboard page.

## 0. Try a case first (no model, no API key)

```bash
pip install -e .
fdebench2 try                                   # the default case, medium, first public rule seed
fdebench2 try --case logistics/bakery_delivery_dispatcher --difficulty hard --lang ko
fdebench2 try --submission my_deliverable/      # score your own deliverable folder the same way
```

`try` prints what the AI is asked, the files it gets, how many facts only the client knows and the score scale,
then scores the case's literal solution, baseline and reference (and your folder) in that setting under the
default policy. Interaction is scored as in an offline submission: nothing was asked, so Ask-F1 is 0, which the
default policy does not weigh. Without a model to convert files, your folder must hold the deliverable under the
names the evaluator reads (`deliverables:` in the case's `case.yaml`, or `program/` with the entry file for a
program case).

## 1. Run a campaign

Copy `configs/experiments.example.yaml`, list your agent and set the rule seeds and trials:

```yaml
defaults:
  models: configs/models.yaml
  out: runs
  isolation: strict                 # every run in the docker sandbox (docker/Dockerfile.agent)
  sandbox: {kind: docker, image: "fde-bench-agent:latest"}
  rule_seeds: [90211, 90212, 90213] # private rule seeds: any ints outside each case's public panel
  trials: 3                         # at least 3
agents:
  - {harness: reference, model: my-model}
experiments:
  main: {cases: all}
```

```bash
fdebench2 campaign my_campaign.yaml
fdebench2 report runs/                          # check the tables before you package them
```

## 2. Package the results

```bash
fdebench2 submit runs/ --name "My system" --model my-model-2026-10 --harness reference \
    --version 1.2 --flag web_tools=off --flag max_steps=400 --flag budget_usd_per_run=5 \
    --date 2026-11-06 --out leaderboard/my-system.json
```

| Option | Meaning |
|---|---|
| `runs/` | the campaign's results directory (`<agent>/<run key>/result.json`) |
| `--name` | the system's name on the leaderboard |
| `--model`, `--harness` | what the leaderboard shows (default: the runs' own model and harness) |
| `--version` | your system's version |
| `--flag KEY=VALUE` | a setting to disclose; repeatable (web tools, step and token budgets, extra tools, prompts) |
| `--date` | the submission date, `YYYY-MM-DD` (default: today, UTC) |
| `--agent` | the agent label `<harness>--<model>` when the directory holds several agents' runs |
| `--cases` | the cases folder (default `cases/`), used to tell public from private rule seeds and to hash the cases |

It prints the file it wrote and a one-line summary: scored runs, cases, the mean final score with its interval, and
the status (`ranked` or `development`, with the reasons).

## 3. Send it

Open a pull request that adds `leaderboard/<name>.json` (one file per system; a new version of a system replaces its
file). Say in the description how the runs were made: the harness and its version, the budgets, whether web tools
were on, and anything else a reader needs to reproduce them.

## Rules

- **Private rule seeds.** Ranking uses private rule seeds only: ints outside every case's public panel
  (`rule_seeds:` in its `case.yaml`), whose answers are stored nowhere. A submission with any run on a public rule
  seed is marked `development` and shown unranked. Choose fresh seeds; they become public once the submission is
  merged.
- **Trials ≥ 3.** Every variant must run at least 3 times (`trials: 3`); with fewer the submission is `development`.
- **Web tools off, or logged.** A run must not look up the case online. If the harness has web tools, turn them off
  (`--flag web_tools=off`) or keep their logs and say so (`--flag web_tools=logged`).
- **Disclose the harness and budgets.** Name the harness and its version and every budget (steps, tokens, dollars,
  wall time) as flags.
- **The benchmark as released.** Run an unmodified checkout. The submission records the commit and a hash of every
  case's files, so results on other case versions are not compared.
- **No hand edits.** The JSON is what `fdebench2 submit` wrote.

## The format

One JSON object, `"format": "fdebench2-submission/1"`:

| Field | Content |
|---|---|
| `kind` | `"system"` (a submission) or `"anchors"` (the cases' own anchors, see below) |
| `example` | `true` only for the example file |
| `system` | `name`, `model`, `harness`, `version`, `agent_label` (`<harness>--<model>` of the runs), `max_steps`, `flags` (`{key: value}`), `date` |
| `benchmark` | `framework_version`, `git_commit`, `git_dirty` (uncommitted changes under `cases/`, `fdebench2/` or `configs/`), `cases`: `{case id: hash of its files}` (the hash a run's fingerprint uses: the case's files except its docs and stored audit) |
| `seeds` | `kind`: `private`, `public`, `mixed` or `none`, and the `public` and `private` rule seeds used |
| `trials` | the fewest trials any variant ran |
| `status` | `ranked` (private rule seeds only, `trials` ≥ 3) or `development`; `anchor` for the anchors |
| `status_reasons` | why a submission is not ranked |
| `aggregate` | the means below, each `{mean, ci: [low, high], n_cases}`, plus `n_runs`, `n_scored`, `n_cases` and `statuses` (runs per status) |
| `runs` | one record per run (below) |

**Aggregate.** Case-macro means, as `fdebench2 report` computes them: within a case, every rule seed weighs the same
(the mean over a seed's runs, then over the seeds), then every case weighs the same. `ci` is the 95% bootstrap
interval over cases (2000 resamples, fixed seed). Runs that ended in a harness or infrastructure error
(`harness_error`, `infra_error`) are counted in `statuses` and left out of every mean.

| Metric | Meaning |
|---|---|
| `final` | the composite score under the run's policy (0 when a hard gate fails) |
| `validity` | share of runs whose deliverable broke no rule |
| `quality` | normalized quality: the case's baseline 0, its reference 1 (0 when invalid) |
| `ask_f1` | Ask-F1 over the client facts (runs where the client was reachable) |
| `enforced_share` | share of client facts the deliverable implements, over the facts the case's diagnostic measured |
| `cost_usd`, `total_tokens` | per run: solver, client, extractor and judges (a CLI solver's own tokens are not parsed yet) |

**Runs.** Each record: `case`, `tier`, `rule_seed`, `seeds` (`public`, `private`, `unknown` for a case not in this
version, or null), `trial`, `noise_seed`, `customer_locale`, `agent_locale`, `policy`, `engagement`, `condition`,
`world_seed`, `status`, `final`, `valid`, `quality`, `ask_f1`, `targets` (the target funnel: `n` targets, and for
`revealed`, `learned` and `enforced` how many passed and how many were measured, `<stage>_measured`),
`enforced_share`, `cost_usd`, `total_tokens` and the run's own `fingerprint`.

**Anchors.** A file of `kind: "anchors"` holds the cases' literal solution, baseline and reference, scored offline
as `fdebench2 try` scores them, with `anchors: {literal | baseline | reference: aggregate}` instead of `aggregate`
and an `anchor` field on every run. The leaderboard shows them as reference rows, never ranked.
[leaderboard/EXAMPLE-anchors.json](../leaderboard/EXAMPLE-anchors.json) is one, written by
`fdebench2 anchors --difficulty easy --difficulty medium --difficulty hard --out leaderboard/EXAMPLE-anchors.json`
on the public rule seeds; it is an example of the format, not a model.
