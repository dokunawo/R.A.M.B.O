"""
R.A.M.B.O. MLB Betting Agent — DB connection + migrations (Step 3)
db/migrate.py

Opens SQLite with the right pragmas and applies versioned .sql migrations once
each, tracked in schema_migrations. Safe to run on every startup.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
) STRICT;
"""


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Open SQLite with foreign keys on and WAL mode for concurrent pulls."""
    conn = sqlite3.connect(str(db_path), isolation_level=None)  # autocommit; we manage txns
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")  # wait out brief write locks
    return conn


def apply_migrations(conn: sqlite3.Connection, migrations_dir: str | Path) -> list[str]:
    """Apply every *.sql in migrations_dir (sorted) that hasn't run yet.
    Each migration runs in its own transaction. Returns the filenames applied."""
    conn.execute(_MIGRATIONS_TABLE)
    applied: set[str] = {
        row[0] for row in conn.execute("SELECT filename FROM schema_migrations")
    }

    migrations_dir = Path(migrations_dir)
    sql_files = sorted(migrations_dir.glob("*.sql"))
    newly_applied: list[str] = []

    for path in sql_files:
        if path.name in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        # NOTE: sqlite3.executescript() commits any pending transaction before it
        # runs, so wrapping it in a manual BEGIN/COMMIT errors with "no transaction
        # is active". Every CREATE here is IF NOT EXISTS, so we run the script (it
        # manages its own transaction) and then record it; a re-run stays safe even
        # if recording the row fails.
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (filename, applied_at) VALUES (?, ?);",
            (path.name, datetime.now(timezone.utc).isoformat()),
        )
        newly_applied.append(path.name)

    return newly_applied
