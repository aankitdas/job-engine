"""Connection setup and schema application for the job-engine database."""

import sqlite3
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

DEFAULT_DB_PATH = Path("data/jobengine.db")

_SCHEMA_VERSION = "0001_initial"


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init(conn: sqlite3.Connection) -> None:
    """Create the schema if absent. Safe to call repeatedly."""
    schema_sql = resources.files("jobengine.db").joinpath("schema.sql").read_text()
    conn.executescript(schema_sql)
    conn.commit()


def migrate(conn: sqlite3.Connection) -> None:
    """Apply the current schema and record it as an applied migration."""
    init(conn)
    applied = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?", (_SCHEMA_VERSION,)
    ).fetchone()
    if applied is None:
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (_SCHEMA_VERSION, datetime.now(UTC).isoformat()),
        )
        conn.commit()


def stats(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' AND name != 'schema_migrations'"
        ).fetchall()
    ]
    return {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in tables
    }
