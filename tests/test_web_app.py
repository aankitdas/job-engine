"""Tests for jobengine.web.app (F1). Written before implementation per
hard rule 7's project-wide tests-first convention. Uses FastAPI's
TestClient against a tmp_path db via dependency override on get_ctx --
never the real data/jobengine.db.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jobengine.db.migrate import connect, init
from jobengine.db.models import (
    BaseResume,
    Job,
    JobResumeVariant,
    RubricResultRow,
    get_job_resume_variant,
    insert_base_resume,
    insert_job_resume_variant,
    insert_rubric_results,
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
    LeadershipConfig,
    LocationConfig,
    ProfileFilterConfig,
    SeniorityConfig,
)
from jobengine.pipeline.relevance import RelevanceConfig
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
    first_seen_at=None,
    apply_url=None,
) -> int:
    # Relative to "now" (1 day old), not a hardcoded literal: several
    # tests below assert a job appears in GET /'s _LIST_WINDOW_DAYS
    # window, and a fixed past date eventually ages out as real session
    # time passes, failing tests that have nothing to do with whatever
    # actually changed.
    if first_seen_at is None:
        first_seen_at = (datetime.now(UTC) - timedelta(days=1)).isoformat()
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
            apply_url=apply_url,
            raw_json="{}",
            first_seen_at=first_seen_at,
            last_seen_at=first_seen_at,
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
        leadership=LeadershipConfig(exclude_phrases=[]),
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
    "required_keywords": ["Go", "Rust"],
    "preferred_keywords": [],
    "tech_stack": ["Go", "Rust"],
}


def _relevance_config(**overrides) -> RelevanceConfig:
    fields = {"disqualifier_blocklist": [], "freshness_window_days": None}
    fields.update(overrides)
    return RelevanceConfig(**fields)


def _ctx(
    conn, local_client, relevance_config: RelevanceConfig | None = None
) -> QueueContext:
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
        relevance_config=relevance_config or _relevance_config(),
        local_client=local_client,
    )


@pytest.fixture
def client_factory(conn):
    """Yields a function that overrides get_ctx with a fresh QueueContext
    wrapping a given local_client, and returns a TestClient. Cleans up
    the override after the test regardless of outcome."""

    def _make(local_client, relevance_config: RelevanceConfig | None = None):
        ctx = _ctx(conn, local_client, relevance_config)
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


def test_detail_page_shows_human_readable_rule_name_alongside_rule_id(
    conn, client_factory
):
    """D46: the raw rule_id/detail pair stays (real measured signal),
    but a reviewer also sees a plain-English name and explanation,
    sourced from specs/08-rubric.md's own text (rubric.rules.RULE_INFO),
    not invented in the template."""
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))

    response = client.get(f"/jobs/{job_id}/software_engineer")

    assert "R001" in response.text
    assert "Keyword coverage" in response.text
    assert "0.70" in response.text


def test_detail_page_links_the_rendered_docx_for_download(conn, client_factory):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))

    response = client.get(f"/jobs/{job_id}/software_engineer")

    variant = get_job_resume_variant(conn, job_id, "software_engineer")
    docx_url = "/resume/" + variant.docx_path.removeprefix("resume/")
    assert f'href="{docx_url}"' in response.text
    assert "download" in response.text


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


def test_list_page_shows_untriggered_job_that_passes_all_filters(conn, client_factory):
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


def test_list_page_omits_untriggered_job_scored_below_relevance_floor(
    conn, client_factory
):
    """Wires C4's relevance_scores into F1's queue gate: a job that
    passes B3 in full but was scored below the configured floor by C4
    must not surface as a "not yet reviewed" candidate, same as a
    B3-excluded job doesn't."""
    from jobengine.db.models import RelevanceScore, upsert_relevance_score

    job_id = _seed_job(conn, ats_job_id="low-relevance", title="Backend Engineer")
    upsert_relevance_score(
        conn,
        RelevanceScore(
            job_id=job_id,
            profile="software_engineer",
            score=10.0,
            scored_at="2026-08-07T00:00:00+00:00",
        ),
    )
    client = client_factory(
        _FakeClient(_EXTRACT_PAYLOAD),
        relevance_config=_relevance_config(min_relevance_score=20),
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "Backend Engineer" not in response.text


def test_list_page_shows_untriggered_job_scored_at_or_above_relevance_floor(
    conn, client_factory
):
    from jobengine.db.models import RelevanceScore, upsert_relevance_score

    job_id = _seed_job(conn, ats_job_id="ok-relevance", title="Backend Engineer")
    upsert_relevance_score(
        conn,
        RelevanceScore(
            job_id=job_id,
            profile="software_engineer",
            score=20.0,
            scored_at="2026-08-07T00:00:00+00:00",
        ),
    )
    client = client_factory(
        _FakeClient(_EXTRACT_PAYLOAD),
        relevance_config=_relevance_config(min_relevance_score=20),
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "Backend Engineer" in response.text


def test_list_page_shows_untriggered_job_with_no_relevance_score_yet(
    conn, client_factory
):
    """Fail open: C4's nightly batch hasn't necessarily scored a job
    that just cleared B3 minutes ago (they run on independent
    schedules) -- an unscored job must still surface, not be treated as
    a rejection."""
    _seed_job(conn, ats_job_id="unscored", title="Backend Engineer")
    client = client_factory(
        _FakeClient(_EXTRACT_PAYLOAD),
        relevance_config=_relevance_config(min_relevance_score=20),
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "Backend Engineer" in response.text


# D42: _EXTRACT_PAYLOAD's ["Go", "Rust"] (["Go", "Kubernetes"] until
# D47's real bank retag gave "Kubernetes" genuine coverage) has no
# coverage in the real bank (the same test_detail_page test below
# already asserts "R001" appears on this exact fixture's rendered page),
# so every variant seeded
# with it is a real, soft (R001-only) rubric failure -- approve() now
# gates on that, and this used to be the bug D42 fixes: a bare POST
# approve on this variant used to succeed silently.


def test_approve_without_override_on_a_soft_failing_variant_is_rejected(
    conn, client_factory
):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))
    client.get(f"/jobs/{job_id}/software_engineer")

    response = client.post(
        f"/jobs/{job_id}/software_engineer/approve", follow_redirects=False
    )

    assert response.status_code == 409
    variant = get_job_resume_variant(conn, job_id, "software_engineer")
    assert variant.review_status == "pending"
    application = conn.execute(
        "SELECT 1 FROM applications WHERE resume_variant_id = ?", (variant.id,)
    ).fetchone()
    assert application is None


def test_approve_with_override_on_a_soft_failing_variant_succeeds(conn, client_factory):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))
    client.get(f"/jobs/{job_id}/software_engineer")

    response = client.post(
        f"/jobs/{job_id}/software_engineer/approve",
        data={"override_soft_failure": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    variant = get_job_resume_variant(conn, job_id, "software_engineer")
    assert variant.review_status == "approved"
    assert variant.accepted is True
    application = conn.execute(
        "SELECT status, autonomy_level FROM applications WHERE resume_variant_id = ?",
        (variant.id,),
    ).fetchone()
    assert application is not None
    assert application["status"] == "queued"
    assert application["autonomy_level"] == 0


def test_detail_page_shows_approve_anyway_button_for_a_soft_failure(
    conn, client_factory
):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))

    response = client.get(f"/jobs/{job_id}/software_engineer")

    assert "override_soft_failure" in response.text
    assert "approve anyway" in response.text.lower()


