"""Central configuration for the World Cup 2026 prediction contest.

Edit the values here to tune scoring, deadlines and contest behaviour.
Nothing else in the codebase hard-codes these numbers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
EXPORT_DIR = REPO_ROOT / "exports"          # tidy CSVs for Power BI
DASHBOARD_DIR = REPO_ROOT / "dashboard"     # HTML dashboard reads data.json here
DB_PATH = DATA_DIR / "contest.db"

TEAMS_CSV = DATA_DIR / "teams.csv"
FIXTURES_CSV = DATA_DIR / "fixtures.csv"
WILDCARDS_CSV = DATA_DIR / "wildcards.csv"

# --------------------------------------------------------------------------- #
# Deadlines  (all times in UTC)
# --------------------------------------------------------------------------- #
# Tournament kicks off 11 June 2026, opening match in Mexico City.
# Result-based (tournament outcome) and wildcard predictions lock at kickoff.
TOURNAMENT_KICKOFF = datetime(2026, 6, 11, 16, 0, tzinfo=timezone.utc)

# Match-by-match predictions lock individually at each match's own kickoff.
# (See fixtures.csv -> kickoff_utc.)
OUTCOME_DEADLINE = TOURNAMENT_KICKOFF
WILDCARD_DEADLINE = TOURNAMENT_KICKOFF

# --------------------------------------------------------------------------- #
# 1) MATCH-BY-MATCH scoring  (predict the scoreline of every match)
# --------------------------------------------------------------------------- #
# Points are awarded on a best-of basis (you get the highest tier you hit):
MATCH_EXACT_SCORE = 5      # exact scoreline correct, e.g. predicted 2-1, actual 2-1
MATCH_GOAL_DIFF = 3        # correct winner AND correct goal difference (non-draw),
#                            e.g. predicted 2-1, actual 3-2
MATCH_OUTCOME = 2          # correct outcome only (home win / draw / away win)
MATCH_WRONG = 0

# Knockout bonus: predicting which team advances (incl. via pens) when your
# 90-minute outcome was a draw but you still named the right side to go through.
KO_ADVANCE_BONUS = 1

# --------------------------------------------------------------------------- #
# 2) RESULT-BASED scoring  (one-off tournament outcome bracket)
# --------------------------------------------------------------------------- #
OUTCOME_POINTS = {
    "champion": 25,         # predicted the tournament winner
    "runner_up": 15,        # predicted the losing finalist
    "third_place": 8,       # predicted the 3rd-place team
    "finalist": 10,         # each correct finalist (order-independent, 2 teams)
    "semi_finalist": 6,     # each correct semi-finalist (4 teams)
    "quarter_finalist": 3,  # each correct quarter-finalist (8 teams)
    "group_winner": 3,      # each correctly predicted group winner (12 groups)
    "golden_boot": 10,      # top scorer of the tournament
}

# --------------------------------------------------------------------------- #
# 3) WILDCARD scoring is defined per-question in data/wildcards.csv
#    (column `points`). Numeric "closest" wildcards use banded scoring below.
# --------------------------------------------------------------------------- #
# For numeric wildcards (type = number), award by absolute error bands.
# Tuple of (max_abs_error_inclusive, points). First band that matches wins.
NUMERIC_WILDCARD_BANDS = [
    (0, 1.0),    # exact            -> 100% of the question's points
    (3, 0.7),    # within 3         -> 70%
    (7, 0.5),    # within 7         -> 50%
    (15, 0.25),  # within 15        -> 25%
]

# --------------------------------------------------------------------------- #
# Tie-breakers (applied in order, highest wins)
# --------------------------------------------------------------------------- #
TIE_BREAKERS = [
    "exact_score_hits",     # most exact scoreline predictions
    "outcome_points",       # most points from the result-based bracket
    "submitted_first",      # earliest overall submission timestamp
]
