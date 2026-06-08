"""World Cup 2026 prediction contest - submission & admin app.

Run with:   uv run streamlit run app/streamlit_app.py

Tabs:
  * Join / pick name
  * Match predictions  (scoreline for each match; locks at kickoff)
  * Tournament outcomes (champion, finalists, group winners, golden boot)
  * Wildcards
  * Leaderboard (live)
  * Admin (enter actual results; refresh exports) - password protected
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# make the src package importable when run via streamlit
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wc_contest import config, db as dbmod, scoring, export  # noqa: E402
from wc_contest.config import OUTCOME_POINTS  # noqa: E402

ADMIN_PASSWORD = "worldcup2026"  # CHANGE THIS before sharing the app

st.set_page_config(page_title="WC 2026 Prediction Contest", page_icon="⚽",
                   layout="wide")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
@st.cache_resource
def get_conn():
    conn = dbmod.connect()
    dbmod.init_db(conn)
    # seed if empty
    if conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0] == 0:
        dbmod.generate_seed_csvs()
        dbmod.load_seed(conn)
    return conn


def now():
    return datetime.now(timezone.utc)


def locked_outcomes() -> bool:
    return now() >= config.OUTCOME_DEADLINE


def match_locked(kickoff_iso: str | None) -> bool:
    if not kickoff_iso:
        return False
    try:
        return now() >= datetime.fromisoformat(kickoff_iso)
    except ValueError:
        return False


def team_options(conn):
    return [r["name"] for r in conn.execute("SELECT name FROM teams ORDER BY name")]


def participant_selector(conn, key="who"):
    names = [r["name"] for r in conn.execute(
        "SELECT name FROM participants ORDER BY name")]
    if not names:
        st.info("No participants yet — add yourself on the **Join** tab first.")
        return None
    return st.selectbox("You are:", names, key=key)


def pid_for(conn, name):
    row = conn.execute(
        "SELECT participant_id FROM participants WHERE name=?", (name,)).fetchone()
    return row["participant_id"] if row else None


conn = get_conn()
st.title("⚽ World Cup 2026 — Prediction Contest")

tabs = st.tabs(["🙋 Join", "🎯 Match picks", "🏆 Tournament outcomes",
                "🃏 Wildcards", "📊 Leaderboard", "🔐 Admin"])

# --------------------------------------------------------------------------- #
# Join
# --------------------------------------------------------------------------- #
with tabs[0]:
    st.subheader("Join the contest")
    st.write("Pick a display name (this is how you appear on the leaderboard).")
    with st.form("join"):
        name = st.text_input("Display name")
        email = st.text_input("Email (optional)")
        if st.form_submit_button("Join") and name.strip():
            try:
                conn.execute(
                    "INSERT INTO participants (name, email, joined_at) VALUES (?,?,?)",
                    (name.strip(), email.strip(), dbmod.now_iso()))
                conn.commit()
                st.success(f"Welcome, {name.strip()}! Head to the prediction tabs.")
            except Exception:
                st.warning("That name is already taken — pick another.")
    st.divider()
    n = conn.execute("SELECT COUNT(*) FROM participants").fetchone()[0]
    st.caption(f"{n} participant(s) so far.")

# --------------------------------------------------------------------------- #
# Match picks
# --------------------------------------------------------------------------- #
with tabs[1]:
    st.subheader("Match-by-match predictions")
    st.caption(f"Exact score = {config.MATCH_EXACT_SCORE} pts · "
               f"correct goal difference = {config.MATCH_GOAL_DIFF} pts · "
               f"correct result = {config.MATCH_OUTCOME} pts. "
               "Each match locks at kickoff.")
    who = participant_selector(conn, key="who_match")
    if who:
        pid = pid_for(conn, who)
        stages = [r["stage"] for r in conn.execute(
            "SELECT DISTINCT stage FROM matches ORDER BY is_knockout, stage")]
        # show group matches grouped by group; knockout grouped by stage
        view = st.radio("Show", ["Group stage", "Knockout"], horizontal=True)
        if view == "Group stage":
            groups = [chr(c) for c in range(ord("A"), ord("L") + 1)]
            g = st.selectbox("Group", groups)
            q = ("SELECT * FROM matches WHERE group_code=? "
                 "ORDER BY matchday, match_id")
            matches = conn.execute(q, (g,)).fetchall()
        else:
            ko_stage = st.selectbox("Round", [s for s in stages if s != "Group"])
            matches = conn.execute(
                "SELECT * FROM matches WHERE stage=? ORDER BY match_id",
                (ko_stage,)).fetchall()

        existing = {r["match_id"]: r for r in conn.execute(
            "SELECT * FROM match_predictions WHERE participant_id=?", (pid,))}

        with st.form(f"matchform_{view}"):
            picks = []
            for m in matches:
                locked = match_locked(m["kickoff_utc"])
                ex = existing.get(m["match_id"])
                c1, c2, c3, c4 = st.columns([3, 1, 1, 3])
                c1.markdown(f"**{m['home_label']}**")
                hv = c2.number_input("H", 0, 20,
                                     value=ex["pred_home"] if ex else 0,
                                     key=f"h_{m['match_id']}",
                                     disabled=locked, label_visibility="collapsed")
                av = c3.number_input("A", 0, 20,
                                     value=ex["pred_away"] if ex else 0,
                                     key=f"a_{m['match_id']}",
                                     disabled=locked, label_visibility="collapsed")
                c4.markdown(f"**{m['away_label']}**"
                            + ("  🔒" if locked else ""))
                picks.append((m["match_id"], hv, av, locked))
            if st.form_submit_button("Save match picks"):
                saved = 0
                for mid, hv, av, locked in picks:
                    if locked:
                        continue
                    conn.execute(
                        "INSERT OR REPLACE INTO match_predictions "
                        "(participant_id, match_id, pred_home, pred_away, "
                        "pred_advance, submitted_at) VALUES (?,?,?,?,?,?)",
                        (pid, mid, int(hv), int(av), None, dbmod.now_iso()))
                    saved += 1
                conn.commit()
                st.success(f"Saved {saved} pick(s).")

# --------------------------------------------------------------------------- #
# Tournament outcomes
# --------------------------------------------------------------------------- #
with tabs[2]:
    st.subheader("Tournament outcome predictions")
    if locked_outcomes():
        st.error("Outcome predictions are locked (tournament has kicked off).")
    st.caption("Submitted once. Locks at the opening match on 11 June 2026.")
    who = participant_selector(conn, key="who_out")
    if who and not locked_outcomes():
        pid = pid_for(conn, who)
        teams = team_options(conn)
        ex = {(r["category"], r["ref"]): r["value"] for r in conn.execute(
            "SELECT * FROM outcome_predictions WHERE participant_id=?", (pid,))}

        def pick(label, cat, ref="", opts=None, is_team=True):
            opts = opts or ([""] + teams if is_team else opts)
            cur = ex.get((cat, ref), "")
            idx = opts.index(cur) if cur in opts else 0
            return st.selectbox(label, opts, index=idx, key=f"{cat}_{ref}")

        with st.form("outcomes"):
            st.markdown(f"**Podium** — champion {OUTCOME_POINTS['champion']} pts, "
                        f"runner-up {OUTCOME_POINTS['runner_up']}, "
                        f"3rd {OUTCOME_POINTS['third_place']}")
            champ = pick("🥇 Champion", "champion")
            runner = pick("🥈 Runner-up", "runner_up")
            third = pick("🥉 Third place", "third_place")

            st.markdown(f"**Finalists** ({OUTCOME_POINTS['finalist']} pts each)")
            f1 = pick("Finalist 1", "finalist", "1")
            f2 = pick("Finalist 2", "finalist", "2")

            st.markdown(f"**Semi-finalists** ({OUTCOME_POINTS['semi_finalist']} each)")
            sf = [pick(f"Semi-finalist {i}", "semi_finalist", str(i))
                  for i in range(1, 5)]

            st.markdown(f"**Golden Boot** ({OUTCOME_POINTS['golden_boot']} pts)")
            gb = st.text_input("Top scorer (player name)",
                               value=ex.get(("golden_boot", ""), ""))

            st.markdown(f"**Group winners** ({OUTCOME_POINTS['group_winner']} each)")
            gw = {}
            cols = st.columns(4)
            for i, gcode in enumerate([chr(c) for c in range(ord("A"), ord("L")+1)]):
                gteams = [r["name"] for r in conn.execute(
                    "SELECT name FROM teams WHERE group_code=? ORDER BY name",
                    (gcode,))]
                cur = ex.get(("group_winner", gcode), "")
                idx = ([""]+gteams).index(cur) if cur in gteams else 0
                gw[gcode] = cols[i % 4].selectbox(
                    f"Group {gcode}", [""]+gteams, index=idx, key=f"gw_{gcode}")

            if st.form_submit_button("Save outcome predictions"):
                rows = [("champion", "", champ), ("runner_up", "", runner),
                        ("third_place", "", third),
                        ("finalist", "1", f1), ("finalist", "2", f2),
                        ("golden_boot", "", gb)]
                rows += [("semi_finalist", str(i+1), t) for i, t in enumerate(sf)]
                rows += [("group_winner", g, t) for g, t in gw.items()]
                for cat, ref, val in rows:
                    if not str(val).strip():
                        continue
                    conn.execute(
                        "INSERT OR REPLACE INTO outcome_predictions "
                        "(participant_id, category, ref, value, submitted_at) "
                        "VALUES (?,?,?,?,?)",
                        (pid, cat, ref, str(val).strip(), dbmod.now_iso()))
                conn.commit()
                st.success("Outcome predictions saved.")

# --------------------------------------------------------------------------- #
# Wildcards
# --------------------------------------------------------------------------- #
with tabs[3]:
    st.subheader("Wildcard predictions")
    if locked_outcomes():
        st.error("Wildcards are locked (tournament has kicked off).")
    who = participant_selector(conn, key="who_wild")
    if who and not locked_outcomes():
        pid = pid_for(conn, who)
        ex = {r["wildcard_id"]: r["value"] for r in conn.execute(
            "SELECT * FROM wildcard_predictions WHERE participant_id=?", (pid,))}
        teams = team_options(conn)
        with st.form("wildcards"):
            answers = {}
            for w in conn.execute("SELECT * FROM wildcards ORDER BY wildcard_id"):
                label = f"{w['question']}  ({w['points']:g} pts)"
                cur = ex.get(w["wildcard_id"], "")
                if w["type"] == "number":
                    answers[w["wildcard_id"]] = st.number_input(
                        label, value=float(cur) if cur else 0.0, step=1.0,
                        key=w["wildcard_id"])
                elif w["type"] in ("boolean", "choice"):
                    opts = [""] + w["options"].split("|")
                    idx = opts.index(cur) if cur in opts else 0
                    answers[w["wildcard_id"]] = st.selectbox(
                        label, opts, index=idx, key=w["wildcard_id"])
                elif w["type"] == "team":
                    opts = [""] + teams
                    idx = opts.index(cur) if cur in opts else 0
                    answers[w["wildcard_id"]] = st.selectbox(
                        label, opts, index=idx, key=w["wildcard_id"])
                if w["hint"]:
                    st.caption(w["hint"])
            if st.form_submit_button("Save wildcards"):
                for wid, val in answers.items():
                    if str(val).strip() == "":
                        continue
                    conn.execute(
                        "INSERT OR REPLACE INTO wildcard_predictions "
                        "(participant_id, wildcard_id, value, submitted_at) "
                        "VALUES (?,?,?,?)",
                        (pid, wid, str(val).strip(), dbmod.now_iso()))
                conn.commit()
                st.success("Wildcards saved.")

# --------------------------------------------------------------------------- #
# Leaderboard
# --------------------------------------------------------------------------- #
with tabs[4]:
    st.subheader("Live leaderboard")
    rows = scoring.leaderboard_rows(conn)
    if rows:
        st.dataframe(
            [{"#": r["rank"], "Name": r["name"], "Total": r["total_points"],
              "Match": r["match_points"], "Outcomes": r["outcome_points"],
              "Wildcards": r["wildcard_points"], "Exact scores": r["exact_score_hits"]}
             for r in rows],
            hide_index=True, use_container_width=True)
    else:
        st.info("No participants yet.")

# --------------------------------------------------------------------------- #
# Admin
# --------------------------------------------------------------------------- #
with tabs[5]:
    st.subheader("Admin — enter results")
    pw = st.text_input("Admin password", type="password")
    if pw != ADMIN_PASSWORD:
        st.stop()
    st.success("Admin unlocked.")

    st.markdown("### Match results")
    only_unplayed = st.checkbox("Hide matches that already have a result", True)
    res = {r["match_id"] for r in conn.execute("SELECT match_id FROM match_results")}
    names = {r["team_id"]: r["name"] for r in conn.execute(
        "SELECT team_id, name FROM teams")}
    q = "SELECT * FROM matches ORDER BY kickoff_utc, match_id"
    with st.form("results"):
        entries = []
        for m in conn.execute(q):
            if only_unplayed and m["match_id"] in res:
                continue
            cur = conn.execute("SELECT * FROM match_results WHERE match_id=?",
                               (m["match_id"],)).fetchone()
            c1, c2, c3 = st.columns([4, 1, 1])
            c1.markdown(f"`{m['match_id']}` {m['home_label']} vs {m['away_label']}")
            hg = c2.number_input("H", 0, 20, value=cur["home_goals"] if cur else 0,
                                 key=f"rh_{m['match_id']}",
                                 label_visibility="collapsed")
            ag = c3.number_input("A", 0, 20, value=cur["away_goals"] if cur else 0,
                                 key=f"ra_{m['match_id']}",
                                 label_visibility="collapsed")
            entries.append((m["match_id"], hg, ag))
        if st.form_submit_button("Save match results") and entries:
            for mid, hg, ag in entries:
                conn.execute(
                    "INSERT OR REPLACE INTO match_results "
                    "(match_id, home_goals, away_goals, advance) VALUES (?,?,?,?)",
                    (mid, int(hg), int(ag), None))
            conn.commit()
            st.success(f"Saved {len(entries)} result(s).")

    st.divider()
    st.markdown("### Outcome & wildcard results")
    with st.expander("Enter tournament outcome results"):
        teams = team_options(conn)
        with st.form("outres"):
            ch = st.selectbox("Champion", [""]+teams)
            ru = st.selectbox("Runner-up", [""]+teams)
            tp = st.selectbox("Third place", [""]+teams)
            sf = st.multiselect("Semi-finalists (4)", teams, max_selections=4)
            qf = st.multiselect("Quarter-finalists (8)", teams, max_selections=8)
            gb = st.text_input("Golden Boot (player)")
            st.markdown("**Group winners**")
            gwres = {}
            gcols = st.columns(4)
            for i, gcode in enumerate([chr(c) for c in range(ord("A"), ord("L")+1)]):
                gteams = [r["name"] for r in conn.execute(
                    "SELECT name FROM teams WHERE group_code=? ORDER BY name",
                    (gcode,))]
                gwres[gcode] = gcols[i % 4].selectbox(
                    f"Group {gcode}", [""]+gteams, key=f"gwres_{gcode}")
            if st.form_submit_button("Save outcome results"):
                conn.execute("DELETE FROM outcome_results")
                pairs = [("champion", "", ch), ("runner_up", "", ru),
                         ("third_place", "", tp), ("golden_boot", "", gb)]
                pairs += [("finalist", str(i), t) for i, t in enumerate([ch, ru], 1) if t]
                pairs += [("semi_finalist", str(i), t) for i, t in enumerate(sf, 1)]
                pairs += [("quarter_finalist", str(i), t) for i, t in enumerate(qf, 1)]
                pairs += [("group_winner", g, t) for g, t in gwres.items() if t]
                for cat, ref, val in pairs:
                    if str(val).strip():
                        conn.execute(
                            "INSERT OR REPLACE INTO outcome_results VALUES (?,?,?)",
                            (cat, ref, str(val).strip()))
                conn.commit()
                st.success("Outcome results saved.")

    with st.expander("Enter wildcard results"):
        with st.form("wres"):
            vals = {}
            for w in conn.execute("SELECT * FROM wildcards ORDER BY wildcard_id"):
                vals[w["wildcard_id"]] = st.text_input(
                    f"{w['wildcard_id']}: {w['question']}",
                    key=f"wr_{w['wildcard_id']}")
            if st.form_submit_button("Save wildcard results"):
                for wid, val in vals.items():
                    if str(val).strip():
                        conn.execute(
                            "INSERT OR REPLACE INTO wildcard_results VALUES (?,?)",
                            (wid, str(val).strip()))
                conn.commit()
                st.success("Wildcard results saved.")

    st.divider()
    if st.button("🔄 Refresh dashboards (export CSV + JSON)"):
        export.export_csvs(conn)
        export.export_dashboard_json(conn)
        st.success(f"Exported to {config.EXPORT_DIR} and {config.DASHBOARD_DIR}")
