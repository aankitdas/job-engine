"""Tests for jobengine.queue.orchestrate (F1). Written before
implementation per hard rule 7's project-wide tests-first convention.

Every test here calls the real ensure_reviewed(), which calls the real
run_ladder() (D3/D4): real render, real PDF conversion, real
score_resume(). There is no lighter-weight mock for that, matching
test_patch.py's own run_ladder integration tests, which use the real
bank (load_bank()) rather than a synthetic one for the same reason. LLM
calls (C3 extraction, D4 rephrase) are mocked via a _FakeClient, same
pattern as test_extract.py/test_patch.py.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from jobengine.db.migrate import connect, init
from jobengine.db.models import (
    BaseResume,
    Job,
    JobAnalysis,
    JobResumeVariant,
    RubricResultRow,
    claim_variant,
    get_job_analysis,
    get_job_resume_variant,
    get_rubric_results,
    insert_base_resume,
    insert_job_resume_variant,
    insert_rubric_results,
    list_claims,
    upsert_job,
    upsert_job_analysis,
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
from jobengine.profiles.config import ProfileConfig
from jobengine.queue import orchestrate
from jobengine.resume.bank import DEFAULT_BANK_PATH, load_bank
from jobengine.resume.render import load_identity


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
    description="Requirements:\n- Go\n",
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
        leadership=LeadershipConfig(exclude_phrases=[]),
        employment_type=EmploymentTypeConfig(
            exclude_ashby_types=[], exclude_title_keywords=[]
        ),
    )


def _profile_config() -> ProfileConfig:
    return ProfileConfig(
        id="software_engineer",
        display_name="Software Engineer",
        section_order=["work_history", "projects", "education", "publications"],
        include_summary=False,
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
    """Serves both the extract stage (C3) and the rephrase stage (D4,
    P3) from one client, since run_ladder() may reach P3 when P0-P2
    can't close a real deficit -- exactly what _EXTRACT_PAYLOAD's real
    Go/Rust gap does. Picks the right payload by inspecting the
    requested schema's field names (kwargs["format"]), same signal
    LocalProvider itself uses to validate the response, rather than
    assuming call order."""

    def __init__(self, extract_payload: dict) -> None:
        self._extract_payload = extract_payload
        # A well-behaved model correctly declining to fabricate
        # cloud/infra content the bank has no coverage for, same shape
        # as D4's own Robinhood precedent in test_patch.py.
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


# Deliberately a real, known gap: the real bank's software_engineer
# content has no Go/Rust coverage (D43's own real gap-frequency table:
# these are the #1 and #2 most frequently uncovered real keywords, 16
# and 12 distinct jobs respectively), so this reliably produces a
# genuine R001 deficit -- a meaningful, non-trivial rubric_results row,
# not a fully-passing no-op. Was ["Go", "Kubernetes"] until D47's real
# bank retag added a genuine Kubernetes tag (b_bantrly_01), which made
# this fixture only half-uncovered and broke the exact-2-keyword
# assertions below; Go/Rust re-confirmed still fully uncovered against
# the retagged bank via measure.missing_keywords(), not reused blindly.
_EXTRACT_PAYLOAD = {
    "required_keywords": ["Go", "Rust"],
    "preferred_keywords": [],
    "tech_stack": ["Go", "Rust"],
}

# No required keywords -> R001 coverage is trivially 1.0 -> a genuinely
# passing variant, for D42's clean-approval-path tests.
_PASSING_EXTRACT_PAYLOAD = {
    "required_keywords": [],
    "preferred_keywords": [],
    "tech_stack": [],
}


def _ctx(conn, local_client) -> orchestrate.QueueContext:
    return orchestrate.QueueContext(
        conn=conn,
        full_bank=load_bank(DEFAULT_BANK_PATH),
        identity=load_identity(),
        profile_configs={"software_engineer": _profile_config()},
        filter_config=_filter_config(),
        llm_config=_llm_config(),
        local_client=local_client,
    )


def test_ensure_reviewed_triggers_extraction_and_persists_variant(conn):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    client = _FakeClient(_EXTRACT_PAYLOAD)

    variant = orchestrate.ensure_reviewed(
        _ctx(conn, client), job_id, "software_engineer"
    )

    assert variant.job_id == job_id
    assert variant.review_status == "pending"
    assert variant.passed is False  # real R001 deficit, Go/Rust uncovered
    assert client.calls  # extraction really called the (fake) model
    assert get_job_analysis(conn, job_id, "software_engineer") is not None


def test_ensure_reviewed_persists_deficits_to_rubric_results(conn):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    client = _FakeClient(_EXTRACT_PAYLOAD)

    variant = orchestrate.ensure_reviewed(
        _ctx(conn, client), job_id, "software_engineer"
    )

    results = get_rubric_results(conn, variant.id)
    assert any(r.rule_id == "R001" and r.passed is False for r in results)


def test_ensure_reviewed_second_call_is_idempotent_and_makes_no_new_calls(conn):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    first_client = _FakeClient(_EXTRACT_PAYLOAD)
    first = orchestrate.ensure_reviewed(
        _ctx(conn, first_client), job_id, "software_engineer"
    )

    second_client = _FakeClient(_EXTRACT_PAYLOAD)
    second = orchestrate.ensure_reviewed(
        _ctx(conn, second_client), job_id, "software_engineer"
    )

    assert second.id == first.id
    assert second_client.calls == []  # zero new extraction or rephrase calls


def test_ensure_reviewed_raises_clear_error_when_no_base_resume_exists(conn):
    job_id = _seed_job(conn)
    client = _FakeClient(_EXTRACT_PAYLOAD)

    with pytest.raises(Exception):  # noqa: B017 -- exact type is an implementation detail
        orchestrate.ensure_reviewed(_ctx(conn, client), job_id, "software_engineer")


def test_ensure_reviewed_raises_clear_error_when_job_does_not_exist(conn):
    _seed_base_resume(conn)
    client = _FakeClient(_EXTRACT_PAYLOAD)

    with pytest.raises(Exception):  # noqa: B017
        orchestrate.ensure_reviewed(_ctx(conn, client), 999999, "software_engineer")


def test_selection_hash_dedup_reuses_rendered_files_across_jobs(conn):
    """Two different jobs whose extraction converges on the same
    required_keywords produce the same deterministic patch-ladder
    selection against the same real bank. The second job must reuse the
    first's already-rendered docx/pdf (spec 08's file-reuse dedup, fixed
    this session after the old DB-level constraint made it impossible),
    not re-render, but must still get its own row."""
    job_id_1 = _seed_job(conn, ats_job_id="1")
    job_id_2 = _seed_job(conn, ats_job_id="2")
    _seed_base_resume(conn)

    variant_1 = orchestrate.ensure_reviewed(
        _ctx(conn, _FakeClient(_EXTRACT_PAYLOAD)), job_id_1, "software_engineer"
    )
    variant_2 = orchestrate.ensure_reviewed(
        _ctx(conn, _FakeClient(_EXTRACT_PAYLOAD)), job_id_2, "software_engineer"
    )

    assert variant_1.id != variant_2.id
    assert variant_1.selection_hash == variant_2.selection_hash
    assert variant_2.docx_path == variant_1.docx_path
    assert variant_2.pdf_path == variant_1.pdf_path


def test_list_queue_returns_pending_entries(conn):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    orchestrate.ensure_reviewed(
        _ctx(conn, _FakeClient(_EXTRACT_PAYLOAD)), job_id, "software_engineer"
    )

    entries = orchestrate.list_queue(conn)
    assert any(e.job_id == job_id for e in entries)


# --- D42: approve() gates on rubric pass/soft-fail/hard-fail state. See
# docs/decisions.md D42 -- real job 3950 queued cleanly despite a real
# R001 hard failure, and orchestrate.approve() never checked variant.
# passed at all. R001-only is a soft, human-overridable deficit (spec
# 08's P4 language, D33); any other hard rule is never overridable.


def test_approve_creates_application_for_a_passing_variant(conn):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    ctx = _ctx(conn, _FakeClient(_PASSING_EXTRACT_PAYLOAD))
    variant = orchestrate.ensure_reviewed(ctx, job_id, "software_engineer")
    assert variant.passed is True  # sanity: this is the clean path

    application_id = orchestrate.approve(ctx, variant)

    application = conn.execute(
        "SELECT status, autonomy_level FROM applications WHERE id = ?",
        (application_id,),
    ).fetchone()
    assert application["status"] == "queued"
    assert application["autonomy_level"] == 0


def test_approve_raises_unacknowledged_soft_failure_without_override(conn):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    ctx = _ctx(conn, _FakeClient(_EXTRACT_PAYLOAD))
    variant = orchestrate.ensure_reviewed(ctx, job_id, "software_engineer")
    assert variant.passed is False  # sanity: real R001-only deficit

    with pytest.raises(orchestrate.UnacknowledgedSoftFailureError):
        orchestrate.approve(ctx, variant)

    application = conn.execute(
        "SELECT 1 FROM applications WHERE resume_variant_id = ?", (variant.id,)
    ).fetchone()
    assert application is None


def test_approve_succeeds_with_override_and_marks_variant_accepted(conn):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    ctx = _ctx(conn, _FakeClient(_EXTRACT_PAYLOAD))
    variant = orchestrate.ensure_reviewed(ctx, job_id, "software_engineer")

    application_id = orchestrate.approve(ctx, variant, override_soft_failure=True)

    application = conn.execute(
        "SELECT status, autonomy_level FROM applications WHERE id = ?",
        (application_id,),
    ).fetchone()
    assert application["status"] == "queued"
    assert application["autonomy_level"] == 0
    reloaded = get_job_resume_variant(conn, job_id, "software_engineer")
    assert reloaded.accepted is True
    assert reloaded.review_status == "approved"


# --- D43 (P4): ensure_reviewed() logs still-missing required keywords to
# gap_ledger after run_ladder() exhausts, unconditional on pass/fail and
# on D42's soft/hard classification -- see docs/decisions.md D43. Never
# touches review_status/accepted (that stays exclusively human-driven via
# D42's approve()).


def test_ensure_reviewed_logs_uncovered_keywords_to_gap_ledger(conn):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    ctx = _ctx(conn, _FakeClient(_EXTRACT_PAYLOAD))

    orchestrate.ensure_reviewed(ctx, job_id, "software_engineer")

    rows = conn.execute(
        "SELECT profile, keyword, job_id FROM gap_ledger ORDER BY keyword"
    ).fetchall()
    assert [dict(r) for r in rows] == [
        {"profile": "software_engineer", "keyword": "Go", "job_id": job_id},
        {"profile": "software_engineer", "keyword": "Rust", "job_id": job_id},
    ]


def test_ensure_reviewed_logs_nothing_when_no_keywords_are_missing(conn):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    ctx = _ctx(conn, _FakeClient(_PASSING_EXTRACT_PAYLOAD))

    orchestrate.ensure_reviewed(ctx, job_id, "software_engineer")

    assert conn.execute("SELECT 1 FROM gap_ledger").fetchone() is None


def test_ensure_reviewed_second_call_does_not_log_gap_ledger_again(conn):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    ctx = _ctx(conn, _FakeClient(_EXTRACT_PAYLOAD))
    orchestrate.ensure_reviewed(ctx, job_id, "software_engineer")

    orchestrate.ensure_reviewed(
        _ctx(conn, _FakeClient(_EXTRACT_PAYLOAD)), job_id, "software_engineer"
    )

    count = conn.execute("SELECT COUNT(*) FROM gap_ledger").fetchone()[0]
    assert count == 2  # Go, Rust -- not 4


def test_ensure_reviewed_does_not_mark_variant_accepted_via_gap_ledger(conn):
    """D43's decision 1: P4 never touches accepted/review_status, even
    on a real R001-only (soft) failure -- that stays exclusively
    human-driven via D42's approve(override_soft_failure=True)."""
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    ctx = _ctx(conn, _FakeClient(_EXTRACT_PAYLOAD))

    variant = orchestrate.ensure_reviewed(ctx, job_id, "software_engineer")

    assert variant.accepted is None
    assert variant.review_status == "pending"


