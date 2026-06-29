"""Knockout bracket resolvers.

Two entry points share one resolver (`_resolve_from`):

* ``resolve_bracket(conn, pid)`` — the per-player bracket derived from that
  player's GROUP PREDICTIONS (kept for display; no longer scored).
* ``actual_bracket(conn)`` — the REAL bracket derived from the actual group
  RESULTS (+ actual knockout results), i.e. the same fixtures for everyone.
  Used to auto-fill the real knockout fixtures players predict.

Seeding uses the official 2026 FIFA bracket + Annex C third-place allocation in
``data/knockout_bracket.json``. A knockout match can't end level, so a draw
prediction/result carries an ``advance`` team id; if a match isn't decided yet
its winner is ``None`` and downstream slots stay "to be decided".
"""

from __future__ import annotations

import json
from functools import lru_cache

from . import config


@lru_cache(maxsize=1)
def load_bracket() -> dict:
    with open(config.DATA_DIR / "knockout_bracket.json", encoding="utf-8") as f:
        return json.load(f)


GROUP_CODES = [chr(c) for c in range(ord("A"), ord("L") + 1)]


def _rank_key(r):
    return (-r["Pts"], -r["GD"], -r["GF"], r["team_id"])


def _blank_table(conn):
    teams = {r["team_id"]: dict(team_id=r["team_id"], name=r["name"],
                                group=r["group_code"])
             for r in conn.execute("SELECT team_id, name, group_code FROM teams")}
    tbl: dict[str, dict] = {}
    for tid, t in teams.items():
        if t["group"]:
            tbl.setdefault(t["group"], {})[tid] = dict(
                team_id=tid, name=t["name"], group=t["group"],
                P=0, W=0, D=0, L=0, GF=0, GA=0, GD=0, Pts=0)
    return tbl


def _apply(hrow, arow, hg, ag):
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


# --------------------------------------------------------------------------- #
# Predicted standings (from a participant's group picks)
# --------------------------------------------------------------------------- #
def group_standings(conn, pid) -> dict[str, list[dict]]:
    tbl = _blank_table(conn)
    preds = {p["match_id"]: p for p in conn.execute(
        "SELECT * FROM match_predictions WHERE participant_id=?", (pid,))}
    for m in conn.execute(
            "SELECT match_id, group_code, home_team_id, away_team_id "
            "FROM matches WHERE is_knockout=0"):
        p = preds.get(m["match_id"])
        if not p:
            continue
        hrow = tbl.get(m["group_code"], {}).get(m["home_team_id"])
        arow = tbl.get(m["group_code"], {}).get(m["away_team_id"])
        if hrow is None or arow is None:
            continue
        _apply(hrow, arow, int(p["pred_home"]), int(p["pred_away"]))
    return {g: sorted(rows.values(), key=_rank_key) for g, rows in tbl.items()}


def qualifiers(conn, pid):
    standings = group_standings(conn, pid)
    complete = all(len(standings.get(g, [])) >= 3 for g in GROUP_CODES)
    thirds = [standings[g][2] for g in GROUP_CODES if len(standings.get(g, [])) >= 3]
    best8_groups = sorted(t["group"] for t in sorted(thirds, key=_rank_key)[:8])
    return standings, best8_groups, complete


def resolve_bracket(conn, pid) -> dict[str, dict]:
    """Per-player bracket from their group predictions (display only)."""
    names = {r["team_id"]: r["name"]
             for r in conn.execute("SELECT team_id, name FROM teams")}
    preds = {p["match_id"]: p for p in conn.execute(
        "SELECT * FROM match_predictions WHERE participant_id=?", (pid,))}
    standings, best8_groups, complete = qualifiers(conn, pid)
    return _resolve_from(conn, names, preds, standings, best8_groups, complete,
                         feeders=effective_feeders(conn))


# --------------------------------------------------------------------------- #
# Shared resolver. `preds` maps ko_id -> object with pred_home/pred_away/
# pred_advance (a participant's picks OR the actual results shaped the same way).
# --------------------------------------------------------------------------- #
def _resolve_from(conn, names, preds, standings, best8_groups, complete,
                  r32_teams=None, feeders=None):
    bracket = load_bracket()
    alloc = bracket["third_alloc"].get("".join(best8_groups)) if complete else None

    def pos_team(kind, group):
        rows = standings.get(group, [])
        if kind == "w":
            return rows[0]["team_id"] if len(rows) >= 1 else None
        if kind == "r":
            return rows[1]["team_id"] if len(rows) >= 2 else None
        if kind == "t":
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
    koid_to_num = {v: int(k) for k, v in ko_id_map.items()}

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
        return None, None

    for num in range(73, 105):
        ko_id = ko_id_map[str(num)]
        if 73 <= num <= 88:
            if r32_teams is not None and ko_id in r32_teams:
                # R32 seeded from the REAL admin-set fixtures
                home_id, away_id = r32_teams[ko_id]
                home_label = names.get(home_id) or "TBD"
                away_label = names.get(away_id) or "TBD"
            else:
                d = bracket["r32"][str(num)]
                hk, hg_ = d["home"]
                ak, ag_ = d["away"]
                home_id = pos_team(hk, hg_)
                away_id = pos_team(ak, ag_)
                home_label = names.get(home_id) or pos_label(hk, hg_)
                away_label = names.get(away_id) or pos_label(ak, ag_)
        else:
            if feeders is not None and ko_id in feeders:
                # admin-overridden mapping (sources given as ko_ids)
                hres, hsrc = feeders[ko_id]["home"]
                ares, asrc = feeders[ko_id]["away"]
                hnum, anum = koid_to_num[hsrc], koid_to_num[asrc]
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


