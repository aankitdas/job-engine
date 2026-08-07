"""Tests for jobengine.web.app (F1). Written before implementation per
hard rule 7's project-wide tests-first convention. Uses FastAPI's
TestClient against a tmp_path db via dependency override on get_ctx --
never the real data/jobengine.db.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jobengine.db.migrate import connect, init
from jobengine.db.models import (
    BaseResume,
    Job,
    get_job_resume_variant,
    insert_base_resume,
    upsert_job,
)
from jobengine.llm.schemas import (
    ApiConfig,
    FallbackConfig,
    LLMConfig,
    LocalConfig,
    RoutingConfig,
)
from jobengine.pipeline.filter import (
    CitizenshipClearanceConfig,
    EmploymentTypeConfig,
    FilterConfig,
    LocationConfig,
    ProfileFilterConfig,
    SeniorityConfig,
)
from jobengine.profiles.config import ProfileConfig
from jobengine.queue.orchestrate import QueueContext
from jobengine.resume.bank import DEFAULT_BANK_PATH, load_bank
from jobengine.resume.render import load_identity
from jobengine.web.app import app, get_ctx


@pytest.fixture
def conn(tmp_path):
    # check_same_thread=False: TestClient dispatches sync routes/deps
    # through FastAPI's threadpool, same as the real running app (see
    # jobengine.db.migrate.connect's docstring).
    db_path = tmp_path / "jobengine.db"
    connection = connect(db_path, check_same_thread=False)
    init(connection)
    yield connection
    connection.close()


def _seed_company(conn):
    conn.execute(
        "INSERT OR IGNORE INTO companies (slug, ats, name, status, source, first_seen_at) "
        "VALUES ('acme', 'greenhouse', 'Acme', 'active', 'seed', '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()


def _seed_job(
    conn,
    *,
    ats_job_id="1",
    title="Software Engineer",
    description="Requirements:\n- Go\n",
    location_raw="San Francisco, CA",
) -> int:
    _seed_company(conn)
    return upsert_job(
        conn,
        Job(
            ats="greenhouse",
            company_slug="acme",
            ats_job_id=ats_job_id,
            title=title,
            description=description,
            location_raw=location_raw,
            raw_json="{}",
            first_seen_at="2026-08-07T00:00:00+00:00",
            last_seen_at="2026-08-07T00:00:00+00:00",
        ),
    )


def _seed_base_resume(conn, profile="software_engineer") -> int:
    return insert_base_resume(
        conn,
        BaseResume(
            profile=profile,
            version=1,
            selection="{}",
            section_order='["work_history", "projects", "education", "publications"]',
            generated_at="2026-08-07T00:00:00+00:00",
        ),
    )


def _llm_config() -> LLMConfig:
    return LLMConfig(
        local=LocalConfig(
            enabled=True,
            base_url="http://fake:11434",
            model="qwen3.5:9b-q4_K_M",
            context=16384,
            timeout_s=120,
        ),
        routing=RoutingConfig(relevance="local", extract="local", rephrase="local"),
        fallback=FallbackConfig(relevance="skip", extract="fail", rephrase="skip"),
        api=ApiConfig(enabled=False),
    )


def _filter_config() -> FilterConfig:
    return FilterConfig(
        profiles={"software_engineer": ProfileFilterConfig(title_aliases=["engineer"])},
        location=LocationConfig(remote_synonyms=[]),
        seniority=SeniorityConfig(exclude_title_keywords=[]),
        citizenship_clearance=CitizenshipClearanceConfig(exclude_phrases=[]),
        employment_type=EmploymentTypeConfig(
            exclude_ashby_types=[], exclude_title_keywords=[]
        ),
    )


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)
        self.prompt_eval_count = 10
        self.eval_count = 5


class _FakeClient:
    def __init__(self, extract_payload: dict) -> None:
        self._extract_payload = extract_payload
        self._rephrase_payload = {"text": "unchanged", "keywords_added": []}
        self.calls: list[dict[str, Any]] = []

    async def chat(self, **kwargs: Any):
        self.calls.append(kwargs)
        schema_props = kwargs.get("format", {}).get("properties", {})
        if "text" in schema_props and "keywords_added" in schema_props:
            content = json.dumps(self._rephrase_payload)
        else:
            content = json.dumps(self._extract_payload)
        return _FakeResponse(content)


_EXTRACT_PAYLOAD = {
    "required_keywords": ["Go", "Kubernetes"],
    "preferred_keywords": [],
    "tech_stack": ["Go", "Kubernetes"],
}


def _ctx(conn, local_client) -> QueueContext:
    return QueueContext(
        conn=conn,
        full_bank=load_bank(DEFAULT_BANK_PATH),
        identity=load_identity(),
        profile_configs={
            "software_engineer": ProfileConfig(
                id="software_engineer",
                display_name="Software Engineer",
                section_order=["work_history", "projects", "education", "publications"],
                include_summary=False,
            )
        },
        filter_config=_filter_config(),
        llm_config=_llm_config(),
        local_client=local_client,
    )


@pytest.fixture
def client_factory(conn):
    """Yields a function that overrides get_ctx with a fresh QueueContext
    wrapping a given local_client, and returns a TestClient. Cleans up
    the override after the test regardless of outcome."""

    def _make(local_client):
        ctx = _ctx(conn, local_client)
        app.dependency_overrides[get_ctx] = lambda: ctx
        return TestClient(app)

    yield _make
    app.dependency_overrides.pop(get_ctx, None)


def test_detail_page_first_visit_triggers_ensure_reviewed_and_persists(
    conn, client_factory
):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))

    assert get_job_resume_variant(conn, job_id, "software_engineer") is None
    response = client.get(f"/jobs/{job_id}/software_engineer")

    assert response.status_code == 200
    assert get_job_resume_variant(conn, job_id, "software_engineer") is not None
    assert "R001" in response.text


def test_detail_page_second_visit_does_not_retrigger(conn, client_factory):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    first_client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))
    first_client.get(f"/jobs/{job_id}/software_engineer")

    fake = _FakeClient(_EXTRACT_PAYLOAD)
    second_client = client_factory(fake)
    response = second_client.get(f"/jobs/{job_id}/software_engineer")

    assert response.status_code == 200
    assert fake.calls == []


def test_detail_page_unknown_job_returns_404(conn, client_factory):
    _seed_base_resume(conn)
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))
    response = client.get("/jobs/999999/software_engineer")
    assert response.status_code == 404


def test_list_page_shows_pending_entry(conn, client_factory):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))
    client.get(f"/jobs/{job_id}/software_engineer")  # trigger it into existence

    response = client.get("/")
    assert response.status_code == 200
    assert "Software Engineer" in response.text


def test_list_page_shows_untriggered_job_that_passes_all_filters(
    conn, client_factory
):
    _seed_job(conn, ats_job_id="untriggered", title="Backend Engineer")
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))

    response = client.get("/")

    assert response.status_code == 200
    assert "Backend Engineer" in response.text


def test_list_page_omits_untriggered_job_that_fails_a_non_title_b3_check(
    conn, client_factory
):
    """Regression test for wiring passes_all_filters() into _new_pairs():
    before this, a job that matched the title alias but failed some
    other B3 check (here, a non-US location) still showed up as "not
    yet reviewed"."""
    _seed_job(
        conn,
        ats_job_id="non-us",
        title="Backend Engineer",
        location_raw="Berlin, Germany",
    )
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))

    response = client.get("/")

    assert response.status_code == 200
    assert "Backend Engineer" not in response.text