# --- D44: approve() redirects back to the detail page, not "/", so the
# approved job stays reachable with its apply URL and resume in hand
# instead of vanishing from both list sections. See docs/decisions.md
# D44. Reuses the override path (same _EXTRACT_PAYLOAD fixture as D42's
# tests above) since a plain pass and an overridden soft failure share
# the exact same `return RedirectResponse(...)` line in approve() -- one
# test on that line is sufficient, not two near-identical ones.


def test_approve_redirects_to_the_detail_page_not_the_list(conn, client_factory):
    job_id = _seed_job(conn, apply_url="https://job-boards.greenhouse.io/acme/jobs/1")
    _seed_base_resume(conn)
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))
    client.get(f"/jobs/{job_id}/software_engineer")

    response = client.post(
        f"/jobs/{job_id}/software_engineer/approve",
        data={"override_soft_failure": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/jobs/{job_id}/software_engineer"


def test_approved_detail_page_shows_apply_url_and_hides_action_buttons(
    conn, client_factory
):
    job_id = _seed_job(conn, apply_url="https://job-boards.greenhouse.io/acme/jobs/1")
    _seed_base_resume(conn)
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))
    client.get(f"/jobs/{job_id}/software_engineer")
    client.post(
        f"/jobs/{job_id}/software_engineer/approve",
        data={"override_soft_failure": "true"},
        follow_redirects=False,
    )

    response = client.get(f"/jobs/{job_id}/software_engineer")

    assert "https://job-boards.greenhouse.io/acme/jobs/1" in response.text
    assert "manual" in response.text.lower()
    assert f'action="/jobs/{job_id}/software_engineer/approve"' not in response.text
    assert f'action="/jobs/{job_id}/software_engineer/reject"' not in response.text


def test_pending_detail_page_does_not_show_the_approved_confirmation_block(
    conn, client_factory
):
    job_id = _seed_job(conn, apply_url="https://job-boards.greenhouse.io/acme/jobs/1")
    _seed_base_resume(conn)
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))

    response = client.get(f"/jobs/{job_id}/software_engineer")

    assert "https://job-boards.greenhouse.io/acme/jobs/1" not in response.text
    assert "manual" not in response.text.lower()


def test_detail_page_hides_any_approve_form_for_a_hard_failure(conn, client_factory):
    job_id = _seed_job(conn)
    resume_id = _seed_base_resume(conn)
    variant_id = insert_job_resume_variant(
        conn,
        JobResumeVariant(
            job_id=job_id,
            profile="software_engineer",
            base_resume_id=resume_id,
            selection_hash="hard-fail-hash",
            score=40.0,
            coverage=0.5,
            front_load=0.5,
            passed=False,
            created_at="2026-08-17T00:00:00+00:00",
        ),
    )
    insert_rubric_results(
        conn,
        [
            RubricResultRow(
                job_resume_variant_id=variant_id,
                rule_id="R010",
                passed=False,
                detail="margins wrong",
                evaluated_at="2026-08-17T00:00:00+00:00",
            )
        ],
    )
    conn.commit()
    client = client_factory(_FakeClient(_EXTRACT_PAYLOAD))

    response = client.get(f"/jobs/{job_id}/software_engineer")

    assert response.status_code == 200
    assert f'action="/jobs/{job_id}/software_engineer/approve"' not in response.text


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
