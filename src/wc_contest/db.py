"""Data layer: schema bootstrap, seeding, auth/profile/settings helpers.

Runs on either SQLite (local, default) or Postgres/Supabase (set DATABASE_URL)
via the engine wrapper in engine.py. The schema itself is defined as SQLAlchemy
tables in engine.py so the correct DDL is emitted for each database.

  Dimensions:  participants, teams, matches, wildcards
  Facts:       match_predictions, outcome_predictions, wildcard_predictions
  Actuals:     match_results, outcome_results, wildcard_results
"""

from __future__ import annotations

import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from . import config
from . import seed_data
from . import engine as eng
from .engine import Database, upsert, metadata


# --------------------------------------------------------------------------- #
# Connection / bootstrap
# --------------------------------------------------------------------------- #
def connect(db_path: Path | str | None = None) -> Database:
    return Database(eng.get_engine(db_path))


def init_db(conn: Database) -> None:
    metadata.create_all(conn.engine)
    migrate(conn)


# --------------------------------------------------------------------------- #
# Migration: bring an older SQLite database up to the current participant schema
# (fresh Postgres databases get every column from create_all, so this is a
#  no-op there).
# --------------------------------------------------------------------------- #
_PARTICIPANT_COLUMNS = {
    "pin_hash": "TEXT",
    "favorite_team": "TEXT",
    "favorite_player": "TEXT",
    "shirt_primary": "TEXT DEFAULT '#1801B4'",
    "shirt_secondary": "TEXT DEFAULT '#ffffff'",
    "shirt_pattern": "TEXT DEFAULT 'solid'",
}


def migrate(conn: Database) -> None:
    if conn.dialect != "sqlite":
        return
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(participants)")}
    for col, decl in _PARTICIPANT_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE participants ADD COLUMN {col} {decl}")


# --------------------------------------------------------------------------- #
# Auth, profile & settings helpers
# --------------------------------------------------------------------------- #
def hash_pin(pin: str) -> str:
    return hashlib.sha256(f"wc2026::{pin}".encode()).hexdigest()


def create_participant(conn, name, pin, email="", *, favorite_team="",
                       favorite_player="", shirt_primary="#1801B4",
                       shirt_secondary="#ffffff", shirt_pattern="solid") -> int:
    row = conn.execute(
        """INSERT INTO participants
           (name, email, joined_at, pin_hash, favorite_team, favorite_player,
            shirt_primary, shirt_secondary, shirt_pattern)
           VALUES (?,?,?,?,?,?,?,?,?) RETURNING participant_id""",
        (name, email, now_iso(), hash_pin(pin), favorite_team, favorite_player,
         shirt_primary, shirt_secondary, shirt_pattern)).fetchone()
    return row[0]


def verify_login(conn, name, pin):
    """Return the participant row if name+PIN match, else None."""
    row = conn.execute("SELECT * FROM participants WHERE name=?", (name,)).fetchone()
    if row is None:
        return None
    if row["pin_hash"] and row["pin_hash"] == hash_pin(pin):
        return row
    return None


def update_profile(conn, pid, **fields) -> None:
    allowed = {"favorite_team", "favorite_player", "shirt_primary",
               "shirt_secondary", "shirt_pattern", "email"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    cols = ", ".join(f"{k}=?" for k in sets)
    conn.execute(f"UPDATE participants SET {cols} WHERE participant_id=?",
                 (*sets.values(), pid))


def set_pin(conn, pid, pin) -> None:
    conn.execute("UPDATE participants SET pin_hash=? WHERE participant_id=?",
                 (hash_pin(pin), pid))


def rename_participant(conn, pid, new_name) -> None:
    conn.execute("UPDATE participants SET name=? WHERE participant_id=?",
                 (new_name, pid))


def reset_profile(conn, pid) -> None:
    """Admin: clear a player's profile customisation back to defaults
    (does not touch their predictions or PIN)."""
    conn.execute(
        "UPDATE participants SET favorite_team='', favorite_player='', "
        "shirt_primary='#1801B4', shirt_secondary='#ffffff', shirt_pattern='solid' "
        "WHERE participant_id=?", (pid,))


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value) -> None:
    upsert(conn, "settings", {"key": key, "value": str(value)}, ["key"])