def test_approve_raises_hard_rubric_failure_even_with_override(conn):
    """override_soft_failure never bypasses a hard (non-R001) failure --
    that's the one case with no override path at all."""
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
    variant = get_job_resume_variant(conn, job_id, "software_engineer")
    ctx = _ctx(conn, _FakeClient(_PASSING_EXTRACT_PAYLOAD))

    with pytest.raises(orchestrate.HardRubricFailureError):
        orchestrate.approve(ctx, variant, override_soft_failure=True)

    application = conn.execute(
        "SELECT 1 FROM applications WHERE resume_variant_id = ?", (variant.id,)
    ).fetchone()
    assert application is None


# --- F1-followup: the claim mechanism (db/models.py's variant_claims)
# that closes the real "UNIQUE constraint failed: job_resume_variants.
# job_id, profile" race -- two concurrent ensure_reviewed() calls for
# the same pair must never both run the ladder or both attempt the
# insert. See docs/decisions.md for the full write-up.


def _seed_job_analysis(conn, job_id, profile="software_engineer") -> None:
    """Pre-seeds job_analysis so ensure_reviewed()'s own extraction step
    is a no-op, isolating these tests' assertions to the claim-guarded
    ladder step specifically (not conflating "no new extraction call"
    with "no new ladder call")."""
    upsert_job_analysis(
        conn,
        JobAnalysis(
            job_id=job_id,
            profile=profile,
            required_keywords='["Go", "Rust"]',
            preferred_keywords="[]",
            tech_stack='["Go", "Rust"]',
            jd_quality="good",
            keyword_hash="deadbeef",
            analyzed_at="2026-08-20T00:00:00+00:00",
            model="qwen3.5:9b-q4_K_M",
            cost_usd=0.0,
        ),
    )
    conn.commit()


