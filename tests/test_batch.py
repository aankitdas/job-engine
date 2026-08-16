"""Tests for src/jobengine/pipeline/batch.py, the daily orchestrator that
closes the sync-to-review gap by running C4 (relevance) then C3
(extraction) for jobs newly synced since the last run. Written before
implementation per CLAUDE.md hard rule 7. See D38 in docs/decisions.md.

LLM calls are mocked via a stage-aware _FakeClient, same pattern as
test_queue_orchestrate.py's own (picks a payload by inspecting the
requested schema's field names in kwargs["format"], not by call order),
since a single batch run can reach both the relevance and extract
schemas.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from jobengine.db.migrate import connect, init
from jobengine.db.models import (
    Job,
    RelevanceScore,
    get_job_analysis,
    get_relevance_score,
    list_unscored_open_jobs,
    upsert_job,
    upsert_relevance_score,
)
from jobengine.llm.schemas import (
    ApiConfig,
    FallbackConfig,
    LLMConfig,
    LocalConfig,
    RoutingConfig,
)
from jobengine.pipeline import batch
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
from jobengine.resume.bank import DEFAULT_BANK_PATH, load_bank


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "jobengine.db"
    connection = connect(db_path)
    init(connection)
    yield connection
    connection.close()


def _seed_company(conn, *, slug="acme", ats="greenhouse"):
    conn.execute(
        "INSERT OR IGNORE INTO companies (slug, ats, name, status, source, first_seen_at) "
        "VALUES (?, ?, ?, 'active', 'seed', '2026-01-01T00:00:00+00:00')",
        (slug, ats, slug.title()),
    )
    conn.commit()


def _seed_job(
    conn,
    *,
    ats_job_id="1",
    title="Software Engineer",
    description="Requirements:\n- Python\n- FastAPI\n",
    first_seen_at="2026-08-12T00:00:00+00:00",
    location_raw="San Francisco, CA",
    closed_at=None,
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
            first_seen_at=first_seen_at,
            last_seen_at=first_seen_at,
            closed_at=closed_at,
        ),
    )


def _filter_config(**profile_overrides) -> FilterConfig:
    profiles = profile_overrides or {
        "software_engineer": ProfileFilterConfig(
            title_aliases=["software engineer", "engineer"]
        ),
        "ai_ml_engineer": ProfileFilterConfig(title_aliases=["ai engineer"]),
    }
    return FilterConfig(
        profiles=profiles,
        location=LocationConfig(
            remote_synonyms=["remote"], us_major_city_names=["san francisco"]
        ),
        seniority=SeniorityConfig(exclude_title_keywords=["manager", "director"]),
        citizenship_clearance=CitizenshipClearanceConfig(exclude_phrases=[]),
        leadership=LeadershipConfig(exclude_phrases=[]),
        employment_type=EmploymentTypeConfig(
            exclude_ashby_types=[], exclude_title_keywords=[]
        ),
    )


def _relevance_config(**overrides) -> RelevanceConfig:
    fields = {
        "disqualifier_blocklist": ["security clearance", "citizenship"],
        "freshness_window_days": None,
        "min_relevance_score": 20,
    }
    fields.update(overrides)
    return RelevanceConfig(**fields)


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


def _bank():
    return load_bank(DEFAULT_BANK_PATH)


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)
        self.prompt_eval_count = 10
        self.eval_count = 5


class _FakeClient:
    """Serves both the relevance schema (C4) and the extract schema (C3)
    from one client, keyed on the requested schema's field names
    (kwargs["format"]), same signal LocalProvider itself uses -- not
    call order, since a batch run interleaves both stages."""

    def __init__(self, relevance_payload: dict, extract_payload: dict) -> None:
        self._relevance_payload = relevance_payload
        self._extract_payload = extract_payload
        self.calls: list[dict[str, Any]] = []

    async def chat(self, **kwargs: Any):
        self.calls.append(kwargs)
        schema_props = kwargs.get("format", {}).get("properties", {})
        if "relevance" in schema_props:
            content = json.dumps(self._relevance_payload)
        else:
            content = json.dumps(self._extract_payload)
        return _FakeResponse(content)

    def relevance_call_count(self) -> int:
        return sum(
            1
            for c in self.calls
            if "relevance" in c.get("format", {}).get("properties", {})
        )

    def extract_call_count(self) -> int:
        return sum(
            1
            for c in self.calls
            if "required_keywords" in c.get("format", {}).get("properties", {})
        )


_HIGH_RELEVANCE_PAYLOAD = {
    "relevance": 80,
    "seniority_match": "match",
    "keyword_hits": ["Python"],
    "disqualifiers": [],
    "one_line": "Strong fit.",
}

_LOW_RELEVANCE_PAYLOAD = {
    "relevance": 5,
    "seniority_match": "match",
    "keyword_hits": [],
    "disqualifiers": [],
    "one_line": "Weak fit.",
}

_EXTRACT_PAYLOAD = {
    "required_keywords": ["Python", "FastAPI"],
    "preferred_keywords": [],
    "tech_stack": ["Python", "FastAPI"],
}


# ---------------------------------------------------------------------------
# list_unscored_open_jobs: the incremental candidate query (db/models.py)
# ---------------------------------------------------------------------------


def test_list_unscored_open_jobs_excludes_job_with_existing_relevance_row(conn):
    job_id = _seed_job(conn)
    upsert_relevance_score(
        conn,
        RelevanceScore(
            job_id=job_id,
            profile="software_engineer",
            score=50,
            selected=0,
            scored_at="2026-08-12T00:00:00+00:00",
        ),
    )
    conn.commit()

    candidates = list_unscored_open_jobs(conn, window_days=7)
    assert job_id not in [j.id for j in candidates]


def test_list_unscored_open_jobs_excludes_closed_job(conn):
    job_id = _seed_job(conn, closed_at="2026-08-12T00:00:00+00:00")
    candidates = list_unscored_open_jobs(conn, window_days=7)
    assert job_id not in [j.id for j in candidates]


def test_list_unscored_open_jobs_excludes_job_outside_window(conn):
    job_id = _seed_job(conn, first_seen_at="2026-01-01T00:00:00+00:00")
    candidates = list_unscored_open_jobs(conn, window_days=7)
    assert job_id not in [j.id for j in candidates]


def test_list_unscored_open_jobs_includes_open_unscored_job_in_window(conn):
    job_id = _seed_job(conn)
    candidates = list_unscored_open_jobs(conn, window_days=7)
    assert job_id in [j.id for j in candidates]


# ---------------------------------------------------------------------------
# run_daily_batch
# ---------------------------------------------------------------------------


def test_run_daily_batch_scores_relevance_for_a_b3_survivor(conn):
    job_id = _seed_job(conn)
    client = _FakeClient(_HIGH_RELEVANCE_PAYLOAD, _EXTRACT_PAYLOAD)

    batch.run_daily_batch(
        conn,
        _filter_config(),
        _relevance_config(),
        _llm_config(),
        _bank(),
        local_client=client,
    )

    score = get_relevance_score(conn, job_id, "software_engineer")
    assert score is not None
    assert score.score == 80


def test_run_daily_batch_skips_llm_entirely_for_a_job_failing_b3_filters(conn):
    job_id = _seed_job(conn, location_raw="Berlin, Germany")
    client = _FakeClient(_HIGH_RELEVANCE_PAYLOAD, _EXTRACT_PAYLOAD)

    result = batch.run_daily_batch(
        conn,
        _filter_config(),
        _relevance_config(),
        _llm_config(),
        _bank(),
        local_client=client,
    )

    assert get_relevance_score(conn, job_id, "software_engineer") is None
    assert client.calls == []
    assert result.relevance_scored_pairs == 0


def test_run_daily_batch_runs_extraction_only_for_floor_clearing_jobs(conn):
    high_job_id = _seed_job(conn, ats_job_id="1")
    low_job_id = _seed_job(conn, ats_job_id="2")

    class _SplitClient(_FakeClient):
        async def chat(self, **kwargs: Any):
            self.calls.append(kwargs)
            schema_props = kwargs.get("format", {}).get("properties", {})
            if "relevance" in schema_props:
                # First relevance call scores the high job, second the low job.
                payload = (
                    self._relevance_payload
                    if self.relevance_call_count() == 1
                    else self._low_payload
                )
                return _FakeResponse(json.dumps(payload))
            return _FakeResponse(json.dumps(self._extract_payload))

    client = _SplitClient(_HIGH_RELEVANCE_PAYLOAD, _EXTRACT_PAYLOAD)
    client._low_payload = _LOW_RELEVANCE_PAYLOAD

    result = batch.run_daily_batch(
        conn,
        _filter_config(),
        _relevance_config(min_relevance_score=20),
        _llm_config(),
        _bank(),
        local_client=client,
    )

    assert result.floor_clearing_jobs == 1
    assert get_job_analysis(conn, high_job_id, "software_engineer") is not None
    assert get_job_analysis(conn, low_job_id, "software_engineer") is None


def test_run_daily_batch_extraction_is_one_call_per_job_not_per_profile(conn):
    """A job matching two profiles gets two relevance calls (one per
    profile, relevance genuinely differs per profile) but only one
    extraction call (extraction is job-level, fanned out to every
    matched profile's job_analysis row after a single call)."""
    job_id = _seed_job(conn, title="Software Engineer / AI Engineer")
    filter_config = _filter_config(
        software_engineer=ProfileFilterConfig(title_aliases=["software engineer"]),
        ai_ml_engineer=ProfileFilterConfig(title_aliases=["ai engineer"]),
    )
    client = _FakeClient(_HIGH_RELEVANCE_PAYLOAD, _EXTRACT_PAYLOAD)

    result = batch.run_daily_batch(
        conn,
        filter_config,
        _relevance_config(),
        _llm_config(),
        _bank(),
        local_client=client,
    )

    assert result.relevance_scored_pairs == 2
    assert client.relevance_call_count() == 2
    assert client.extract_call_count() == 1
    assert get_job_analysis(conn, job_id, "software_engineer") is not None
    assert get_job_analysis(conn, job_id, "ai_ml_engineer") is not None


def test_run_daily_batch_does_not_rescore_an_already_scored_job(conn):
    """The explicit incremental-safety guarantee this whole orchestrator
    depends on: a job already scored by a prior run (or a manual click
    through F1) must not be re-sent to the LLM by a later scheduled
    run, however large the open-jobs backlog grows."""
    job_id = _seed_job(conn)
    upsert_relevance_score(
        conn,
        RelevanceScore(
            job_id=job_id,
            profile="software_engineer",
            score=42,
            selected=0,
            scored_at="2026-08-12T00:00:00+00:00",
        ),
    )
    conn.commit()
    client = _FakeClient(_HIGH_RELEVANCE_PAYLOAD, _EXTRACT_PAYLOAD)

    result = batch.run_daily_batch(
        conn,
        _filter_config(),
        _relevance_config(),
        _llm_config(),
        _bank(),
        local_client=client,
    )

    assert client.calls == []
    assert result.candidate_jobs == 0
    score = get_relevance_score(conn, job_id, "software_engineer")
    assert score.score == 42  # untouched, not overwritten by a re-score


def test_run_daily_batch_does_not_reextract_a_job_with_existing_job_analysis(conn):
    """Same incremental guarantee as relevance, for extraction: a job
    already analyzed (e.g. via F1's lazy per-click trigger reaching it
    before the batch ever ran) is not re-sent through analyze_job()."""
    job_id = _seed_job(conn)

    class _SplitClient(_FakeClient):
        async def chat(self, **kwargs: Any):
            self.calls.append(kwargs)
            schema_props = kwargs.get("format", {}).get("properties", {})
            if "relevance" in schema_props:
                return _FakeResponse(json.dumps(self._relevance_payload))
            raise AssertionError("extract_keywords should not be called")

    from jobengine.db.models import JobAnalysis, upsert_job_analysis

    upsert_job_analysis(
        conn,
        JobAnalysis(
            job_id=job_id,
            profile="software_engineer",
            required_keywords="[]",
            preferred_keywords="[]",
            tech_stack="[]",
            jd_quality="good",
            keyword_hash="deadbeef",
            analyzed_at="2026-08-12T00:00:00+00:00",
            model="qwen3.5:9b-q4_K_M",
            cost_usd=0.0,
        ),
    )
    conn.commit()

    client = _SplitClient(_HIGH_RELEVANCE_PAYLOAD, _EXTRACT_PAYLOAD)
    result = batch.run_daily_batch(
        conn,
        _filter_config(),
        _relevance_config(),
        _llm_config(),
        _bank(),
        local_client=client,
    )

    assert result.extraction_scored_jobs == 0


def test_run_daily_batch_records_a_runs_row(conn):
    _seed_job(conn)
    client = _FakeClient(_HIGH_RELEVANCE_PAYLOAD, _EXTRACT_PAYLOAD)

    batch.run_daily_batch(
        conn,
        _filter_config(),
        _relevance_config(),
        _llm_config(),
        _bank(),
        local_client=client,
    )

    row = conn.execute(
        "SELECT * FROM runs WHERE stage = 'daily_batch' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    counts = json.loads(row["counts"])
    assert counts["candidate_jobs"] == 1
    assert counts["relevance_scored_pairs"] == 1
    assert counts["floor_clearing_jobs"] == 1
    assert counts["extraction_scored_jobs"] == 1


# ---------------------------------------------------------------------------
# WINDOW_DAYS: single source of truth shared with web/app.py
# ---------------------------------------------------------------------------


def test_web_app_reuses_batchs_window_days_constant():
    from jobengine.web import app

    assert app._LIST_WINDOW_DAYS == batch.WINDOW_DAYS