def predictions_locked(conn) -> bool:
    return get_setting(conn, "predictions_locked", "0") == "1"


def set_predictions_locked(conn, locked: bool) -> None:
    set_setting(conn, "predictions_locked", "1" if locked else "0")


# --------------------------------------------------------------------------- #
# Global per-stage admin locks (independent of each player's own lock-in).
# Let the organiser freeze the group stage group-by-group as each kicks off,
# and the knockout / wildcards separately — so late registrants can still enter
# whatever stage is still open.
# --------------------------------------------------------------------------- #
def group_pred_locked(conn, gcode) -> bool:
    return get_setting(conn, f"glock_group_{gcode}", "0") == "1"


def set_group_pred_locked(conn, gcode, locked: bool) -> None:
    set_setting(conn, f"glock_group_{gcode}", "1" if locked else "0")


def any_group_pred_locked(conn) -> bool:
    return any(group_pred_locked(conn, g) for g in GROUP_CODES)


def knockout_pred_locked(conn) -> bool:
    return get_setting(conn, "glock_knockout", "0") == "1"


def set_knockout_pred_locked(conn, locked: bool) -> None:
    set_setting(conn, "glock_knockout", "1" if locked else "0")


def wildcards_pred_locked(conn) -> bool:
    return get_setting(conn, "glock_wildcards", "0") == "1"


def set_wildcards_pred_locked(conn, locked: bool) -> None:
    set_setting(conn, "glock_wildcards", "1" if locked else "0")


def any_stage_locked(conn) -> bool:
    return (any_group_pred_locked(conn) or knockout_pred_locked(conn)
            or wildcards_pred_locked(conn))


# --------------------------------------------------------------------------- #
# ACTUAL knockout (real fixtures everyone predicts) — separate global lock +
# helpers to assign the real teams to knockout `matches` rows. Does NOT affect
# the per-player derived bracket (which ignores matches' KO team ids).
# --------------------------------------------------------------------------- #
def actual_ko_locked(conn) -> bool:
    return get_setting(conn, "glock_actual_ko", "0") == "1"


def set_actual_ko_locked(conn, locked: bool) -> None:
    set_setting(conn, "glock_actual_ko", "1" if locked else "0")


def set_actual_ko_teams(conn, match_id, home_team_id, away_team_id) -> None:
    names = {r["team_id"]: r["name"]
             for r in conn.execute("SELECT team_id, name FROM teams")}
    conn.execute(
        "UPDATE matches SET home_team_id=?, away_team_id=?, home_label=?, "
        "away_label=? WHERE match_id=? AND is_knockout=1",
        (home_team_id, away_team_id, names.get(home_team_id),
         names.get(away_team_id), match_id))


def autofill_actual_ko(conn) -> int:
    """Populate real teams on knockout `matches` rows from the results-derived
    bracket. Returns how many fixtures now have both teams known."""
    from . import knockout
    n = 0
    for ko_id, slot in knockout.actual_bracket(conn).items():
        if slot["home_id"] and slot["away_id"]:
            set_actual_ko_teams(conn, ko_id, slot["home_id"], slot["away_id"])
            n += 1
    return n


# --------------------------------------------------------------------------- #
# Wildcard sync: keep the live `wildcards` table in step with seed_data so that
# question text / type / options / new questions update on existing databases
# (not just freshly-seeded ones).
# --------------------------------------------------------------------------- #
def sync_wildcards(conn: Database) -> None:
    for r in seed_data.WILDCARDS:
        upsert(conn, "wildcards", {
            "wildcard_id": r["wildcard_id"], "question": r["question"],
            "type": r["type"], "options": r["options"],
            "points": float(r["points"]), "hint": r.get("hint", ""),
        }, ["wildcard_id"])