def test_ensure_reviewed_raises_already_processing_when_claim_is_held(conn):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    _seed_job_analysis(conn, job_id)
    # Freshly claimed relative to real wall-clock time, so it reads as
    # "not stale" against ensure_reviewed()'s own real-time cutoff below.
    real_now = datetime.now(UTC).isoformat()
    claim_variant(conn, job_id, "software_engineer", "web", real_now, real_now)
    client = _FakeClient(_EXTRACT_PAYLOAD)

    with pytest.raises(orchestrate.AlreadyProcessingError):
        orchestrate.ensure_reviewed(_ctx(conn, client), job_id, "software_engineer")

    assert client.calls == []  # the ladder never ran a second time
    assert get_job_resume_variant(conn, job_id, "software_engineer") is None


def test_ensure_reviewed_reclaims_a_stale_claim_and_completes(conn):
    """A claim whose owning process died mid-ladder (crash, Ctrl+C, a
    reload) must self-heal, not permanently block the pair. Seeds a
    claim old enough to be past orchestrate.STALE_CLAIM_SECONDS."""
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    _seed_job_analysis(conn, job_id)
    stale_claimed_at = (
        datetime.now(UTC) - timedelta(seconds=orchestrate.STALE_CLAIM_SECONDS + 60)
    ).isoformat()
    conn.execute(
        "INSERT INTO variant_claims (job_id, profile, claimed_by, claimed_at) "
        "VALUES (?, ?, 'web', ?)",
        (job_id, "software_engineer", stale_claimed_at),
    )
    conn.commit()
    client = _FakeClient(_EXTRACT_PAYLOAD)

    variant = orchestrate.ensure_reviewed(
        _ctx(conn, client), job_id, "software_engineer"
    )

    assert variant.job_id == job_id
    assert client.calls  # the ladder really ran, reclaim succeeded


