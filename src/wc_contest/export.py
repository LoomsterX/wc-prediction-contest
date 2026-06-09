"""Export the contest data into two consumable shapes:

  1. exports/*.csv  -> tidy star-schema tables for Power BI
  2. dashboard/data.json -> everything the static HTML dashboard needs

Run after entering new results to refresh both dashboards.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from collections import defaultdict

from . import config
from . import db as dbmod
from . import scoring


def _team_names(conn) -> dict[int, str]:
    return {r["team_id"]: r["name"] for r in conn.execute("SELECT team_id, name FROM teams")}


def _matches_resolved(conn) -> list[dict]:
    names = _team_names(conn)
    res = {r["match_id"]: r for r in conn.execute("SELECT * FROM match_results")}
    rows = []
    for m in conn.execute("SELECT * FROM matches ORDER BY kickoff_utc, match_id"):
        r = res.get(m["match_id"])
        home = names.get(m["home_team_id"], m["home_label"])
        away = names.get(m["away_team_id"], m["away_label"])
        rows.append({
            "match_id": m["match_id"],
            "stage": m["stage"],
            "group_code": m["group_code"] or "",
            "matchday": m["matchday"] if m["matchday"] is not None else "",
            "kickoff_utc": m["kickoff_utc"] or "",
            "date": (m["kickoff_utc"] or "")[:10],
            "home_team": home,
            "away_team": away,
            "is_knockout": m["is_knockout"],
            "home_goals": r["home_goals"] if r else "",
            "away_goals": r["away_goals"] if r else "",
            "played": 1 if r else 0,
        })
    return rows


# --------------------------------------------------------------------------- #
# CSV exports for Power BI
# --------------------------------------------------------------------------- #
def export_csvs(conn: sqlite3.Connection) -> None:
    config.EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    _dump(config.EXPORT_DIR / "dim_participants.csv",
          ["participant_id", "name", "email", "joined_at"],
          [dict(r) for r in conn.execute(
              "SELECT participant_id, name, email, joined_at FROM participants")])

    _dump(config.EXPORT_DIR / "dim_teams.csv",
          ["team_id", "name", "group_code", "confederation", "is_host"],
          [dict(r) for r in conn.execute("SELECT * FROM teams")])

    matches = _matches_resolved(conn)
    _dump(config.EXPORT_DIR / "dim_matches.csv",
          ["match_id", "stage", "group_code", "matchday", "kickoff_utc", "date",
           "home_team", "away_team", "is_knockout", "home_goals", "away_goals",
           "played"], matches)

    _dump(config.EXPORT_DIR / "dim_wildcards.csv",
          ["wildcard_id", "question", "type", "options", "points", "hint"],
          [dict(r) for r in conn.execute("SELECT * FROM wildcards")])

    # fact: leaderboard
    lb = scoring.leaderboard_rows(conn)
    _dump(config.EXPORT_DIR / "fact_leaderboard.csv",
          ["rank", "participant_id", "name", "total_points", "match_points",
           "outcome_points", "wildcard_points", "exact_score_hits"], lb)

    # fact: per-match points (drill-down)
    per_match = _fact_match_points(conn)
    _dump(config.EXPORT_DIR / "fact_match_points.csv",
          ["participant_id", "name", "match_id", "date", "stage", "points",
           "is_exact"], per_match)

    # fact: cumulative points over time (per participant, per date)
    timeline = _fact_timeline(conn, per_match)
    _dump(config.EXPORT_DIR / "fact_points_timeline.csv",
          ["participant_id", "name", "date", "daily_points", "cumulative_points"],
          timeline)


def _fact_match_points(conn) -> list[dict]:
    pscores = scoring.compute_scores(conn)
    name_by_id = {s.participant_id: s.name for s in pscores}
    date_by_match = {m["match_id"]: m["date"] for m in _matches_resolved(conn)}
    stage_by_match = {m["match_id"]: m["stage"] for m in _matches_resolved(conn)}
    res = {r["match_id"]: r for r in conn.execute("SELECT * FROM match_results")}
    rows = []
    for p in conn.execute("SELECT * FROM match_predictions"):
        if p["match_id"] not in res:
            continue
        r = res[p["match_id"]]
        pts, exact = scoring.score_match(
            p["pred_home"], p["pred_away"], r["home_goals"], r["away_goals"],
            p["pred_advance"], r["advance"])
        rows.append({
            "participant_id": p["participant_id"],
            "name": name_by_id.get(p["participant_id"], ""),
            "match_id": p["match_id"],
            "date": date_by_match.get(p["match_id"], ""),
            "stage": stage_by_match.get(p["match_id"], ""),
            "points": pts,
            "is_exact": int(exact),
        })
    return rows


def _fact_timeline(conn, per_match) -> list[dict]:
    by_pd: dict[tuple, float] = defaultdict(float)
    names: dict[int, str] = {}
    for row in per_match:
        pid = row["participant_id"]
        names[pid] = row["name"]
        by_pd[(pid, row["date"])] += row["points"]
    out = []
    for pid in names:
        cum = 0.0
        dates = sorted({d for (p, d) in by_pd if p == pid})
        for d in dates:
            daily = by_pd[(pid, d)]
            cum += daily
            out.append({
                "participant_id": pid, "name": names[pid], "date": d,
                "daily_points": round(daily, 2),
                "cumulative_points": round(cum, 2),
            })
    return out


def _dump(path, fieldnames, rows) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


# --------------------------------------------------------------------------- #
# JSON for the HTML dashboard
# --------------------------------------------------------------------------- #
def export_dashboard_json(conn: sqlite3.Connection) -> None:
    config.DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    lb = scoring.leaderboard_rows(conn)
    per_match = _fact_match_points(conn)
    timeline = _fact_timeline(conn, per_match)
    matches = _matches_resolved(conn)

    # attach jersey/profile info to each leaderboard row (for the podium)
    profiles = {}
    try:
        for r in conn.execute(
            "SELECT participant_id, favorite_team, shirt_primary, shirt_secondary, "
            "shirt_pattern FROM participants"):
            profiles[r["participant_id"]] = dict(r)
    except Exception:
        pass
    for r in lb:
        p = profiles.get(r["participant_id"], {})
        r["shirt_primary"] = p.get("shirt_primary") or "#1801B4"
        r["shirt_secondary"] = p.get("shirt_secondary") or "#ffffff"
        r["shirt_pattern"] = p.get("shirt_pattern") or "solid"
        r["favorite_team"] = p.get("favorite_team") or ""

    # timeline -> per-name series for the line chart
    series: dict[str, list[dict]] = defaultdict(list)
    for row in timeline:
        series[row["name"]].append(
            {"date": row["date"], "y": row["cumulative_points"]})

    counts = conn.execute(
        "SELECT COUNT(*) AS n FROM participants").fetchone()["n"]
    played = sum(1 for m in matches if m["played"])

    data = {
        "generated_at": dbmod.now_iso(),
        "meta": {
            "participants": counts,
            "matches_total": len(matches),
            "matches_played": played,
        },
        "leaderboard": lb,
        "timeline": {name: pts for name, pts in series.items()},
        "matches": [m for m in matches if m["played"]],
        "category_breakdown": [
            {"name": r["name"], "match": r["match_points"],
             "outcome": r["outcome_points"], "wildcard": r["wildcard_points"]}
            for r in lb
        ],
    }
    with open(config.DASHBOARD_DIR / "data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def export_to_db(conn) -> None:
    """Write the *scored* tables back into the database so Power BI can read
    already-computed standings directly (no CSV needed).

    Creates/replaces three tables alongside the raw data:
      vw_leaderboard      - one row per player with total + per-category points
      vw_match_points     - one row per player x scored match (drill-down)
      vw_timeline         - cumulative points per player per date
    Power BI connects to these for a ready-made dashboard.
    """
    import pandas as pd

    lb = scoring.leaderboard_rows(conn)
    pm = _fact_match_points(conn)
    tl = _fact_timeline(conn, pm)

    frames = {
        "vw_leaderboard": (lb, ["rank", "participant_id", "name", "total_points",
                                "match_points", "outcome_points", "wildcard_points",
                                "exact_score_hits"]),
        "vw_match_points": (pm, ["participant_id", "name", "match_id", "date",
                                 "stage", "points", "is_exact"]),
        "vw_timeline": (tl, ["participant_id", "name", "date", "daily_points",
                             "cumulative_points"]),
    }
    for name, (rows, cols) in frames.items():
        df = pd.DataFrame(rows, columns=cols)
        df.to_sql(name, conn.engine, if_exists="replace", index=False)


def export_all(db_path=None, to_db=False) -> None:
    conn = dbmod.connect(db_path)
    export_csvs(conn)
    export_dashboard_json(conn)
    if to_db:
        export_to_db(conn)
    conn.close()


if __name__ == "__main__":
    import os
    # When pointed at a hosted DB, also publish the scored tables for Power BI.
    export_all(to_db=bool(os.environ.get("DATABASE_URL")))
    print("Exports written to", config.EXPORT_DIR, "and", config.DASHBOARD_DIR)
