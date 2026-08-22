"""Connection setup and schema application for the job-engine database."""

import sqlite3
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

DEFAULT_DB_PATH = Path("data/jobengine.db")

_SCHEMA_VERSION = "0003_variant_claims"


def connect(
    db_path: Path = DEFAULT_DB_PATH, *, check_same_thread: bool = True
) -> sqlite3.Connection:
    """check_same_thread defaults to sqlite3's own default (True):
    every caller in this codebase is single-threaded except
    jobengine.web.app, which sets it False deliberately. FastAPI runs
    sync route handlers and sync Depends() callables in a threadpool
    (even when the route itself is declared async), so a connection
    built once at app startup gets used from a different thread on
    every request; there is no per-request connection lifecycle here to
    avoid that instead. Safe for this app's actual usage (one operator,
    one browser, requests that are not genuinely concurrent), not a
    general concurrency guarantee -- do not default this on for
    everything else in the codebase, where the check catches real bugs.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init(conn: sqlite3.Connection) -> None:
    """Create the schema if absent. Safe to call repeatedly."""
    schema_sql = resources.files("jobengine.db").joinpath("schema.sql").read_text()
    conn.executescript(schema_sql)
    conn.commit()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _rebuild_job_resume_variants_if_needed(conn: sqlite3.Connection) -> None:
    """F1 (docs/decisions.md): job_resume_variants' old table-level
    UNIQUE(base_resume_id, selection_hash) constraint blocked two
    different jobs from ever sharing a selection_hash, contradicting
    spec 08's own file-reuse dedup intent. schema.sql now omits that
    constraint and relies on idx_job_resume_variants_job_profile
    instead, but init()'s CREATE TABLE IF NOT EXISTS is a no-op against
    a table that already exists in the old shape -- a db that predates
    this migration needs an actual rebuild, not just a re-run of
    schema.sql. Zero real rows exist in data/jobengine.db's copy of this
    table as of this migration, so the copy step below is trivial, but
    it's still written to preserve rows generically, not assumed empty.

    A no-op if the table doesn't exist yet (fresh db: schema.sql alone
    creates it correctly) or if it's already been rebuilt (has
    review_status, matching the new shape)."""
    if not _table_exists(conn, "job_resume_variants"):
        return
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(job_resume_variants)")
    }
    if "review_status" in columns:
        return

    conn.execute(
        """
        CREATE TABLE job_resume_variants_new (
            id                  INTEGER PRIMARY KEY,
            job_id              INTEGER NOT NULL REFERENCES jobs (id),
            profile             TEXT NOT NULL,
            base_resume_id      INTEGER NOT NULL REFERENCES base_resumes (id),
            patch_tiers_applied TEXT,
            bullet_ids          TEXT,
            selection_hash      TEXT NOT NULL,
            docx_path           TEXT,
            pdf_path            TEXT,
            score               REAL,
            coverage            REAL,
            front_load          REAL,
            passed              INTEGER,
            accepted            INTEGER,
            review_status       TEXT NOT NULL DEFAULT 'pending',
            reviewed_at         TEXT,
            created_at          TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO job_resume_variants_new (
            id, job_id, profile, base_resume_id, patch_tiers_applied, bullet_ids,
            selection_hash, docx_path, pdf_path, score, coverage, front_load,
            passed, accepted, created_at
        )
        SELECT
            id, job_id, profile, base_resume_id, patch_tiers_applied, bullet_ids,
            selection_hash, docx_path, pdf_path, score, coverage, front_load,
            passed, accepted, created_at
        FROM job_resume_variants
        """
    )
    conn.execute("DROP TABLE job_resume_variants")
    conn.execute("ALTER TABLE job_resume_variants_new RENAME TO job_resume_variants")
    conn.commit()


def migrate(conn: sqlite3.Connection) -> None:
    """Apply the current schema and record it as an applied migration."""
    _rebuild_job_resume_variants_if_needed(conn)
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
