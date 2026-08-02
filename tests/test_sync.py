import json

import pytest

from jobengine.db.migrate import connect, init
from jobengine.sources import sync
from jobengine.sources.models import JobPosting


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "jobengine.db"
    connection = connect(db_path)
    init(connection)
    yield connection
    connection.close()


def _seed_company(conn, *, slug="acme", ats="greenhouse", status="active"):
    conn.execute(
        "INSERT INTO companies (slug, ats, name, status, source, first_seen_at) "
        "VALUES (?, ?, ?, ?, 'seed', '2026-01-01T00:00:00+00:00')",
        (slug, ats, slug.title(), status),
    )
    conn.commit()


def _posting(
    slug: str, ats_job_id: str, description: str = "Do the work."
) -> JobPosting:
    return JobPosting(
        source="greenhouse",
        company_slug=slug,
        ats_job_id=ats_job_id,
        title=f"Job {ats_job_id}",
        description_plain=description,
        raw_json="{}",
    )


def _fetchers(boards: dict[str, list[JobPosting]]):
    async def _fetch(slug: str) -> list[JobPosting]:
        return boards.get(slug, [])

    return {"greenhouse": _fetch}


def _failing_fetchers(boards: dict[str, list[JobPosting]], *, fails: set[str]):
    async def _fetch(slug: str) -> list[JobPosting]:
        if slug in fails:
            raise ConnectionError(f"boom: {slug}")
        return boards.get(slug, [])

    return {"greenhouse": _fetch}


def _job_rows(conn):
    return {
        row["ats_job_id"]: dict(row)
        for row in conn.execute("SELECT * FROM jobs").fetchall()
    }


# ---------------------------------------------------------------------------
# The two explicit acceptance-criterion tests (spec 04's stated DoD)
# ---------------------------------------------------------------------------


def test_second_sync_of_unchanged_data_does_not_change_first_seen_at(conn):
    _seed_company(conn)
    boards = {"acme": [_posting("acme", "1"), _posting("acme", "2")]}
    fetchers = _fetchers(boards)

    sync.sync(conn, fetchers=fetchers)
    first_run = _job_rows(conn)

    sync.sync(conn, fetchers=fetchers)
    second_run = _job_rows(conn)

    assert first_run["1"]["first_seen_at"] == second_run["1"]["first_seen_at"]
    assert first_run["2"]["first_seen_at"] == second_run["2"]["first_seen_at"]


def test_new_posting_on_second_run_gets_its_own_first_seen_at(conn):
    _seed_company(conn)

    sync.sync(conn, fetchers=_fetchers({"acme": [_posting("acme", "1")]}))
    first_run = _job_rows(conn)

    sync.sync(
        conn,
        fetchers=_fetchers({"acme": [_posting("acme", "1"), _posting("acme", "2")]}),
    )
    second_run = _job_rows(conn)

    assert first_run["1"]["first_seen_at"] == second_run["1"]["first_seen_at"]
    assert "2" not in first_run
    assert "2" in second_run
    assert second_run["2"]["first_seen_at"] is not None


# ---------------------------------------------------------------------------
# Edit detection
# ---------------------------------------------------------------------------


def test_content_hash_change_is_logged_and_counted_as_edited(conn, caplog):
    _seed_company(conn)
    sync.sync(
        conn, fetchers=_fetchers({"acme": [_posting("acme", "1", "Original text.")]})
    )

    with caplog.at_level("INFO"):
        summary = sync.sync(
            conn, fetchers=_fetchers({"acme": [_posting("acme", "1", "Changed text.")]})
        )

    assert summary.edited == 1
    assert any(
        "acme" in record.message and "1" in record.message for record in caplog.records
    )

    rows = _job_rows(conn)
    assert rows["1"]["description"] == "Changed text."


def test_unchanged_content_is_not_counted_as_edited(conn):
    _seed_company(conn)
    boards = {"acme": [_posting("acme", "1", "Same text.")]}
    fetchers = _fetchers(boards)
    sync.sync(conn, fetchers=fetchers)

    summary = sync.sync(conn, fetchers=fetchers)

    assert summary.edited == 0
    assert summary.updated == 1


# ---------------------------------------------------------------------------
# closed_at
# ---------------------------------------------------------------------------


def test_job_missing_from_second_fetch_gets_closed_at_set(conn):
    _seed_company(conn)
    sync.sync(
        conn,
        fetchers=_fetchers({"acme": [_posting("acme", "1"), _posting("acme", "2")]}),
    )

    summary = sync.sync(conn, fetchers=_fetchers({"acme": [_posting("acme", "1")]}))

    rows = _job_rows(conn)
    assert rows["1"]["closed_at"] is None
    assert rows["2"]["closed_at"] is not None
    assert summary.closed == 1


def test_job_reappearing_after_close_gets_closed_at_cleared(conn):
    _seed_company(conn)
    sync.sync(conn, fetchers=_fetchers({"acme": [_posting("acme", "1")]}))
    sync.sync(conn, fetchers=_fetchers({"acme": []}))
    assert _job_rows(conn)["1"]["closed_at"] is not None

    sync.sync(conn, fetchers=_fetchers({"acme": [_posting("acme", "1")]}))

    assert _job_rows(conn)["1"]["closed_at"] is None


# ---------------------------------------------------------------------------
# Per-company failure isolation
# ---------------------------------------------------------------------------


def test_failed_company_is_skipped_without_crashing_the_run(conn):
    _seed_company(conn, slug="acme")
    _seed_company(conn, slug="broken")
    fetchers = _failing_fetchers(
        {"acme": [_posting("acme", "1")]},
        fails={"broken"},
    )

    summary = sync.sync(conn, fetchers=fetchers)

    assert summary.companies_ok == 1
    assert summary.companies_failed == 1
    assert len(summary.errors) == 1
    assert "broken" in summary.errors[0]
    assert "1" in _job_rows(conn)


def test_failed_company_does_not_close_its_jobs(conn):
    _seed_company(conn, slug="broken")
    sync.sync(conn, fetchers=_fetchers({"broken": [_posting("broken", "9")]}))
    assert _job_rows(conn)["9"]["closed_at"] is None

    summary = sync.sync(conn, fetchers=_failing_fetchers({}, fails={"broken"}))

    assert summary.companies_failed == 1
    assert _job_rows(conn)["9"]["closed_at"] is None


# ---------------------------------------------------------------------------
# dry-run and the runs table
# ---------------------------------------------------------------------------


def test_dry_run_writes_nothing(conn):
    _seed_company(conn)

    summary = sync.sync(
        conn, dry_run=True, fetchers=_fetchers({"acme": [_posting("acme", "1")]})
    )

    assert summary.new == 1
    assert _job_rows(conn) == {}
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_runs_table_gets_one_row_per_sync_with_counts(conn):
    _seed_company(conn)

    sync.sync(
        conn,
        fetchers=_fetchers({"acme": [_posting("acme", "1"), _posting("acme", "2")]}),
    )

    rows = conn.execute("SELECT stage, counts, errors FROM runs").fetchall()
    assert len(rows) == 1
    assert rows[0]["stage"] == "sync"
    counts = json.loads(rows[0]["counts"])
    assert counts["new"] == 2
    assert counts["companies_ok"] == 1
    assert rows[0]["errors"] is None
