"""
Thin SQLite wrapper: connection handling + generic parameterized insert/query
helpers.

Your SQL is already strong, so there's no learning ceiling in hand-rolling
this -- it's mechanical plumbing. Fully implemented so every other module
(ingestion, features, checkpointing) has a single, boring way to talk to the
database. The *logic* of what to insert, when, and how to interpret it back
out for feature engineering is where the actual learning work is -- that
lives in leagueml/features/ and leagueml/ingestion/, not here.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from leagueml.config import DB_PATH, SCHEMA_PATH


@contextmanager
def get_connection(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    """Yield a sqlite3 connection, committing on success and closing always.

    Usage:
        with get_connection() as conn:
            conn.execute(...)
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = DB_PATH, schema_path: Path = SCHEMA_PATH) -> None:
    """Create all tables from db/schema.sql if they don't already exist."""
    sql = schema_path.read_text(encoding="utf-8")
    with get_connection(db_path) as conn:
        conn.executescript(sql)


def insert_row(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    """Generic single-row INSERT OR REPLACE, built from a dict's keys/values.

    Table and column names are only ever passed by our own code (never by
    user/API input), so building the statement with an f-string here is safe
    -- the *values* still go through '?' placeholders to avoid SQL injection
    and to let sqlite3 handle type conversion.
    """
    columns = ", ".join(row.keys())
    placeholders = ", ".join("?" for _ in row)
    sql = f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({placeholders})"
    conn.execute(sql, tuple(row.values()))


def insert_rows(conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> None:
    """Batch version of insert_row -- same column set assumed for every row."""
    if not rows:
        return
    columns = ", ".join(rows[0].keys())
    placeholders = ", ".join("?" for _ in rows[0])
    sql = f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({placeholders})"
    conn.executemany(sql, [tuple(r.values()) for r in rows])


def fetch_all(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[tuple]:
    """Run a SELECT and return all rows. For anything more than a quick
    lookup, prefer pandas.read_sql_query(sql, conn) directly in features/."""
    cur = conn.execute(sql, params)
    return cur.fetchall()


def get_existing_match_ids(conn: sqlite3.Connection) -> set[str]:
    """Match IDs already present in the matches table -- used by ingestion to
    skip matches it has already pulled and stored."""
    rows = fetch_all(conn, "SELECT match_id FROM matches")
    return {r[0] for r in rows}
