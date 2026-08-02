import json

import httpx
import pytest
import yaml

from jobengine.db.migrate import connect, init
from jobengine.sources import ashby, greenhouse, registry
from jobengine.sources.models import JobPosting

# ---------------------------------------------------------------------------
# Greenhouse client
# ---------------------------------------------------------------------------


def _gh_response(jobs: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"jobs": jobs})


def test_greenhouse_parses_normal_response():
    job = {
        "id": 12345,
        "title": "Software Engineer",
        "updated_at": "2026-07-01T00:00:00Z",
        "location": {"name": "Remote - US"},
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/12345",
        "content": "<p>Build things.</p>",
        "departments": [{"name": "Engineering"}],
        "offices": [],
    }
    transport = httpx.MockTransport(lambda request: _gh_response([job]))

    postings = _run(greenhouse.fetch_board("acme", transport=transport))

    assert len(postings) == 1
    posting = postings[0]
    assert isinstance(posting, JobPosting)
    assert posting.source == "greenhouse"
    assert posting.company_slug == "acme"
    assert posting.ats_job_id == "12345"
    assert posting.title == "Software Engineer"
    assert posting.location_raw == "Remote - US"
    assert posting.department == "Engineering"
    assert posting.url == "https://boards.greenhouse.io/acme/jobs/12345"
    assert posting.apply_url == "https://boards.greenhouse.io/acme/jobs/12345"
    assert posting.description_plain == "Build things."
    assert posting.ats_date == "2026-07-01T00:00:00Z"
    assert json.loads(posting.raw_json)["id"] == 12345


def test_greenhouse_strips_html_entities_and_tags():
    job = {
        "id": 1,
        "title": "T",
        "updated_at": None,
        "location": {"name": "NYC"},
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
        "content": "<p>Build &amp; ship &lt;fast&gt;</p><ul><li>Own it</li></ul>",
        "departments": [],
        "offices": [],
    }
    transport = httpx.MockTransport(lambda request: _gh_response([job]))

    postings = _run(greenhouse.fetch_board("acme", transport=transport))

    assert postings[0].description_plain == "Build & ship <fast> Own it"


def test_greenhouse_retries_on_5xx_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(502)
        return _gh_response([])

    transport = httpx.MockTransport(handler)

    postings = _run(greenhouse.fetch_board("acme", transport=transport))

    assert postings == []
    assert calls["n"] == 3


def test_greenhouse_does_not_retry_on_404():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        _run(greenhouse.fetch_board("acme", transport=transport))

    assert exc_info.value.response.status_code == 404
    assert calls["n"] == 1


def test_greenhouse_raises_after_exhausting_retries_on_persistent_5xx():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)

    with pytest.raises(httpx.HTTPStatusError):
        _run(greenhouse.fetch_board("acme", transport=transport))

    assert calls["n"] == 3


# ---------------------------------------------------------------------------
# Ashby client
# ---------------------------------------------------------------------------


def _ashby_response(jobs: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"jobs": jobs})


def test_ashby_parses_normal_response():
    job = {
        "id": "abc-123",
        "title": "ML Engineer",
        "location": "Remote",
        "department": "Research",
        "team": "Core ML",
        "isListed": True,
        "isRemote": True,
        "workplaceType": "Remote",
        "descriptionPlain": "Do research.",
        "publishedAt": "2026-07-01T00:00:00Z",
        "employmentType": "FullTime",
        "jobUrl": "https://jobs.ashbyhq.com/acme/abc-123",
        "applyUrl": "https://jobs.ashbyhq.com/acme/abc-123/apply",
        "compensation": {"min": 150000, "max": 200000},
    }
    transport = httpx.MockTransport(lambda request: _ashby_response([job]))

    postings = _run(ashby.fetch_board("acme", transport=transport))

    assert len(postings) == 1
    posting = postings[0]
    assert posting.source == "ashby"
    assert posting.company_slug == "acme"
    assert posting.ats_job_id == "abc-123"
    assert posting.title == "ML Engineer"
    assert posting.location_raw == "Remote"
    assert posting.remote is True
    assert posting.department == "Research"
    assert posting.url == "https://jobs.ashbyhq.com/acme/abc-123"
    assert posting.apply_url == "https://jobs.ashbyhq.com/acme/abc-123/apply"
    assert posting.description_plain == "Do research."
    assert posting.ats_date == "2026-07-01T00:00:00Z"
    assert json.loads(posting.compensation_raw) == {"min": 150000, "max": 200000}
    assert json.loads(posting.raw_json)["id"] == "abc-123"