# --------------------------------------------------------------------------- #
# ACTUAL standings/bracket — from real match_results (group + knockout)
# --------------------------------------------------------------------------- #
def actual_group_standings(conn) -> dict[str, list[dict]]:
    tbl = _blank_table(conn)
    results = {r["match_id"]: r for r in conn.execute("SELECT * FROM match_results")}
    for m in conn.execute(
            "SELECT match_id, group_code, home_team_id, away_team_id "
            "FROM matches WHERE is_knockout=0"):
        r = results.get(m["match_id"])
        if not r:
            continue
        hrow = tbl.get(m["group_code"], {}).get(m["home_team_id"])
        arow = tbl.get(m["group_code"], {}).get(m["away_team_id"])
        if hrow is None or arow is None:
            continue
        _apply(hrow, arow, int(r["home_goals"]), int(r["away_goals"]))
    return {g: sorted(rows.values(), key=_rank_key) for g, rows in tbl.items()}


def actual_bracket(conn) -> dict[str, dict]:
    """Real bracket from actual results. R32 from real group standings; later
    rounds from real KO results (match_results) + the 'advance' column."""
    names = {r["team_id"]: r["name"]
             for r in conn.execute("SELECT team_id, name FROM teams")}
    standings = actual_group_standings(conn)
    preds = {}
    for r in conn.execute("SELECT * FROM match_results"):
        preds[r["match_id"]] = {
            "pred_home": r["home_goals"], "pred_away": r["away_goals"],
            "pred_advance": r["advance"],
        }
    complete = all(
        sum(row["P"] for row in standings.get(g, [])) >= 12
        for g in GROUP_CODES)
    thirds = [standings[g][2] for g in GROUP_CODES if len(standings.get(g, [])) >= 3]
    best8_groups = sorted(t["group"] for t in sorted(thirds, key=_rank_key)[:8])
    return _resolve_from(conn, names, preds, standings, best8_groups, complete,
                         feeders=effective_feeders(conn))


# --------------------------------------------------------------------------- #
# Per-player ACTUAL bracket: R32 seeded from the admin-set real fixtures, then
# R16 → Final derived from THIS player's predicted winners (actual_ko_predictions).
# --------------------------------------------------------------------------- #
def real_r32_teams(conn) -> dict[str, tuple]:
    """{ko_id: (home_id, away_id)} for Round-of-32 fixtures the admin has set."""
    out = {}
    for m in conn.execute(
            "SELECT match_id, home_team_id, away_team_id FROM matches "
            "WHERE is_knockout=1 AND stage='Round of 32'"):
        if m["home_team_id"] and m["away_team_id"]:
            out[m["match_id"]] = (m["home_team_id"], m["away_team_id"])
    return out


def actual_player_bracket(conn, pid) -> dict[str, dict]:
    names = {r["team_id"]: r["name"]
             for r in conn.execute("SELECT team_id, name FROM teams")}
    preds = {p["match_id"]: p for p in conn.execute(
        "SELECT * FROM actual_ko_predictions WHERE participant_id=?", (pid,))}
    return _resolve_from(conn, names, preds, {}, [], False,
                         r32_teams=real_r32_teams(conn),
                         feeders=effective_feeders(conn))


# --------------------------------------------------------------------------- #
# Feeder mapping (which earlier match feeds each R16+ slot). The official 2026
# bracket is the default; the admin can override any slot's sources, stored in
# the DB. Sources are expressed as ko_ids so the app can edit them directly.
# --------------------------------------------------------------------------- #
def ko_id_order() -> list[str]:
    """All knockout ko_ids in bracket (match-number) order, R32 → Final."""
    ko_id_map = load_bracket()["ko_id"]
    return [ko_id_map[str(n)] for n in range(73, 105)]


def default_feeders() -> dict[str, dict]:
    """Official-bracket sources for each R16+ slot.
    {ko_id: {'home': (res, src_ko_id), 'away': (res, src_ko_id)}}  res = 'W'|'L'."""
    bracket = load_bracket()
    ko_id_map = bracket["ko_id"]
    out: dict[str, dict] = {}
    for num in range(89, 105):
        d = bracket["feeders"][str(num)]
        hres, hnum = d["home"]
        ares, anum = d["away"]
        out[ko_id_map[str(num)]] = {
            "home": (hres, ko_id_map[str(hnum)]),
            "away": (ares, ko_id_map[str(anum)]),
        }
    return out


def effective_feeders(conn) -> dict[str, dict]:
    """Default feeders overlaid with any admin overrides stored in the DB."""
    from . import db as dbmod
    feeders = default_feeders()
    for ko_id, o in (dbmod.get_ko_feeder_overrides(conn) or {}).items():
        if ko_id not in feeders:
            continue
        cur = dict(feeders[ko_id])
        if "home" in o:
            cur["home"] = (o["home"][0], o["home"][1])
        if "away" in o:
            cur["away"] = (o["away"][0], o["away"][1])
        feeders[ko_id] = cur
    return feeders


def feeder_logic(conn=None) -> dict[str, dict]:
    """For R16+ slots: {ko_id: {home: 'Winner of <ko_id>', away: ...}} describing
    where each side comes from. Applies admin overrides when a conn is given."""
    feeders = effective_feeders(conn) if conn is not None else default_feeders()
    word = {"W": "Winner", "L": "Loser"}

    def pretty(src_ko_id):
        return src_ko_id.replace("KO_", "").replace("_", " ")

    out = {}
    for ko_id, f in feeders.items():
        hres, hsrc = f["home"]
        ares, asrc = f["away"]
        out[ko_id] = {
            "home": f"{word[hres]} of {pretty(hsrc)}",
            "away": f"{word[ares]} of {pretty(asrc)}",
        }
    return out
