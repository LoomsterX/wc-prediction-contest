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

    # participants
    pids = {}
    for name in DEMO_PLAYERS:
        cur = conn.execute(
            "INSERT INTO participants (name, email, joined_at) VALUES (?,?,?)",
            (name, f"{name.lower()}@example.com", dbmod.now_iso()))
        pids[name] = cur.lastrowid

    group_matches = conn.execute(
        "SELECT * FROM matches WHERE is_knockout=0").fetchall()

    # everyone predicts every group match + outcomes + wildcards
    for name, pid in pids.items():
        for m in group_matches:
            conn.execute(
                "INSERT OR REPLACE INTO match_predictions VALUES (?,?,?,?,?,?)",
                (pid, m["match_id"], random.randint(0, 3), random.randint(0, 3),
                 None, dbmod.now_iso()))
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
            conn.execute(
                "INSERT OR REPLACE INTO outcome_predictions VALUES (?,?,?,?,?)",
                (pid, cat, ref, val, dbmod.now_iso()))
        # wildcards
        for w in conn.execute("SELECT * FROM wildcards"):
            if w["type"] == "number":
                v = str(random.randint(80, 180)) if w["wildcard_id"] == "W01" \
                    else str(random.randint(3, 9))
            elif w["type"] in ("boolean", "choice"):
                v = random.choice(w["options"].split("|"))
            else:
                v = random.choice(teams)
            conn.execute(
                "INSERT OR REPLACE INTO wildcard_predictions VALUES (?,?,?,?)",
                (pid, w["wildcard_id"], v, dbmod.now_iso()))

    # enter results for matchday 1 + 2 so the timeline has movement
    played = conn.execute(
        "SELECT * FROM matches WHERE is_knockout=0 AND matchday IN (1,2)").fetchall()
    for m in played:
        conn.execute(
            "INSERT OR REPLACE INTO match_results VALUES (?,?,?,?)",
            (m["match_id"], random.randint(0, 3), random.randint(0, 3), None))

    # a couple of wildcard results
    conn.execute("INSERT OR REPLACE INTO wildcard_results VALUES ('W01','142')")
    conn.execute("INSERT OR REPLACE INTO wildcard_results VALUES ('W05','UEFA')")
    conn.commit()

    export.export_csvs(conn)
    export.export_dashboard_json(conn)
    conn.close()
    print("Sample data loaded; exports + dashboard/data.json generated.")
    print(f"  CSVs:      {config.EXPORT_DIR}")
    print(f"  Dashboard: {config.DASHBOARD_DIR / 'data.json'}")


if __name__ == "__main__":
    main()
