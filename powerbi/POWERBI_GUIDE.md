# Power BI Dashboard — Build Guide

This contest exports a clean **star schema** to `../exports/` every time you
click *Refresh dashboards* in the app (or run
`uv run python -m wc_contest.export`). Power BI connects to those CSVs, and a
single *Refresh* in Power BI re-pulls the latest standings. No code required.

## 1. Files Power BI will use

From the `exports/` folder:

| File | Role | Grain |
|---|---|---|
| `dim_participants.csv` | Dimension | one row per player |
| `dim_teams.csv` | Dimension | one row per team |
| `dim_matches.csv` | Dimension | one row per match (with result + `date`) |
| `dim_wildcards.csv` | Dimension | one row per wildcard question |
| `fact_leaderboard.csv` | Fact | one row per player (totals + per-category) |
| `fact_match_points.csv` | Fact | one row per player × scored match |
| `fact_points_timeline.csv` | Fact | one row per player × date (cumulative) |

## 2. Load the data

1. Open **Power BI Desktop** → **Get data** → **Text/CSV**.
2. Add each of the seven files above. (Tip: *Get data → Folder*, point it at
   `exports/`, and load them all at once.)
3. Set data types: `date` columns → **Date**; all `*_points`, `points`,
   `rank`, `*_goals`, `*_hits` → **Whole number / Decimal**.

## 3. Model (relationships)

In **Model view**, create these relationships (all single-direction,
one-to-many from the dimension to the fact):

```
dim_participants[participant_id] 1 ──── * fact_leaderboard[participant_id]
dim_participants[participant_id] 1 ──── * fact_match_points[participant_id]
dim_participants[participant_id] 1 ──── * fact_points_timeline[participant_id]
dim_matches[match_id]            1 ──── * fact_match_points[match_id]
```

Optionally add a simple Date table and link it to
`fact_points_timeline[date]` and `dim_matches[date]` for nicer time axes:

```
Date = CALENDAR(DATE(2026,6,11), DATE(2026,7,19))
```

Mark it as a date table, then relate `Date[Date]` → the two `date` columns.

## 4. DAX measures

Create these in `fact_leaderboard` (right-click → *New measure*):

```DAX
Total Points     = SUM ( fact_leaderboard[total_points] )
Match Points     = SUM ( fact_leaderboard[match_points] )
Outcome Points   = SUM ( fact_leaderboard[outcome_points] )
Wildcard Points  = SUM ( fact_leaderboard[wildcard_points] )
Exact Hits       = SUM ( fact_leaderboard[exact_score_hits] )
Players          = DISTINCTCOUNT ( fact_leaderboard[participant_id] )
```

Live rank (so it recalculates even if you filter):

```DAX
Live Rank =
RANKX (
    ALLSELECTED ( dim_participants[name] ),
    [Total Points],
    ,
    DESC,
    Dense
)
```

Cumulative points over time (works on the timeline fact + Date table):

```DAX
Cumulative Points =
CALCULATE (
    SUM ( fact_points_timeline[daily_points] ),
    FILTER (
        ALLSELECTED ( 'Date'[Date] ),
        'Date'[Date] <= MAX ( 'Date'[Date] )
    )
)
```

Matches played (for a KPI card):

```DAX
Matches Played = CALCULATE ( COUNTROWS ( dim_matches ), dim_matches[played] = 1 )
```

## 5. Suggested visuals

| Visual | Type | Fields |
|---|---|---|
| Leaderboard | Table / Matrix | `name`, `[Total Points]`, `[Match Points]`, `[Outcome Points]`, `[Wildcard Points]`, `[Exact Hits]`; sort by Total desc |
| Race over time | Line chart | Axis `Date[Date]`, Values `[Cumulative Points]`, Legend `dim_participants[name]` |
| Points by category | Stacked bar | Axis `name`, Values match/outcome/wildcard points |
| KPI cards | Card | `[Players]`, `[Matches Played]` |
| Per-match drill-down | Matrix | Rows `dim_matches[stage]` › `match_id`, Values `SUM(fact_match_points[points])` |
| Filters | Slicers | `dim_matches[stage]`, `dim_teams[group_code]` |

## 6. Refreshing during the tournament

1. In the app's **Admin** tab, enter the latest results and click
   **Refresh dashboards** (this rewrites the CSVs in `exports/`).
2. In Power BI Desktop, click **Home → Refresh**.
3. To share, **Publish** to the Power BI Service; schedule a refresh against
   the `exports/` folder (or a OneDrive/SharePoint copy of it) so colleagues
   always see current standings.

> The HTML dashboard (`../dashboard/index.html`) reads the same data and
> needs no Power BI — use whichever your audience prefers, or both.
