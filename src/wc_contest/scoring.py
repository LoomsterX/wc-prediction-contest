"""Scoring engine.

Computes points for every participant across the three categories
(match-by-match, result-based outcomes, wildcards) by comparing the
predictions in the database against the recorded actual results.

Only matches/outcomes/wildcards that HAVE a recorded result contribute;
everything else scores 0 until results are entered, so the leaderboard
updates naturally as the tournament progresses.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from . import config
from . import db as dbmod


# --------------------------------------------------------------------------- #
# Per-prediction scorers
# --------------------------------------------------------------------------- #
def score_match(pred_h: int, pred_a: int, act_h: int, act_a: int,
                pred_advance: int | None = None,
                act_advance: int | None = None) -> tuple[int, bool]:
    """Return (points, is_exact) for one match prediction."""
    exact = (pred_h == act_h and pred_a == act_a)
    if exact:
        return config.MATCH_EXACT_SCORE, True

    pred_diff = pred_h - pred_a
    act_diff = act_h - act_a
    pred_out = _sign(pred_diff)
    act_out = _sign(act_diff)

    pts = 0
    if pred_out == act_out:
        # correct tendency; better tier if goal difference also matches (non-draw)
        if pred_out != 0 and pred_diff == act_diff:
            pts = config.MATCH_GOAL_DIFF
        else:
            pts = config.MATCH_OUTCOME

    # knockout: bonus for naming the side that advanced even if 90' outcome differed
    if (pred_advance is not None and act_advance is not None
            and pred_advance == act_advance):
        pts += config.KO_ADVANCE_BONUS

    return pts, False


def _sign(x: int) -> int:
    return (x > 0) - (x < 0)


def score_numeric_wildcard(predicted: float, actual: float, points: float) -> float:
    err = abs(predicted - actual)
    for max_err, frac in config.NUMERIC_WILDCARD_BANDS:
        if err <= max_err:
            return round(points * frac, 2)
    return 0.0


def bin_contains(label: str, value: float) -> bool:
    """Whether `value` falls inside a bin label like '<100', '100-109', '300+'."""
    label = str(label).strip()
    try:
        if label.startswith("<"):
            return value < float(label[1:])
        if label.endswith("+"):
            return value >= float(label[:-1])
        lo, hi = label.split("-")
        return float(lo) <= value <= float(hi)
    except (ValueError, AttributeError):
        return False


# --------------------------------------------------------------------------- #
# Result containers
# --------------------------------------------------------------------------- #
@dataclass
class ParticipantScore:
    participant_id: int
    name: str
    match_points: float = 0.0
    outcome_points: float = 0.0
    wildcard_points: float = 0.0
    exact_score_hits: int = 0
    submitted_at: str = "9999"          # earliest submission, for tie-break
    per_match: dict[str, float] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return round(self.match_points + self.outcome_points + self.wildcard_points, 2)


# --------------------------------------------------------------------------- #
# Main computation
# --------------------------------------------------------------------------- #
def compute_scores(conn: sqlite3.Connection) -> list[ParticipantScore]:
    scores: dict[int, ParticipantScore] = {}
    for row in conn.execute("SELECT participant_id, name FROM participants"):
        scores[row["participant_id"]] = ParticipantScore(
            participant_id=row["participant_id"], name=row["name"])

    _score_matches(conn, scores)
    _score_wildcards(conn, scores)
    _track_submission_times(conn, scores)

    ranked = sorted(
        scores.values(),
        key=lambda s: (
            -s.total,
            -s.exact_score_hits,
            -s.wildcard_points,
            s.submitted_at,
        ),
    )
    return ranked


def _score_matches(conn, scores) -> None:
    results = {r["match_id"]: r for r in conn.execute("SELECT * FROM match_results")}
    if not results:
        return
    for p in conn.execute("SELECT * FROM match_predictions"):
        res = results.get(p["match_id"])
        if res is None:
            continue
        pts, exact = score_match(
            p["pred_home"], p["pred_away"],
            res["home_goals"], res["away_goals"],
            p["pred_advance"], res["advance"],
        )
        s = scores.get(p["participant_id"])
        if s is None:
            continue
        s.match_points += pts
        s.per_match[p["match_id"]] = pts
        if exact:
            s.exact_score_hits += 1


def _score_wildcards(conn, scores) -> None:
    actuals = {r["wildcard_id"]: r["value"]
               for r in conn.execute("SELECT * FROM wildcard_results")}
    if not actuals:
        return
    wmeta = {r["wildcard_id"]: r for r in conn.execute("SELECT * FROM wildcards")}
    for p in conn.execute("SELECT * FROM wildcard_predictions"):
        actual = actuals.get(p["wildcard_id"])
        if actual is None:
            continue
        meta = wmeta[p["wildcard_id"]]
        s = scores.get(p["participant_id"])
        if s is None:
            continue
        if meta["type"] == "number":
            try:
                s.wildcard_points += score_numeric_wildcard(
                    float(p["value"]), float(actual), meta["points"])
            except ValueError:
                pass
        elif meta["type"] == "bin":
            # actual is the recorded number; full points if it lands in the band
            try:
                if bin_contains(p["value"], float(actual)):
                    s.wildcard_points += meta["points"]
            except ValueError:
                pass
        else:
            if str(p["value"]).strip().lower() == str(actual).strip().lower():
                s.wildcard_points += meta["points"]


def _track_submission_times(conn, scores) -> None:
    q = """
      SELECT participant_id, MIN(submitted_at) AS first_sub FROM (
        SELECT participant_id, submitted_at FROM match_predictions
        UNION ALL SELECT participant_id, submitted_at FROM outcome_predictions
        UNION ALL SELECT participant_id, submitted_at FROM wildcard_predictions
      ) GROUP BY participant_id
    """
    for r in conn.execute(q):
        s = scores.get(r["participant_id"])
        if s and r["first_sub"]:
            s.submitted_at = r["first_sub"]


def leaderboard_rows(conn: sqlite3.Connection) -> list[dict]:
    """Flat dict rows ready for export / display."""
    out = []
    for rank, s in enumerate(compute_scores(conn), start=1):
        out.append({
            "rank": rank,
            "participant_id": s.participant_id,
            "name": s.name,
            "total_points": s.total,
            "match_points": round(s.match_points, 2),
            "outcome_points": round(s.outcome_points, 2),
            "wildcard_points": round(s.wildcard_points, 2),
            "exact_score_hits": s.exact_score_hits,
        })
    return out


if __name__ == "__main__":
    conn = dbmod.connect()
    for row in leaderboard_rows(conn):
        print(f"{row['rank']:>2}. {row['name']:<20} {row['total_points']:>6}  "
              f"(M {row['match_points']} / O {row['outcome_points']} / "
              f"W {row['wildcard_points']}, exact {row['exact_score_hits']})")
    conn.close()
