# Going online with Supabase (free) + Power BI

This app runs on local **SQLite** by default. Set a `DATABASE_URL` and the exact
same code runs on **Supabase Postgres** instead — so everyone can submit picks
online and Power BI can read live standings. CSV export stays as your backup.

## What you set up outside the app (one-time)

Everything here is **free**; none of it needs a paid plan for a small contest.

- [ ] **Supabase account + project** — free tier, no card required. This is your
      database. (One project is plenty.) → step 1–2 below.
- [ ] **GitHub account + repo** — push this project so it can be deployed. Free.
- [ ] **Streamlit Community Cloud account** — free, sign in with GitHub; this is
      what actually hosts the web app people visit. → step 4 below.
- [ ] **Power BI Desktop** (optional) — free download, Windows only; used to
      build the dashboard. Sharing dashboards via the Power BI *Service* needs a
      Pro/Fabric licence, but building locally and the database itself are free.
- [ ] **Two secrets to set** in Streamlit Cloud: `DATABASE_URL` (from Supabase)
      and `ADMIN_PASSWORD`. → step 4 below.

No domain, server, or payment is needed. Rough time: ~20–30 minutes.

## 1. Create the Supabase project (free)

1. Sign up at supabase.com → **New project**.
2. Pick a **region close to you** (for Norway, an EU region like `eu-central` /
   Frankfurt) and set a strong **database password** (save it).
3. Wait for it to provision.

## 2. Get the connection string (use the Session Pooler — IPv4)

In the project: **Connect** (top bar) → **Session pooler**. It looks like:

```
postgresql://postgres.<project-ref>:<DB-PASSWORD>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

Use the **Session pooler** (host `...pooler.supabase.com`, port **5432**). It's
IPv4-friendly, which both Streamlit Community Cloud and Power BI need. (The
"Direct connection" is IPv6-only and often won't work from Power BI.)

## 3. Create the tables in Supabase

From your machine, point the app at Supabase once to build + seed the schema:

```powershell
# Windows PowerShell
$env:DATABASE_URL = "postgresql://postgres.<ref>:<pwd>@aws-0-<region>.pooler.supabase.com:5432/postgres"
uv run python main.py seed
```

```bash
# macOS/Linux
export DATABASE_URL="postgresql://postgres.<ref>:<pwd>@aws-0-<region>.pooler.supabase.com:5432/postgres"
uv run python main.py seed
```

`seed` is destructive (it drops + recreates tables), so only run it for initial
setup or a full reset — never mid-contest.

## 4. Deploy the app on Streamlit Community Cloud (free)

1. Push this repo to GitHub.
2. Go to share.streamlit.io → **New app** → choose the repo/branch and set the
   main file to `app/streamlit_app.py`.
3. In **Advanced settings → Secrets**, paste:

   ```toml
   DATABASE_URL = "postgresql://postgres.<ref>:<pwd>@aws-0-<region>.pooler.supabase.com:5432/postgres"
   ADMIN_PASSWORD = "choose-something-strong"
   SIGNUP_KEY = "invite-code-for-colleagues"   # optional; gate who can sign up
   ```

4. Deploy. The app detects `DATABASE_URL` and uses Supabase automatically; share
   the URL with colleagues. Accounts, picks, the lock and results all live in
   Supabase now, so nothing is lost when the app restarts.

> Streamlit Cloud's disk is temporary, but that's fine — your data is in
> Supabase. The HTML dashboard's `data.json` and the CSVs written on the cloud
> are also temporary; for a durable **CSV backup**, run `uv run python -m
> wc_contest.export` locally with `DATABASE_URL` set (writes `exports/*.csv`),
> or use Supabase's Table Editor → Export to CSV.

## 5. Connect Power BI to Supabase

Power BI talks to Supabase directly — no CSVs required.

1. Power BI Desktop → **Get data → PostgreSQL database**.
2. **Server:** `aws-0-<region>.pooler.supabase.com:5432`  ·  **Database:** `postgres`
3. Data connectivity mode: **Import**.
4. Credentials (the **Database** tab): 
   - User name: `postgres.<project-ref>`  (the pooler username, *not* your Supabase login)
   - Password: your database password
5. If prompted about encryption, keep **SSL on** (Supabase requires it).
6. In the Navigator, load these tables (the app writes them already-scored every
   time you click **Refresh dashboards** in the Admin page):

   | Table | What it gives you |
   |---|---|
   | `vw_leaderboard` | ranked players with total + per-category points |
   | `vw_match_points` | per-player, per-match points (drill-down) |
   | `vw_timeline` | cumulative points per player per date (race chart) |
   | `participants`, `teams`, `matches`, `match_results` | raw data for extra views |

Because `vw_leaderboard` is already scored, your old DAX measures still work —
just point them at these tables. After each match-day: enter results in the app's
Admin page, click **Refresh dashboards**, then hit **Refresh** in Power BI.

## Switching back to local

Unset `DATABASE_URL` (close the terminal or `Remove-Item Env:DATABASE_URL`) and
the app/tools use local SQLite again. The two never interfere.
