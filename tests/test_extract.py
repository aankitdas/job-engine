"""Tests for src/jobengine/pipeline/extract.py (C3). Written before
implementation per CLAUDE.md hard rule 7. See specs/00-data-model.md's
job_analysis/keyword_corpus tables and specs/07-model-eval.md's Task 2.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from jobengine.db.migrate import connect, init
from jobengine.db.models import Job, upsert_job
from jobengine.llm.schemas import (
    ApiConfig,
    FallbackConfig,
    LLMConfig,
    LocalConfig,
    RoutingConfig,
)
from jobengine.pipeline.extract import (
    ExtractionSchema,
    analyze_job,
    extract_keywords,
    is_good_quality_jd,
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


def _run(coro):
    return asyncio.run(coro)


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
    conn, *, ats_job_id="1", title="Software Engineer", description="Do the work."
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
            raw_json="{}",
            first_seen_at="2026-08-02T00:00:00+00:00",
            last_seen_at="2026-08-02T00:00:00+00:00",
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


def _single_profile_config(
    alias: str = "engineer", profile: str = "software_engineer"
) -> FilterConfig:
    return FilterConfig(
        profiles={profile: ProfileFilterConfig(title_aliases=[alias])},
        location=LocationConfig(remote_synonyms=[]),
        seniority=SeniorityConfig(exclude_title_keywords=[]),
        citizenship_clearance=CitizenshipClearanceConfig(exclude_phrases=[]),
        leadership=LeadershipConfig(exclude_phrases=[]),
        employment_type=EmploymentTypeConfig(
            exclude_ashby_types=[], exclude_title_keywords=[]
        ),
    )


def _two_profile_config() -> FilterConfig:
    return FilterConfig(
        profiles={
            "ai_ml_engineer": ProfileFilterConfig(title_aliases=["engineer"]),
            "software_engineer": ProfileFilterConfig(title_aliases=["engineer"]),
        },
        location=LocationConfig(remote_synonyms=[]),
        seniority=SeniorityConfig(exclude_title_keywords=[]),
        citizenship_clearance=CitizenshipClearanceConfig(exclude_phrases=[]),
        leadership=LeadershipConfig(exclude_phrases=[]),
        employment_type=EmploymentTypeConfig(
            exclude_ashby_types=[], exclude_title_keywords=[]
        ),
    )


def _no_match_config() -> FilterConfig:
    return FilterConfig(
        profiles={"data_scientist": ProfileFilterConfig(title_aliases=["scientist"])},
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
    def __init__(self, payload: dict) -> None:
        self._content = json.dumps(payload)
        self.calls: list[dict[str, Any]] = []

    async def chat(self, **kwargs: Any):
        self.calls.append(kwargs)
        return _FakeResponse(self._content)


_PAYLOAD = {
    "required_keywords": ["Python", "Kubernetes"],
    "preferred_keywords": ["Go"],
    "tech_stack": ["Python", "Kubernetes", "Docker"],
}


# ---------------------------------------------------------------------------
# is_good_quality_jd: deterministic, no LLM involved
# ---------------------------------------------------------------------------


def test_good_quality_jd_with_requirements_section():
    text = "About us...\n\nRequirements:\n- 5 years Python\n- Kubernetes"
    assert is_good_quality_jd(text) is True


def test_good_quality_jd_with_qualifications_heading():
    text = "What you'll do...\n\nQualifications\n- Strong CS fundamentals"
    assert is_good_quality_jd(text) is True


def test_bad_quality_jd_prose_only():
    text = (
        "We are a fast-growing startup looking for passionate people who love to build."
    )
    assert is_good_quality_jd(text) is False


def test_bad_quality_jd_empty_description():
    assert is_good_quality_jd("") is False
    assert is_good_quality_jd(None) is False


# ---------------------------------------------------------------------------
# extract_keywords: reuses the router, think=False, no ad-hoc ollama client
# ---------------------------------------------------------------------------


def test_extract_module_never_imports_ollama_directly():
    source = Path("src/jobengine/pipeline/extract.py").read_text()
    assert "import ollama" not in source
    assert "ollama.Client" not in source
    assert "ollama.AsyncClient" not in source


def test_extract_keywords_sets_think_false():
    client = _FakeClient(_PAYLOAD)
    _run(extract_keywords("some JD text", _llm_config(), local_client=client))

    assert len(client.calls) == 1
    assert client.calls[0]["think"] is False


def test_extract_keywords_passes_constrained_schema():
    client = _FakeClient(_PAYLOAD)
    _run(extract_keywords("some JD text", _llm_config(), local_client=client))

    assert client.calls[0]["format"] == ExtractionSchema.model_json_schema()


def test_extract_keywords_returns_parsed_output():
    client = _FakeClient(_PAYLOAD)
    result = _run(extract_keywords("some JD text", _llm_config(), local_client=client))

    assert result.output == _PAYLOAD
    assert result.cost_usd == 0.0


# ---------------------------------------------------------------------------
# analyze_job: profile fan-out, persistence, corpus accumulation
# ---------------------------------------------------------------------------


def test_analyze_job_with_no_matched_profile_skips_the_llm_call_entirely(conn):
    job_id = _seed_job(conn, title="Corporate Recruiter")
    job = Job(id=job_id, **{**_job_kwargs(), "title": "Corporate Recruiter"})
    client = _FakeClient(_PAYLOAD)

    row_ids = _run(
        analyze_job(conn, job, _no_match_config(), _llm_config(), local_client=client)
    )

    assert row_ids == []
    assert client.calls == []


def test_analyze_job_writes_one_job_analysis_row_per_matched_profile(conn):
    job_id = _seed_job(conn)
    job = Job(id=job_id, **_job_kwargs())
    client = _FakeClient(_PAYLOAD)

    row_ids = _run(
        analyze_job(
            conn, job, _two_profile_config(), _llm_config(), local_client=client
        )
    )

    assert len(client.calls) == 1, "one LLM call regardless of matched-profile count"
    assert len(row_ids) == 2
    rows = conn.execute(
        "SELECT profile, required_keywords, keyword_hash FROM job_analysis WHERE job_id = ? "
        "ORDER BY profile",
        (job_id,),
    ).fetchall()
    assert [r["profile"] for r in rows] == ["ai_ml_engineer", "software_engineer"]
    assert all(
        json.loads(r["required_keywords"]) == _PAYLOAD["required_keywords"]
        for r in rows
    )
    assert rows[0]["keyword_hash"] == rows[1]["keyword_hash"]


def test_get_job_analysis_reads_back_a_written_row(conn):
    from jobengine.db.models import get_job_analysis

    job_id = _seed_job(conn)
    job = Job(id=job_id, **_job_kwargs())
    client = _FakeClient(_PAYLOAD)
    _run(
        analyze_job(
            conn, job, _two_profile_config(), _llm_config(), local_client=client
        )
    )

    analysis = get_job_analysis(conn, job_id, "ai_ml_engineer")
    assert analysis is not None
    assert json.loads(analysis.required_keywords) == _PAYLOAD["required_keywords"]
    assert get_job_analysis(conn, job_id, "data_scientist") is None


def test_analyze_job_rerun_upserts_instead_of_duplicating(conn):
    job_id = _seed_job(conn)
    job = Job(id=job_id, **_job_kwargs())
    client = _FakeClient(_PAYLOAD)

    first_ids = _run(
        analyze_job(
            conn, job, _single_profile_config(), _llm_config(), local_client=client
        )
    )
    second_ids = _run(
        analyze_job(
            conn, job, _single_profile_config(), _llm_config(), local_client=client
        )
    )

    assert first_ids == second_ids
    count = conn.execute(
        "SELECT COUNT(*) FROM job_analysis WHERE job_id = ?", (job_id,)
    ).fetchone()[0]
    assert count == 1


def test_analyze_job_feeds_required_keywords_into_keyword_corpus(conn):
    job_id = _seed_job(conn)
    job = Job(id=job_id, **_job_kwargs())
    client = _FakeClient(_PAYLOAD)

    _run(
        analyze_job(
            conn, job, _single_profile_config(), _llm_config(), local_client=client
        )
    )

    rows = {
        r["keyword"]: r["occurrences"]
        for r in conn.execute(
            "SELECT keyword, occurrences FROM keyword_corpus WHERE profile = 'software_engineer'"
        ).fetchall()
    }
    assert rows == {"Python": 1, "Kubernetes": 1}
    # preferred_keywords/tech_stack must not leak into the corpus.
    assert "Go" not in rows
    assert "Docker" not in rows


def test_keyword_corpus_occurrences_accumulate_across_jobs_and_last_seen_advances(conn):
    job_id_1 = _seed_job(conn, ats_job_id="1")
    job_id_2 = _seed_job(conn, ats_job_id="2")
    job_1 = Job(id=job_id_1, **_job_kwargs())
    job_2 = Job(id=job_id_2, **{**_job_kwargs(), "ats_job_id": "2"})

    _run(
        analyze_job(
            conn,
            job_1,
            _single_profile_config(),
            _llm_config(),
            local_client=_FakeClient(_PAYLOAD),
        )
    )
    _run(
        analyze_job(
            conn,
            job_2,
            _single_profile_config(),
            _llm_config(),
            local_client=_FakeClient(_PAYLOAD),
        )
    )

    row = conn.execute(
        "SELECT occurrences, first_seen_at, last_seen_at FROM keyword_corpus "
        "WHERE profile = 'software_engineer' AND keyword = 'Python'"
    ).fetchone()
    assert row["occurrences"] == 2
    assert row["first_seen_at"] <= row["last_seen_at"]


def _job_kwargs() -> dict:
    return {
        "ats": "greenhouse",
        "company_slug": "acme",
        "ats_job_id": "1",
        "title": "Software Engineer",
        "description": "Requirements:\n- Python\n- Kubernetes",
        "raw_json": "{}",
        "first_seen_at": "2026-08-02T00:00:00+00:00",
        "last_seen_at": "2026-08-02T00:00:00+00:00",
    }
