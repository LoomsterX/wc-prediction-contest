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
from datetime import datetime, timezone, timedelta

import os

import streamlit as st


# Norwegian wall-clock time for kickoff display. Europe/Oslo if tzdata is
# available, else a fixed +2 (CEST) which is correct for the whole tournament
# window (Jun–Jul 2026).
try:
    from zoneinfo import ZoneInfo

    OSLO_TZ = ZoneInfo("Europe/Oslo")
except Exception:
    OSLO_TZ = timezone(timedelta(hours=2))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Use a hosted database (Supabase/Postgres) when DATABASE_URL is provided via
# Streamlit secrets; otherwise fall back to local SQLite. Must run before the
# engine is created.
try:
    if "DATABASE_URL" in st.secrets:
        os.environ["DATABASE_URL"] = st.secrets["DATABASE_URL"]
except Exception:
    pass

from wc_contest import config, db as dbmod, scoring, export, avatar, knockout  # noqa: E402
from wc_contest.engine import upsert  # noqa: E402

# Admin password comes ONLY from Streamlit secrets or the ADMIN_PASSWORD env var
# — never hard-coded. If unset, the Admin page stays locked.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
try:
    ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", ADMIN_PASSWORD)
except Exception:
    pass

# Optional invite code required to create a new account, so only people you
# share it with can join. From the SIGNUP_KEY secret / env var. If unset,
# sign-up is open (no code required).
SIGNUP_KEY = os.environ.get("SIGNUP_KEY")
try:
    SIGNUP_KEY = st.secrets.get("SIGNUP_KEY", SIGNUP_KEY)
except Exception:
    pass

st.set_page_config(page_title="VM 2026 SWON-GAMES", page_icon="⚽", layout="wide")


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
    # Keep the wildcard set in step with the seed (updates questions / adds new
    # ones on databases that were seeded before these changes).
    dbmod.sync_wildcards(conn)
    return conn


conn = get_conn()

