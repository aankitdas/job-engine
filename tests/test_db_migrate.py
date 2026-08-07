"""migrate.py: schema application and the F1 job_resume_variants rebuild.

Most of this project's dbs (tests, and data/jobengine.db until this
migration is actually applied to it) were created before review_status/
reviewed_at existed and while the old table-level
UNIQUE(base_resume_id, selection_hash) constraint was still in place.
init()'s CREATE TABLE IF NOT EXISTS is a no-op against an existing
table, so removing that old constraint for an already-created db needs
a real rebuild, not just an edited schema.sql. These tests simulate
that "old" state directly with raw SQL (the exact 0001_initial shape)
rather than relying on git history, so they keep working even after
schema.sql itself has moved on.
"""

import sqlite3

import pytest

from jobengine.db.migrate import _SCHEMA_VERSION, connect, init, migrate

_OLD_JOB_RESUME_VARIANTS_SQL = """
CREATE TABLE job_resume_variants (
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
    created_at          TEXT NOT NULL,
    UNIQUE (base_resume_id, selection_hash)
)
"""


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "jobengine.db"
    connection = connect(db_path)
    yield connection
    connection.close()


@pytest.fixture
def old_shape_conn(conn):
    """A db built exactly like a real one that has only ever run
    0001_initial: full schema via init(), a real '0001_initial' row in
    schema_migrations (matching what data/jobengine.db actually has
    today, confirmed live), then job_resume_variants dropped and
    recreated in its old (pre-review_status, old-UNIQUE-constraint)
    shape."""
    init(conn)
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at) VALUES "
        "('0001_initial', '2026-08-04T00:02:11.767678+00:00')"
    )
    conn.execute("DROP TABLE job_resume_variants")
    conn.execute(_OLD_JOB_RESUME_VARIANTS_SQL)
    conn.commit()
    return conn


def _seed_company(conn):
    conn.execute(
        "INSERT INTO companies (slug, ats, name, status, source, first_seen_at) "
        "VALUES ('acme', 'greenhouse', 'Acme', 'active', 'seed', "
        "'2026-08-07T00:00:00+00:00')"
    )


def _seed_job_and_base_resume(conn, ats_job_id="1"):
    job_id = conn.execute(
        "INSERT INTO jobs (ats, company_slug, ats_job_id, title, "
        "first_seen_at, last_seen_at) VALUES ('greenhouse', 'acme', ?, "
        "'Software Engineer', '2026-08-07T00:00:00+00:00', "
        "'2026-08-07T00:00:00+00:00') RETURNING id",
        (ats_job_id,),
    ).fetchone()[0]
    resume_id = conn.execute(
        "INSERT INTO base_resumes (profile, version, selection, "
        "section_order, generated_at) VALUES ('software_engineer', 1, "
        "'{}', '[]', '2026-08-07T00:00:00+00:00') RETURNING id"
    ).fetchone()[0]
    conn.commit()
    return job_id, resume_id


def test_migrate_on_fresh_db_records_current_version(conn):
    migrate(conn)
    row = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?", (_SCHEMA_VERSION,)
    ).fetchone()
    assert row is not None


def test_migrate_is_idempotent(conn):
    migrate(conn)
    migrate(conn)
    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM schema_migrations WHERE version = ?",
        (_SCHEMA_VERSION,),
    ).fetchone()
    assert rows["n"] == 1


def test_migrate_on_fresh_db_creates_job_profile_unique_index(conn):
    migrate(conn)
    indexes = {
        row["name"]
        for row in conn.execute(
            "PRAGMA index_list(job_resume_variants)"
        ).fetchall()
    }
    assert "idx_job_resume_variants_job_profile" in indexes


def test_migrate_rebuilds_old_job_resume_variants_preserving_rows(
    old_shape_conn,
):
    conn = old_shape_conn
    _seed_company(conn)
    job_id, resume_id = _seed_job_and_base_resume(conn)
    conn.execute(
        "INSERT INTO job_resume_variants "
        "(job_id, profile, base_resume_id, selection_hash, created_at) "
        "VALUES (?, 'software_engineer', ?, 'hash1', '2026-08-07T00:00:00+00:00')",
        (job_id, resume_id),
    )
    conn.commit()

    migrate(conn)

    row = conn.execute(
        "SELECT job_id, review_status FROM job_resume_variants WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    assert row is not None, "existing row must survive the rebuild"
    assert row["review_status"] == "pending"


def test_migrate_rebuild_adds_review_status_and_reviewed_at_columns(
    old_shape_conn,
):
    conn = old_shape_conn
    migrate(conn)
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(job_resume_variants)")
    }
    assert "review_status" in columns
    assert "reviewed_at" in columns


def test_migrate_rebuild_drops_old_base_resume_hash_unique_constraint(
    old_shape_conn,
):
    """The actual bug this migration exists to fix: two different jobs
    with the same (base_resume_id, selection_hash) must both be
    insertable after migrate(), which the old constraint alone forbid."""
    conn = old_shape_conn
    _seed_company(conn)
    job_id, resume_id = _seed_job_and_base_resume(conn, ats_job_id="1")
    other_job_id, _ = _seed_job_and_base_resume(conn, ats_job_id="2")

    migrate(conn)

    conn.execute(
        "INSERT INTO job_resume_variants "
        "(job_id, profile, base_resume_id, selection_hash, created_at) "
        "VALUES (?, 'software_engineer', ?, 'shared', '2026-08-07T00:00:00+00:00')",
        (job_id, resume_id),
    )
    conn.execute(
        "INSERT INTO job_resume_variants "
        "(job_id, profile, base_resume_id, selection_hash, created_at) "
        "VALUES (?, 'software_engineer', ?, 'shared', '2026-08-07T00:00:00+00:00')",
        (other_job_id, resume_id),
    )
    conn.commit()

    count = conn.execute(
        "SELECT COUNT(*) AS n FROM job_resume_variants WHERE selection_hash = 'shared'"
    ).fetchone()["n"]
    assert count == 2


def test_migrate_rebuild_still_enforces_new_job_profile_uniqueness(
    old_shape_conn,
):
    conn = old_shape_conn
    _seed_company(conn)
    job_id, resume_id = _seed_job_and_base_resume(conn)
    migrate(conn)

    conn.execute(
        "INSERT INTO job_resume_variants "
        "(job_id, profile, base_resume_id, selection_hash, created_at) "
        "VALUES (?, 'software_engineer', ?, 'a', '2026-08-07T00:00:00+00:00')",
        (job_id, resume_id),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO job_resume_variants "
            "(job_id, profile, base_resume_id, selection_hash, created_at) "
            "VALUES (?, 'software_engineer', ?, 'b', '2026-08-07T00:00:00+00:00')",
            (job_id, resume_id),
        )


def test_migrate_rebuild_records_both_migration_versions(old_shape_conn):
    conn = old_shape_conn
    migrate(conn)
    versions = {
        row["version"] for row in conn.execute("SELECT version FROM schema_migrations")
    }
    assert "0001_initial" in versions
    assert _SCHEMA_VERSION in versions


def test_migrate_rebuild_is_idempotent(old_shape_conn):
    conn = old_shape_conn
    migrate(conn)
    migrate(conn)  # must not raise (e.g. "table already exists")
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM schema_migrations WHERE version = ?",
        (_SCHEMA_VERSION,),
    ).fetchone()["n"]
    assert count == 1