def test_ashby_skips_unlisted_postings():
    listed = {
        "id": "1",
        "title": "Listed",
        "location": "Remote",
        "department": "Eng",
        "isListed": True,
        "isRemote": True,
        "descriptionPlain": "x",
        "publishedAt": None,
        "jobUrl": "https://jobs.ashbyhq.com/acme/1",
        "applyUrl": "https://jobs.ashbyhq.com/acme/1/apply",
    }
    unlisted = {**listed, "id": "2", "title": "Unlisted", "isListed": False}
    transport = httpx.MockTransport(lambda request: _ashby_response([listed, unlisted]))

    postings = _run(ashby.fetch_board("acme", transport=transport))

    assert [p.ats_job_id for p in postings] == ["1"]


# ---------------------------------------------------------------------------
# Registry: seed
# ---------------------------------------------------------------------------


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "jobengine.db"
    connection = connect(db_path)
    init(connection)
    yield connection
    connection.close()


@pytest.fixture
def seed_file(tmp_path):
    path = tmp_path / "seed_companies.yaml"
    path.write_text(
        yaml.dump(
            [
                {"ats": "greenhouse", "slug": "acme", "name": "Acme"},
                {"ats": "ashby", "slug": "beta", "name": "Beta Inc"},
            ]
        )
    )
    return path


def test_seed_inserts_new_companies_from_yaml(conn, seed_file):
    inserted, total = registry.seed(conn, path=seed_file)

    assert inserted == 2
    assert total == 2
    rows = conn.execute(
        "SELECT slug, ats, name, status, source FROM companies ORDER BY slug"
    ).fetchall()
    assert [tuple(r) for r in rows] == [
        ("acme", "greenhouse", "Acme", "unverified", "seed"),
        ("beta", "ashby", "Beta Inc", "unverified", "seed"),
    ]


def test_seed_is_idempotent_and_does_not_reset_validated_status(conn, seed_file):
    registry.seed(conn, path=seed_file)
    conn.execute(
        "UPDATE companies SET status = 'active', consecutive_failures = 2 "
        "WHERE slug = 'acme' AND ats = 'greenhouse'"
    )
    conn.commit()

    inserted, total = registry.seed(conn, path=seed_file)

    assert inserted == 0
    assert total == 2
    row = conn.execute(
        "SELECT status, consecutive_failures FROM companies WHERE slug = 'acme' AND ats = 'greenhouse'"
    ).fetchone()
    assert tuple(row) == ("active", 2)


# ---------------------------------------------------------------------------
# Registry: add
# ---------------------------------------------------------------------------


def test_add_manual_company_uses_manual_source(conn):
    added = registry.add(conn, "greenhouse", "foo", "Foo Inc")

    assert added is True
    row = conn.execute(
        "SELECT name, status, source FROM companies WHERE slug = 'foo' AND ats = 'greenhouse'"
    ).fetchone()
    assert tuple(row) == ("Foo Inc", "unverified", "manual")


def test_add_does_not_duplicate_existing_company(conn):
    registry.add(conn, "greenhouse", "foo", "Foo Inc")

    added_again = registry.add(conn, "greenhouse", "foo", "Foo Inc")

    assert added_again is False
    count = conn.execute(
        "SELECT COUNT(*) FROM companies WHERE slug = 'foo' AND ats = 'greenhouse'"
    ).fetchone()[0]
    assert count == 1


# ---------------------------------------------------------------------------
# Registry: validate
# ---------------------------------------------------------------------------


async def _fake_fetch_ok(slug: str) -> list[JobPosting]:
    return [
        JobPosting(
            source="greenhouse",
            company_slug=slug,
            ats_job_id="1",
            title="T",
            raw_json="{}",
        )
    ]