def test_ensure_reviewed_releases_claim_after_success(conn):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    client = _FakeClient(_EXTRACT_PAYLOAD)

    orchestrate.ensure_reviewed(_ctx(conn, client), job_id, "software_engineer")

    assert list_claims(conn) == set()


def test_ensure_reviewed_releases_claim_even_when_the_ladder_raises(conn, monkeypatch):
    """The finally-block guarantee: a claim must not survive an
    exception raised mid-ladder, or the pair would be stuck "processing"
    until STALE_CLAIM_SECONDS elapses instead of being immediately
    retriable."""
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    _seed_job_analysis(conn, job_id)

    def _boom(**kwargs):
        raise RuntimeError("simulated ladder failure")

    monkeypatch.setattr(orchestrate.patch, "run_ladder", _boom)
    client = _FakeClient(_EXTRACT_PAYLOAD)

    with pytest.raises(RuntimeError, match="simulated ladder failure"):
        orchestrate.ensure_reviewed(_ctx(conn, client), job_id, "software_engineer")

    assert list_claims(conn) == set()
    assert get_job_resume_variant(conn, job_id, "software_engineer") is None


def test_ensure_reviewed_claimed_by_defaults_to_web(conn, monkeypatch):
    job_id = _seed_job(conn)
    _seed_base_resume(conn)
    _seed_job_analysis(conn, job_id)
    seen_claimed_by = []
    real_claim_variant = orchestrate.claim_variant

    def _spy(conn_, job_id_, profile_, claimed_by, *args):
        seen_claimed_by.append(claimed_by)
        return real_claim_variant(conn_, job_id_, profile_, claimed_by, *args)

    monkeypatch.setattr(orchestrate, "claim_variant", _spy)
    client = _FakeClient(_EXTRACT_PAYLOAD)

    orchestrate.ensure_reviewed(_ctx(conn, client), job_id, "software_engineer")

    assert seen_claimed_by == ["web"]
