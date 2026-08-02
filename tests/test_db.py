import sqlite3

import pytest

from jobengine.db.migrate import connect, init
from jobengine.db.models import (
    Company,
    Job,
    Outcome,
    get_company,
    get_job,
    insert_outcome,
    upsert_company,
    upsert_job,
)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "jobengine.db"
    connection = connect(db_path)
    init(connection)
    yield connection
    connection.close()


@pytest.fixture
def conn_with_company(conn):
    """A connection with the acme/greenhouse company already seeded, for
    tests whose focus is jobs rather than companies. Job tests that also
    want to assert on company immutability upsert their own company row
    instead, so their first upsert call is the one that fixes first_seen_at.
    """
    upsert_company(
        conn,
        Company(
            slug="acme",
            ats="greenhouse",
            name="Acme",
            status="active",
            source="seed",
            first_seen_at="2026-06-01T00:00:00+00:00",
        ),
    )
    return conn


def test_init_is_idempotent(conn):
    init(conn)
    init(conn)


def test_job_upsert_inserts_new_row(conn_with_company):
    conn = conn_with_company
    job = Job(
        ats="greenhouse",
        company_slug="acme",
        ats_job_id="123",
        title="Software Engineer",
        content_hash="hash-a",
        first_seen_at="2026-07-01T00:00:00+00:00",
        last_seen_at="2026-07-01T00:00:00+00:00",
    )
    job_id = upsert_job(conn, job)
    stored = get_job(conn, "greenhouse", "acme", "123")
    assert stored is not None
    assert stored.id == job_id
    assert stored.title == "Software Engineer"
    assert stored.first_seen_at == "2026-07-01T00:00:00+00:00"


def test_second_sync_of_unchanged_job_does_not_move_first_seen_at(conn_with_company):
    """The exact scenario from specs/00-data-model.md's definition of done:
    a second sync of the same job must not clobber first_seen_at, even
    though the syncing code always computes a "now" candidate for it."""
    conn = conn_with_company
    first_sync = Job(
        ats="greenhouse",
        company_slug="acme",
        ats_job_id="123",
        title="Software Engineer",
        content_hash="hash-a",
        first_seen_at="2026-07-01T00:00:00+00:00",
        last_seen_at="2026-07-01T00:00:00+00:00",
    )
    upsert_job(conn, first_sync)

    second_sync = Job(
        ats="greenhouse",
        company_slug="acme",
        ats_job_id="123",
        title="Software Engineer",
        content_hash="hash-a",
        first_seen_at="2026-07-02T00:00:00+00:00",
        last_seen_at="2026-07-02T00:00:00+00:00",
    )
    upsert_job(conn, second_sync)

    stored = get_job(conn, "greenhouse", "acme", "123")
    assert stored.first_seen_at == "2026-07-01T00:00:00+00:00"
    assert stored.last_seen_at == "2026-07-02T00:00:00+00:00"


def test_job_upsert_updates_changed_fields_on_real_edit(conn_with_company):
    conn = conn_with_company
    upsert_job(
        conn,
        Job(
            ats="greenhouse",
            company_slug="acme",
            ats_job_id="123",
            title="Software Engineer",
            content_hash="hash-a",
            first_seen_at="2026-07-01T00:00:00+00:00",
            last_seen_at="2026-07-01T00:00:00+00:00",
        ),
    )
    upsert_job(
        conn,
        Job(
            ats="greenhouse",
            company_slug="acme",
            ats_job_id="123",
            title="Senior Software Engineer",
            content_hash="hash-b",
            first_seen_at="2026-07-02T00:00:00+00:00",
            last_seen_at="2026-07-02T00:00:00+00:00",
        ),
    )
    stored = get_job(conn, "greenhouse", "acme", "123")
    assert stored.title == "Senior Software Engineer"
    assert stored.content_hash == "hash-b"
    assert stored.first_seen_at == "2026-07-01T00:00:00+00:00"


def test_job_direct_update_of_first_seen_at_raises(conn_with_company):
    conn = conn_with_company
    job_id = upsert_job(
        conn,
        Job(
            ats="greenhouse",
            company_slug="acme",
            ats_job_id="123",
            title="Software Engineer",
            first_seen_at="2026-07-01T00:00:00+00:00",
            last_seen_at="2026-07-01T00:00:00+00:00",
        ),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE jobs SET first_seen_at = ? WHERE id = ?",
            ("2026-08-01T00:00:00+00:00", job_id),
        )


def test_second_sync_of_unchanged_company_does_not_move_first_seen_at(conn):
    upsert_company(
        conn,
        Company(
            slug="acme",
            ats="greenhouse",
            name="Acme",
            status="active",
            source="seed",
            first_seen_at="2026-07-01T00:00:00+00:00",
        ),
    )
    upsert_company(
        conn,
        Company(
            slug="acme",
            ats="greenhouse",
            name="Acme",
            status="active",
            source="seed",
            first_seen_at="2026-07-02T00:00:00+00:00",
            last_checked_at="2026-07-02T00:00:00+00:00",
        ),
    )
    stored = get_company(conn, "acme", "greenhouse")
    assert stored.first_seen_at == "2026-07-01T00:00:00+00:00"
    assert stored.last_checked_at == "2026-07-02T00:00:00+00:00"


def test_company_direct_update_of_first_seen_at_raises(conn):
    upsert_company(
        conn,
        Company(
            slug="acme",
            ats="greenhouse",
            name="Acme",
            status="active",
            source="seed",
            first_seen_at="2026-07-01T00:00:00+00:00",
        ),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE companies SET first_seen_at = ? WHERE slug = ? AND ats = ?",
            ("2026-08-01T00:00:00+00:00", "acme", "greenhouse"),
        )


def test_outcomes_are_append_only(conn_with_company):
    conn = conn_with_company
    job_id = upsert_job(
        conn,
        Job(
            ats="greenhouse",
            company_slug="acme",
            ats_job_id="123",
            title="Software Engineer",
            first_seen_at="2026-07-01T00:00:00+00:00",
            last_seen_at="2026-07-01T00:00:00+00:00",
        ),
    )
    conn.execute(
        "INSERT INTO base_resumes (id, profile, version, selection, section_order, generated_at) "
        "VALUES (1, 'software_engineer', 1, '[]', '[]', '2026-07-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO job_resume_variants "
        "(id, job_id, profile, base_resume_id, selection_hash, created_at) "
        "VALUES (1, ?, 'software_engineer', 1, 'hash', '2026-07-01T00:00:00+00:00')",
        (job_id,),
    )
    conn.execute(
        "INSERT INTO applications (job_id, resume_variant_id, autonomy_level, status) "
        "VALUES (?, 1, 0, 'pending')",
        (job_id,),
    )
    application_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    outcome_id = insert_outcome(
        conn,
        Outcome(
            application_id=application_id,
            status="submitted",
            occurred_at="2026-07-01T00:00:00+00:00",
        ),
    )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE outcomes SET status = 'rejected' WHERE id = ?", (outcome_id,)
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM outcomes WHERE id = ?", (outcome_id,))