st.markdown(
    """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Orbitron:wght@500;700&display=swap');
  :root { --neon:#6f5bff; --neon2:#29f0ff; --gold:#ffd23f;
          --pixel:"Press Start 2P", monospace; --tech:"Orbitron", sans-serif; }
  .stApp { background:
      linear-gradient(rgba(111,91,255,.04) 1px, transparent 1px) 0 0 / 100% 28px,
      radial-gradient(1100px 560px at 50% -10%, rgba(111,91,255,0.18), transparent 60%),
      #0a0c16; }
  .wc-hero {
    border-radius: 6px; padding: 26px 30px; color: #fff; position: relative;
    overflow: hidden; border:1px solid var(--neon);
    background: linear-gradient(120deg,#0a0c16 0%,#14123f 55%,#0a0c16 100%);
    background-size: 200% 200%; animation: wcflow 12s ease infinite;
    box-shadow: 0 0 22px rgba(111,91,255,.5), inset 0 0 22px rgba(111,91,255,.12);
  }
  @keyframes wcflow { 0%{background-position:0% 50%} 50%{background-position:100% 50%}
                      100%{background-position:0% 50%} }
  .wc-hero h1 { margin:0; font-family:var(--pixel); font-size:20px; line-height:1.5;
                text-shadow:0 0 8px var(--neon),0 0 18px rgba(111,91,255,.7); }
  .wc-hero p { margin:12px 0 0; opacity:.92; font-family:var(--tech);
               letter-spacing:.04em; color:var(--neon2); }
  .wc-hero .ball { position:absolute; right:24px; top:18px; font-size:60px;
                   animation: spin 8s linear infinite;
                   filter:drop-shadow(0 0 8px var(--neon2)); }
  @keyframes spin { from{transform:rotate(0)} to{transform:rotate(360deg)} }

  /* podium */
  .podium-wrap { display:flex; justify-content:center; align-items:flex-end;
                 gap:18px; margin:18px 0 8px; flex-wrap:nowrap; }
  .podium { text-align:center; position:relative; }
  .pod-card { display:flex; flex-direction:column; align-items:center; gap:6px; }
  .pod-name { font-weight:700; font-size:15px; font-family:var(--tech);
              letter-spacing:.04em; }
  .pod-pts { font-size:12px; opacity:.8; font-family:var(--tech); }
  .pedestal { border-radius:4px 4px 0 0; width:120px;
              display:flex; align-items:flex-start; justify-content:center;
              color:#05060d; font-weight:800; padding-top:12px;
              font-family:var(--pixel); font-size:20px; }
  .p1 .pedestal { height:150px; background:linear-gradient(180deg,#ffe27a,#f3b521);
                  border:1px solid var(--gold); animation: glow 2.4s ease-in-out infinite; }
  .p2 .pedestal { height:110px; background:linear-gradient(180deg,#e9edf6,#aeb9cc);
                  border:1px solid #c7d0e0; box-shadow:0 0 14px rgba(199,208,224,.5); }
  .p3 .pedestal { height:88px;  background:linear-gradient(180deg,#f0b483,#cd7f32);
                  border:1px solid #e08a3c; box-shadow:0 0 14px rgba(224,138,60,.5); }
  @keyframes glow { 0%,100%{box-shadow:0 0 16px rgba(255,210,63,.6)}
        50%{box-shadow:0 0 34px rgba(255,210,63,.95)} }
  .crown { font-size:30px; animation: bob 2s ease-in-out infinite;
           filter:drop-shadow(0 0 8px rgba(255,210,63,.8)); }
  @keyframes bob { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-6px)} }
  .jersey-badge { filter: drop-shadow(0 0 7px rgba(111,91,255,.7)); }
  .spark { position:absolute; width:7px; height:7px; border-radius:0;
           background:var(--neon2); box-shadow:0 0 8px var(--neon2);
           opacity:.0; animation: sparkle 2.2s linear infinite; }
  @keyframes sparkle { 0%{opacity:0; transform:scale(.4) translateY(0)}
        30%{opacity:1} 100%{opacity:0; transform:scale(1.1) translateY(-26px)} }
  .lock-banner { border-radius:4px; padding:10px 16px; font-weight:600;
                 margin-bottom:10px; font-family:var(--tech); letter-spacing:.04em; }
  .lock-on  { background:rgba(255,60,90,.10); color:#ff6b86;
              border:1px solid #ff4d6d; box-shadow:0 0 12px rgba(255,77,109,.4); }
  .lock-off { background:rgba(41,240,255,.08); color:var(--neon2);
              border:1px solid var(--neon2); box-shadow:0 0 12px rgba(41,240,255,.35); }
  .id-card { background:#11152a; border:1px solid var(--neon);
             border-radius:6px; padding:12px; text-align:center;
             box-shadow:0 0 12px rgba(111,91,255,.4), inset 0 0 12px rgba(111,91,255,.08); }
  .wc-badge { display:inline-block; padding:2px 10px; border-radius:3px;
              background:transparent; border:1px solid var(--neon2);
              color:var(--neon2); font-size:12px; font-weight:600; font-family:var(--tech); }
  /* headings + primary buttons get the futuristic treatment */
  h1, h2, h3 { font-family:var(--tech) !important; letter-spacing:.03em; }
  .stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] {
      border:1px solid var(--neon) !important;
      box-shadow:0 0 12px rgba(111,91,255,.5) !important;
      font-family:var(--tech) !important; letter-spacing:.04em; }

  /* ---- top header navigation ---- */
  /* the key class sits on the vertical block itself (and/or a wrapper); force
     a horizontal, wrapping row either way */
  .st-key-nav_full,
  .st-key-nav_full > div[data-testid="stVerticalBlock"]{
      display:flex !important; flex-direction:row !important; flex-wrap:wrap !important;
      gap:8px !important; align-items:center; }
  .st-key-nav_full div[data-testid="stElementContainer"]{
      width:auto !important; flex:0 0 auto !important; }
  .st-key-nav_full div[data-testid="stElementContainer"] .stButton{ width:auto !important; }
  /* nav item boxes */
  .st-key-nav_full .stButton button, .st-key-nav_burger .stButton button{
      font-family:var(--tech) !important; letter-spacing:.02em; font-weight:600;
      border:1px solid var(--line) !important; border-radius:6px !important;
      background:#11152a !important; color:#cdd6f4 !important;
      padding:6px 14px !important; transition:all .15s ease; box-shadow:none !important; }
  .st-key-nav_full .stButton button:hover, .st-key-nav_burger .stButton button:hover{
      border-color:var(--neon2) !important; color:#fff !important;
      box-shadow:0 0 12px rgba(41,240,255,.45) !important; transform:translateY(-1px); }
  /* active item (rendered as a primary button) */
  .st-key-nav_full .stButton button[kind="primary"],
  .st-key-nav_burger .stButton button[kind="primary"]{
      background:linear-gradient(180deg,#1801B4,#3a23c9) !important;
      border:1px solid var(--neon) !important; color:#fff !important;
      box-shadow:0 0 16px rgba(111,91,255,.65) !important; }
  .nav-bar{ border-bottom:1px solid var(--neon); padding:6px 0 12px; margin-bottom:14px;
            box-shadow:0 6px 18px -12px rgba(111,91,255,.6); }
  /* responsive: inline bar on wide screens, hamburger on small */
  .st-key-nav_burger{ display:none; }
  @media (max-width: 820px){
      .st-key-nav_full{ display:none; }
      .st-key-nav_burger{ display:block; }
  }
  /* account control pinned to the right of the nav row */
  .st-key-acct{ display:flex; justify-content:flex-end; }
  .brand{ font-family:var(--tech); font-weight:700; color:#cdd6f4;
          padding:8px 2px; font-size:16px; letter-spacing:.03em; }
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


def group_editable(g, pid) -> bool:
    """Can this player still edit Group g? Open unless the organiser locked that
    group globally, or the player has submitted their final predictions."""
    return not dbmod.group_pred_locked(conn, g) and not dbmod.final_submitted(conn, pid)


def knockout_editable(pid) -> bool:
    return not dbmod.knockout_pred_locked(conn) and not dbmod.final_submitted(conn, pid)


def wildcards_editable(pid) -> bool:
    return not dbmod.wildcards_pred_locked(conn) and not dbmod.final_submitted(
        conn, pid
    )


def reveal_others() -> bool:
    """Everyone's picks become visible once any stage has been globally locked
    (i.e. the tournament has started)."""
    return dbmod.any_stage_locked(conn)


def jersey_img(primary, secondary, pattern, size=64, cls="jersey-badge"):
    uri = avatar.data_uri(
        primary or "#1801B4", secondary or "#ffffff", pattern or "solid", size
    )
    return f'<img class="{cls}" src="{uri}" width="{size}" height="{size}" />'


def my_row():
    return conn.execute(
        "SELECT * FROM participants WHERE participant_id=?", (ss().pid,)
    ).fetchone()


def team_options():
    return [r["name"] for r in conn.execute("SELECT name FROM teams ORDER BY name")]


# --------------------------------------------------------------------------- #
# Account controls (rendered at the right end of the top nav row)
# --------------------------------------------------------------------------- #
def _login_form():
    names = [
        r["name"] for r in conn.execute("SELECT name FROM participants ORDER BY name")
    ]
    if not names:
        st.caption("No players yet — switch to **Sign up**.")
        return
    ln = st.selectbox("Name", names, key="login_name")
    lp = st.text_input("PIN", type="password", key="login_pin")
    if st.button("Log in", use_container_width=True, type="primary"):
        row = dbmod.verify_login(conn, ln, lp)
        if row:
            ss().pid = row["participant_id"]
            ss().pname = row["name"]
            st.rerun()
        else:
            st.error("Wrong name or PIN.")


def _signup_form():
    nn = st.text_input("Display name", key="new_name")
    np1 = st.text_input("Choose a PIN", type="password", key="new_pin")
    np2 = st.text_input("Confirm PIN", type="password", key="new_pin2")
    invite = ""
    if SIGNUP_KEY:
        invite = st.text_input(
            "Invite code",
            type="password",
            key="new_invite",
            help="Ask the organiser for the code.",
        )
    if st.button("Sign up", use_container_width=True, type="primary"):
        if not nn.strip() or not np1:
            st.warning("Name and PIN required.")
        elif np1 != np2:
            st.warning("PINs don't match.")
        elif SIGNUP_KEY and invite.strip() != SIGNUP_KEY:
            st.error("Wrong invite code — ask the organiser.")
        else:
            try:
                pid = dbmod.create_participant(conn, nn.strip(), np1)
                ss().pid = pid
                ss().pname = nn.strip()
                st.rerun()
            except Exception:
                st.warning("That name is already taken.")


def render_account():
    with st.container(key="acct"):
        if logged_in():
            r = my_row()
            with st.popover(f"👤 {ss().pname}"):
                st.markdown(
                    f'<div style="text-align:center">'
                    f"{jersey_img(r['shirt_primary'], r['shirt_secondary'], r['shirt_pattern'], 84)}"
                    f'<div style="font-weight:700;margin-top:6px;">{r["name"]}</div>'
                    f'<div style="font-size:12px;opacity:.7;">{r["favorite_team"] or "no favorite team yet"}</div></div>',
                    unsafe_allow_html=True,
                )
                if st.button("Log out", use_container_width=True):
                    ss().pid = None
                    ss().pname = None
                    ss().nav_page = "🏠 Home"
                    ss().is_admin = False
                    st.rerun()
        else:
            with st.popover("🔐 Log in"):
                mode = st.radio(
                    "mode",
                    ["Log in", "Sign up"],
                    horizontal=True,
                    key="auth_mode",
                    label_visibility="collapsed",
                )
                if mode == "Log in":
                    _login_form()
                else:
                    _signup_form()


def need_login():
    st.info(
        "Use the **🔐 Log in** button at the top right to log in or sign up "
        "and join the contest."
    )


def lock_banner():
    g_locked = [g for g in dbmod.GROUP_CODES if dbmod.group_pred_locked(conn, g)]
    ko = dbmod.knockout_pred_locked(conn)
    wc = dbmod.wildcards_pred_locked(conn)
    if not g_locked and not ko and not wc:
        st.markdown(
            '<div class="lock-banner lock-off">✏️ Predictions are OPEN — Gjør dine predikasjoner før første gruppekamp i hver gruppe.</div>',
            unsafe_allow_html=True,
        )
        return
    bits = []
    if len(g_locked) == len(dbmod.GROUP_CODES):
        bits.append("all groups")
    elif g_locked:
        bits.append("groups " + ", ".join(g_locked))
    if ko:
        bits.append("knockout")
    if wc:
        bits.append("wildcards")
    st.markdown(
        f'<div class="lock-banner lock-on">🔒 Locked by the organiser: '
        f"{'; '.join(bits)}. Other stages remain open.</div>",
        unsafe_allow_html=True,
    )


GROUPS_AL = [chr(c) for c in range(ord("A"), ord("L") + 1)]


def group_tile_picker(state_key: str, options=None, prefix="Group "):
    """Render a tile-style row of group buttons; return the selected option."""
    options = options or GROUPS_AL
    ss().setdefault(state_key, options[0])
    rows = [options[i : i + 6] for i in range(0, len(options), 6)]
    for rowg in rows:
        cols = st.columns(6)
        for i, g in enumerate(rowg):
            label = g if prefix == "" else f"{prefix}{g}"
            typ = "primary" if ss()[state_key] == g else "secondary"
            if cols[i].button(
                label, key=f"{state_key}_{g}", type=typ, use_container_width=True
            ):
                ss()[state_key] = g
                st.rerun()
    return ss()[state_key]


def group_standings(gcode):
    """Compute W/D/L, GF/GA/GD, Pts for a group from recorded match_results."""
    names = {
        r["team_id"]: r["name"] for r in conn.execute("SELECT team_id, name FROM teams")
    }
    teams = [
        r["name"]
        for r in conn.execute(
            "SELECT name FROM teams WHERE group_code=? ORDER BY name", (gcode,)
        )
    ]
    tbl = {t: dict(team=t, P=0, W=0, D=0, L=0, GF=0, GA=0, GD=0, Pts=0) for t in teams}
    q = """SELECT m.home_team_id AS h, m.away_team_id AS a,
                  r.home_goals AS hg, r.away_goals AS ag
           FROM matches m JOIN match_results r ON r.match_id = m.match_id
           WHERE m.group_code=?"""
    for r in conn.execute(q, (gcode,)):
        home, away = names.get(r["h"]), names.get(r["a"])
        if home not in tbl or away not in tbl:
            continue
        hg, ag = r["hg"], r["ag"]
        for t, gf, ga in ((home, hg, ag), (away, ag, hg)):
            tbl[t]["P"] += 1
            tbl[t]["GF"] += gf
            tbl[t]["GA"] += ga
            tbl[t]["GD"] = tbl[t]["GF"] - tbl[t]["GA"]
        if hg > ag:
            tbl[home]["W"] += 1
            tbl[home]["Pts"] += 3
            tbl[away]["L"] += 1
        elif hg < ag:
            tbl[away]["W"] += 1
            tbl[away]["Pts"] += 3
            tbl[home]["L"] += 1
        else:
            tbl[home]["D"] += 1
            tbl[away]["D"] += 1
            tbl[home]["Pts"] += 1
            tbl[away]["Pts"] += 1
    return sorted(
        tbl.values(), key=lambda x: (-x["Pts"], -x["GD"], -x["GF"], x["team"])
    )


def standings_from_scorelines(gcode, scorelines):
    """Build a group table from arbitrary scorelines.

    `scorelines` is an iterable of (home_team_id, away_team_id, home_goals,
    away_goals). Used to show a player's *predicted* standings (live from the
    score inputs, or from their saved picks)."""
    names = {
        r["team_id"]: r["name"] for r in conn.execute("SELECT team_id, name FROM teams")
    }
    teams = [
        r["name"]
        for r in conn.execute(
            "SELECT name FROM teams WHERE group_code=? ORDER BY name", (gcode,)
        )
    ]
    tbl = {t: dict(team=t, P=0, W=0, D=0, L=0, GF=0, GA=0, GD=0, Pts=0) for t in teams}
    for hid, aid, hg, ag in scorelines:
        home, away = names.get(hid), names.get(aid)
        if home not in tbl or away not in tbl:
            continue
        hg, ag = int(hg), int(ag)
        for t, gf, ga in ((home, hg, ag), (away, ag, hg)):
            tbl[t]["P"] += 1
            tbl[t]["GF"] += gf
            tbl[t]["GA"] += ga
            tbl[t]["GD"] = tbl[t]["GF"] - tbl[t]["GA"]
        if hg > ag:
            tbl[home]["W"] += 1
            tbl[home]["Pts"] += 3
            tbl[away]["L"] += 1
        elif hg < ag:
            tbl[away]["W"] += 1
            tbl[away]["Pts"] += 3
            tbl[home]["L"] += 1
        else:
            tbl[home]["D"] += 1
            tbl[away]["D"] += 1
            tbl[home]["Pts"] += 1
            tbl[away]["Pts"] += 1
    return sorted(
        tbl.values(), key=lambda x: (-x["Pts"], -x["GD"], -x["GF"], x["team"])
    )


def render_standings_table(standings):
    """Render a standings list as a dataframe with the top-2 (qualifiers)
    flagged. Expects rows from group_standings / standings_from_scorelines."""
    rows = []
    for i, s in enumerate(standings):
        rows.append(
            {
                "": "🟢" if i < 2 else "",
                "Team": s["team"],
                "P": s["P"],
                "W": s["W"],
                "D": s["D"],
                "L": s["L"],
                "GF": s["GF"],
                "GA": s["GA"],
                "GD": s["GD"],
                "Pts": s["Pts"],
            }
        )
    st.dataframe(rows, hide_index=True, use_container_width=True)


def match_label(m):
    return f"{m['home_label']} vs {m['away_label']}"


# --------------------------------------------------------------------------- #
# Top header navigation (boxes + hover/active; hamburger on small screens)
# --------------------------------------------------------------------------- #
PAGES = [
    "🏠 Home",
    "👤 My profile",
    "🎯 Match picks",
    "🃏 Wildcards",
    "🗳️ Predictions",
    "📅 Matches & results",
    "📊 Leaderboard",
    "🔐 Admin",
]
ss().setdefault("nav_page", PAGES[0])


def _nav_buttons(prefix):
    for p in PAGES:
        if st.button(
            p,
            key=f"{prefix}_{p}",
            type="primary" if ss().nav_page == p else "secondary",
            use_container_width=(prefix == "burger"),
        ):
            ss().nav_page = p
            st.rerun()


def render_top_nav():
    st.markdown('<div class="nav-bar"></div>', unsafe_allow_html=True)
    left, right = st.columns([6, 1.4], vertical_alignment="center")
    with left:
        if logged_in():
            with st.container(key="nav_full"):
                _nav_buttons("nav")
            with st.container(key="nav_burger"):
                with st.popover("☰ Menu", use_container_width=True):
                    _nav_buttons("burger")
        else:
            st.markdown(
                '<div class="brand">⚽ World Cup 2026 — Prediction Contest</div>',
                unsafe_allow_html=True,
            )
    with right:
        render_account()
    # Logged-out visitors only ever see the front page.
    return ss().nav_page if logged_in() else "🏠 Home"


page = render_top_nav()

# =========================================================================== #
# HOME
# =========================================================================== #
if page == "🏠 Home":
    st.markdown(
        """
    <div class="wc-hero">
      <div class="ball">⚽</div>
      <h1>SWON GAMES - VM 2026 </h1>
      <p>Hvem er best til å forutse resultatene i årest fotball-vm? Gjør dine predikasjoner og konkurrer om premien! 🏆</p>
    </div>
    """,
        unsafe_allow_html=True,
    )
    st.write("")
    lock_banner()
    if logged_in():
        pid = ss().pid

        # ---- ranking summary: rank, points, deficit to leader ----
        rows = scoring.leaderboard_rows(conn)
        me = next((r for r in rows if r["participant_id"] == pid), None)
        leader = rows[0] if rows else None
        earned = me["total_points"] if me else 0
        c1, c2, c3 = st.columns(3)
        c1.metric("Your rank", f"#{me['rank']} of {len(rows)}" if me else "—")
        c2.metric("Your points", f"{earned:g}")
        if me and leader and me["rank"] > 1:
            c3.metric(
                "Behind leader",
                f"{leader['total_points'] - earned:g} pts",
                delta=f"leader: {leader['name']}",
                delta_color="off",
            )
        elif me:
            c3.metric("Behind leader", "🏆 You're leading!")

        # ---- points progress bar: earned vs total possible ----
        num_matches = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        wild_max = (
            conn.execute("SELECT COALESCE(SUM(points), 0) FROM wildcards").fetchone()[0]
            or 0
        )
        total_max = num_matches * config.MATCH_EXACT_SCORE + wild_max
        played = conn.execute("SELECT COUNT(*) FROM match_results").fetchone()[0]
        st.markdown(f"**Points earned — {earned:g} / {total_max:g} possible**")
        st.progress(min(max(earned / total_max, 0.0), 1.0) if total_max else 0.0)
        st.caption(
            f"{played} of {num_matches} matches have results in · "
            "fills as the organiser enters results."
        )

        st.divider()

        # ---- today's matches (Norwegian time) with your prediction ----
        st.subheader("📅 Today's matches")
        today = datetime.now(OSLO_TZ).date()
        preds = {
            p["match_id"]: p
            for p in conn.execute(
                "SELECT * FROM match_predictions WHERE participant_id=?", (pid,)
            )
        }
        todays = []
        for m in conn.execute("SELECT * FROM matches ORDER BY kickoff_utc, match_id"):
            iso = m["kickoff_utc"]
            if not iso:
                continue
            try:
                dt = datetime.fromisoformat(iso).astimezone(OSLO_TZ)
            except ValueError:
                continue
            if dt.date() == today:
                todays.append((dt, m))
        if not todays:
            st.caption("No matches kick off today. 💤")
        else:
            ko_today = any(m["is_knockout"] for _, m in todays)
            bracket = knockout.resolve_bracket(conn, pid) if ko_today else {}
            trows = []
            for dt, m in todays:
                if m["is_knockout"] and m["match_id"] in bracket:
                    slot = bracket[m["match_id"]]
                    matchup = f"{slot['home_label']} vs {slot['away_label']}"
                else:
                    matchup = f"{m['home_label']} vs {m['away_label']}"
                p = preds.get(m["match_id"])
                pick = f"{p['pred_home']}–{p['pred_away']}" if p else "—"
                trows.append({"Match": matchup, "Your pick": pick})
            st.dataframe(trows, hide_index=True, use_container_width=True)

        st.divider()

        # ---- progress counters ----
        nmatch = conn.execute(
            "SELECT COUNT(*) FROM match_predictions WHERE participant_id=?", (pid,)
        ).fetchone()[0]
        nwild = conn.execute(
            "SELECT COUNT(*) FROM wildcard_predictions WHERE participant_id=?", (pid,)
        ).fetchone()[0]
        nwild_total = conn.execute("SELECT COUNT(*) FROM wildcards").fetchone()[0]
        d1, d2 = st.columns(2)
        d1.metric("Your match picks", f"{nmatch} / {num_matches}")
        d2.metric("Wildcard picks", f"{nwild} / {nwild_total}")
        if dbmod.final_submitted(conn, pid):
            st.success("✅ Your predictions are submitted and locked in.")
        st.caption(
            "Use the top nav to navigate. Start with **My profile** to design your jersey!"
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
            prim = cc1.color_picker("Primary colour", r["shirt_primary"] or "#1801B4")
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
        scopes = dbmod.locked_scopes(conn, pid)
        submitted_final = dbmod.final_submitted(conn, pid, scopes)
        # editability is decided per-stage further down (group g / knockout)

        if submitted_final:
            st.markdown(
                '<div class="lock-banner lock-on">✅ Your predictions are SUBMITTED '
                "and locked. Ask an admin to unlock if you need to make changes.</div>",
                unsafe_allow_html=True,
            )

        ko_stages = [
            r["stage"]
            for r in conn.execute(
                "SELECT stage FROM matches WHERE is_knockout=1 "
                "GROUP BY stage ORDER BY MIN(kickoff_utc), MIN(match_id)"
            )
        ]
        groups_done = dbmod.all_groups_locked(conn, pid, scopes)
        ko_done = dbmod.ko_stages_locked(conn, pid, ko_stages, scopes)

        # all of this player's match predictions (used by both views)
        existing = {
            x["match_id"]: x
            for x in conn.execute(
                "SELECT * FROM match_predictions WHERE participant_id=?", (pid,)
            )
        }

        # layout + bracket styling
        st.markdown(
            """
