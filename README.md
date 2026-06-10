# World Cup 2026 Prediction Contest

An office prediction competition for the 2026 FIFA World Cup (48 teams,
12 groups, 104 matches, 11 June – 19 July 2026). Colleagues submit predictions
through a small web app; an organiser enters results as matches finish; and the
standings show up on a live HTML dashboard and/or in Power BI.

It covers two prediction types:

- **Match-by-match** — predict the scoreline of every match. Lock in each
  group (its filter turns green), then the knockout rounds unlock; once all
  knockout rounds are locked you press **Submit predictions** to freeze them.
- **Wildcards** — fun side bets (banded total goals, penalty-shootout final,
  which host nation goes furthest, Golden Boot winner, dark horse, plus stat
  bets on corners, defender/goalkeeper goals and possession).

Full scoring is in **[docs/RULES.md](docs/RULES.md)**.

### Player experience

- **Accounts (name + PIN):** each player creates an account with a display
  name and a short PIN and logs in from the sidebar. You can only edit your
  own predictions. The admin can reset anyone's PIN.
- **Profile & jersey:** set a favorite team and player, and design a custom
  football kit (two colours + pattern: solid / stripes / halves / sash). Your
  jersey appears in the sidebar and on the leaderboard podium.
- **Navigation:** a sidebar switches between Home, My profile, Match picks,
  Wildcards, Predictions, Matches & results, Leaderboard and Admin. On Match
  picks, group A–L are buttons you click to navigate; each group's button
  turns **green** once you lock it in.
- **Submit flow:** lock in all 12 groups to unlock the knockout rounds; lock
  every knockout round to reveal the **Submit predictions** button, which
  freezes all of that player's picks. An admin can unlock an individual player
  again from the Admin → Manage users panel.
- **Editing stays open** until either the player submits, or the organiser
  flips the global **prediction lock** in the Admin page.
- **Animated podium:** the leaderboard shows a big top-3 podium with crowns,
  jerseys, sparkles and confetti — both in the app and the HTML dashboard.

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
#    (demo players all use PIN "0000" so you can log in as them)
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

### Run it online for everyone (Supabase + Streamlit Cloud)

By default the app stores data in a local SQLite file. To host it online so
colleagues submit from anywhere, set a `DATABASE_URL` and the same code runs on
a free **Supabase** Postgres database, with **Power BI** connecting directly to
live, already-scored tables (`vw_leaderboard`, `vw_match_points`, `vw_timeline`).
Step-by-step: **[SUPABASE_SETUP.md](SUPABASE_SETUP.md)** for the database, then
**[DEPLOY_STREAMLIT.md](DEPLOY_STREAMLIT.md)** to host the app free on Streamlit
Community Cloud. CSV export remains your backup.

## Running the contest

**Before kickoff (by 11 June 2026)**

1. `uv run python main.py seed` to build a clean database.
2. Optionally edit the seed CSVs in `data/` (see below) and re-run seed.
3. **Before sharing:** set the `ADMIN_PASSWORD` secret (it is no longer
   hard-coded — see below), and confirm the matchday 2 & 3 dates in
   `data/fixtures.csv` against the official FIFA schedule.
4. Share the app link. Colleagues open it, create an account (name + PIN),
   design their jersey on **My profile**, and fill in their match and wildcard
   predictions. Editing stays open until they submit (or you lock it).
5. **At the deadline**, open **Admin** and flip the **🔒 Predictions locked**
   toggle on — this freezes everyone's picks. (Flip it off again only if you
   want to reopen editing.)

**During the tournament**

1. Open the app's **Admin** page (password protected), enter the actual scores
   for finished matches, and — as rounds resolve — the wildcard results. (For
   the banded "total goals" wildcard, enter the actual goal *number*; it's
   matched to the band automatically.)
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
| Admin password | `ADMIN_PASSWORD` secret (Streamlit secrets / env var) |

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