# --------------------------------------------------------------------------- #
# Per-participant prediction locks (group lock-in / knockout / final submit)
# --------------------------------------------------------------------------- #
GROUP_CODES = [chr(c) for c in range(ord("A"), ord("L") + 1)]


def lock_scope(conn, pid, scope) -> None:
    upsert(conn, "pred_locks",
           {"participant_id": pid, "scope": scope, "locked_at": now_iso()},
           ["participant_id", "scope"])


def unlock_scope(conn, pid, scope) -> None:
    conn.execute("DELETE FROM pred_locks WHERE participant_id=? AND scope=?",
                 (pid, scope))


def locked_scopes(conn, pid) -> set[str]:
    return {r["scope"] for r in conn.execute(
        "SELECT scope FROM pred_locks WHERE participant_id=?", (pid,))}


def group_locked(conn, pid, gcode, scopes: set[str] | None = None) -> bool:
    scopes = locked_scopes(conn, pid) if scopes is None else scopes
    return f"group:{gcode}" in scopes


def all_groups_locked(conn, pid, scopes: set[str] | None = None) -> bool:
    scopes = locked_scopes(conn, pid) if scopes is None else scopes
    return all(f"group:{g}" in scopes for g in GROUP_CODES)


def ko_stages_locked(conn, pid, stages, scopes: set[str] | None = None) -> bool:
    scopes = locked_scopes(conn, pid) if scopes is None else scopes
    return bool(stages) and all(f"ko:{s}" in scopes for s in stages)


def final_submitted(conn, pid, scopes: set[str] | None = None) -> bool:
    scopes = locked_scopes(conn, pid) if scopes is None else scopes
    return "final" in scopes


# --------------------------------------------------------------------------- #
# Generate seed CSVs from seed_data (these are the editable source of truth)
# --------------------------------------------------------------------------- #
def generate_seed_csvs() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

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

    fixtures: list[dict] = []
    for group, members in seed_data.GROUPS.items():
        md1 = datetime.fromisoformat(seed_data.GROUP_MD1_DATE[group])
        for md, pairs in seed_data.ROUND_ROBIN.items():
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
# Load CSVs into the dimension tables (dialect-agnostic upserts)
# --------------------------------------------------------------------------- #
def load_seed(conn: Database) -> None:
    with open(config.TEAMS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            upsert(conn, "teams", {
                "team_id": int(r["team_id"]), "name": r["name"],
                "group_code": r["group_code"] or None,
                "confederation": r["confederation"] or None,
                "is_host": int(r["is_host"] or 0),
            }, ["team_id"])
    with open(config.FIXTURES_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            upsert(conn, "matches", {
                "match_id": r["match_id"], "stage": r["stage"],
                "group_code": r["group_code"] or None,
                "matchday": int(r["matchday"]) if r["matchday"] else None,
                "kickoff_utc": r["kickoff_utc"] or None,
                "home_team_id": int(r["home_team_id"]) if r["home_team_id"] else None,
                "away_team_id": int(r["away_team_id"]) if r["away_team_id"] else None,
                "home_label": r["home_label"] or None,
                "away_label": r["away_label"] or None,
                "is_knockout": int(r["is_knockout"] or 0),
            }, ["match_id"])
    with open(config.WILDCARDS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            upsert(conn, "wildcards", {
                "wildcard_id": r["wildcard_id"], "question": r["question"],
                "type": r["type"], "options": r["options"],
                "points": float(r["points"]), "hint": r.get("hint", ""),
            }, ["wildcard_id"])


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_fresh(db_path: Path | str | None = None) -> None:
    """(Re)create all tables from scratch and load the dimensions.

    Destructive: drops existing tables first, so use only for setup / reseeding,
    never mid-contest. Works on both SQLite and Postgres/Supabase.
    """
    generate_seed_csvs()
    engine = eng.get_engine(db_path)
    metadata.drop_all(engine)
    metadata.create_all(engine)
    conn = connect(db_path)
    load_seed(conn)
    conn.close()


if __name__ == "__main__":
    build_fresh()
    print("Database built and seeded.")
