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
import random
import html

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

from wc_contest import config, db as dbmod, scoring, export, avatar, knockout, flags  # noqa: E402
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

st.set_page_config(
    page_title="VM 2026 SWON-GAMES",
    page_icon=":material/sports_soccer:",
    layout="wide",
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
    # Keep the wildcard set in step with the seed (updates questions / adds new
    # ones on databases that were seeded before these changes).
    dbmod.sync_wildcards(conn)
    return conn


conn = get_conn()


# --------------------------------------------------------------------------- #
# Cached read layer. Every conn.execute() opens a pooled connection and commits
# (a network round-trip on hosted Postgres), so hot pages that re-query static
# data on every rerun get slow. These caches hold the rarely-changing data in
# memory and are cleared explicitly when an admin/player mutates the relevant
# rows. Keep TTLs short so the live app still feels fresh.
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=600, show_spinner=False)
def cx_teams():
    """Static team dimension: list of dicts (team_id, name, group_code, ...)."""
    return [dict(r) for r in conn.execute(
        "SELECT team_id, name, group_code, confederation, is_host "
        "FROM teams ORDER BY name")]


@st.cache_data(ttl=600, show_spinner=False)
def cx_matches():
    """Static match dimension (fixtures don't change after seeding)."""
    return [dict(r) for r in conn.execute(
        "SELECT * FROM matches ORDER BY matchday, match_id")]


@st.cache_data(ttl=10, show_spinner=False)
def cx_settings():
    """All settings (lock flags etc.) in one query instead of ~15."""
    return {r["key"]: r["value"] for r in conn.execute(
        "SELECT key, value FROM settings")}


@st.cache_data(ttl=20, show_spinner=False)
def cx_leaderboard():
    """Computed standings — the heaviest read. Short TTL keeps it lively."""
    return scoring.leaderboard_rows(conn)


@st.cache_data(ttl=30, show_spinner=False)
def cx_player_bracket(pid):
    """A player's derived knockout bracket. Re-derived on every round-button
    click otherwise (several remote round-trips each time); cache it and clear
    when the player saves picks or the admin changes fixtures/feeders."""
    return knockout.actual_player_bracket(conn, pid)


@st.cache_data(ttl=30, show_spinner=False)
def cx_real_r32():
    """The published Round-of-32 fixtures (shared by all players)."""
    return knockout.real_r32_teams(conn)


def cx_clear_settings():
    cx_settings.clear()


def cx_clear_scores():
    cx_leaderboard.clear()


def cx_clear_brackets():
    """Clear derived knockout state after fixtures, feeders or picks change."""
    cx_player_bracket.clear()
    cx_real_r32.clear()


# convenience views over the cached team list
def team_names():
    return [t["name"] for t in cx_teams()]


def team_name_by_id():
    return {t["team_id"]: t["name"] for t in cx_teams()}


def group_team_names(gcode):
    return sorted(t["name"] for t in cx_teams() if t["group_code"] == gcode)


def setting_on(key):
    return cx_settings().get(key, "0") == "1"


