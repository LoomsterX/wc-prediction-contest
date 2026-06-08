"""Small CLI for the World Cup 2026 prediction contest.

    uv run python main.py seed        # build/reseed the database from the draw
    uv run python main.py sample      # load demo data so you can see it working
    uv run python main.py score       # print the current leaderboard
    uv run python main.py export      # refresh exports/ + dashboard/data.json
    uv run streamlit run app/streamlit_app.py   # the submission/admin app
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    from wc_contest import db, scoring, export, config

    if cmd == "seed":
        db.build_fresh()
        print(f"Built {config.DB_PATH} and seed CSVs in {config.DATA_DIR}")
    elif cmd == "sample":
        import runpy
        runpy.run_path(str(Path(__file__).parent / "scripts" / "make_sample_data.py"),
                       run_name="__main__")
    elif cmd == "score":
        conn = db.connect()
        for r in scoring.leaderboard_rows(conn):
            print(f"{r['rank']:>2}. {r['name']:<20} {r['total_points']:>6}  "
                  f"(M {r['match_points']} / O {r['outcome_points']} / "
                  f"W {r['wildcard_points']}, exact {r['exact_score_hits']})")
        conn.close()
    elif cmd == "export":
        export.export_all()
        print(f"Exports -> {config.EXPORT_DIR}; dashboard JSON -> {config.DASHBOARD_DIR}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
