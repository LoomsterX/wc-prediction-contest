"""Populate the database with fake participants, predictions AND some results
so you can see the full pipeline + dashboards working before launch.

    uv run python scripts/make_sample_data.py

This is for DEMO/TESTING only. Run scripts/seed.py afterwards to wipe it.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wc_contest import db as dbmod, config, export  # noqa: E402
from wc_contest.engine import upsert  # noqa: E402

random.seed(2026)

DEMO_PLAYERS = ["Sondre", "Ingrid", "Lars", "Mette", "Jonas", "Kari",
                "Erik", "Nina", "Ola", "Silje"]


def main():
    dbmod.build_fresh()  # fresh DB + seed
    conn = dbmod.connect()

    teams = [r["name"] for r in conn.execute("SELECT name FROM teams")]
    group_teams = {}
    for g in [chr(c) for c in range(ord("A"), ord("L") + 1)]:
        group_teams[g] = [r["name"] for r in conn.execute(
            "SELECT name FROM teams WHERE group_code=?", (g,))]

    # participants (all with PIN "0000" for demo + a random jersey + favorites)
    palette = ["#e2231a", "#0b3d91", "#f3b521", "#1d9e75", "#7f77dd",
               "#d85a30", "#185fa5", "#0a6b3c", "#111111", "#d4537e"]
    patterns = ["solid", "stripes", "halves", "sash"]
    pids = {}
    for i, name in enumerate(DEMO_PLAYERS):
        prim = palette[i % len(palette)]
        sec = "#ffffff" if i % 2 == 0 else "#0b1020"
        pid = dbmod.create_participant(
            conn, name, "0000", f"{name.lower()}@example.com",
            favorite_team=random.choice([r["name"] for r in conn.execute("SELECT name FROM teams")]),
            favorite_player=f"Player {random.randint(1, 30)}",
            shirt_primary=prim, shirt_secondary=sec,
            shirt_pattern=patterns[i % len(patterns)])
        pids[name] = pid

    group_matches = conn.execute(
        "SELECT * FROM matches WHERE is_knockout=0").fetchall()

    # everyone predicts every group match + outcomes + wildcards
    for name, pid in pids.items():
        for m in group_matches:
            upsert(conn, "match_predictions", {
                "participant_id": pid, "match_id": m["match_id"],
                "pred_home": random.randint(0, 3), "pred_away": random.randint(0, 3),
                "pred_advance": None, "submitted_at": dbmod.now_iso(),
            }, ["participant_id", "match_id"])
        # outcomes
        champ, ru, third = random.sample(teams, 3)
        sfs = random.sample(teams, 4)
        rows = [("champion", "", champ), ("runner_up", "", ru),
                ("third_place", "", third),
                ("finalist", "1", champ), ("finalist", "2", ru),
                ("golden_boot", "", f"Player {random.randint(1,30)}")]
        rows += [("semi_finalist", str(i+1), t) for i, t in enumerate(sfs)]
        rows += [("group_winner", g, random.choice(ts))
                 for g, ts in group_teams.items()]
        for cat, ref, val in rows:
            upsert(conn, "outcome_predictions", {
                "participant_id": pid, "category": cat, "ref": ref,
                "value": val, "submitted_at": dbmod.now_iso(),
            }, ["participant_id", "category", "ref"])
        # wildcards
        for w in conn.execute("SELECT * FROM wildcards"):
            if w["type"] == "number":
                v = str(random.randint(80, 180)) if w["wildcard_id"] == "W01" \
                    else str(random.randint(3, 9))
            elif w["type"] in ("boolean", "choice"):
                v = random.choice(w["options"].split("|"))
            else:
                v = random.choice(teams)
            upsert(conn, "wildcard_predictions", {
                "participant_id": pid, "wildcard_id": w["wildcard_id"],
                "value": v, "submitted_at": dbmod.now_iso(),
            }, ["participant_id", "wildcard_id"])

    # enter results for matchday 1 + 2 so the timeline has movement
    played = conn.execute(
        "SELECT * FROM matches WHERE is_knockout=0 AND matchday IN (1,2)").fetchall()
    for m in played:
        upsert(conn, "match_results", {
            "match_id": m["match_id"], "home_goals": random.randint(0, 3),
            "away_goals": random.randint(0, 3), "advance": None,
        }, ["match_id"])

    # a couple of wildcard results
    upsert(conn, "wildcard_results", {"wildcard_id": "W01", "value": "142"}, ["wildcard_id"])
    upsert(conn, "wildcard_results", {"wildcard_id": "W05", "value": "UEFA"}, ["wildcard_id"])

    export.export_csvs(conn)
    export.export_dashboard_json(conn)
    export.export_to_db(conn)   # publish scored tables (also feeds Power BI)
    conn.close()
    print("Sample data loaded; exports + dashboard/data.json generated.")
    print(f"  CSVs:      {config.EXPORT_DIR}")
    print(f"  Dashboard: {config.DASHBOARD_DIR / 'data.json'}")


if __name__ == "__main__":
    main()