async def _fake_fetch_zero(slug: str) -> list[JobPosting]:
    return []


async def _fake_fetch_404(slug: str) -> list[JobPosting]:
    raise httpx.HTTPStatusError(
        "not found",
        request=httpx.Request("GET", "https://x"),
        response=httpx.Response(404),
    )


async def _fake_fetch_timeout(slug: str) -> list[JobPosting]:
    raise httpx.TimeoutException("timed out")


def _seed_one(conn, *, slug="acme", ats="greenhouse", status="unverified", failures=0):
    conn.execute(
        "INSERT INTO companies (slug, ats, name, status, source, first_seen_at, consecutive_failures) "
        "VALUES (?, ?, ?, ?, 'seed', '2026-01-01T00:00:00+00:00', ?)",
        (slug, ats, slug.title(), status, failures),
    )
    conn.commit()


def test_validate_marks_200_with_jobs_active_and_resets_failures(conn):
    _seed_one(conn, status="unverified", failures=2)

    counts = registry.validate(conn, fetchers={"greenhouse": _fake_fetch_ok})

    row = conn.execute(
        "SELECT status, consecutive_failures, last_ok_at FROM companies"
    ).fetchone()
    assert row["status"] == "active"
    assert row["consecutive_failures"] == 0
    assert row["last_ok_at"] is not None
    assert counts == {"active": 1, "dead": 0}


def test_validate_marks_200_zero_jobs_active_without_resetting_failures(conn):
    _seed_one(conn, status="unverified", failures=2)

    counts = registry.validate(conn, fetchers={"greenhouse": _fake_fetch_zero})

    row = conn.execute("SELECT status, consecutive_failures FROM companies").fetchone()
    assert row["status"] == "active"
    assert row["consecutive_failures"] == 2
    assert counts == {"active": 1, "dead": 0}


def test_validate_increments_failures_on_404_and_marks_dead_at_three(conn):
    _seed_one(conn, status="active", failures=2)

    counts = registry.validate(conn, fetchers={"greenhouse": _fake_fetch_404})

    row = conn.execute("SELECT status, consecutive_failures FROM companies").fetchone()
    assert row["status"] == "dead"
    assert row["consecutive_failures"] == 3
    assert counts == {"active": 0, "dead": 1}


def test_validate_404_below_threshold_does_not_change_status(conn):
    _seed_one(conn, status="unverified", failures=0)

    counts = registry.validate(conn, fetchers={"greenhouse": _fake_fetch_404})

    row = conn.execute("SELECT status, consecutive_failures FROM companies").fetchone()
    assert row["status"] == "unverified"
    assert row["consecutive_failures"] == 1
    assert counts == {"active": 0, "dead": 0}


def test_validate_5xx_or_timeout_does_not_increment_failures(conn):
    _seed_one(conn, status="active", failures=1)

    counts = registry.validate(conn, fetchers={"greenhouse": _fake_fetch_timeout})

    row = conn.execute("SELECT status, consecutive_failures FROM companies").fetchone()
    assert row["status"] == "active"
    assert row["consecutive_failures"] == 1
    assert counts == {"active": 0, "dead": 0}


def test_validate_reports_active_and_dead_counts(conn):
    _seed_one(conn, slug="acme", ats="greenhouse", status="unverified", failures=0)
    _seed_one(conn, slug="beta", ats="ashby", status="active", failures=2)
    _seed_one(conn, slug="gamma", ats="greenhouse", status="unverified", failures=0)

    counts = registry.validate(
        conn,
        fetchers={
            "greenhouse": lambda slug: (
                _fake_fetch_ok if slug == "acme" else _fake_fetch_404
            )(slug),
            "ashby": _fake_fetch_404,
        },
    )

    assert counts == {"active": 1, "dead": 1}


def test_validate_skips_dead_companies(conn):
    _seed_one(conn, status="dead", failures=3)

    counts = registry.validate(conn, fetchers={"greenhouse": _fake_fetch_ok})

    row = conn.execute("SELECT status FROM companies").fetchone()
    assert row["status"] == "dead"
    assert counts == {"active": 0, "dead": 0}


def _run(coro):
    import asyncio

    return asyncio.run(coro)