st.markdown(
    """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Orbitron:wght@500;700&display=swap');
  @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0');
  :root { --neon:#6f5bff; --neon2:#29f0ff; --gold:#ffd23f;
          --pixel:"Press Start 2P", monospace; --tech:"Orbitron", sans-serif; }
  /* Material Symbols used inside raw HTML (hero, podium, banners). .msym
     inherits the surrounding colour; .nicon forces the purple neon. */
  .msym, .nicon { font-family:'Material Symbols Outlined'; font-weight:normal;
      font-style:normal; line-height:1; vertical-align:middle;
      font-feature-settings:'liga'; }
  .nicon { color:var(--neon); filter:drop-shadow(0 0 5px rgba(111,91,255,.7)); }
  /* "Compare everyone" match-picks table */
  .cmp { border-collapse:collapse; width:100%; font-size:13px; margin-top:6px; }
  .cmp th, .cmp td { border:1px solid rgba(111,91,255,.25); padding:6px 8px;
      text-align:center; }
  .cmp th { color:var(--neon2); font-family:var(--tech); font-weight:600;
      vertical-align:bottom; line-height:1.25; white-space:normal; }
  .cmp td.pl { text-align:left; font-weight:600; white-space:nowrap; }
  .cmp tbody tr:nth-child(even){ background:rgba(111,91,255,.06); }
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
  /* neon-tint the monochrome Material icons used as app icons (nav, headings,
     buttons, toggles). Alert status icons (info/warning/etc.) keep their own
     colour because they live inside stAlert, not these. */
  .st-key-nav_full [data-testid="stIconMaterial"],
  .st-key-nav_burger [data-testid="stIconMaterial"],
  [data-testid="stHeading"] [data-testid="stIconMaterial"],
  .stButton [data-testid="stIconMaterial"],
  .stFormSubmitButton [data-testid="stIconMaterial"],
  .stDownloadButton [data-testid="stIconMaterial"],
  [data-testid="stPopover"] [data-testid="stIconMaterial"],
  [data-testid="stMarkdownContainer"] [data-testid="stIconMaterial"]{
      color:var(--neon) !important;
      filter:drop-shadow(0 0 5px rgba(111,91,255,.7)); }
  .nav-bar{ border-bottom:1px solid var(--neon); padding:6px 0 12px; margin-bottom:14px;
            box-shadow:0 6px 18px -12px rgba(111,91,255,.6); }
  /* responsive: inline bar on wide screens, hamburger on small */
  .st-key-nav_burger{ display:none; }
  @media (max-width: 820px){
      .st-key-nav_full,
      .st-key-nav_full > div[data-testid="stVerticalBlock"]{ display:none !important; }
      .st-key-nav_burger{ display:block !important; }
  }
  /* ---- knockout match cards ---- */
  .ko-head{ font-family:var(--tech); font-size:12px; letter-spacing:.08em;
            text-transform:uppercase; color:var(--neon2); margin:2px 0 4px;
            text-shadow:0 0 6px rgba(41,240,255,.5); }
  .ko-meta{ font-family:var(--tech); font-size:11px; color:#8aa0c0; }
  .tchip{ display:inline-flex; align-items:center; gap:8px; }
  .tchip-flag{ font-size:22px; line-height:1; }
  .tchip-code{ font-family:var(--pixel); font-size:11px; color:var(--neon2);
               border:1px solid var(--neon); border-radius:3px; padding:2px 5px; }
  .tchip-name{ font-family:var(--tech); font-weight:600; font-size:14px; color:#e7eaf6; }
  .tchip-tbd{ opacity:.6; }
  .tchip-tbd .tchip-name{ color:#8aa0c0; font-style:italic; }
  /* account control pinned to the right of the nav row */
  .st-key-acct{ display:flex; justify-content:flex-end; }
  .brand{ font-family:var(--tech); font-weight:700; color:#cdd6f4;
          padding:8px 2px; font-size:16px; letter-spacing:.03em; }
  /* keep both prediction toggles compact rather than full-width
     (~300px per choice → ~600px for the two-option toggle) */
  .st-key-mk_toggle, .st-key-mp_toggle,
  .st-key-sp_mode_box, .st-key-sp_cat_box{ max-width:600px; }
  /* Make-predictions toggle — matches the top-nav menu items, so it reads as a
     section selector and is visually distinct from the in-page Stage toggle */
  .st-key-mk_toggle .stButton button{
      font-family:var(--tech) !important; letter-spacing:.02em; font-weight:600;
      border:1px solid var(--line) !important; border-radius:6px !important;
      background:#11152a !important; color:#cdd6f4 !important; box-shadow:none !important; }
  .st-key-mk_toggle .stButton button:hover{
      border-color:var(--neon2) !important; color:#fff !important;
      box-shadow:0 0 12px rgba(41,240,255,.45) !important; transform:translateY(-1px); }
  .st-key-mk_toggle .stButton button[kind="primary"]{
      background:linear-gradient(180deg,#1801B4,#3a23c9) !important;
      border:1px solid var(--neon) !important; color:#fff !important;
      box-shadow:0 0 16px rgba(111,91,255,.65) !important; }
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
    """Can this player still edit Group g? Open unless: the organiser locked the
    group globally, the player has already SUBMITTED this group (group:<g>), or
    the player has submitted their final predictions. Draft-saved (but not
    submitted) groups stay editable."""
    scopes = dbmod.locked_scopes(conn, pid)
    return (not setting_on(f"glock_group_{g}")
            and f"group:{g}" not in scopes
            and "final" not in scopes)


def knockout_editable(pid) -> bool:
    return not setting_on("glock_knockout") and not dbmod.final_submitted(conn, pid)


def wildcards_editable(pid) -> bool:
    return not setting_on("glock_wildcards") and not dbmod.final_submitted(conn, pid)


def reveal_others() -> bool:
    """Everyone's picks become visible once any stage has been globally locked
    (i.e. the tournament has started)."""
    s = cx_settings()
    return (s.get("glock_knockout") == "1" or s.get("glock_wildcards") == "1"
            or any(s.get(f"glock_group_{g}") == "1" for g in dbmod.GROUP_CODES))


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
    return team_names()


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
            with st.popover(f":material/account_circle: {ss().pname}"):
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
            with st.popover(":material/login: Log in"):
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
    s = cx_settings()
    g_locked = [g for g in dbmod.GROUP_CODES if s.get(f"glock_group_{g}") == "1"]
    ko = s.get("glock_knockout") == "1"
    wc = s.get("glock_wildcards") == "1"
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
        f'<div class="lock-banner lock-on"><span class="msym">lock</span> '
        f"Locked by the organiser: "
        f"{'; '.join(bits)}. Other stages remain open.</div>",
        unsafe_allow_html=True,
    )


GROUPS_AL = [chr(c) for c in range(ord("A"), ord("L") + 1)]


def tile_toggle(state_key: str, options: list[str], default: str | None = None,
                labels: list[str] | None = None):
    """Render options as a row of equal-width box buttons (same look as the
    group filters); the selected one is highlighted. Returns the selected
    option key. `labels` (optional) sets the button text shown for each option,
    so the returned key can stay stable while the display uses Material icons."""
    ss().setdefault(state_key, default or options[0])
    if ss()[state_key] not in options:
        ss()[state_key] = options[0]
    cols = st.columns(len(options))
    for i, opt in enumerate(options):
        lbl = labels[i] if labels else opt
        typ = "primary" if ss()[state_key] == opt else "secondary"
        if cols[i].button(lbl, key=f"{state_key}_{i}", type=typ,
                          use_container_width=True):
            ss()[state_key] = opt
            st.rerun()
    return ss()[state_key]


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
    names = team_name_by_id()
    teams = group_team_names(gcode)
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
    names = team_name_by_id()
    teams = group_team_names(gcode)
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


def html_table(rows, headers=None):
    """Render a list-of-dicts as a neon-styled HTML table (same look as the
    Compare-everyone table) so every table in the app matches. Content is
    escaped; `headers` optionally maps a column key to a display label.
    Wrapped for horizontal scroll so wide tables don't overflow the page."""
    if not rows:
        return
    cols = list(rows[0].keys())
    hmap = headers or {}
    head = "".join(f"<th>{html.escape(str(hmap.get(c, c)))}</th>" for c in cols)

    def _fmt(v):
        # show whole numbers as integers (no trailing .0); leave the rest as-is
        if isinstance(v, bool):
            return str(v)
        if isinstance(v, (int, float)) and float(v).is_integer():
            return str(int(v))
        return str(v)

    body = ""
    for r in rows:
        body += "<tr>" + "".join(
            f"<td>{html.escape(_fmt(r.get(c, '')))}</td>" for c in cols) + "</tr>"
    st.markdown(
        "<div style='overflow-x:auto'><table class='cmp'><thead><tr>"
        f"{head}</tr></thead><tbody>{body}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def render_standings_table(standings):
    """Render a standings list with the top-2 (qualifiers) flagged."""
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
    html_table(rows)


def match_label(m):
    return f"{m['home_label']} vs {m['away_label']}"


def autofill_predictions(pid, scopes, ko_stages):
    """Random-fill every still-editable, not-yet-predicted match (groups +
    knockout) with a 0–3 scoreline, plus a random advancing side on knockout
    draws. Non-destructive: skips matches you've already entered and stages
    you've submitted or the organiser has locked. Saves as drafts (no submit).
    Returns the number of matches filled."""
    if "final" in scopes:
        return 0
    have = {x["match_id"] for x in conn.execute(
        "SELECT match_id FROM match_predictions WHERE participant_id=?", (pid,))}
    now = dbmod.now_iso()
    filled = 0

    def put(mid, hg, ag, adv=None):
        upsert(conn, "match_predictions", {
            "participant_id": pid, "match_id": mid,
            "pred_home": hg, "pred_away": ag, "pred_advance": adv,
            "submitted_at": now,
        }, ["participant_id", "match_id"])

    # group stage — skip submitted / organiser-locked groups
    for g in dbmod.GROUP_CODES:
        if setting_on(f"glock_group_{g}") or f"group:{g}" in scopes:
            continue
        for m in cx_matches():
            if m["is_knockout"] or m["group_code"] != g or m["match_id"] in have:
                continue
            put(m["match_id"], random.randint(0, 3), random.randint(0, 3))
            have.add(m["match_id"])
            filled += 1

    # knockout — cascade in round order so each round's match-ups reflect the
    # winners just filled in the previous round
    if not setting_on("glock_knockout"):
        for stage in ko_stages:
            if f"ko:{stage}" in scopes:
                continue
            bracket = knockout.resolve_bracket(conn, pid)
            stage_ms = sorted(
                (m for m in cx_matches()
                 if m["is_knockout"] and m["stage"] == stage),
                key=lambda mm: int(str(mm["match_id"]).rsplit("_", 1)[-1]))
            for m in stage_ms:
                mid = m["match_id"]
                if mid in have:
                    continue
                hg, ag = random.randint(0, 3), random.randint(0, 3)
                adv = None
                if hg == ag:
                    slot = bracket.get(mid, {})
                    hid, aid = slot.get("home_id"), slot.get("away_id")
                    if hid is not None and aid is not None:
                        adv = random.choice([hid, aid])
                put(mid, hg, ag, adv)
                have.add(mid)
                filled += 1
    conn.commit()
    return filled


# --------------------------------------------------------------------------- #
# Top header navigation (boxes + hover/active; hamburger on small screens)
# --------------------------------------------------------------------------- #
# Each nav item: (page key used in `page == ...` checks, Material icon, label).
# The emoji key is kept only as a stable identifier; the button shows the
# monochrome Material icon (neon-coloured via CSS) + text instead.
NAV = [
    ("🏠 Home", ":material/home:", "Home"),
    ("👤 My profile", ":material/person:", "My profile"),
    ("🎯 Make predictions", ":material/edit_square:", "Make predictions"),
    ("🗳️ See predictions", ":material/visibility:", "See predictions"),
    ("📅 Matches & results", ":material/calendar_month:", "Matches & results"),
    ("📊 Leaderboard", ":material/leaderboard:", "Leaderboard"),
    ("🔐 Admin", ":material/admin_panel_settings:", "Admin"),
]
PAGES = [key for key, _icon, _label in NAV]
ss().setdefault("nav_page", PAGES[0])


def _nav_buttons(prefix):
    for key, icon, label in NAV:
        if st.button(
            f"{icon} {label}",
            key=f"{prefix}_{key}",
            type="primary" if ss().nav_page == key else "secondary",
            use_container_width=(prefix == "burger"),
        ):
            ss().nav_page = key
            st.rerun()


def render_top_nav():
    st.markdown('<div class="nav-bar"></div>', unsafe_allow_html=True)
    left, right = st.columns([6, 1.4], vertical_alignment="center")
    with left:
        if logged_in():
            with st.container(key="nav_full"):
                _nav_buttons("nav")
            with st.container(key="nav_burger"):
                with st.popover(":material/menu: Menu", use_container_width=True):
                    _nav_buttons("burger")
        else:
            st.markdown(
                '<div class="brand"><span class="nicon">sports_soccer</span> '
                "World Cup 2026 — Prediction Contest</div>",
                unsafe_allow_html=True,
            )
    with right:
        render_account()
    # Logged-out visitors only ever see the front page.
    return ss().nav_page if logged_in() else "🏠 Home"


page = render_top_nav()

# "Make predictions" is one nav page with a toggle between the match-picks and
# wildcards views. Render the toggle here and map to the internal page the
# blocks below already handle (keeps the nav button highlighted as one page).
if page == "🎯 Make predictions":
    with st.container(key="mk_toggle"):
        page = tile_toggle(
            "mk_view", ["🎯 Match picks", "🃏 Wildcards"],
            labels=[":material/sports_soccer: Match picks",
                    ":material/casino: Wildcards"])

# =========================================================================== #
# HOME
# =========================================================================== #
if page == "🏠 Home":
    st.markdown(
        """
    <div class="wc-hero">
      <div class="ball"><span class="nicon">sports_soccer</span></div>
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
        rows = cx_leaderboard()
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
        st.subheader(":material/calendar_today: Today's matches")
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
            html_table(trows)

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
            st.success("Your predictions are submitted and locked in.", icon=":material/check_circle:")
        st.caption(
            "Use the top nav to navigate. Start with **My profile** to design your jersey!"
        )
    else:
        need_login()

# =========================================================================== #
# MY PROFILE
# =========================================================================== #
elif page == "👤 My profile":
    st.header(":material/person: My profile")
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
        if st.button(":material/save: Save profile", type="primary"):
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
    st.header(":material/sports_soccer: Match-by-match predictions")
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
                '<div class="lock-banner" style="background:rgba(242,166,120,.14);'
                "border:1px solid #f2a678;color:#f2a678;"
                'box-shadow:0 0 12px rgba(242,166,120,.4);">'
                '<span class="msym">check_circle</span> Your predictions are '
                "SUBMITTED and locked. Ask an admin to unlock if you need to make "
                'changes.</div>',
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

        # ---- Auto-fill: random scores for everything still open ----
        groups_open = [g for g in dbmod.GROUP_CODES
                       if not setting_on(f"glock_group_{g}")
                       and f"group:{g}" not in scopes and not submitted_final]
        ko_open = (not setting_on("glock_knockout") and not submitted_final
                   and any(f"ko:{s}" not in scopes for s in ko_stages))
        if groups_open or ko_open:
            if st.button(
                ":material/casino: Auto-fill remaining (random)",
                help="Gives each team a random score of 0, 1, 2 or 3 for every "
                     "match you haven't filled yet, in any group/round you "
                     "haven't submitted. Saved as drafts — review and Submit "
                     "yourself.",
            ):
                n = autofill_predictions(pid, scopes, ko_stages)
                st.success(f"Auto-filled {n} match(es) with random scores "
                           "(saved as drafts). Review, then Submit each stage.")
                st.rerun()

        with st.container(key="mp_toggle"):
            view = tile_toggle(
                "mp_view", ["Group stage", "Knockout"],
                labels=[":material/groups: Group stage",
                        ":material/emoji_events: Knockout"])

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
                    st.markdown("**Pick a group**  ·  🟢 = submitted")
                    gcols = st.columns(2)
                    for i, g in enumerate(groups):
                        is_locked = f"group:{g}" in scopes
                        org_locked = setting_on(f"glock_group_{g}")
                        suffix = (" :material/lock:" if org_locked
                                  else (" ✓" if is_locked else ""))
                        btn_type = "primary" if ss().sel_group == g else "secondary"
                        if gcols[i % 2].button(
                            f"Group {g}{suffix}",
                            key=f"gbtn_{g}",
                            type=btn_type,
                            use_container_width=True,
                        ):
                            ss().sel_group = g
                            st.rerun()
                    st.caption("🟢 = submitted (scores points) · "
                               ":material/lock: = closed by organiser")
                with right:
                    g = ss().sel_group
                    can_edit = group_editable(g, pid)
                    g_submitted = f"group:{g}" in scopes
                    st.subheader(
                        f"Group {g}" + ("  🟢 submitted" if g_submitted else "")
                    )
                    if setting_on(f"glock_group_{g}"):
                        st.info(
                            ":material/lock: Group " + g + " predictions are closed by the "
                            "organiser — viewing only."
                        )
                    elif submitted_final:
                        st.caption(
                            "Your predictions are submitted — ask an admin to "
                            "unlock to edit."
                        )
                    elif g_submitted:
                        st.info(
                            "🟢 Group " + g + " is submitted and locked — it counts "
                            "for points. Ask an admin to unlock if you need changes."
                        )
                    else:
                        st.caption(
                            "**Save** keeps a draft you can edit later. **Submit** "
                            "locks the group — only submitted groups score points."
                        )
                    gmatches = [
                        m for m in cx_matches()
                        if not m["is_knockout"] and m["group_code"] == g
                    ]
                    # Inputs live in a form, so editing does NOT rerun on every
                    # keystroke — the page only reruns (and the standings update)
                    # when Save or Submit is pressed.
                    with st.form(f"gform_{g}"):
                        fc1, fc2 = st.columns(2)
                        with fc1:
                            g_save = st.form_submit_button(
                                ":material/save: Save predictions",
                                disabled=not can_edit,
                                use_container_width=True)
                        with fc2:
                            g_submit = st.form_submit_button(
                                f":material/lock: Submit Group {g}", type="primary",
                                disabled=not can_edit, use_container_width=True)
                        picks = []
                        for m in gmatches:
                            ex = existing.get(m["match_id"])
                            c1, c2, c3, c4 = st.columns([3, 1, 1, 3])
                            c1.markdown(f"**{m['home_label']}**")
                            hv = c2.number_input(
                                "H", 0, 30, value=ex["pred_home"] if ex else 0,
                                key=f"h_{m['match_id']}", disabled=not can_edit,
                                label_visibility="collapsed")
                            av = c3.number_input(
                                "A", 0, 30, value=ex["pred_away"] if ex else 0,
                                key=f"a_{m['match_id']}", disabled=not can_edit,
                                label_visibility="collapsed")
                            c4.markdown(f"**{m['away_label']}**")
                            picks.append((m, hv, av))
                    if g_save or g_submit:
                        for m, hv, av in picks:
                            upsert(conn, "match_predictions", {
                                "participant_id": pid, "match_id": m["match_id"],
                                "pred_home": int(hv), "pred_away": int(av),
                                "pred_advance": None, "submitted_at": dbmod.now_iso(),
                            }, ["participant_id", "match_id"])
                        if g_submit:
                            dbmod.lock_scope(conn, pid, f"group:{g}")
                            cx_clear_scores()
                        conn.commit()
                        st.success(
                            f"Group {g} submitted & locked! It now counts for points."
                            if g_submit else
                            f"Group {g} draft saved (won't score until you submit).")
                        st.rerun()

                    # Predicted standings — from your SAVED picks (updates on Save/Submit).
                    st.markdown(":material/leaderboard: **Your predicted standings**")
                    saved_lines = [
                        (m["home_team_id"], m["away_team_id"],
                         existing[m["match_id"]]["pred_home"],
                         existing[m["match_id"]]["pred_away"])
                        for m in gmatches if m["match_id"] in existing
                    ]
                    render_standings_table(standings_from_scorelines(g, saved_lines))
                    st.caption(
                        "🟢 = top 2 advance · "
                        + ("submitted & locked."
                           if g_submitted else "updates when you Save or Submit.")
                    )

        # ------------------------------------------------------------------- #
        else:  # Knockout — predict your WHOLE bracket; R16+ derive from your picks
            ako_locked = dbmod.actual_ko_locked(conn)
            SHORT = {"Round of 32": "R32", "Round of 16": "R16",
                     "Quarter-final": "QF", "Semi-final": "SF",
                     "Third place": "3rd", "Final": "Final"}
            r32 = cx_real_r32()
            if not r32:
                st.info(":material/lock: Knockout fixtures aren't published yet — "
                        "they appear once the group stage is done and the organiser "
                        "publishes the real Round of 32.")
            else:
                if ako_locked:
                    st.info(":material/lock: Knockout predictions are closed by the "
                            "organiser — viewing only.")
                st.caption("Predict your **whole** bracket: pick the Round of 32, and "
                           "each later round fills in from the winners you choose.")
                bracket = cx_player_bracket(pid)
                meta = {m["match_id"]: m for m in cx_matches()
                        if m["is_knockout"]}
                stages_avail = ko_stages
                ss().setdefault("sel_ko", stages_avail[0])
                if ss().sel_ko not in stages_avail:
                    ss().sel_ko = stages_avail[0]
                st.write("**Pick a round:**")
                kcols = st.columns(len(stages_avail))
                for i, s in enumerate(stages_avail):
                    btype = "primary" if ss().sel_ko == s else "secondary"
                    if kcols[i].button(SHORT.get(s, s), key=f"kobtn_{i}",
                                       type=btype, use_container_width=True):
                        ss().sel_ko = s
                        st.rerun()

                stage = ss().sel_ko
                st.subheader(stage)
                ex = {r["match_id"]: r for r in conn.execute(
                    "SELECT * FROM actual_ko_predictions WHERE participant_id=?", (pid,))}
                slots = [s for s in bracket.values()
                         if meta.get(s["ko_id"], {}).get("stage") == stage]
                slots.sort(key=lambda s: s["num"])

                def _side_html(slot, side):
                    tid = slot[f"{side}_id"]
                    lbl = slot[f"{side}_label"]
                    if tid:
                        return flags.chip(lbl)
                    return ("<span class='tchip tchip-tbd'>🏳️ "
                            f"<span class='tchip-name'>{lbl}</span></span>")

                picks = []
                with st.form(f"koform_{stage}"):
                    k_submit = st.form_submit_button(
                        f":material/lock: Lock in {SHORT.get(stage, stage)} picks",
                        type="primary", disabled=ako_locked, use_container_width=True)
                    ncol = 2 if len(slots) > 1 else 1
                    cols = st.columns(ncol)
                    for i, slot in enumerate(slots):
                        with cols[i % ncol]:
                            mid = slot["ko_id"]
                            e = ex.get(mid)
                            date = (meta.get(mid, {}).get("kickoff_utc") or "")[:10]
                            ready = (slot["home_id"] is not None
                                     and slot["away_id"] is not None)
                            st.markdown(
                                f"<div class='ko-head'>{SHORT.get(stage, stage)} · "
                                f"match {i + 1}</div><div class='ko-meta'>{date}</div>",
                                unsafe_allow_html=True)
                            st.markdown(_side_html(slot, "home"), unsafe_allow_html=True)
                            hv = st.number_input(
                                "H", 0, 30, value=e["pred_home"] if e else 0,
                                key=f"akh_{mid}", disabled=ako_locked or not ready,
                                label_visibility="collapsed")
                            st.markdown(_side_html(slot, "away"), unsafe_allow_html=True)
                            av = st.number_input(
                                "A", 0, 30, value=e["pred_away"] if e else 0,
                                key=f"aka_{mid}", disabled=ako_locked or not ready,
                                label_visibility="collapsed")
                            adv = None
                            if ready:
                                opts = [slot["home_id"], slot["away_id"]]
                                cur = e["pred_advance"] if e else None
                                idx = opts.index(cur) if cur in opts else 0
                                adv = st.radio(
                                    "Advances if level", opts, index=idx,
                                    format_func=lambda t, h=slot["home_id"],
                                    hl=slot["home_label"], al=slot["away_label"]:
                                        hl if t == h else al,
                                    key=f"akadv_{mid}", disabled=ako_locked,
                                    horizontal=True)
                            else:
                                st.caption("Decide the earlier round first.")
                            picks.append((mid, hv, av, adv, ready))
                            st.markdown("<div class='ko-gap'></div>",
                                        unsafe_allow_html=True)
                if k_submit:
                    for mid, hv, av, adv, ready in picks:
                        if not ready:
                            continue
                        upsert(conn, "actual_ko_predictions", {
                            "participant_id": pid, "match_id": mid,
                            "pred_home": int(hv), "pred_away": int(av),
                            "pred_advance": int(adv) if adv is not None else None,
                            "submitted_at": dbmod.now_iso(),
                        }, ["participant_id", "match_id"])
                    cx_clear_scores()
                    cx_clear_brackets()
                    conn.commit()
                    st.success(f"{stage} picks locked in! 🏆")
                    st.rerun()

# =========================================================================== #
# WILDCARDS
# =========================================================================== #
elif page == "🃏 Wildcards":
    st.header(":material/casino: Wildcard predictions")
    lock_banner()
    if not logged_in():
        need_login()
    elif not wildcards_editable(ss().pid):
        if dbmod.final_submitted(conn, ss().pid):
            st.markdown(
                '<div class="lock-banner" style="background:rgba(242,166,120,.14);'
                "border:1px solid #f2a678;color:#f2a678;"
                'box-shadow:0 0 12px rgba(242,166,120,.4);">'
                '<span class="msym">check_circle</span> Your predictions are '
                "submitted and locked. Ask an admin to unlock if you need to edit "
                'wildcards.</div>',
                unsafe_allow_html=True,
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
                        value=int(float(cur)) if cur else 0,
                        step=1,
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
            if st.form_submit_button(":material/lock: Lock in wildcards", type="primary"):
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
elif page == "🗳️ See predictions":
    st.header(":material/visibility: See predictions")
    if not logged_in():
        need_login()
    else:
        with st.container(key="sp_mode_box"):
            mode = tile_toggle(
                "sp_mode", ["My predictions", "Compare everyone"],
                labels=[":material/person: My predictions",
                        ":material/groups: Compare everyone"])
        with st.container(key="sp_cat_box"):
            cat = tile_toggle(
                "sp_cat", ["Match picks", "Wildcards"],
                labels=[":material/sports_soccer: Match picks",
                        ":material/casino: Wildcards"])
        if mode == "Compare everyone":
            st.caption("Everyone's picks for a group or stage are revealed only "
                       "after the organiser locks it — no peeking before then. 🙈")
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
                html_table(rows)
                # predicted standings from this player's saved group picks
                st.markdown(f":material/leaderboard: **Predicted standings — Group {g}**")
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
                html_table(rows)

        if mode == "My predictions":
            st.caption(f"Showing **{ss().pname}**")
            render_one(ss().pid, ss().pname)
        else:  # Compare everyone — reveal only stages the organiser has locked
            if cat == "Match picks":
                g = group_tile_picker("pred_grp")
                if not setting_on(f"glock_group_{g}"):
                    st.info(
                        f":material/lock: Everyone's **Group {g}** picks unlock once the "
                        f"organiser locks Group {g}. Your own are under "
                        "**My predictions**."
                    )
                else:
                    ms = conn.execute(
                        "SELECT * FROM matches WHERE group_code=? "
                        "ORDER BY matchday, match_id", (g,),
                    ).fetchall()
                    allpred = {}
                    for x in conn.execute("SELECT * FROM match_predictions"):
                        allpred[(x["participant_id"], x["match_id"])] = x
                    # one column per match (full names, 3-line header) — avoids the
                    # abbreviation collisions that previously dropped a column
                    head = "".join(
                        f"<th>{html.escape(m['home_label'] or '')}<br>vs.<br>"
                        f"{html.escape(m['away_label'] or '')}</th>" for m in ms)
                    body = ""
                    for pid, name in players:
                        cells = ""
                        for m in ms:
                            p = allpred.get((pid, m["match_id"]))
                            pick = f"{p['pred_home']}–{p['pred_away']}" if p else "—"
                            cells += f"<td>{pick}</td>"
                        body += (f"<tr><td class='pl'>{html.escape(name)}</td>"
                                 f"{cells}</tr>")
                    st.markdown(
                        "<table class='cmp'><thead><tr><th>Player</th>"
                        f"{head}</tr></thead><tbody>{body}</tbody></table>",
                        unsafe_allow_html=True,
                    )
            elif not setting_on("glock_wildcards"):
                st.info(
                    ":material/lock: Everyone's wildcard picks unlock once the organiser locks "
                    "wildcard predictions. Yours are under **My predictions**."
                )
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
                html_table(rows)

# =========================================================================== #
# MATCHES & RESULTS  (per group, tile filter + standings)
# =========================================================================== #
elif page == "📅 Matches & results":
    st.header(":material/calendar_month: Matches & results")
    g = group_tile_picker("mr_grp")
    names = {
        r["team_id"]: r["name"] for r in conn.execute("SELECT team_id, name FROM teams")
    }
    st.subheader(f"Group {g} — standings")
    standings = group_standings(g)
    html_table(
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
        ]
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
    html_table(frows)

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
        if krows:
            html_table(krows)
        else:
            st.caption("No knockout results entered yet.")

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
    rows = cx_leaderboard()
    profiles = {
        r["participant_id"]: r for r in conn.execute("SELECT * FROM participants")
    }
    if not rows:
        st.info("No participants yet.")
    else:
        top = rows[:3]
        order = [1, 0, 2]  # render 2nd, 1st, 3rd for podium effect
        pod = ['<div class="podium-wrap">']
        crowns = {
            0: "👑",
            1: '<span class="nicon">military_tech</span>',
            2: '<span class="nicon">workspace_premium</span>',
        }
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
            pod.append(
                f'<div class="podium p{slot + 1}">{sparks}'
                f'<div class="pod-card"><div class="crown">{crowns[slot]}</div>'
                f'{jersey}<div class="pod-name">{r["name"]}</div>'
                f'<div class="pod-pts">{r["total_points"]:g} pts · {r["exact_score_hits"]} exact</div></div>'
                f'<div class="pedestal">{r["rank"]}</div></div>'
            )
        pod.append("</div>")
        st.markdown("".join(pod), unsafe_allow_html=True)

        if not ss().balloons_done:
            st.balloons()
            ss().balloons_done = True

        st.write("")
        st.subheader("Full standings")
        html_table(
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
            ]
        )

# =========================================================================== #
# ADMIN
# =========================================================================== #
elif page == "🔐 Admin":
    st.header(":material/admin_panel_settings: Admin")
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

    admin_view = tile_toggle(
        "admin_section", ["📝 Match scores", "⚙️ Settings & users"],
        labels=[":material/scoreboard: Match scores",
                ":material/settings: Settings & users"])
    st.divider()

    # ---- subpage: register match scores (filtered, loads on selection) ----
    if admin_view == "📝 Match scores":
        st.subheader(":material/scoreboard: Register match scores")
        st.caption("Pick a stage, then a group or knockout round to load its "
                   "matches.")
        kind = st.radio("Stage", ["Group stage", "Knockout"], horizontal=True,
                        key="adm_stage_kind")
        if kind == "Group stage":
            pick = st.selectbox("Group", ["— select —"] + dbmod.GROUP_CODES,
                                key="adm_group")
            chosen = ("group", pick) if pick != "— select —" else None
        else:
            ko_stages_adm = [
                r["stage"] for r in conn.execute(
                    "SELECT stage FROM matches WHERE is_knockout=1 "
                    "GROUP BY stage ORDER BY MIN(kickoff_utc), MIN(match_id)")]
            pick = st.selectbox("Knockout round", ["— select —"] + ko_stages_adm,
                                key="adm_kostage")
            chosen = ("ko", pick) if pick != "— select —" else None

        if chosen is None:
            st.info("Select a group or knockout round above to load its matches.")
        else:
            ckind, cval = chosen
            if ckind == "group":
                ms = conn.execute(
                    "SELECT * FROM matches WHERE group_code=? AND is_knockout=0 "
                    "ORDER BY matchday, match_id", (cval,)).fetchall()
            else:
                ms = conn.execute(
                    "SELECT * FROM matches WHERE stage=? AND is_knockout=1 "
                    "ORDER BY match_id", (cval,)).fetchall()
            st.caption("Tick **Played** for matches that have a result; untick and "
                       "Save to remove one entered by mistake. 0–0 is a real "
                       "result — keep it ticked.")
            with st.form(f"adm_results_{ckind}_{cval}"):
                h0, h1, h2, h3 = st.columns([0.8, 3.2, 1, 1])
                h0.caption("Played")
                h1.caption("Match")
                h2.caption("H")
                h3.caption("A")
                entries = []
                for m in ms:
                    cur = conn.execute(
                        "SELECT * FROM match_results WHERE match_id=?",
                        (m["match_id"],)).fetchone()
                    c0, c1, c2, c3 = st.columns([0.8, 3.2, 1, 1])
                    played = c0.checkbox(
                        "Played", value=cur is not None,
                        key=f"play_{m['match_id']}", label_visibility="collapsed")
                    c1.markdown(
                        f"`{m['match_id']}` {m['home_label']} vs {m['away_label']}")
                    hg = c2.number_input(
                        "H", 0, 30, value=cur["home_goals"] if cur else 0,
                        key=f"arh_{m['match_id']}", label_visibility="collapsed")
                    ag = c3.number_input(
                        "A", 0, 30, value=cur["away_goals"] if cur else 0,
                        key=f"ara_{m['match_id']}", label_visibility="collapsed")
                    entries.append((m["match_id"], played, hg, ag, cur is not None))
                if st.form_submit_button(":material/save: Save results", type="primary"):
                    saved = removed = 0
                    for mid, played, hg, ag, had in entries:
                        if played:
                            upsert(conn, "match_results", {
                                "match_id": mid, "home_goals": int(hg),
                                "away_goals": int(ag), "advance": None,
                            }, ["match_id"])
                            saved += 1
                        elif had:                         # unticked a saved result
                            conn.execute(
                                "DELETE FROM match_results WHERE match_id=?", (mid,))
                            removed += 1
                    cx_clear_scores()
                    msg = f"Saved {saved} result(s)"
                    if removed:
                        msg += f", removed {removed}"
                    st.success(msg + f" for {cval}.")
        st.stop()

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
                cx_clear_settings()
                st.rerun()

    lc1, lc2 = st.columns(2)
    ko_cur = dbmod.knockout_pred_locked(conn)
    ko_new = lc1.toggle(":material/lock: Lock knockout predictions", value=ko_cur, key="glock_ko")
    if ko_new != ko_cur:
        dbmod.set_knockout_pred_locked(conn, ko_new)
        cx_clear_settings()
        st.rerun()
    wc_cur = dbmod.wildcards_pred_locked(conn)
    wc_new = lc2.toggle(":material/lock: Lock wildcard predictions", value=wc_cur, key="glock_wc")
    if wc_new != wc_cur:
        dbmod.set_wildcards_pred_locked(conn, wc_new)
        cx_clear_settings()
        st.rerun()

    # ---- actual knockout (real fixtures everyone predicts) ----
    st.divider()
    st.subheader(":material/trophy: Actual knockout fixtures")
    n_set = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE is_knockout=1 AND home_team_id IS NOT NULL "
        "AND away_team_id IS NOT NULL").fetchone()[0]
    st.caption(f"Real fixtures everyone predicts (separate from the derived "
               f"bracket). {n_set} fixture(s) have real teams set so far.")
    ak1, ak2 = st.columns(2)
    if ak1.button(":material/auto_fix_high: Auto-fill from group results",
                  use_container_width=True):
        n = dbmod.autofill_actual_ko(conn)
        cx_clear_settings()
        cx_clear_brackets()
        st.success(f"Set real teams on {n} knockout fixture(s) from the entered "
                   "group results. (Re-run after each round's results are in.)")
        st.rerun()
    ako_cur = dbmod.actual_ko_locked(conn)
    ako_new = ak2.toggle(":material/lock: Lock actual-KO predictions",
                         value=ako_cur, key="glock_ako")
    if ako_new != ako_cur:
        dbmod.set_actual_ko_locked(conn, ako_new)
        cx_clear_settings()
        st.rerun()
    with st.expander("Set the Round of 32 fixtures"):
        st.caption("Set only the **Round of 32** here (the real draw). Each player's "
                   "R16 → Final then derive automatically from the winners THEY pick.")
        tnames = [""] + team_options()
        name2id = {r["name"]: r["team_id"]
                   for r in conn.execute("SELECT team_id, name FROM teams")}
        id2name = {v: k for k, v in name2id.items()}
        r32rows = list(conn.execute(
            "SELECT * FROM matches WHERE is_knockout=1 AND stage='Round of 32' "
            "ORDER BY kickoff_utc, match_id"))
        with st.form("ako_setfix"):
            edits = []
            for n, m in enumerate(r32rows, 1):
                ch = id2name.get(m["home_team_id"], "")
                ca = id2name.get(m["away_team_id"], "")
                date = (m["kickoff_utc"] or "")[:10]
                st.markdown(
                    f"<div class='ko-head'>R32 · match {n} "
                    f"<span class='ko-meta'>· {date}</span></div>"
                    f"{flags.chip(ch or None)}"
                    f"<span style='color:#5f7180;margin:0 8px'>vs</span>"
                    f"{flags.chip(ca or None)}",
                    unsafe_allow_html=True)
                c2, c3 = st.columns(2)
                h = c2.selectbox("Home", tnames,
                                 index=tnames.index(ch) if ch in tnames else 0,
                                 key=f"akoh_{m['match_id']}", label_visibility="collapsed")
                a = c3.selectbox("Away", tnames,
                                 index=tnames.index(ca) if ca in tnames else 0,
                                 key=f"akoa_{m['match_id']}", label_visibility="collapsed")
                edits.append((m["match_id"], h, a))
            if st.form_submit_button("Save Round of 32"):
                cnt = 0
                for mid, h, a in edits:
                    if h and a:
                        dbmod.set_actual_ko_teams(conn, mid, name2id[h], name2id[a])
                        cnt += 1
                cx_clear_settings()
                cx_clear_brackets()
                st.success(f"Saved {cnt} Round-of-32 fixture(s).")

    with st.expander("How later rounds are built (R16 → Final)"):
        st.caption("Each later match takes the **winner** (or, for the 3rd-place "
                   "match, the **loser**) of two earlier matches. Defaults follow the "
                   "official 2026 bracket — change a source below only if your bracket "
                   "needs it. Players still pick winners; these mappings decide who "
                   "meets whom, and every player's bracket updates to match.")
        SHORTK = {"Round of 32": "R32", "Round of 16": "R16", "Quarter-final": "QF",
                  "Semi-final": "SF", "Third place": "3rd", "Final": "Final"}
        PRIOR = {"Round of 16": "Round of 32", "Quarter-final": "Round of 16",
                 "Semi-final": "Quarter-final", "Third place": "Semi-final",
                 "Final": "Semi-final"}
        meta2 = {m["match_id"]: m for m in conn.execute(
            "SELECT match_id, stage, home_team_id, away_team_id "
            "FROM matches WHERE is_knockout=1")}
        eff = knockout.effective_feeders(conn)

        # label each ko_id ("R32 #3") and list the members of each round in order
        lbl, members = {}, {}
        for kid in knockout.ko_id_order():
            stage = meta2.get(kid, {}).get("stage")
            members.setdefault(stage, []).append(kid)
            lbl[kid] = f"{SHORTK.get(stage, stage)} #{len(members[stage])}"

        _names = {t["team_id"]: t["name"] for t in cx_teams()}

        def _src_label(kid):
            m = meta2.get(kid, {})
            ids = (m.get("home_team_id"), m.get("away_team_id"))
            tag = ""
            if all(ids):
                tag = (f" ({flags.code(_names.get(ids[0]))}"
                       f"/{flags.code(_names.get(ids[1]))})")
            return lbl.get(kid, kid) + tag

        later = [k for k in knockout.ko_id_order()
                 if meta2.get(k, {}).get("stage") in PRIOR]
        with st.form("ko_feeders"):
            edits = []
            for kid in later:
                stage = meta2[kid]["stage"]
                res = "L" if stage == "Third place" else "W"
                verb = "Loser" if res == "L" else "Winner"
                opts = members.get(PRIOR[stage], [])
                hdef, adef = eff[kid]["home"][1], eff[kid]["away"][1]
                st.markdown(f"<div class='ko-head'>{lbl[kid]}</div>",
                            unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                hs = c1.selectbox(
                    f"Home = {verb} of", opts,
                    index=opts.index(hdef) if hdef in opts else 0,
                    format_func=_src_label, key=f"fdh_{kid}")
                as_ = c2.selectbox(
                    f"Away = {verb} of", opts,
                    index=opts.index(adef) if adef in opts else 0,
                    format_func=_src_label, key=f"fda_{kid}")
                edits.append((kid, res, hs, as_))
            b1, b2 = st.columns(2)
            save_fd = b1.form_submit_button("Save matchups", type="primary",
                                            use_container_width=True)
            reset_fd = b2.form_submit_button("Reset to official bracket",
                                             use_container_width=True)
        if save_fd:
            for kid, res, hs, as_ in edits:
                dbmod.set_ko_feeder_override(conn, kid, res, hs, res, as_)
            conn.commit()
            cx_clear_settings()
            cx_clear_scores()
            cx_clear_brackets()
            st.success("Saved. Every player's R16 → Final now follows these matchups.")
            st.rerun()
        if reset_fd:
            dbmod.clear_ko_feeder_overrides(conn)
            conn.commit()
            cx_clear_settings()
            cx_clear_scores()
            cx_clear_brackets()
            st.success("Reset to the official 2026 bracket.")
            st.rerun()

    # ---- submission stats ----
    st.divider()
    st.subheader(":material/insights: Submission stats")
    st.caption("Who has locked in what. 'Submitted' = pressed the final submit "
               "(everything frozen & scoring).")
    splayers = list(conn.execute("SELECT participant_id, name FROM participants ORDER BY name"))
    sn = len(splayers)
    if not sn:
        st.caption("No players yet.")
    else:
        group_total = len(dbmod.GROUP_CODES)
        wc_total = conn.execute("SELECT COUNT(*) FROM wildcards").fetchone()[0]
        scopes_by: dict[int, set] = {}
        for r in conn.execute("SELECT participant_id AS pid, scope FROM pred_locks"):
            scopes_by.setdefault(r["pid"], set()).add(r["scope"])
        wc_by = {r["pid"]: r["c"] for r in conn.execute(
            "SELECT participant_id AS pid, COUNT(*) AS c FROM wildcard_predictions "
            "GROUP BY participant_id")}

        def _scopes(pid):
            return scopes_by.get(pid, set())

        def _groups(pid):
            return sum(1 for g in dbmod.GROUP_CODES if f"group:{g}" in _scopes(pid))

        def _ko(pid):
            return any(s.startswith("ko:") for s in _scopes(pid))

        def _final(pid):
            return "final" in _scopes(pid)

        ids = [p["participant_id"] for p in splayers]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Players", sn)
        c2.metric("Submitted", f"{sum(_final(i) for i in ids)}/{sn}")
        c3.metric("All groups locked", f"{sum(_groups(i) == group_total for i in ids)}/{sn}")
        c4.metric("Knockout locked", f"{sum(_ko(i) for i in ids)}/{sn}")
        c5.metric("Wildcards complete",
                  f"{sum(wc_by.get(i, 0) >= wc_total for i in ids)}/{sn}")
        st.dataframe(
            [{"Player": p["name"],
              "Groups": f"{_groups(p['participant_id'])}/{group_total}",
              "Knockout": "✓" if _ko(p["participant_id"]) else "—",
              "Wildcards": f"{wc_by.get(p['participant_id'], 0)}/{wc_total}",
              "Submitted": "✓" if _final(p["participant_id"]) else "—"}
             for p in splayers],
            hide_index=True, use_container_width=True)

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
                cx_clear_scores()
                st.success("Wildcard results saved.")

    st.divider()
    st.subheader(":material/group: Manage users")
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
                if st.form_submit_button(":material/save: Save changes", type="primary"):
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

        st.markdown("**Prediction submission** (submitted = locked & scores points)")
        u_scopes = dbmod.locked_scopes(conn, upid)
        sub_groups = sorted(g for g in dbmod.GROUP_CODES if f"group:{g}" in u_scopes)
        ko_count = sum(1 for s in u_scopes if s.startswith("ko:"))
        is_final = "final" in u_scopes
        st.caption(
            f"Submitted groups: {', '.join(sub_groups) or 'none'} "
            f"({len(sub_groups)}/12) · knockout: {'yes' if ko_count else 'no'} · "
            f"final submit: {'yes' if is_final else 'no'}"
        )
        reopen = st.multiselect(
            "Reopen specific groups (lets the player edit & re-submit them)",
            sub_groups, key="mu_reopen_g")
        ru1, ru2 = st.columns(2)
        if ru1.button(":material/lock_open: Reopen selected groups", disabled=not reopen,
                      use_container_width=True, key="mu_reopen_btn"):
            for g in reopen:
                dbmod.unlock_scope(conn, upid, f"group:{g}")
            dbmod.unlock_scope(conn, upid, "final")   # can't stay 'final' if a group reopens
            cx_clear_scores()
            st.success(f"Reopened groups {', '.join(reopen)} for {who}.")
            st.rerun()
        if ru2.button(":material/lock_open: Reopen ALL predictions", use_container_width=True,
                      key="mu_unlock_all"):
            conn.execute("DELETE FROM pred_locks WHERE participant_id=?", (upid,))
            cx_clear_scores()
            st.success(f"All predictions reopened for {who} (groups + knockout + "
                       "final). They'll need to re-submit to score.")
            st.rerun()

        st.markdown("**Reset actions**")
        rc1, rc2 = st.columns(2)
        with rc1:
            if st.button(":material/restart_alt: Reset profile to defaults",
                         use_container_width=True):
                dbmod.reset_profile(conn, upid)
                st.success(f"Profile reset for {who} (predictions kept).")
                st.rerun()
        with rc2:
            with st.popover(":material/key: Reset PIN", use_container_width=True):
                newpin = st.text_input("New PIN", type="password", key="mu_pin")
                if st.button("Set new PIN") and newpin:
                    dbmod.set_pin(conn, upid, newpin)
                    st.success(f"PIN reset for {who}.")

    st.divider()
    if st.button(":material/refresh: Refresh dashboards (HTML + Power BI tables + CSV)"):
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
            ":material/download: Download backup ZIP",
            data=st.session_state["_backup_zip"],
            file_name="wc2026_backup.zip",
            mime="application/zip",
        )
