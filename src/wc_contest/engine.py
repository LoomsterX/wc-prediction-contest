"""Database engine layer.

A thin SQLAlchemy-backed abstraction so the *same* code runs on:
  * local SQLite        (default, zero setup)
  * Supabase / Postgres (set DATABASE_URL — used online + for Power BI)

The wrapper keeps the simple interface the rest of the code already uses
(`conn.execute("... ?", (params,))`, iterate rows, `row["col"]` or `row[0]`,
`conn.commit()`), so scoring.py / export.py / the app barely change.

Connection strategy: every execute runs on its own pooled connection and
commits immediately. That is thread-safe (Streamlit reruns hop threads) and
resilient to idle drops on hosted Postgres — ideal for a small online app.
"""

from __future__ import annotations

import os
from pathlib import Path

import sqlalchemy as sa

from . import config

# --------------------------------------------------------------------------- #
# Schema (defined once; SQLAlchemy emits correct DDL for each dialect)
# --------------------------------------------------------------------------- #
metadata = sa.MetaData()

participants = sa.Table(
    "participants", metadata,
    sa.Column("participant_id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("name", sa.Text, nullable=False, unique=True),
    sa.Column("email", sa.Text),
    sa.Column("joined_at", sa.Text, nullable=False),
    sa.Column("pin_hash", sa.Text),
    sa.Column("favorite_team", sa.Text),
    sa.Column("favorite_player", sa.Text),
    sa.Column("shirt_primary", sa.Text, server_default="#1801B4"),
    sa.Column("shirt_secondary", sa.Text, server_default="#ffffff"),
    sa.Column("shirt_pattern", sa.Text, server_default="solid"),
)

settings = sa.Table(
    "settings", metadata,
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("value", sa.Text),
)

teams = sa.Table(
    "teams", metadata,
    sa.Column("team_id", sa.Integer, primary_key=True, autoincrement=False),
    sa.Column("name", sa.Text, nullable=False, unique=True),
    sa.Column("group_code", sa.Text),
    sa.Column("confederation", sa.Text),
    sa.Column("is_host", sa.Integer, nullable=False, server_default="0"),
)

matches = sa.Table(
    "matches", metadata,
    sa.Column("match_id", sa.Text, primary_key=True),
    sa.Column("stage", sa.Text, nullable=False),
    sa.Column("group_code", sa.Text),
    sa.Column("matchday", sa.Integer),
    sa.Column("kickoff_utc", sa.Text),
    sa.Column("home_team_id", sa.Integer),
    sa.Column("away_team_id", sa.Integer),
    sa.Column("home_label", sa.Text),
    sa.Column("away_label", sa.Text),
    sa.Column("is_knockout", sa.Integer, nullable=False, server_default="0"),
)

wildcards = sa.Table(
    "wildcards", metadata,
    sa.Column("wildcard_id", sa.Text, primary_key=True),
    sa.Column("question", sa.Text, nullable=False),
    sa.Column("type", sa.Text, nullable=False),
    sa.Column("options", sa.Text),
    sa.Column("points", sa.Float, nullable=False),
    sa.Column("hint", sa.Text),
)

match_predictions = sa.Table(
    "match_predictions", metadata,
    sa.Column("participant_id", sa.Integer, primary_key=True),
    sa.Column("match_id", sa.Text, primary_key=True),
    sa.Column("pred_home", sa.Integer, nullable=False),
    sa.Column("pred_away", sa.Integer, nullable=False),
    sa.Column("pred_advance", sa.Integer),
    sa.Column("submitted_at", sa.Text, nullable=False),
)

outcome_predictions = sa.Table(
    "outcome_predictions", metadata,
    sa.Column("participant_id", sa.Integer, primary_key=True),
    sa.Column("category", sa.Text, primary_key=True),
    sa.Column("ref", sa.Text, primary_key=True),
    sa.Column("value", sa.Text, nullable=False),
    sa.Column("submitted_at", sa.Text, nullable=False),
)

wildcard_predictions = sa.Table(
    "wildcard_predictions", metadata,
    sa.Column("participant_id", sa.Integer, primary_key=True),
    sa.Column("wildcard_id", sa.Text, primary_key=True),
    sa.Column("value", sa.Text, nullable=False),
    sa.Column("submitted_at", sa.Text, nullable=False),
)

match_results = sa.Table(
    "match_results", metadata,
    sa.Column("match_id", sa.Text, primary_key=True),
    sa.Column("home_goals", sa.Integer, nullable=False),
    sa.Column("away_goals", sa.Integer, nullable=False),
    sa.Column("advance", sa.Integer),
)

outcome_results = sa.Table(
    "outcome_results", metadata,
    sa.Column("category", sa.Text, primary_key=True),
    sa.Column("ref", sa.Text, primary_key=True),
    sa.Column("value", sa.Text, nullable=False),
)

wildcard_results = sa.Table(
    "wildcard_results", metadata,
    sa.Column("wildcard_id", sa.Text, primary_key=True),
    sa.Column("value", sa.Text, nullable=False),
)

# Per-participant prediction locks. `scope` is one of:
#   "group:A" ... "group:L"  -> a group's picks have been locked in (green tile)
#   "ko:<stage>"             -> a knockout round's picks have been locked in
#   "final"                  -> the player has submitted; everything is frozen
# An admin removes the "final" row to let a player edit again.
pred_locks = sa.Table(
    "pred_locks", metadata,
    sa.Column("participant_id", sa.Integer, primary_key=True),
    sa.Column("scope", sa.Text, primary_key=True),
    sa.Column("locked_at", sa.Text, nullable=False),
)

# --- ACTUAL knockout: everyone predicts the SAME real fixtures (the real R32+
# bracket), separate from the per-player derived bracket. Real teams live on the
# knockout rows of `matches` (home_team_id/away_team_id); real results reuse
# match_results. This table just holds each player's scoreline pick. --- #
actual_ko_predictions = sa.Table(
    "actual_ko_predictions", metadata,
    sa.Column("participant_id", sa.Integer, primary_key=True),
    sa.Column("match_id", sa.Text, primary_key=True),     # KO_* id in matches
    sa.Column("pred_home", sa.Integer, nullable=False),
    sa.Column("pred_away", sa.Integer, nullable=False),
    sa.Column("pred_advance", sa.Integer),                # team_id for draws
    sa.Column("submitted_at", sa.Text, nullable=False),
)


# --------------------------------------------------------------------------- #
# Row / Result wrappers (preserve row["col"] AND row[0] access)
# --------------------------------------------------------------------------- #
class Row(dict):
    def __getitem__(self, k):
        if isinstance(k, int):
            return list(self.values())[k]
        return dict.__getitem__(self, k)


class Result:
    def __init__(self, rows):
        self._rows = rows or []

    def __iter__(self):
        return iter(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def _to_named(sql: str) -> str:
    """Translate '?' positional placeholders to ':p0, :p1, ...' for text()."""
    out, i = [], 0
    for ch in sql:
        if ch == "?":
            out.append(f":p{i}")
            i += 1
        else:
            out.append(ch)
    return "".join(out)


# --------------------------------------------------------------------------- #
# Engine + connection wrapper
# --------------------------------------------------------------------------- #
_ENGINES: dict[str, sa.Engine] = {}


def _resolve_url(db_path: Path | str | None) -> str:
    if db_path is not None:                       # explicit sqlite file (tests/CLI)
        return f"sqlite:///{Path(db_path).as_posix()}"
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{config.DB_PATH.as_posix()}"
    # normalise common Postgres prefixes to the psycopg2 driver
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def get_engine(db_path: Path | str | None = None) -> sa.Engine:
    url = _resolve_url(db_path)
    if url not in _ENGINES:
        if url.startswith("sqlite"):
            config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            _ENGINES[url] = sa.create_engine(
                url, connect_args={"check_same_thread": False},
                poolclass=sa.pool.QueuePool, pool_size=5, max_overflow=10)
        else:
            _ENGINES[url] = sa.create_engine(
                url, pool_pre_ping=True, pool_recycle=300, pool_size=5,
                max_overflow=5)
    return _ENGINES[url]


class Database:
    """Minimal DBAPI-like wrapper backed by a pooled SQLAlchemy engine."""

    def __init__(self, engine: sa.Engine):
        self.engine = engine
        self.dialect = engine.dialect.name      # 'sqlite' | 'postgresql'

    def execute(self, sql: str, params=None) -> Result:
        named = _to_named(sql)
        pdict = {f"p{i}": v for i, v in enumerate(params)} if params else {}
        with self.engine.connect() as c:
            res = c.execute(sa.text(named), pdict)
            rows = [Row(m) for m in res.mappings().all()] if res.returns_rows else None
            c.commit()
        return Result(rows)

    def commit(self):     # statements auto-commit; kept for interface parity
        pass

    def close(self):
        pass


def upsert(conn: Database, table: str, values: dict, conflict: list[str]) -> None:
    """Insert-or-update keyed on the given conflict columns (works on both)."""
    cols = list(values)
    placeholders = ",".join("?" * len(cols))
    collist = ",".join(cols)
    if conn.dialect == "postgresql":
        sets = [f"{c}=EXCLUDED.{c}" for c in cols if c not in conflict]
        tail = (f"ON CONFLICT ({','.join(conflict)}) DO UPDATE SET {','.join(sets)}"
                if sets else f"ON CONFLICT ({','.join(conflict)}) DO NOTHING")
        sql = f"INSERT INTO {table} ({collist}) VALUES ({placeholders}) {tail}"
    else:
        sql = f"INSERT OR REPLACE INTO {table} ({collist}) VALUES ({placeholders})"
    conn.execute(sql, tuple(values.values()))
