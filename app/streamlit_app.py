"""World Cup 2026 prediction contest - submission & admin app.

Run with:   uv run streamlit run app/streamlit_app.py

Features:
  * Name + PIN login (you can only edit your own predictions)
  * Profile: favorite team / player + a customizable jersey avatar
  * Sidebar navigation between pages
  * Group picker with a "lock in" submit per group
  * Admin lock that freezes all predictions after the deadline
  * Fancy animated top-3 podium on the leaderboard
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wc_contest import config, db as dbmod, scoring, export, avatar  # noqa: E402
from wc_contest.config import OUTCOME_POINTS  # noqa: E402

ADMIN_PASSWORD = "worldcup2026"  # CHANGE THIS before sharing the app

st.set_page_config(
    page_title="WC 2026 Prediction Contest", page_icon="⚽", layout="wide"
)


# --------------------------------------------------------------------------- #
# Connection + global styling
# --------------------------------------------------------------------------- #
@st.cache_resource
def get_conn():
    conn = dbmod.connect()
    dbmod.init_db(conn)
    if conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0] == 0:
        dbmod.generate_seed_csvs()
        dbmod.load_seed(conn)
    return conn


conn = get_conn()

st.markdown(
    """
<style>
  .stApp { background: radial-gradient(1200px 600px at 50% -10%,
           rgba(47,129,247,0.10), transparent 60%); }
  .wc-hero {
    border-radius: 18px; padding: 26px 30px; color: #fff;
    background: linear-gradient(120deg,#0b3d91 0%,#1a73e8 45%,#00c2a8 100%);
    background-size: 200% 200%; animation: wcflow 12s ease infinite;
    box-shadow: 0 10px 30px rgba(11,61,145,0.35); position: relative;
    overflow: hidden;
  }
  @keyframes wcflow { 0%{background-position:0% 50%} 50%{background-position:100% 50%}
                      100%{background-position:0% 50%} }
  .wc-hero h1 { margin:0; font-size:30px; }
  .wc-hero p { margin:6px 0 0; opacity:.9; }
  .wc-hero .ball { position:absolute; right:24px; top:18px; font-size:64px;
                   animation: spin 8s linear infinite; }
  @keyframes spin { from{transform:rotate(0)} to{transform:rotate(360deg)} }

  /* podium */
  .podium-wrap { display:flex; justify-content:center; align-items:flex-end;
                 gap:18px; margin:18px 0 8px; flex-wrap:nowrap; }
  .podium { text-align:center; position:relative; }
  .pod-card { display:flex; flex-direction:column; align-items:center; gap:6px; }
  .pod-name { font-weight:700; font-size:16px; }
  .pod-pts { font-size:13px; opacity:.8; }
  .pedestal { border-radius:14px 14px 6px 6px; width:120px;
              display:flex; align-items:flex-start; justify-content:center;
              color:#08213f; font-weight:800; padding-top:8px; font-size:34px;
              box-shadow: inset 0 -8px 0 rgba(0,0,0,0.12); }
  .p1 .pedestal { height:150px; background:linear-gradient(180deg,#ffe27a,#f3b521);
                  animation: glow 2.4s ease-in-out infinite; }
  .p2 .pedestal { height:110px; background:linear-gradient(180deg,#e9eef3,#b8c2cc); }
  .p3 .pedestal { height:88px;  background:linear-gradient(180deg,#f0b483,#cd7f32); }
  @keyframes glow { 0%,100%{box-shadow:inset 0 -8px 0 rgba(0,0,0,.12),
        0 0 0 rgba(243,181,33,0)} 50%{box-shadow:inset 0 -8px 0 rgba(0,0,0,.12),
        0 0 28px rgba(243,181,33,.8)} }
  .crown { font-size:30px; animation: bob 2s ease-in-out infinite; }
  @keyframes bob { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-6px)} }
  .jersey-badge { filter: drop-shadow(0 4px 6px rgba(0,0,0,.25)); }
  .spark { position:absolute; width:8px; height:8px; border-radius:50%;
           background:#fff; opacity:.0; animation: sparkle 2.2s linear infinite; }
  @keyframes sparkle { 0%{opacity:0; transform:scale(.4) translateY(0)}
        30%{opacity:1} 100%{opacity:0; transform:scale(1.1) translateY(-26px)} }
  .lock-banner { border-radius:12px; padding:10px 16px; font-weight:600;
                 margin-bottom:10px; }
  .lock-on  { background:#fde7e7; color:#a11; border:1px solid #f3b1b1; }
  .lock-off { background:#e7f7ee; color:#0a6b3c; border:1px solid #a9ddc1; }
  .id-card { background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.12);
             border-radius:14px; padding:12px; text-align:center; }
</style>
""",
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Session / auth helpers
# --------------------------------------------------------------------------- #
def ss():
    return st.session_state


for k, v in {
    "pid": None,
    "pname": None,
    "is_admin": False,
    "sel_group": "A",
    "balloons_done": False,
}.items():
    ss().setdefault(k, v)


def logged_in() -> bool:
    return ss().pid is not None


def editing_open() -> bool:
    return not dbmod.predictions_locked(conn)


def jersey_img(primary, secondary, pattern, size=64, cls="jersey-badge"):
    uri = avatar.data_uri(
        primary or "#2f81f7", secondary or "#ffffff", pattern or "solid", size
    )
    return f'<img class="{cls}" src="{uri}" width="{size}" height="{size}" />'


def my_row():
    return conn.execute(
        "SELECT * FROM participants WHERE participant_id=?", (ss().pid,)
    ).fetchone()


def team_options():
    return [r["name"] for r in conn.execute("SELECT name FROM teams ORDER BY name")]


# --------------------------------------------------------------------------- #
# Sidebar: identity + login + navigation
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### ⚽ WC 2026 Contest")

    if logged_in():
        r = my_row()
        st.markdown(
            f'<div class="id-card">{jersey_img(r["shirt_primary"], r["shirt_secondary"], r["shirt_pattern"], 72)}'
            f'<div style="font-weight:700;margin-top:6px;">{r["name"]}</div>'
            f'<div style="font-size:12px;opacity:.7;">{r["favorite_team"] or "no favorite team yet"}</div></div>',
            unsafe_allow_html=True,
        )
        if st.button("Log out", use_container_width=True):
            ss().pid = None
            ss().pname = None
            st.rerun()
    else:
        tab_login, tab_new = st.tabs(["Log in", "Create"])
        names = [
            r["name"]
            for r in conn.execute("SELECT name FROM participants ORDER BY name")
        ]
        with tab_login:
            if names:
                ln = st.selectbox("Name", names, key="login_name")
                lp = st.text_input("PIN", type="password", key="login_pin")
                if st.button("Log in", use_container_width=True):
                    row = dbmod.verify_login(conn, ln, lp)
                    if row:
                        ss().pid = row["participant_id"]
                        ss().pname = row["name"]
                        st.rerun()
                    else:
                        st.error("Wrong name or PIN.")
            else:
                st.caption("No players yet — create an account.")
        with tab_new:
            nn = st.text_input("Display name", key="new_name")
            np1 = st.text_input("Choose a PIN", type="password", key="new_pin")
            np2 = st.text_input("Confirm PIN", type="password", key="new_pin2")
            if st.button("Create account", use_container_width=True):
                if not nn.strip() or not np1:
                    st.warning("Name and PIN required.")
                elif np1 != np2:
                    st.warning("PINs don't match.")
                else:
                    try:
                        pid = dbmod.create_participant(conn, nn.strip(), np1)
                        ss().pid = pid
                        ss().pname = nn.strip()
                        st.rerun()
                    except Exception:
                        st.warning("That name is already taken.")

    st.divider()
    page = st.radio(
        "Go to",
        [
            "🏠 Home",
            "👤 My profile",
            "🎯 Match picks",
            "🏆 Outcomes",
            "🃏 Wildcards",
            "📊 Leaderboard",
            "🔐 Admin",
        ],
        label_visibility="collapsed",
    )


def need_login():
    st.info("Log in (or create an account) in the sidebar to make or edit predictions.")


def lock_banner():
    if dbmod.predictions_locked(conn):
        st.markdown(
            '<div class="lock-banner lock-on">🔒 Predictions are LOCKED by the organiser — viewing only.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="lock-banner lock-off">✏️ Predictions are OPEN — you can edit until the organiser locks them.</div>',
            unsafe_allow_html=True,
        )


# =========================================================================== #
# HOME
# =========================================================================== #
if page == "🏠 Home":
    st.markdown(
        """
    <div class="wc-hero">
      <div class="ball">⚽</div>
      <h1>World Cup 2026 — Office Prediction Contest</h1>
      <p>Predict every match, call the tournament outcomes, gamble on the wildcards.
         Design your kit. Climb the podium. 🏆</p>
    </div>
    """,
        unsafe_allow_html=True,
    )
    st.write("")
    lock_banner()
    if logged_in():
        nmatch = conn.execute(
            "SELECT COUNT(*) FROM match_predictions WHERE participant_id=?", (ss().pid,)
        ).fetchone()[0]
        nout = conn.execute(
            "SELECT COUNT(*) FROM outcome_predictions WHERE participant_id=?",
            (ss().pid,),
        ).fetchone()[0]
        nwild = conn.execute(
            "SELECT COUNT(*) FROM wildcard_predictions WHERE participant_id=?",
            (ss().pid,),
        ).fetchone()[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Your match picks", f"{nmatch} / 104")
        c2.metric("Outcome picks", nout)
        c3.metric("Wildcard picks", f"{nwild} / 8")
        st.caption(
            "Use the sidebar to navigate. Start with **My profile** to design your jersey!"
        )
    else:
        need_login()

# =========================================================================== #
# MY PROFILE
# =========================================================================== #
elif page == "👤 My profile":
    st.header("👤 My profile")
    if not logged_in():
        need_login()
    else:
        r = my_row()
        col_form, col_preview = st.columns([3, 2])
        with col_form:
            teams = [""] + team_options()
            ft = st.selectbox(
                "Favorite team",
                teams,
                index=teams.index(r["favorite_team"])
                if r["favorite_team"] in teams
                else 0,
            )
            fp = st.text_input("Favorite player", value=r["favorite_player"] or "")
            st.markdown("**Design your kit**")
            cc1, cc2 = st.columns(2)
            prim = cc1.color_picker("Primary colour", r["shirt_primary"] or "#2f81f7")
            sec = cc2.color_picker(
                "Secondary colour", r["shirt_secondary"] or "#ffffff"
            )
            pat = st.radio(
                "Pattern",
                avatar.PATTERNS,
                index=avatar.PATTERNS.index(r["shirt_pattern"])
                if r["shirt_pattern"] in avatar.PATTERNS
                else 0,
                horizontal=True,
            )
        with col_preview:
            st.markdown("**Live preview**")
            st.markdown(
                f'<div style="text-align:center">{jersey_img(prim, sec, pat, 150)}</div>',
                unsafe_allow_html=True,
            )
        if st.button("💾 Save profile", type="primary"):
            dbmod.update_profile(
                conn,
                ss().pid,
                favorite_team=ft,
                favorite_player=fp,
                shirt_primary=prim,
                shirt_secondary=sec,
                shirt_pattern=pat,
            )
            st.success("Profile saved!")
            st.rerun()

        with st.expander("Change my PIN"):
            p1 = st.text_input("New PIN", type="password", key="cp1")
            p2 = st.text_input("Confirm new PIN", type="password", key="cp2")
            if st.button("Update PIN"):
                if p1 and p1 == p2:
                    dbmod.set_pin(conn, ss().pid, p1)
                    st.success("PIN updated.")
                else:
                    st.warning("PINs empty or don't match.")

# =========================================================================== #
# MATCH PICKS
# =========================================================================== #
elif page == "🎯 Match picks":
    st.header("🎯 Match-by-match predictions")
    st.caption(
        f"Exact score = {config.MATCH_EXACT_SCORE} · correct goal diff = "
        f"{config.MATCH_GOAL_DIFF} · correct result = {config.MATCH_OUTCOME} pts."
    )
    lock_banner()
    if not logged_in():
        need_login()
    else:
        pid = ss().pid
        can_edit = editing_open()
        view = st.radio("Stage", ["Group stage", "Knockout"], horizontal=True)

        if view == "Group stage":
            groups = [chr(c) for c in range(ord("A"), ord("L") + 1)]
            st.write("**Pick a group:**")
            rows = [groups[:6], groups[6:]]
            for rowg in rows:
                cols = st.columns(6)
                for i, g in enumerate(rowg):
                    btn_type = "primary" if ss().sel_group == g else "secondary"
                    if cols[i].button(
                        f"Group {g}",
                        key=f"gbtn_{g}",
                        type=btn_type,
                        use_container_width=True,
                    ):
                        ss().sel_group = g
                        st.rerun()
            g = ss().sel_group
            st.subheader(f"Group {g}")
            matches = conn.execute(
                "SELECT * FROM matches WHERE group_code=? ORDER BY matchday, match_id",
                (g,),
            ).fetchall()
            existing = {
                x["match_id"]: x
                for x in conn.execute(
                    "SELECT * FROM match_predictions WHERE participant_id=?", (pid,)
                )
            }
            with st.form(f"mf_{g}"):
                picks = []
                for m in matches:
                    ex = existing.get(m["match_id"])
                    c1, c2, c3, c4 = st.columns([3, 1, 1, 3])
                    c1.markdown(f"**{m['home_label']}**")
                    hv = c2.number_input(
                        "H",
                        0,
                        30,
                        value=ex["pred_home"] if ex else 0,
                        key=f"h_{m['match_id']}",
                        disabled=not can_edit,
                        label_visibility="collapsed",
                    )
                    av = c3.number_input(
                        "A",
                        0,
                        30,
                        value=ex["pred_away"] if ex else 0,
                        key=f"a_{m['match_id']}",
                        disabled=not can_edit,
                        label_visibility="collapsed",
                    )
                    c4.markdown(f"**{m['away_label']}**")
                    picks.append((m["match_id"], hv, av))
                submitted = st.form_submit_button(
                    f"🔒 Lock in Group {g} picks", type="primary", disabled=not can_edit
                )
                if submitted:
                    for mid, hv, av in picks:
                        conn.execute(
                            "INSERT OR REPLACE INTO match_predictions "
                            "(participant_id, match_id, pred_home, pred_away, pred_advance, submitted_at) "
                            "VALUES (?,?,?,?,?,?)",
                            (pid, mid, int(hv), int(av), None, dbmod.now_iso()),
                        )
                    conn.commit()
                    st.success(f"Group {g} picks locked in! ⚽")
        else:
            ko_stages = [
                r["stage"]
                for r in conn.execute(
                    "SELECT DISTINCT stage FROM matches WHERE is_knockout=1 ORDER BY match_id"
                )
            ]
            stage = st.selectbox("Round", ko_stages)
            matches = conn.execute(
                "SELECT * FROM matches WHERE stage=? ORDER BY match_id", (stage,)
            ).fetchall()
            existing = {
                x["match_id"]: x
                for x in conn.execute(
                    "SELECT * FROM match_predictions WHERE participant_id=?", (pid,)
                )
            }
            with st.form(f"kf_{stage}"):
                picks = []
                for m in matches:
                    ex = existing.get(m["match_id"])
                    c1, c2, c3, c4 = st.columns([3, 1, 1, 3])
                    c1.markdown(f"{m['home_label']}")
                    hv = c2.number_input(
                        "H",
                        0,
                        30,
                        value=ex["pred_home"] if ex else 0,
                        key=f"h_{m['match_id']}",
                        disabled=not can_edit,
                        label_visibility="collapsed",
                    )
                    av = c3.number_input(
                        "A",
                        0,
                        30,
                        value=ex["pred_away"] if ex else 0,
                        key=f"a_{m['match_id']}",
                        disabled=not can_edit,
                        label_visibility="collapsed",
                    )
                    c4.markdown(f"{m['away_label']}")
                    picks.append((m["match_id"], hv, av))
                if st.form_submit_button(
                    f"🔒 Lock in {stage} picks", type="primary", disabled=not can_edit
                ):
                    for mid, hv, av in picks:
                        conn.execute(
                            "INSERT OR REPLACE INTO match_predictions "
                            "(participant_id, match_id, pred_home, pred_away, pred_advance, submitted_at) "
                            "VALUES (?,?,?,?,?,?)",
                            (pid, mid, int(hv), int(av), None, dbmod.now_iso()),
                        )
                    conn.commit()
                    st.success(f"{stage} picks locked in!")

# =========================================================================== #
# OUTCOMES
# =========================================================================== #
elif page == "🏆 Outcomes":
    st.header("🏆 Tournament outcome predictions")
    lock_banner()
    if not logged_in():
        need_login()
    elif not editing_open():
        st.warning("Predictions are locked — you can't edit outcomes now.")
    else:
        pid = ss().pid
        teams = team_options()
        ex = {
            (r["category"], r["ref"]): r["value"]
            for r in conn.execute(
                "SELECT * FROM outcome_predictions WHERE participant_id=?", (pid,)
            )
        }

        def pick(label, cat, ref="", opts=None):
            opts = opts if opts is not None else ([""] + teams)
            cur = ex.get((cat, ref), "")
            idx = opts.index(cur) if cur in opts else 0
            return st.selectbox(label, opts, index=idx, key=f"{cat}_{ref}")

        with st.form("outcomes"):
            st.markdown(
                f"**Podium** — champion {OUTCOME_POINTS['champion']}, "
                f"runner-up {OUTCOME_POINTS['runner_up']}, "
                f"3rd {OUTCOME_POINTS['third_place']} pts"
            )
            champ = pick("🥇 Champion", "champion")
            runner = pick("🥈 Runner-up", "runner_up")
            third = pick("🥉 Third place", "third_place")
            st.markdown(f"**Finalists** ({OUTCOME_POINTS['finalist']} pts each)")
            f1 = pick("Finalist 1", "finalist", "1")
            f2 = pick("Finalist 2", "finalist", "2")
            st.markdown(f"**Semi-finalists** ({OUTCOME_POINTS['semi_finalist']} each)")
            sf = [
                pick(f"Semi-finalist {i}", "semi_finalist", str(i)) for i in range(1, 5)
            ]
            st.markdown(f"**Golden Boot** ({OUTCOME_POINTS['golden_boot']} pts)")
            gb = st.text_input(
                "Top scorer (player name)", value=ex.get(("golden_boot", ""), "")
            )
            st.markdown(f"**Group winners** ({OUTCOME_POINTS['group_winner']} each)")
            gw, cols = {}, st.columns(4)
            for i, gc in enumerate([chr(c) for c in range(ord("A"), ord("L") + 1)]):
                gteams = [
                    x["name"]
                    for x in conn.execute(
                        "SELECT name FROM teams WHERE group_code=? ORDER BY name", (gc,)
                    )
                ]
                cur = ex.get(("group_winner", gc), "")
                idx = ([""] + gteams).index(cur) if cur in gteams else 0
                gw[gc] = cols[i % 4].selectbox(
                    f"Group {gc}", [""] + gteams, index=idx, key=f"gw_{gc}"
                )
            if st.form_submit_button("🔒 Lock in outcome picks", type="primary"):
                rows = [
                    ("champion", "", champ),
                    ("runner_up", "", runner),
                    ("third_place", "", third),
                    ("finalist", "1", f1),
                    ("finalist", "2", f2),
                    ("golden_boot", "", gb),
                ]
                rows += [("semi_finalist", str(i + 1), t) for i, t in enumerate(sf)]
                rows += [("group_winner", g, t) for g, t in gw.items()]
                for cat, ref, val in rows:
                    if str(val).strip():
                        conn.execute(
                            "INSERT OR REPLACE INTO outcome_predictions "
                            "(participant_id, category, ref, value, submitted_at) VALUES (?,?,?,?,?)",
                            (pid, cat, ref, str(val).strip(), dbmod.now_iso()),
                        )
                conn.commit()
                st.success("Outcome picks locked in! 🏆")

# =========================================================================== #
# WILDCARDS
# =========================================================================== #
elif page == "🃏 Wildcards":
    st.header("🃏 Wildcard predictions")
    lock_banner()
    if not logged_in():
        need_login()
    elif not editing_open():
        st.warning("Predictions are locked — you can't edit wildcards now.")
    else:
        pid = ss().pid
        teams = team_options()
        ex = {
            r["wildcard_id"]: r["value"]
            for r in conn.execute(
                "SELECT * FROM wildcard_predictions WHERE participant_id=?", (pid,)
            )
        }
        with st.form("wildcards"):
            answers = {}
            for w in conn.execute("SELECT * FROM wildcards ORDER BY wildcard_id"):
                label = f"{w['question']}  ({w['points']:g} pts)"
                cur = ex.get(w["wildcard_id"], "")
                if w["type"] == "number":
                    answers[w["wildcard_id"]] = st.number_input(
                        label,
                        value=float(cur) if cur else 0.0,
                        step=1.0,
                        key=w["wildcard_id"],
                    )
                elif w["type"] in ("boolean", "choice"):
                    opts = [""] + w["options"].split("|")
                    idx = opts.index(cur) if cur in opts else 0
                    answers[w["wildcard_id"]] = st.selectbox(
                        label, opts, index=idx, key=w["wildcard_id"]
                    )
                elif w["type"] == "team":
                    opts = [""] + teams
                    idx = opts.index(cur) if cur in opts else 0
                    answers[w["wildcard_id"]] = st.selectbox(
                        label, opts, index=idx, key=w["wildcard_id"]
                    )
                if w["hint"]:
                    st.caption(w["hint"])
            if st.form_submit_button("🔒 Lock in wildcards", type="primary"):
                for wid, val in answers.items():
                    if str(val).strip():
                        conn.execute(
                            "INSERT OR REPLACE INTO wildcard_predictions "
                            "(participant_id, wildcard_id, value, submitted_at) VALUES (?,?,?,?)",
                            (pid, wid, str(val).strip(), dbmod.now_iso()),
                        )
                conn.commit()
                st.success("Wildcards locked in! 🃏")

# =========================================================================== #
# LEADERBOARD
# =========================================================================== #
elif page == "📊 Leaderboard":
    st.markdown(
        '<div class="wc-hero" style="padding:18px 26px"><div class="ball">🏆</div>'
        "<h1>Leaderboard</h1><p>The race for World Cup bragging rights.</p></div>",
        unsafe_allow_html=True,
    )
    st.write("")
    rows = scoring.leaderboard_rows(conn)
    profiles = {
        r["participant_id"]: r for r in conn.execute("SELECT * FROM participants")
    }
    if not rows:
        st.info("No participants yet.")
    else:
        top = rows[:3]
        order = [1, 0, 2]  # render 2nd, 1st, 3rd for podium effect
        html = ['<div class="podium-wrap">']
        crowns = {0: "👑", 1: "🥈", 2: "🥉"}
        for slot in order:
            if slot >= len(top):
                continue
            r = top[slot]
            pr = profiles.get(r["participant_id"])
            jersey = jersey_img(
                pr["shirt_primary"] if pr else "#2f81f7",
                pr["shirt_secondary"] if pr else "#fff",
                pr["shirt_pattern"] if pr else "solid",
                84,
            )
            sparks = (
                "".join(
                    f'<span class="spark" style="left:{x}%;top:{y}%;animation-delay:{d}s"></span>'
                    for x, y, d in [
                        (15, 30, 0),
                        (80, 20, 0.6),
                        (50, 10, 1.1),
                        (30, 60, 0.3),
                    ]
                )
                if slot == 0
                else ""
            )
            html.append(
                f'<div class="podium p{slot + 1}">{sparks}'
                f'<div class="pod-card"><div class="crown">{crowns[slot]}</div>'
                f'{jersey}<div class="pod-name">{r["name"]}</div>'
                f'<div class="pod-pts">{r["total_points"]:g} pts · {r["exact_score_hits"]} exact</div></div>'
                f'<div class="pedestal">{r["rank"]}</div></div>'
            )
        html.append("</div>")
        st.markdown("".join(html), unsafe_allow_html=True)

        if not ss().balloons_done:
            st.balloons()
            ss().balloons_done = True

        st.write("")
        st.subheader("Full standings")
        st.dataframe(
            [
                {
                    "#": r["rank"],
                    "Player": r["name"],
                    "Total": r["total_points"],
                    "Match": r["match_points"],
                    "Outcomes": r["outcome_points"],
                    "Wildcards": r["wildcard_points"],
                    "Exact scores": r["exact_score_hits"],
                }
                for r in rows
            ],
            hide_index=True,
            use_container_width=True,
        )

# =========================================================================== #
# ADMIN
# =========================================================================== #
elif page == "🔐 Admin":
    st.header("🔐 Admin")
    if not ss().is_admin:
        pw = st.text_input("Admin password", type="password")
        if st.button("Unlock admin"):
            if pw == ADMIN_PASSWORD:
                ss().is_admin = True
                st.rerun()
            else:
                st.error("Wrong password.")
        st.stop()

    st.success("Admin unlocked.")

    # ---- prediction lock toggle ----
    locked = dbmod.predictions_locked(conn)
    st.subheader("Prediction lock")
    st.caption("Turn this ON at the deadline so nobody can change their picks.")
    new_locked = st.toggle("🔒 Predictions locked", value=locked)
    if new_locked != locked:
        dbmod.set_predictions_locked(conn, new_locked)
        st.success(f"Predictions are now {'LOCKED' if new_locked else 'OPEN'}.")
        st.rerun()

    st.divider()
    st.subheader("Match results")
    only_unplayed = st.checkbox("Hide matches that already have a result", True)
    res = {r["match_id"] for r in conn.execute("SELECT match_id FROM match_results")}
    with st.form("results"):
        entries = []
        for m in conn.execute("SELECT * FROM matches ORDER BY kickoff_utc, match_id"):
            if only_unplayed and m["match_id"] in res:
                continue
            cur = conn.execute(
                "SELECT * FROM match_results WHERE match_id=?", (m["match_id"],)
            ).fetchone()
            c1, c2, c3 = st.columns([4, 1, 1])
            c1.markdown(f"`{m['match_id']}` {m['home_label']} vs {m['away_label']}")
            hg = c2.number_input(
                "H",
                0,
                30,
                value=cur["home_goals"] if cur else 0,
                key=f"rh_{m['match_id']}",
                label_visibility="collapsed",
            )
            ag = c3.number_input(
                "A",
                0,
                30,
                value=cur["away_goals"] if cur else 0,
                key=f"ra_{m['match_id']}",
                label_visibility="collapsed",
            )
            entries.append((m["match_id"], hg, ag))
        if st.form_submit_button("Save match results") and entries:
            for mid, hg, ag in entries:
                conn.execute(
                    "INSERT OR REPLACE INTO match_results (match_id, home_goals, away_goals, advance) "
                    "VALUES (?,?,?,?)",
                    (mid, int(hg), int(ag), None),
                )
            conn.commit()
            st.success(f"Saved {len(entries)} result(s).")

    st.divider()
    with st.expander("Tournament outcome results"):
        teams = team_options()
        with st.form("outres"):
            ch = st.selectbox("Champion", [""] + teams)
            ru = st.selectbox("Runner-up", [""] + teams)
            tp = st.selectbox("Third place", [""] + teams)
            sf = st.multiselect("Semi-finalists (4)", teams, max_selections=4)
            qf = st.multiselect("Quarter-finalists (8)", teams, max_selections=8)
            gb = st.text_input("Golden Boot (player)")
            st.markdown("**Group winners**")
            gwres, gcols = {}, st.columns(4)
            for i, gc in enumerate([chr(c) for c in range(ord("A"), ord("L") + 1)]):
                gteams = [
                    r["name"]
                    for r in conn.execute(
                        "SELECT name FROM teams WHERE group_code=? ORDER BY name", (gc,)
                    )
                ]
                gwres[gc] = gcols[i % 4].selectbox(
                    f"Group {gc}", [""] + gteams, key=f"gwres_{gc}"
                )
            if st.form_submit_button("Save outcome results"):
                conn.execute("DELETE FROM outcome_results")
                pairs = [
                    ("champion", "", ch),
                    ("runner_up", "", ru),
                    ("third_place", "", tp),
                    ("golden_boot", "", gb),
                ]
                pairs += [
                    ("finalist", str(i), t) for i, t in enumerate([ch, ru], 1) if t
                ]
                pairs += [("semi_finalist", str(i), t) for i, t in enumerate(sf, 1)]
                pairs += [("quarter_finalist", str(i), t) for i, t in enumerate(qf, 1)]
                pairs += [("group_winner", g, t) for g, t in gwres.items() if t]
                for cat, ref, val in pairs:
                    if str(val).strip():
                        conn.execute(
                            "INSERT OR REPLACE INTO outcome_results VALUES (?,?,?)",
                            (cat, ref, str(val).strip()),
                        )
                conn.commit()
                st.success("Outcome results saved.")

    with st.expander("Wildcard results"):
        with st.form("wres"):
            vals = {}
            for w in conn.execute("SELECT * FROM wildcards ORDER BY wildcard_id"):
                vals[w["wildcard_id"]] = st.text_input(
                    f"{w['wildcard_id']}: {w['question']}", key=f"wr_{w['wildcard_id']}"
                )
            if st.form_submit_button("Save wildcard results"):
                for wid, val in vals.items():
                    if str(val).strip():
                        conn.execute(
                            "INSERT OR REPLACE INTO wildcard_results VALUES (?,?)",
                            (wid, str(val).strip()),
                        )
                conn.commit()
                st.success("Wildcard results saved.")

    with st.expander("Reset a player's PIN"):
        pnames = [
            r["name"]
            for r in conn.execute("SELECT name FROM participants ORDER BY name")
        ]
        if pnames:
            who = st.selectbox("Player", pnames, key="pinreset_who")
            newpin = st.text_input("New PIN", key="pinreset_pin")
            if st.button("Reset PIN") and newpin:
                pid = conn.execute(
                    "SELECT participant_id FROM participants WHERE name=?", (who,)
                ).fetchone()[0]
                dbmod.set_pin(conn, pid, newpin)
                st.success(f"PIN reset for {who}.")

    st.divider()
    if st.button("🔄 Refresh dashboards (export CSV + JSON)"):
        export.export_csvs(conn)
        export.export_dashboard_json(conn)
        st.success(f"Exported to {config.EXPORT_DIR} and {config.DASHBOARD_DIR}")
