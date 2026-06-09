# Deploy to Streamlit Community Cloud (free)

A step-by-step to get the contest online for everyone. Assumes you've already
created the Supabase database and have its **Session pooler** connection string
(see [SUPABASE_SETUP.md](SUPABASE_SETUP.md)). Total time ~15 minutes.

## Prerequisites

- A **GitHub** account.
- A **Streamlit Community Cloud** account (free) — sign in at
  share.streamlit.io with your GitHub login.
- Your Supabase `DATABASE_URL` (session pooler, port 5432) and a chosen
  `ADMIN_PASSWORD`.
- These files already in the repo: `requirements.txt`, `app/streamlit_app.py`.

## Step 1 — Put the project on GitHub

If it isn't on GitHub yet, from the project folder:

```bash
git init                # skip if already a git repo
git add .
git commit -m "World Cup 2026 prediction contest"
gh repo create wc-prediction-contest --private --source=. --push
# (or create the repo on github.com and: git remote add origin <url> && git push -u origin main)
```

Private repo is fine — Streamlit Community Cloud can deploy from private repos
when you authorise GitHub access. (Note: the *running app* is still reachable by
anyone who has its URL; the PIN login and admin password protect editing/admin.)

## Step 2 — Create the app on Streamlit Community Cloud

1. Go to **share.streamlit.io** and sign in with GitHub (authorise it to see
   your repos the first time).
2. Click **Create app → Deploy a public app from GitHub** (works for private
   repos too once authorised).
3. Fill in:
   - **Repository:** `your-username/wc-prediction-contest`
   - **Branch:** `main`
   - **Main file path:** `app/streamlit_app.py`
4. (Optional) **Advanced settings → Python version:** pick **3.12** or **3.13**.

## Step 3 — Add your secrets

Still in **Advanced settings → Secrets**, paste (TOML format):

```toml
DATABASE_URL = "postgresql://postgres.<project-ref>:<DB-PASSWORD>@aws-0-<region>.pooler.supabase.com:5432/postgres"
ADMIN_PASSWORD = "choose-something-strong"
SIGNUP_KEY = "the-invite-code-you-share-with-colleagues"   # optional
```

`SIGNUP_KEY` is the invite code people must enter to create an account, so only
those you share it with can join. Omit it to allow open sign-up. The app
automatically uses Supabase when `DATABASE_URL` is present, and falls
back to local SQLite when it isn't. You can edit secrets later under the app's
**⋮ → Settings → Secrets** (the app reboots on save).

## Step 4 — Deploy

Click **Deploy**. First build takes a few minutes while it installs
`requirements.txt`. When it's live you'll get a URL like
`https://wc-prediction-contest.streamlit.app`.

## Step 5 — Initialise the database (once)

The tables need to exist in Supabase. Either:

- **From your machine** (recommended), pointing at Supabase:
  ```powershell
  $env:DATABASE_URL = "postgresql://postgres.<ref>:<pwd>@aws-0-<region>.pooler.supabase.com:5432/postgres"
  uv run python main.py seed
  ```
- Or seed locally first, then it's already there — just make sure you ran
  `seed` against the **Supabase** URL at least once. (`seed` is destructive;
  run it only for setup/reset, never mid-contest.)

## Step 6 — Go live

1. Open the app URL, go to **🔐 Admin**, log in with `ADMIN_PASSWORD`.
2. Confirm predictions are **OPEN** (lock toggle off).
3. Share the URL with colleagues. They create an account (name + PIN), design a
   jersey, and submit picks.
4. At the deadline, flip **🔒 Predictions locked** on in Admin.
5. As matches finish: enter results in Admin → **Refresh dashboards** (updates
   the HTML dashboard and the Power BI tables). Grab a **backup ZIP** from Admin
   any time.

## Everyday operations & gotchas

- **Updates:** push to GitHub and the app auto-redeploys (max ~5 updates/min).
- **Sleeping:** if unused for a while the app sleeps; the next visitor waits a
  few seconds while it wakes. Data is safe in Supabase regardless.
- **Resources:** the free tier gives ~1 GB RAM — plenty for <30 players.
- **Supabase pausing:** the free Supabase project pauses after ~7 days of
  inactivity; just open the Supabase dashboard to wake it. During an active
  tournament it won't pause.
- **Reset for a new tournament:** edit the seed CSVs / `seed_data.py`, then run
  `main.py seed` against the Supabase URL (wipes and rebuilds).

## Troubleshooting

**`ModuleNotFoundError: No module named 'sqlalchemy'` (or psycopg2) on deploy.**
The repo has both a `uv.lock` and a `requirements.txt`; Streamlit Cloud prefers
`uv.lock`. If you changed dependencies in `pyproject.toml` but didn't refresh the
lockfile, the deploy installs stale packages. Fix:

```bash
uv lock                       # regenerate uv.lock from pyproject.toml
git add uv.lock
git commit -m "Update lockfile"
git push
```

Then **Reboot app** on Streamlit Cloud. Rule of thumb: any time you edit
dependencies, run `uv lock` and commit `uv.lock` in the same push. Keep
`uv.lock` in the repo (don't delete it) — `pyproject.toml` alone can be
misdetected as a Poetry project and fail differently.

## When you outgrow it → Azure

To make it private (only Crayon staff) or more robust later, containerise the
app (a `Dockerfile`) and host on **Azure App Service / Container Apps** behind
**Entra ID** SSO, keeping the same Supabase database. Ask and I'll add the
Dockerfile + Azure steps.
