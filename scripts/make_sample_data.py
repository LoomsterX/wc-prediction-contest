"""Populate the database with fake participants, predictions and some results
so you can see the full pipeline + dashboards working before launch.

    uv run python scripts/make_sample_data.py --yes

⚠️  DESTRUCTIVE: this calls db.build_fresh(), which DROPS AND RECREATES every
table before loading data. It writes to whatever DATABASE_URL points at (or the
local SQLite file if unset). The script prints the target and refuses to run
without --yes, so you can confirm you're aimed at the TEST database — never run
it against production.

This is for DEMO/TESTING only. Run scripts/seed.py afterwards to reset to a
clean, empty-but-seeded database.
"""
from __future__ import annotations

import os
import random
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wc_contest import db as dbmod, config, export, knockout  # noqa: E402
from wc_contest.engine import upsert  # noqa: E402

RNG = random.Random(2026)

DEMO_PLAYERS = ["Sondre", "Ingrid", "Lars", "Mette", "Jonas", "Kari",
                "Erik", "Nina", "Ola", "Silje"]
# A few players "submit" their predictions (final lock) to exercise that flow.
SUBMITTED = {"Sondre", "Ingrid", "Lars"}

GOLDEN_BOOT_NAMES = ["Kylian Mbappé", "Harry Kane", "Vinícius Júnior",
                     "Erling Haaland", "Lautaro Martínez", "Jude Bellingham"]

# Sensible random ranges for the numeric wildcards (by id).
NUMBER_RANGES = {
    "W03": (4, 9),      # golden boot goals
    "W06": (4, 8),      # most goals by one team in a match
    "W08": (2, 14),     # group-stage red cards
    "W10": (700, 1100),  # total corners
    "W11": (12, 45),    # goals by defenders
    "W12": (0, 3),      # goals by goalkeepers
    "W13": (60, 78),    # highest single-match possession %
}

KO_STAGE_IDS = [
    [f"KO_Roundof32_{i}" for i in range(1, 17)],
    [f"KO_Roundof16_{i}" for i in range(1, 9)],
    [f"KO_Quarterfinal_{i}" for i in range(1, 5)],
    [f"KO_Semifinal_{i}" for i in range(1, 3)],
    ["KO_Thirdplace_1", "KO_Final_1"],
]


# --------------------------------------------------------------------------- #
# Safety guard
# --------------------------------------------------------------------------- #
def _target_description() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return f"LOCAL SQLite → {config.DB_PATH}"
    host = urlparse(url.replace("postgres://", "postgresql://", 1)).hostname or "?"
    return f"REMOTE Postgres → host '{host}'"


def _confirm_or_exit() -> None:
    target = _target_description()
    print("=" * 70)
    print("  make_sample_data.py")
    print(f"  TARGET: {target}")
    print("  This DROPS and RECREATES all tables, then loads demo data.")
    print("=" * 70)
    if "--yes" not in sys.argv:
        print("\nRefusing to run without confirmation.")
        print("Re-run with  --yes  once you've checked the TARGET above is your")
        print("TEST database (set DATABASE_URL to the test URL first).")
        sys.exit(1)
    print("--yes given — proceeding.\n")


# --------------------------------------------------------------------------- #
# Value generators
# --------------------------------------------------------------------------- #
def wildcard_value(w, teams) -> str:
    t = w["type"]
    if t == "number":
        lo, hi = NUMBER_RANGES.get(w["wildcard_id"], (1, 10))
        return str(RNG.randint(lo, hi))
    if t in ("bin", "boolean", "choice"):
        return RNG.choice(w["options"].split("|"))
    if t == "team":
        return RNG.choice(teams)
    if t == "text":
        return RNG.choice(GOLDEN_BOOT_NAMES)
    return ""


def fill_knockout(conn, pid) -> None:
    """Walk the rounds in order; each round's match-ups derive from the
    winners of the previous round's saved scorelines."""
    for ids in KO_STAGE_IDS:
        bracket = knockout.resolve_bracket(conn, pid)
        for kid in ids:
            slot = bracket.get(kid, {})
            hid, aid = slot.get("home_id"), slot.get("away_id")
            hg, ag = RNG.randint(0, 3), RNG.randint(0, 3)
            adv = None
            if hg == ag and hid is not None and aid is not None:
                adv = RNG.choice([hid, aid])     # who advances on penalties
            upsert(conn, "match_predictions", {
                "participant_id": pid, "match_id": kid,
                "pred_home": hg, "pred_away": ag, "pred_advance": adv,
                "submitted_at": dbmod.now_iso(),
            }, ["participant_id", "match_id"])


