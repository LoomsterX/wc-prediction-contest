"""(Re)build the database and seed CSVs from the official draw data.

    uv run python scripts/seed.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wc_contest import db, config  # noqa: E402

if __name__ == "__main__":
    db.build_fresh()
    print(f"Built {config.DB_PATH}")
    print(f"Seed CSVs in {config.DATA_DIR} (teams.csv, fixtures.csv, wildcards.csv)")
    print("Edit those CSVs and re-run to adjust teams / fixtures / wildcards.")
