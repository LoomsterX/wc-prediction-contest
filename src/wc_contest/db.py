"""SQLite data layer: schema, seeding and connection helpers.

The schema is a small star schema:

  Dimensions:  participants, teams, matches, wildcards
  Facts:       match_predictions, outcome_predictions, wildcard_predictions
  Actuals:     match_results, outcome_results, wildcard_results

Team identity uses an integer team_id; knockout fixtures keep team ids NULL
until the admin fills them in as the bracket fills out.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config
from . import seed_data


# --------------------------------------------------------------------------- #
# Connection
# --------------------------------------------------------------------------- #
def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS participants (
    participant_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL UNIQUE,
    email          TEXT,
    joined_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
    team_id       INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    group_code    TEXT,
    confederation TEXT,
    is_host       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS matches (
    match_id     TEXT PRIMARY KEY,
    stage        TEXT NOT NULL,          -- 'Group' or knockout stage name
    group_code   TEXT,                   -- A..L for group games, else NULL
    matchday     INTEGER,                -- 1..3 for groups
    kickoff_utc  TEXT,                   -- ISO 8601; drives the per-match lock
    home_team_id INTEGER REFERENCES teams(team_id),
    away_team_id INTEGER REFERENCES teams(team_id),
    home_label   TEXT,                   -- placeholder label for TBD knockout slots
    away_label   TEXT,
    is_knockout  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS wildcards (
    wildcard_id TEXT PRIMARY KEY,
    question    TEXT NOT NULL,
    type        TEXT NOT NULL,           -- number | boolean | choice | team
    options     TEXT,                    -- pipe-separated for boolean/choice
    points      REAL NOT NULL,
    hint        TEXT
);

CREATE TABLE IF NOT EXISTS match_predictions (
    participant_id INTEGER NOT NULL REFERENCES participants(participant_id),
    match_id       TEXT NOT NULL REFERENCES matches(match_id),
    pred_home      INTEGER NOT NULL,
    pred_away      INTEGER NOT NULL,
    pred_advance   INTEGER REFERENCES teams(team_id),  -- knockout: who goes through
    submitted_at   TEXT NOT NULL,
    PRIMARY KEY (participant_id, match_id)
);

CREATE TABLE IF NOT EXISTS outcome_predictions (
    participant_id INTEGER NOT NULL REFERENCES participants(participant_id),
    category       TEXT NOT NULL,        -- champion, runner_up, finalist, ...
    ref            TEXT NOT NULL,        -- group code / slot index / ''
    value          TEXT NOT NULL,        -- team name (or player for golden_boot)
    submitted_at   TEXT NOT NULL,
    PRIMARY KEY (participant_id, category, ref)
);

CREATE TABLE IF NOT EXISTS wildcard_predictions (
    participant_id INTEGER NOT NULL REFERENCES participants(participant_id),
    wildcard_id    TEXT NOT NULL REFERENCES wildcards(wildcard_id),
    value          TEXT NOT NULL,
    submitted_at   TEXT NOT NULL,
    PRIMARY KEY (participant_id, wildcard_id)
);

CREATE TABLE IF NOT EXISTS match_results (
    match_id     TEXT PRIMARY KEY REFERENCES matches(match_id),
    home_goals   INTEGER NOT NULL,
    away_goals   INTEGER NOT NULL,
    advance      INTEGER REFERENCES teams(team_id)  -- knockout winner (after pens)
);

CREATE TABLE IF NOT EXISTS outcome_results (
    category TEXT NOT NULL,
    ref      TEXT NOT NULL,
    value    TEXT NOT NULL,
    PRIMARY KEY (category, ref)
);

CREATE TABLE IF NOT EXISTS wildcard_results (
    wildcard_id TEXT PRIMARY KEY REFERENCES wildcards(wildcard_id),
    value       TEXT NOT NULL
);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


# --------------------------------------------------------------------------- #
# Generate seed CSVs from seed_data (these are the editable source of truth)
# --------------------------------------------------------------------------- #
def generate_seed_csvs() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    # teams.csv
    teams: list[dict] = []
    tid = 1
    name_to_id: dict[str, int] = {}
    for group, members in seed_data.GROUPS.items():
        for name, conf, is_host in members:
            teams.append({
                "team_id": tid, "name": name, "group_code": group,
                "confederation": conf, "is_host": int(is_host),
            })
            name_to_id[name] = tid
            tid += 1
    _write_csv(config.TEAMS_CSV,
               ["team_id", "name", "group_code", "confederation", "is_host"],
               teams)

    # fixtures.csv  (72 group matches + 32 knockout placeholders)
    fixtures: list[dict] = []
    for group, members in seed_data.GROUPS.items():
        md1 = datetime.fromisoformat(seed_data.GROUP_MD1_DATE[group])
        for md, pairs in seed_data.ROUND_ROBIN.items():
            # space matchdays ~4 days apart within the group window
            day = md1.replace() if md == 1 else md1.replace(day=md1.day + (md - 1) * 4)
            for i, (hs, as_) in enumerate(pairs, start=1):
                home = members[hs - 1][0]
                away = members[as_ - 1][0]
                fixtures.append({
                    "match_id": f"G{group}M{md}{i}",
                    "stage": "Group",
                    "group_code": group,
                    "matchday": md,
                    "kickoff_utc": f"{day.date().isoformat()}T18:00:00+00:00",
                    "home_team_id": name_to_id[home],
                    "away_team_id": name_to_id[away],
                    "home_label": home,
                    "away_label": away,
                    "is_knockout": 0,
                })
    # knockout placeholders
    for stage, count, start in seed_data.KNOCKOUT_STAGES:
        for n in range(1, count + 1):
            slug = stage.replace(" ", "").replace("-", "")
            fixtures.append({
                "match_id": f"KO_{slug}_{n}",
                "stage": stage,
                "group_code": "",
                "matchday": "",
                "kickoff_utc": f"{start}T18:00:00+00:00",
                "home_team_id": "",
                "away_team_id": "",
                "home_label": f"{stage} #{n} home (TBD)",
                "away_label": f"{stage} #{n} away (TBD)",
                "is_knockout": 1,
            })
    _write_csv(config.FIXTURES_CSV,
               ["match_id", "stage", "group_code", "matchday", "kickoff_utc",
                "home_team_id", "away_team_id", "home_label", "away_label",
                "is_knockout"],
               fixtures)

    # wildcards.csv
    _write_csv(config.WILDCARDS_CSV,
               ["wildcard_id", "question", "type", "options", "points", "hint"],
               seed_data.WILDCARDS)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


# --------------------------------------------------------------------------- #
# Load CSVs into the dimension tables
# --------------------------------------------------------------------------- #
def load_seed(conn: sqlite3.Connection) -> None:
    with open(config.TEAMS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            conn.execute(
                "INSERT OR REPLACE INTO teams VALUES (?,?,?,?,?)",
                (int(r["team_id"]), r["name"], r["group_code"] or None,
                 r["confederation"] or None, int(r["is_host"] or 0)),
            )
    with open(config.FIXTURES_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            conn.execute(
                "INSERT OR REPLACE INTO matches VALUES (?,?,?,?,?,?,?,?,?,?)",
                (r["match_id"], r["stage"], r["group_code"] or None,
                 int(r["matchday"]) if r["matchday"] else None,
                 r["kickoff_utc"] or None,
                 int(r["home_team_id"]) if r["home_team_id"] else None,
                 int(r["away_team_id"]) if r["away_team_id"] else None,
                 r["home_label"] or None, r["away_label"] or None,
                 int(r["is_knockout"] or 0)),
            )
    with open(config.WILDCARDS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            conn.execute(
                "INSERT OR REPLACE INTO wildcards VALUES (?,?,?,?,?,?)",
                (r["wildcard_id"], r["question"], r["type"], r["options"],
                 float(r["points"]), r.get("hint", "")),
            )
    conn.commit()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_fresh(db_path: Path | str | None = None) -> None:
    """Generate CSVs, (re)create the DB and load the dimensions.

    Any existing database file is removed first so this always produces a
    clean build (predictions in an old DB are discarded - use it only for
    setup / reseeding, not mid-contest).
    """
    generate_seed_csvs()
    path = Path(db_path) if db_path else config.DB_PATH
    for p in (path, path.with_name(path.name + "-journal")):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    conn = connect(path)
    init_db(conn)
    load_seed(conn)
    conn.close()


if __name__ == "__main__":
    build_fresh()
    print("Database built and seeded at", config.DB_PATH)