# --------------------------------------------------------------------------- #
def main() -> None:
    _confirm_or_exit()

    dbmod.build_fresh()                 # fresh DB + seed (DROPS everything first)
    conn = dbmod.connect()

    teams = [r["name"] for r in conn.execute("SELECT name FROM teams")]
    wildcards = list(conn.execute("SELECT * FROM wildcards ORDER BY wildcard_id"))
    group_matches = conn.execute(
        "SELECT * FROM matches WHERE is_knockout=0").fetchall()

    palette = ["#e2231a", "#0b3d91", "#f3b521", "#1d9e75", "#7f77dd",
               "#d85a30", "#185fa5", "#0a6b3c", "#111111", "#d4537e"]
    patterns = ["solid", "stripes", "halves", "sash"]

    for i, name in enumerate(DEMO_PLAYERS):
        pid = dbmod.create_participant(
            conn, name, "0000", f"{name.lower()}@example.com",
            favorite_team=RNG.choice(teams),
            favorite_player=RNG.choice(GOLDEN_BOOT_NAMES),
            shirt_primary=palette[i % len(palette)],
            shirt_secondary="#ffffff" if i % 2 == 0 else "#0b1020",
            shirt_pattern=patterns[i % len(patterns)])

        # 1) group-stage scorelines, then "lock in" every group
        for m in group_matches:
            upsert(conn, "match_predictions", {
                "participant_id": pid, "match_id": m["match_id"],
                "pred_home": RNG.randint(0, 3), "pred_away": RNG.randint(0, 3),
                "pred_advance": None, "submitted_at": dbmod.now_iso(),
            }, ["participant_id", "match_id"])
        for g in dbmod.GROUP_CODES:
            dbmod.lock_scope(conn, pid, f"group:{g}")

        # 2) knockout bracket, derived round by round
        fill_knockout(conn, pid)
        for ids in KO_STAGE_IDS:
            stage = conn.execute(
                "SELECT stage FROM matches WHERE match_id=?", (ids[0],)
            ).fetchone()["stage"]
            dbmod.lock_scope(conn, pid, f"ko:{stage}")

        # 3) wildcards
        for w in wildcards:
            upsert(conn, "wildcard_predictions", {
                "participant_id": pid, "wildcard_id": w["wildcard_id"],
                "value": wildcard_value(w, teams), "submitted_at": dbmod.now_iso(),
            }, ["participant_id", "wildcard_id"])

        # 4) a few players submit (final lock)
        if name in SUBMITTED:
            dbmod.lock_scope(conn, pid, "final")

    # ---- enter some actual results so the leaderboard / home bar move ----
    played = conn.execute(
        "SELECT * FROM matches WHERE is_knockout=0 AND matchday IN (1, 2)").fetchall()
    for m in played:
        upsert(conn, "match_results", {
            "match_id": m["match_id"], "home_goals": RNG.randint(0, 3),
            "away_goals": RNG.randint(0, 3), "advance": None,
        }, ["match_id"])

    # a couple of wildcard results (W01 is a bin: enter the actual NUMBER,
    # it's matched to the band automatically by the scorer)
    upsert(conn, "wildcard_results", {"wildcard_id": "W01", "value": "142"}, ["wildcard_id"])
    upsert(conn, "wildcard_results", {"wildcard_id": "W05", "value": "UEFA"}, ["wildcard_id"])
    upsert(conn, "wildcard_results", {"wildcard_id": "W03", "value": "7"}, ["wildcard_id"])

    export.export_csvs(conn)
    export.export_dashboard_json(conn)
    export.export_to_db(conn)           # publish scored tables (feeds Power BI)
    conn.close()

    print("Sample data loaded.")
    print(f"  Target:    {_target_description()}")
    print(f"  Players:   {len(DEMO_PLAYERS)} (PIN 0000; submitted: {', '.join(sorted(SUBMITTED))})")
    print(f"  CSVs:      {config.EXPORT_DIR}")
    print(f"  Dashboard: {config.DASHBOARD_DIR / 'data.json'}")


if __name__ == "__main__":
    main()
