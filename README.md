# World Cup 2026 Prediction Contest

An office prediction competition for the 2026 FIFA World Cup (48 teams,
12 groups, 104 matches, 11 June – 19 July 2026). Colleagues submit predictions
through a small web app; an organiser enters results as matches finish; and the
standings show up on a live HTML dashboard and/or in Power BI.

It covers all three prediction types:

- **Match-by-match** — predict the scoreline of every match.
- **Tournament outcomes** — champion, finalists, semi/quarter-finalists,
  group winners and the Golden Boot.
- **Wildcards** — fun side bets (total goals, penalty-shootout final, dark
  horse, …).

Full scoring is in **[docs/RULES.md](docs/RULES.md)**.

## How it fits together

```
 participants                    organiser
      │ submit picks                  │ enter results
      ▼                               ▼
 ┌──────────────── Streamlit app (app/streamlit_app.py) ───────────────┐
 │  forms + admin   ───────────────►   data/contest.db  (SQLite)        │
 └──────────────────────────────────────────┬──────────────────────────┘
                                             │ scoring engine
                          ┌──────────────────┴───────────────────┐
                          ▼                                       ▼
            exports/*.csv  (Power BI star schema)      dashboard/data.json
                          │                                       │
                          ▼                                       ▼
                   Power BI dashboard                  dashboard/index.html
                  (powerbi/POWERBI_GUIDE.md)            (open in any browser)
```

## Quick start

Prerequisites: [uv](https://docs.astral.sh/uv/) (the repo is a uv/Python 3.13
project).

```bash
# 1. install dependencies
uv sync

# 2. build the database from the official group draw
uv run python main.py seed

# 3. (optional) load demo players + results to see everything working
uv run python main.py sample

# 4. run the submission + admin app
uv run streamlit run app/streamlit_app.py

# 5. open the HTML dashboard
#    open dashboard/index.html in a browser
#    (ships with a small SAMPLE data.json so it renders immediately; it is
#     overwritten with real standings the first time you run an export)
```

`main.py score` prints the leaderboard to the terminal, and `main.py export`
refreshes the dashboards — but day to day you'll just use the app.

## Running the contest

**Before kickoff (by 11 June 2026)**

1. `uv run python main.py seed` to build a clean database.
2. Optionally edit the seed CSVs in `data/` (see below) and re-run seed.
3. **Change two things before sharing:** the admin password near the top of
   `app/streamlit_app.py` (`ADMIN_PASSWORD`), and confirm the matchday 2 & 3
   dates in `data/fixtures.csv` against the official FIFA schedule.
4. Share the app link. Colleagues open it, **Join**, and fill in their match,
   outcome and wildcard predictions. Outcomes and wildcards lock at the opening
   match; each match's scoreline locks at its own kickoff.

**During the tournament**

1. Open the app's **Admin** tab (password protected), enter the actual scores
   for finished matches, and — as rounds resolve — the outcome and wildcard
   results.
2. Click **Refresh dashboards**. This recomputes every score and rewrites
   `exports/*.csv` and `dashboard/data.json`.
3. The HTML dashboard updates on reload; in Power BI click **Refresh**.

Only results you've entered count toward scores, so the leaderboard builds up
naturally as the World Cup progresses.

## Editing the contest

Everything is data-driven and easy to change:

| To change… | Edit… |
|---|---|
| Point values, deadlines, tie-breakers | `src/wc_contest/config.py` |
| Teams / groups | `data/teams.csv` (then re-seed) |
| Fixtures, kickoff times | `data/fixtures.csv` (then re-seed) |
| Wildcard questions | `data/wildcards.csv` (then re-seed) |
| Admin password | `ADMIN_PASSWORD` in `app/streamlit_app.py` |

> Re-seeding (`main.py seed`) rebuilds the database **from scratch** and
> discards any predictions, so finalise your CSV edits *before* launch. Mid
> contest you only ever use the app, never re-seed.

## Layout

```
wc-prediction-contest/
├── main.py                     CLI (seed / sample / score / export)
├── data/                       seed CSVs (teams, fixtures, wildcards) + contest.db
├── src/wc_contest/
│   ├── config.py               all scoring weights, deadlines, paths
│   ├── seed_data.py            official 2026 draw (groups, dates, wildcards)
│   ├── db.py                   SQLite schema, seeding, CSV generation
│   ├── scoring.py              the scoring engine (+ self-test)
│   └── export.py               CSV (Power BI) + JSON (HTML) exports
├── app/streamlit_app.py        submission forms + admin
├── dashboard/index.html        self-contained HTML dashboard (Chart.js)
├── exports/                    star-schema CSVs for Power BI
├── powerbi/POWERBI_GUIDE.md    data model, DAX measures, build steps
├── scripts/                    seed.py, make_sample_data.py
└── docs/RULES.md               contest rules & scoring
```

## Notes & caveats

- **Group composition is the official 5 December 2025 draw.** Matchday-1 dates
  are confirmed; matchday-2/3 dates are spaced approximately — verify them in
  `data/fixtures.csv` before launch. Knockout fixtures start as TBD
  placeholders and the admin fills in the teams as each round is set.
- The database is a single local SQLite file. For a contest of <30 people run
  on one machine (or a shared drive / simple Streamlit deployment) that's
  plenty; predictions are not in version control (see `.gitignore`).
- Golden Boot is a free-text player name; everything else is a dropdown.