<style>
  /* group view: stack the filter/picks split on small screens only */
  @media (max-width: 760px){
    .st-key-mp_split > div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"]{
        flex-direction:column !important; }
    .st-key-mp_split > div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"]
        > div[data-testid="stColumn"]{ width:100% !important; flex:1 1 100% !important; }
  }
  .ko-col-title{ font-family:var(--tech); font-size:12px; letter-spacing:.08em;
      color:var(--neon2); text-align:center; padding-bottom:3px; margin-bottom:8px;
      border-bottom:1px solid rgba(41,240,255,.3); }
  .ko-team{ font-size:11px; opacity:.85; margin:1px 0; white-space:nowrap;
      overflow:hidden; text-overflow:ellipsis; }
  .ko-gap{ height:16px; }
  .ko-pad-1{ height:64px; } .ko-pad-2{ height:150px; } .ko-pad-3{ height:215px; }
</style>
""",
            unsafe_allow_html=True,
        )

        view = st.radio("Stage", ["Group stage", "Knockout"], horizontal=True)

        # ------------------------------------------------------------------- #
        if view == "Group stage":
            groups = dbmod.GROUP_CODES
            # Paint locked-in groups green via their button container key.
            locked_groups = [g for g in groups if f"group:{g}" in scopes]
            if locked_groups:
                css = "".join(
                    f".st-key-gbtn_{g} button{{background:#0f7b3f !important;"
                    f"border-color:#28e07a !important;color:#eafff2 !important;"
                    f"box-shadow:0 0 12px rgba(40,224,122,.5) !important;}}"
                    for g in locked_groups
                )
                st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

            with st.container(key="mp_split"):
                left, right = st.columns([1, 2], gap="large")
                with left:
                    st.markdown("**Pick a group**  ·  🟢 = locked in")
                    gcols = st.columns(2)
                    for i, g in enumerate(groups):
                        is_locked = f"group:{g}" in scopes
                        org_locked = dbmod.group_pred_locked(conn, g)
                        suffix = " 🔒" if org_locked else (" ✓" if is_locked else "")
                        btn_type = "primary" if ss().sel_group == g else "secondary"
                        if gcols[i % 2].button(
                            f"Group {g}{suffix}",
                            key=f"gbtn_{g}",
                            type=btn_type,
                            use_container_width=True,
                        ):
                            ss().sel_group = g
                            st.rerun()
                    st.caption("🟢 = you locked it in · 🔒 = closed by organiser")
                with right:
                    g = ss().sel_group
                    can_edit = group_editable(g, pid)
                    st.subheader(
                        f"Group {g}"
                        + ("  🟢 locked in" if f"group:{g}" in scopes else "")
                    )
                    if dbmod.group_pred_locked(conn, g):
                        st.info(
                            "🔒 Group " + g + " predictions are closed by the "
                            "organiser — viewing only."
                        )
                    elif submitted_final:
                        st.caption(
                            "Your predictions are submitted — ask an admin to "
                            "unlock to edit."
                        )
                    gmatches = conn.execute(
                        "SELECT * FROM matches WHERE group_code=? "
                        "ORDER BY matchday, match_id",
                        (g,),
                    ).fetchall()
                    # Live inputs (no form) so the predicted standings below update
                    # as soon as a scoreline changes.
                    picks = []
                    for m in gmatches:
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
                        picks.append((m, int(hv), int(av)))

                    if st.button(
                        f"🔒 Lock in Group {g} picks",
                        type="primary",
                        disabled=not can_edit,
                        key=f"lockbtn_{g}",
                    ):
                        for m, hv, av in picks:
                            upsert(
                                conn,
                                "match_predictions",
                                {
                                    "participant_id": pid,
                                    "match_id": m["match_id"],
                                    "pred_home": hv,
                                    "pred_away": av,
                                    "pred_advance": None,
                                    "submitted_at": dbmod.now_iso(),
                                },
                                ["participant_id", "match_id"],
                            )
                        dbmod.lock_scope(conn, pid, f"group:{g}")
                        conn.commit()
                        st.success(f"Group {g} picks locked in! ⚽")
                        st.rerun()

                    # Predicted standings — recomputed live from the inputs above.
                    st.markdown("**📊 Your predicted standings**")
                    render_standings_table(
                        standings_from_scorelines(
                            g,
                            [
                                (m["home_team_id"], m["away_team_id"], hv, av)
                                for m, hv, av in picks
                            ],
                        )
                    )
                    st.caption(
                        "🟢 = top 2 advance. Updates as you edit · "
                        + (
                            "locked in."
                            if f"group:{g}" in scopes
                            else "press **Lock in** to save."
                        )
                    )

        # ------------------------------------------------------------------- #
        else:  # Knockout — functional entry; centered bracket layout is TBD
            if not groups_done:
                missing = [g for g in dbmod.GROUP_CODES if f"group:{g}" not in scopes]
                st.info(
                    "🔒 Knockout predictions unlock once you've locked in **all 12 "
                    "groups**. Still to lock in: "
                    + ", ".join(f"Group {g}" for g in missing)
                )
            else:
                can_edit = knockout_editable(pid)
                if dbmod.knockout_pred_locked(conn):
                    st.info(
                        "🔒 Knockout predictions are closed by the organiser — "
                        "viewing only."
                    )
                elif submitted_final:
                    st.caption(
                        "Your predictions are submitted — ask an admin to "
                        "unlock to edit."
                    )
                st.caption(
                    (
                        "🟢 Knockout picks are locked in."
                        if ko_done
                        else "Match-ups are derived from your group predictions. Enter your "
                        "scorelines, then **Save knockout picks** — saving also feeds the "
                        "next round (R32 winners → R16, and so on)."
                    )
                )

                # Derived bracket for this player (from their group + KO picks).
                bracket = knockout.resolve_bracket(conn, pid)

                by_stage: dict[str, list] = {}
                for m in conn.execute("SELECT * FROM matches WHERE is_knockout=1"):
                    by_stage.setdefault(m["stage"], []).append(m)

                def _num(m):
                    try:
                        return int(str(m["match_id"]).rsplit("_", 1)[-1])
                    except ValueError:
                        return 0

                for s in by_stage:
                    by_stage[s].sort(key=_num)

                picks: list = []

                def ko_slot(m):
                    mid = m["match_id"]
                    slot = bracket.get(mid, {})
                    home_id, away_id = slot.get("home_id"), slot.get("away_id")
                    hl = slot.get("home_label", m["home_label"])
                    al = slot.get("away_label", m["away_label"])
                    ex = existing.get(mid)
                    st.markdown(
                        f"<div class='ko-team'>{hl}</div>", unsafe_allow_html=True
                    )
                    hv = st.number_input(
                        "H",
                        0,
                        30,
                        value=ex["pred_home"] if ex else 0,
                        key=f"h_{mid}",
                        disabled=not can_edit,
                        label_visibility="collapsed",
                    )
                    st.markdown(
                        f"<div class='ko-team'>{al}</div>", unsafe_allow_html=True
                    )
                    av = st.number_input(
                        "A",
                        0,
                        30,
                        value=ex["pred_away"] if ex else 0,
                        key=f"a_{mid}",
                        disabled=not can_edit,
                        label_visibility="collapsed",
                    )
                    # who-advances picker (used only if the scoreline is level)
                    adv = None
                    if home_id is not None and away_id is not None:
                        opts = [home_id, away_id]
                        cur = ex["pred_advance"] if ex else None
                        idx = opts.index(cur) if cur in opts else 0
                        adv = st.radio(
                            "Advances if level",
                            opts,
                            index=idx,
                            format_func=lambda t: bracket[mid][
                                "home_label" if t == home_id else "away_label"
                            ],
                            key=f"adv_{mid}",
                            disabled=not can_edit,
                            horizontal=True,
                        )
                    picks.append((mid, hv, av, adv))
                    st.markdown("<div class='ko-gap'></div>", unsafe_allow_html=True)

                with st.form("ko_all"):
                    for stage in ko_stages:
                        ms = by_stage.get(stage, [])
                        if not ms:
                            continue
                        st.markdown(f"**{stage}**")
                        ncol = 2 if len(ms) > 1 else 1
                        cols = st.columns(ncol)
                        for i, m in enumerate(ms):
                            with cols[i % ncol]:
                                ko_slot(m)
                        st.divider()
                    if st.form_submit_button(
                        "💾 Save knockout picks", type="primary", disabled=not can_edit
                    ):
                        for mid, hv, av, adv in picks:
                            upsert(
                                conn,
                                "match_predictions",
                                {
                                    "participant_id": pid,
                                    "match_id": mid,
                                    "pred_home": int(hv),
                                    "pred_away": int(av),
                                    "pred_advance": int(adv)
                                    if adv is not None
                                    else None,
                                    "submitted_at": dbmod.now_iso(),
                                },
                                ["participant_id", "match_id"],
                            )
                        for s in ko_stages:
                            dbmod.lock_scope(conn, pid, f"ko:{s}")
                        conn.commit()
                        st.success(
                            "Knockout picks saved! Match-ups for the next "
                            "rounds now reflect your results. 🏆"
                        )
                        st.rerun()

                # final submit: once the knockout stage is locked in
                st.divider()
                if ko_done and not submitted_final and can_edit:
                    st.markdown("**All groups and the knockout stage are locked in.**")
                    st.caption(
                        "Submitting freezes ALL your picks. An admin can "
                        "unlock you afterwards if you need changes."
                    )
                    if st.button("✅ Submit predictions (final)", type="primary"):
                        dbmod.lock_scope(conn, pid, "final")
                        conn.commit()
                        ss().balloons_done = False
                        st.success("Predictions submitted and locked! 🎉")
                        st.rerun()
                elif not ko_done and not submitted_final:
                    st.caption(
                        "Save your knockout picks to enable the final "
                        "**Submit predictions** button."
                    )

# =========================================================================== #
# WILDCARDS
# =========================================================================== #
elif page == "🃏 Wildcards":
    st.header("🃏 Wildcard predictions")
    lock_banner()
    if not logged_in():
        need_login()
    elif not wildcards_editable(ss().pid):
        if dbmod.final_submitted(conn, ss().pid):
            st.warning(
                "Your predictions are submitted and locked — ask an admin "
                "to unlock if you need to edit wildcards."
            )
        else:
            st.warning(
                "Wildcard predictions are closed by the organiser — viewing only."
            )
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
                elif w["type"] in ("boolean", "choice", "bin"):
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
                elif w["type"] == "text":
                    answers[w["wildcard_id"]] = st.text_input(
                        label, value=cur or "", key=w["wildcard_id"]
                    )
                if w["hint"]:
                    st.caption(w["hint"])
            if st.form_submit_button("🔒 Lock in wildcards", type="primary"):
                for wid, val in answers.items():
                    if str(val).strip():
                        upsert(
                            conn,
                            "wildcard_predictions",
                            {
                                "participant_id": pid,
                                "wildcard_id": wid,
                                "value": str(val).strip(),
                                "submitted_at": dbmod.now_iso(),
                            },
                            ["participant_id", "wildcard_id"],
                        )
                st.success("Wildcards locked in! 🃏")

# =========================================================================== #
# PREDICTIONS  (own anytime; everyone's only after the lock)
# =========================================================================== #
elif page == "🗳️ Predictions":
    st.header("🗳️ Predictions")
    locked = reveal_others()
    if not logged_in():
        need_login()
    else:
        if not locked:
            st.info(
                "You can review **your own** predictions here. Everyone "
                "else's unlock automatically once the organiser locks the "
                "first stage — no peeking before then. 🙈"
            )
        modes = ["My predictions"] + (["Compare everyone"] if locked else [])
        mode = st.radio("View", modes, horizontal=True)
        cat = st.radio("Category", ["Match picks", "Wildcards"], horizontal=True)
        players = [
            (r["participant_id"], r["name"])
            for r in conn.execute(
                "SELECT participant_id, name FROM participants ORDER BY name"
            )
        ]

        def render_one(pid, name):
            if cat == "Match picks":
                g = group_tile_picker("pred_grp")
                ms = conn.execute(
                    "SELECT * FROM matches WHERE group_code=? ORDER BY matchday, match_id",
                    (g,),
                ).fetchall()
                pr = {
                    x["match_id"]: x
                    for x in conn.execute(
                        "SELECT * FROM match_predictions WHERE participant_id=?", (pid,)
                    )
                }
                rows = []
                for m in ms:
                    p = pr.get(m["match_id"])
                    rows.append(
                        {
                            "Match": match_label(m),
                            "Pick": f"{p['pred_home']}–{p['pred_away']}" if p else "—",
                        }
                    )
                st.dataframe(rows, hide_index=True, use_container_width=True)
                # predicted standings from this player's saved group picks
                st.markdown(f"**📊 Predicted standings — Group {g}**")
                scorelines = [
                    (
                        m["home_team_id"],
                        m["away_team_id"],
                        pr[m["match_id"]]["pred_home"],
                        pr[m["match_id"]]["pred_away"],
                    )
                    for m in ms
                    if m["match_id"] in pr
                ]
                render_standings_table(standings_from_scorelines(g, scorelines))
                st.caption("🟢 = top 2 advance, based on saved picks.")
            else:
                ex = {
                    r["wildcard_id"]: r["value"]
                    for r in conn.execute(
                        "SELECT * FROM wildcard_predictions WHERE participant_id=?",
                        (pid,),
                    )
                }
                rows = [
                    {"Question": w["question"], "Answer": ex.get(w["wildcard_id"], "—")}
                    for w in conn.execute(
                        "SELECT * FROM wildcards ORDER BY wildcard_id"
                    )
                ]
                st.dataframe(rows, hide_index=True, use_container_width=True)

        if mode == "My predictions":
            st.caption(f"Showing **{ss().pname}**")
            render_one(ss().pid, ss().pname)
        else:  # Compare everyone (locked only)
            if cat == "Match picks":
                g = group_tile_picker("pred_grp")
                ms = conn.execute(
                    "SELECT * FROM matches WHERE group_code=? ORDER BY matchday, match_id",
                    (g,),
                ).fetchall()
                cols = {
                    m[
                        "match_id"
                    ]: f"{(m['home_label'] or '')[:3]}–{(m['away_label'] or '')[:3]}"
                    for m in ms
                }
                allpred = {}
                for x in conn.execute("SELECT * FROM match_predictions"):
                    allpred[(x["participant_id"], x["match_id"])] = x
                rows = []
                for pid, name in players:
                    row = {"Player": name}
                    for m in ms:
                        p = allpred.get((pid, m["match_id"]))
                        row[cols[m["match_id"]]] = (
                            f"{p['pred_home']}–{p['pred_away']}" if p else "—"
                        )
                    rows.append(row)
                st.dataframe(rows, hide_index=True, use_container_width=True)
            else:
                wq = [
                    (w["wildcard_id"], w["question"])
                    for w in conn.execute(
                        "SELECT * FROM wildcards ORDER BY wildcard_id"
                    )
                ]
                allw = {}
                for r in conn.execute("SELECT * FROM wildcard_predictions"):
                    allw[(r["participant_id"], r["wildcard_id"])] = r["value"]
                rows = []
                for pid, name in players:
                    row = {"Player": name}
                    for wid, q in wq:
                        row[wid] = allw.get((pid, wid), "—")
                    rows.append(row)
                st.caption(
                    "Columns are wildcard IDs — see the Wildcards page for the questions."
                )
                st.dataframe(rows, hide_index=True, use_container_width=True)

# =========================================================================== #
# MATCHES & RESULTS  (per group, tile filter + standings)
# =========================================================================== #
elif page == "📅 Matches & results":
    st.header("📅 Matches & results")
    g = group_tile_picker("mr_grp")
    names = {
        r["team_id"]: r["name"] for r in conn.execute("SELECT team_id, name FROM teams")
    }
    st.subheader(f"Group {g} — standings")
    standings = group_standings(g)
    st.dataframe(
        [
            {
                "Team": s["team"],
                "P": s["P"],
                "W": s["W"],
                "D": s["D"],
                "L": s["L"],
                "GF": s["GF"],
                "GA": s["GA"],
                "GD": s["GD"],
                "Pts": s["Pts"],
            }
            for s in standings
        ],
        hide_index=True,
        use_container_width=True,
    )
    st.caption("Top 2 of each group advance, plus the 8 best third-placed teams.")

    st.subheader(f"Group {g} — fixtures")
    res = {r["match_id"]: r for r in conn.execute("SELECT * FROM match_results")}
    frows = []
    for m in conn.execute(
        "SELECT * FROM matches WHERE group_code=? ORDER BY matchday, match_id", (g,)
    ):
        r = res.get(m["match_id"])
        score = f"{r['home_goals']} – {r['away_goals']}" if r else "— vs —"
        frows.append(
            {
                "MD": m["matchday"],
                "Home": m["home_label"],
                "Score": score,
                "Away": m["away_label"],
                "Date": (m["kickoff_utc"] or "")[:10],
            }
        )
    st.dataframe(frows, hide_index=True, use_container_width=True)

    with st.expander("Knockout results"):
        krows = []
        for m in conn.execute(
            "SELECT * FROM matches WHERE is_knockout=1 ORDER BY match_id"
        ):
            r = res.get(m["match_id"])
            if not r:
                continue
            krows.append(
                {
                    "Stage": m["stage"],
                    "Home": m["home_label"],
                    "Score": f"{r['home_goals']} – {r['away_goals']}",
                    "Away": m["away_label"],
                }
            )
        st.dataframe(
            krows, hide_index=True, use_container_width=True
        ) if krows else st.caption("No knockout results entered yet.")

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
                pr["shirt_primary"] if pr else "#1801B4",
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
    if not ADMIN_PASSWORD:
        st.error(
            "Admin is not configured. Set an **ADMIN_PASSWORD** secret "
            "(Streamlit Cloud → app ⋮ → Settings → Secrets) and reboot."
        )
        st.stop()
    if not ss().is_admin:
        pw = st.text_input("Admin password", type="password")
        if st.button("Unlock admin"):
            if pw and pw == ADMIN_PASSWORD:
                ss().is_admin = True
                st.rerun()
            else:
                st.error("Wrong password.")
        st.stop()

    st.success("Admin unlocked.")

    # ---- per-stage prediction locks ----
    st.subheader("Prediction locks")
    st.caption(
        "Lock each stage as it kicks off so picks freeze for everyone. "
        "Stages left open stay editable — so late registrants can still "
        "enter them."
    )

    st.markdown("**Group stage** — lock each group when it starts:")
    grps = dbmod.GROUP_CODES
    for rowg in (grps[:6], grps[6:]):
        gcols = st.columns(6)
        for i, g in enumerate(rowg):
            cur = dbmod.group_pred_locked(conn, g)
            new = gcols[i].toggle(f"Grp {g}", value=cur, key=f"glock_g_{g}")
            if new != cur:
                dbmod.set_group_pred_locked(conn, g, new)
                st.rerun()

    lc1, lc2 = st.columns(2)
    ko_cur = dbmod.knockout_pred_locked(conn)
    ko_new = lc1.toggle("🔒 Lock knockout predictions", value=ko_cur, key="glock_ko")
    if ko_new != ko_cur:
        dbmod.set_knockout_pred_locked(conn, ko_new)
        st.rerun()
    wc_cur = dbmod.wildcards_pred_locked(conn)
    wc_new = lc2.toggle("🔒 Lock wildcard predictions", value=wc_cur, key="glock_wc")
    if wc_new != wc_cur:
        dbmod.set_wildcards_pred_locked(conn, wc_new)
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
                upsert(
                    conn,
                    "match_results",
                    {
                        "match_id": mid,
                        "home_goals": int(hg),
                        "away_goals": int(ag),
                        "advance": None,
                    },
                    ["match_id"],
                )
            st.success(f"Saved {len(entries)} result(s).")

    st.divider()
    with st.expander("Wildcard results"):
        st.caption(
            "For the banded 'total goals' question (W01), enter the actual "
            "**number** of goals — it's matched to the band automatically. "
            "For others, enter the exact answer (team / player / Yes-No / band)."
        )
        with st.form("wres"):
            vals = {}
            for w in conn.execute("SELECT * FROM wildcards ORDER BY wildcard_id"):
                vals[w["wildcard_id"]] = st.text_input(
                    f"{w['wildcard_id']}: {w['question']}", key=f"wr_{w['wildcard_id']}"
                )
            if st.form_submit_button("Save wildcard results"):
                for wid, val in vals.items():
                    if str(val).strip():
                        upsert(
                            conn,
                            "wildcard_results",
                            {
                                "wildcard_id": wid,
                                "value": str(val).strip(),
                            },
                            ["wildcard_id"],
                        )
                st.success("Wildcard results saved.")

    st.divider()
    st.subheader("👥 Manage users")
    users = list(conn.execute("SELECT * FROM participants ORDER BY name"))
    if not users:
        st.caption("No players yet.")
    else:
        umap = {u["name"]: u for u in users}
        who = st.selectbox("Select player", list(umap.keys()), key="mu_who")
        u = umap[who]
        upid = u["participant_id"]
        c1, c2 = st.columns([3, 1])
        with c2:
            st.markdown(
                f'<div style="text-align:center">{jersey_img(u["shirt_primary"], u["shirt_secondary"], u["shirt_pattern"], 110)}</div>',
                unsafe_allow_html=True,
            )
        with c1:
            with st.form("mu_edit"):
                new_name = st.text_input("Display name", value=u["name"])
                new_email = st.text_input("Email", value=u["email"] or "")
                teams = [""] + team_options()
                ft = st.selectbox(
                    "Favorite team",
                    teams,
                    index=teams.index(u["favorite_team"])
                    if u["favorite_team"] in teams
                    else 0,
                )
                fp = st.text_input("Favorite player", value=u["favorite_player"] or "")
                jc1, jc2 = st.columns(2)
                prim = jc1.color_picker("Primary", u["shirt_primary"] or "#1801B4")
                sec = jc2.color_picker("Secondary", u["shirt_secondary"] or "#ffffff")
                pat = st.radio(
                    "Pattern",
                    avatar.PATTERNS,
                    index=avatar.PATTERNS.index(u["shirt_pattern"])
                    if u["shirt_pattern"] in avatar.PATTERNS
                    else 0,
                    horizontal=True,
                )
                if st.form_submit_button("💾 Save changes", type="primary"):
                    try:
                        if new_name.strip() and new_name.strip() != u["name"]:
                            dbmod.rename_participant(conn, upid, new_name.strip())
                        dbmod.update_profile(
                            conn,
                            upid,
                            favorite_team=ft,
                            favorite_player=fp,
                            email=new_email,
                            shirt_primary=prim,
                            shirt_secondary=sec,
                            shirt_pattern=pat,
                        )
                        st.success(f"Saved changes for {new_name.strip() or who}.")
                        st.rerun()
                    except Exception:
                        st.error("Could not save — is that display name already taken?")

        st.markdown("**Prediction submission**")
        u_scopes = dbmod.locked_scopes(conn, upid)
        if dbmod.final_submitted(conn, upid, u_scopes):
            st.caption(f"🔒 {who} has **submitted** their predictions (frozen).")
            if st.button(
                "🔓 Unlock predictions (allow edits)",
                use_container_width=True,
                key="mu_unlock",
            ):
                dbmod.unlock_scope(conn, upid, "final")
                st.success(f"{who} can edit their predictions again.")
                st.rerun()
        else:
            n_glocked = sum(1 for g in dbmod.GROUP_CODES if f"group:{g}" in u_scopes)
            st.caption(
                f"✏️ {who} has not submitted yet ({n_glocked}/12 groups locked in)."
            )

        st.markdown("**Reset actions**")
        rc1, rc2 = st.columns(2)
        with rc1:
            if st.button("♻️ Reset profile to defaults", use_container_width=True):
                dbmod.reset_profile(conn, upid)
                st.success(f"Profile reset for {who} (predictions kept).")
                st.rerun()
        with rc2:
            with st.popover("🔑 Reset PIN", use_container_width=True):
                newpin = st.text_input("New PIN", type="password", key="mu_pin")
                if st.button("Set new PIN") and newpin:
                    dbmod.set_pin(conn, upid, newpin)
                    st.success(f"PIN reset for {who}.")

    st.divider()
    if st.button("🔄 Refresh dashboards (HTML + Power BI tables + CSV)"):
        export.export_csvs(conn)
        export.export_dashboard_json(conn)
        # publish scored tables (vw_leaderboard, ...) into the database so
        # Power BI reads ready-computed standings
        export.export_to_db(conn)
        msg = "Refreshed HTML dashboard + CSV backup"
        if conn.dialect == "postgresql":
            msg += " + Power BI tables (vw_leaderboard, vw_match_points, vw_timeline)"
        st.success(msg + ".")

    st.divider()
    st.subheader("Download backup")
    st.caption(
        "One ZIP with every table as CSV — works on the hosted app, no "
        "local run needed. Grab one before/after the deadline to be safe."
    )
    import io
    import zipfile

    def _csv_bytes(rows, cols):
        import csv as _csv

        buf = io.StringIO()
        w = _csv.DictWriter(buf, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: dict(r).get(c, "") for c in cols})
        return buf.getvalue().encode("utf-8")

    def _table(name):
        rows = list(conn.execute(f"SELECT * FROM {name}"))
        cols = list(rows[0].keys()) if rows else []
        return rows, cols

    if st.button("Prepare backup ZIP"):
        zbuf = io.BytesIO()
        tables = [
            "participants",
            "teams",
            "matches",
            "wildcards",
            "match_predictions",
            "wildcard_predictions",
            "match_results",
            "wildcard_results",
            "settings",
            "pred_locks",
        ]
        with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
            for t in tables:
                rows, cols = _table(t)
                if cols:
                    zf.writestr(f"{t}.csv", _csv_bytes(rows, cols))
            lb = scoring.leaderboard_rows(conn)
            if lb:
                zf.writestr("leaderboard.csv", _csv_bytes(lb, list(lb[0].keys())))
        st.session_state["_backup_zip"] = zbuf.getvalue()
        st.success("Backup ready — click below to download.")
    if st.session_state.get("_backup_zip"):
        st.download_button(
            "⬇️ Download backup ZIP",
            data=st.session_state["_backup_zip"],
            file_name="wc2026_backup.zip",
            mime="application/zip",
        )
