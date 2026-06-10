"""Derive a participant's knockout bracket from their group-stage predictions.

The Round of 32 is seeded from the player's predicted group standings (group
winners, runners-up and the eight best third-placed teams) using the official
2026 FIFA bracket + Annex C third-place allocation table, both stored in
``data/knockout_bracket.json``. Every later round is then derived from the
winners of the player's predicted knockout scorelines, so the bracket fills in
as predictions are entered.

A knockout match can't end level, so when a player predicts a draw the winner
is taken from ``match_predictions.pred_advance`` (the advancing team_id). If a
match isn't predicted yet (or a draw has no advance pick), its winner is
``None`` and downstream slots stay "to be decided".
"""

from __future__ import annotations

import json
from functools import lru_cache

from . import config


# --------------------------------------------------------------------------- #
# Bracket template (official mapping) — loaded once
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def load_bracket() -> dict:
    with open(config.DATA_DIR / "knockout_bracket.json", encoding="utf-8") as f:
        return json.load(f)


GROUP_CODES = [chr(c) for c in range(ord("A"), ord("L") + 1)]


# --------------------------------------------------------------------------- #
# Predicted group standings (by team_id) from a participant's match picks
# --------------------------------------------------------------------------- #
def group_standings(conn, pid) -> dict[str, list[dict]]:
    """Return {group_code: [rows]} ordered best-first. Each row has team_id,
    name, group, P/W/D/L/GF/GA/GD/Pts."""
    teams = {r["team_id"]: dict(team_id=r["team_id"], name=r["name"],
                                group=r["group_code"])
             for r in conn.execute(
                 "SELECT team_id, name, group_code FROM teams")}
    tbl: dict[str, dict] = {}
    for tid, t in teams.items():
        if t["group"]:
            tbl.setdefault(t["group"], {})[tid] = dict(
                team_id=tid, name=t["name"], group=t["group"],
                P=0, W=0, D=0, L=0, GF=0, GA=0, GD=0, Pts=0)

    preds = {p["match_id"]: p for p in conn.execute(
        "SELECT * FROM match_predictions WHERE participant_id=?", (pid,))}
    for m in conn.execute(
            "SELECT match_id, group_code, home_team_id, away_team_id "
            "FROM matches WHERE is_knockout=0"):
        p = preds.get(m["match_id"])
        if not p:
            continue
        g = m["group_code"]
        hrow = tbl.get(g, {}).get(m["home_team_id"])
        arow = tbl.get(g, {}).get(m["away_team_id"])
        if hrow is None or arow is None:
            continue
        hg, ag = int(p["pred_home"]), int(p["pred_away"])
        for row, gf, ga in ((hrow, hg, ag), (arow, ag, hg)):
            row["P"] += 1
            row["GF"] += gf
            row["GA"] += ga
            row["GD"] = row["GF"] - row["GA"]
        if hg > ag:
            hrow["W"] += 1; hrow["Pts"] += 3; arow["L"] += 1
        elif hg < ag:
            arow["W"] += 1; arow["Pts"] += 3; hrow["L"] += 1
        else:
            hrow["D"] += 1; arow["D"] += 1; hrow["Pts"] += 1; arow["Pts"] += 1

    out = {}
    for g, rows in tbl.items():
        out[g] = sorted(rows.values(),
                        key=lambda r: (-r["Pts"], -r["GD"], -r["GF"], r["team_id"]))
    return out


def _rank_key(r):
    return (-r["Pts"], -r["GD"], -r["GF"], r["team_id"])


# --------------------------------------------------------------------------- #
# Qualifiers: winners, runners-up, and the best 8 third-placed teams
# --------------------------------------------------------------------------- #
def qualifiers(conn, pid):
    standings = group_standings(conn, pid)
    # only meaningful once every group has a full set of 4 teams ranked
    complete = all(len(standings.get(g, [])) >= 3 for g in GROUP_CODES)
    thirds = []
    for g in GROUP_CODES:
        rows = standings.get(g, [])
        if len(rows) >= 3:
            thirds.append(rows[2])
    thirds_sorted = sorted(thirds, key=_rank_key)
    best8_groups = sorted(t["group"] for t in thirds_sorted[:8])
    return standings, best8_groups, complete