def test_approve_flips_review_status_and_creates_application(conn, client_factory):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))
    client.get(f"/jobs/{job_id}/software_engineer")

    response = client.post(
        f"/jobs/{job_id}/software_engineer/approve", follow_redirects=False
    )

    assert response.status_code == 303
    variant = get_job_resume_variant(conn, job_id, "software_engineer")
    assert variant.review_status == "approved"
    application = conn.execute(
        "SELECT status, autonomy_level FROM applications WHERE resume_variant_id = ?",
        (variant.id,),
    ).fetchone()
    assert application is not None
    assert application["status"] == "queued"
    assert application["autonomy_level"] == 0


def test_reject_flips_review_status_and_creates_no_application(conn, client_factory):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))
    client.get(f"/jobs/{job_id}/software_engineer")

    response = client.post(
        f"/jobs/{job_id}/software_engineer/reject", follow_redirects=False
    )

    assert response.status_code == 303
    variant = get_job_resume_variant(conn, job_id, "software_engineer")
    assert variant.review_status == "rejected"
    application = conn.execute(
        "SELECT 1 FROM applications WHERE resume_variant_id = ?", (variant.id,)
    ).fetchone()
    assert application is None


def test_rejected_job_drops_off_the_list_page(conn, client_factory):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))
    client.get(f"/jobs/{job_id}/software_engineer")
    client.post(f"/jobs/{job_id}/software_engineer/reject", follow_redirects=False)

    response = client.get("/")
    assert "Software Engineer" not in response.text


def test_approve_on_never_reviewed_pair_returns_404(conn, client_factory):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))

    response = client.post(
        f"/jobs/{job_id}/software_engineer/approve", follow_redirects=False
    )
    assert response.status_code == 404