# --------------------------------------------------------------------------- #
# Resolve the full bracket for one participant
# --------------------------------------------------------------------------- #
def resolve_bracket(conn, pid) -> dict[str, dict]:
    """Return {ko_match_id: slot} where slot has:
        home_id, away_id (team_id or None), home_label, away_label,
        winner_id, loser_id, stage, num (official match number).
    """
    bracket = load_bracket()
    names = {r["team_id"]: r["name"]
             for r in conn.execute("SELECT team_id, name FROM teams")}
    preds = {p["match_id"]: p for p in conn.execute(
        "SELECT * FROM match_predictions WHERE participant_id=?", (pid,))}

    standings, best8_groups, complete = qualifiers(conn, pid)
    alloc = bracket["third_alloc"].get("".join(best8_groups)) if complete else None

    def pos_team(kind, group):
        """team_id for a group position, or None if not derivable yet."""
        rows = standings.get(group, [])
        if kind == "w":
            return rows[0]["team_id"] if len(rows) >= 1 else None
        if kind == "r":
            return rows[1]["team_id"] if len(rows) >= 2 else None
        if kind == "t":            # third placed allocated to winner-column `group`
            if not alloc:
                return None
            src = alloc.get(group)
            srows = standings.get(src, [])
            return srows[2]["team_id"] if len(srows) >= 3 else None
        return None

    def pos_label(kind, group):
        word = {"w": "Winner", "r": "Runner-up", "t": "3rd"}[kind]
        if kind == "t":
            return f"3rd place (Group {group} seed)"
        return f"{word} Group {group}"

    resolved: dict[int, dict] = {}
    ko_id_map = bracket["ko_id"]

    def winner_loser(num):
        slot = resolved.get(num)
        if not slot:
            return None, None
        h, a = slot["home_id"], slot["away_id"]
        if h is None or a is None:
            return None, None
        p = preds.get(slot["ko_id"])
        if not p:
            return None, None
        hg, ag = int(p["pred_home"]), int(p["pred_away"])
        if hg > ag:
            return h, a
        if ag > hg:
            return a, h
        adv = p["pred_advance"]
        if adv in (h, a):
            return adv, (a if adv == h else h)
        return None, None          # level score, no advance pick yet

    for num in range(73, 105):
        ko_id = ko_id_map[str(num)]
        if 73 <= num <= 88:
            d = bracket["r32"][str(num)]
            hk, hg_ = d["home"]
            ak, ag_ = d["away"]
            home_id = pos_team(hk, hg_)
            away_id = pos_team(ak, ag_)
            home_label = names.get(home_id) or pos_label(hk, hg_)
            away_label = names.get(away_id) or pos_label(ak, ag_)
        else:
            d = bracket["feeders"][str(num)]
            (hres, hnum) = d["home"]
            (ares, anum) = d["away"]

            def from_feeder(res, src):
                w, l = winner_loser(src)
                tid = w if res == "W" else l
                if tid is not None:
                    return tid, names.get(tid)
                word = "Winner" if res == "W" else "Loser"
                return None, f"{word} of {ko_id_map[str(src)].replace('KO_', '').replace('_', ' ')}"

            home_id, home_label = from_feeder(hres, hnum)
            away_id, away_label = from_feeder(ares, anum)

        win_id, lose_id = (None, None)
        resolved[num] = {
            "num": num, "ko_id": ko_id,
            "home_id": home_id, "away_id": away_id,
            "home_label": home_label, "away_label": away_label,
            "winner_id": None, "loser_id": None,
        }
        w, l = winner_loser(num)
        resolved[num]["winner_id"] = w
        resolved[num]["loser_id"] = l

    return {slot["ko_id"]: slot for slot in resolved.values()}
