"""F1's lazy-trigger orchestration: turns a real (job, profile) pair
into a persisted, reviewable job_resume_variant. See the F1 plan
(docs/decisions.md) and specs/00-data-model.md/specs/08-rubric.md for
the schema this writes to.

ensure_reviewed() is idempotent and shared by two callers: a human
opening a (job, profile) pair that has no scored resume yet (the web
app's on-demand fallback), and pipeline/batch.py's scheduled prefetch
stage (F1-followup), which now runs this same function ahead of time for
every candidate pair so most are already rendered by the time a human
gets to them. A second call for an already-rendered pair is a pure read,
zero new model calls, zero new rendering, regardless of which caller
reaches it first.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jobengine.db.models import (
    Application,
    GapLedgerRow,
    JobResumeVariant,
    QueueEntry,
    RubricResultRow,
    claim_variant,
    find_job_resume_variant_by_hash,
    get_job_analysis,
    get_job_by_id,
    get_job_resume_variant,
    get_rubric_results,
    insert_application,
    insert_gap_ledger_entries,
    insert_job_resume_variant,
    insert_rubric_results,
    latest_base_resume,
    list_pending_review_queue,
    release_claim,
    update_review_status,
)
from jobengine.llm.schemas import LLMConfig
from jobengine.pipeline.extract import analyze_job
from jobengine.pipeline.filter import FilterConfig
from jobengine.pipeline.relevance import RelevanceConfig
from jobengine.profiles.config import ProfileConfig
from jobengine.resume.bank import Bank
from jobengine.resume.render import Identity
from jobengine.rubric import measure, patch
from jobengine.rubric.rules import has_unrecoverable_rubric_failure

_VARIANTS_OUT_ROOT = Path("resume/rendered/variants")

# How long a claim (db/models.py's variant_claims) is honored before a new
# claim_variant() call is allowed to reclaim it as abandoned. Generous
# against every real measurement available: the local model's real
# full-prompt latency is ~5.1s/call (D38, live-measured against relevance/
# extraction, the closest real analog to P3's rephrase call), a real PDF
# conversion measured ~0.8s, and pdf.py's own subprocess call is hard-
# capped at 60s. 10 minutes is wide headroom above any realistic ladder
# run (including a cold Ollama start, ~15-22s per C1/D35) while still
# self-healing a genuinely stuck claim -- process crash, Ctrl+C, a reload
# mid-call -- well within a single scheduled batch window rather than
# hours later.
STALE_CLAIM_SECONDS = 600


@dataclass
class QueueContext:
    """Everything ensure_reviewed() needs, built once (app startup or
    once per test), not re-loaded per call."""

    conn: sqlite3.Connection
    full_bank: Bank
    identity: Identity
    profile_configs: dict[str, ProfileConfig]
    filter_config: FilterConfig
    llm_config: LLMConfig
    relevance_config: RelevanceConfig = field(default_factory=RelevanceConfig)
    local_client: Any | None = None


class NoBaseResumeError(RuntimeError):
    """Raised when ensure_reviewed() is asked to score a profile that
    has no base_resumes row yet (E2 must run first)."""


class JobNotFoundError(RuntimeError):
    """Raised when ensure_reviewed() is given a job_id that doesn't
    exist in jobs."""


class HardRubricFailureError(RuntimeError):
    """Raised by approve() when the variant fails a hard rule other than
    R001 -- a genuine document defect (D33), never overridable. See D42
    in docs/decisions.md."""


class UnacknowledgedSoftFailureError(RuntimeError):
    """Raised by approve() when the variant fails R001 only (a soft,
    human-overridable deficit per spec 08's P4 language) and
    override_soft_failure was not passed. See D42 in docs/decisions.md."""


class AlreadyProcessingError(RuntimeError):
    """Raised by ensure_reviewed() when another caller (a concurrent web
    request, or pipeline/batch.py's prefetch stage) already holds an
    active, non-stale claim on this (job_id, profile) pair. Not an
    error condition to retry-loop past silently: the caller decides what
    "someone else is already rendering this" means for it (the web route
    shows a wait/retry page; pipeline/batch.py just skips the pair for
    this run)."""


def _selection_hash(bank: Bank) -> str:
    bullet_ids = [b.id for role in bank.roles for b in role.bullets]
    return hashlib.sha256(json.dumps(bullet_ids).encode()).hexdigest()


def ensure_reviewed(
    ctx: QueueContext, job_id: int, profile: str, *, claimed_by: str = "web"
) -> JobResumeVariant:
    """Idempotent lazy-trigger entry point. A second call for the same
    (job_id, profile) does zero extraction/patch work and just returns
    the already-persisted row, regardless of its review_status.

    claimed_by identifies who's asking (the web app's on-demand fallback,
    or pipeline/batch.py's prefetch stage) for the variant_claims row's
    own debug-only column -- it plays no role in the claim/reclaim logic
    itself. Raises AlreadyProcessingError if another caller already holds
    an active claim on this pair; never silently blocks or retries."""
    job = get_job_by_id(ctx.conn, job_id)
    if job is None:
        raise JobNotFoundError(f"no job with id {job_id}")

    analysis = get_job_analysis(ctx.conn, job_id, profile)
    if analysis is None:
        asyncio.run(
            analyze_job(
                ctx.conn,
                job,
                ctx.filter_config,
                ctx.llm_config,
                local_client=ctx.local_client,
            )
        )
        analysis = get_job_analysis(ctx.conn, job_id, profile)

    existing = get_job_resume_variant(ctx.conn, job_id, profile)
    if existing is not None:
        return existing

    base_resume = latest_base_resume(ctx.conn, profile)
    if base_resume is None or base_resume.id is None:
        raise NoBaseResumeError(
            f"no base_resumes row exists yet for profile {profile!r}; "
            "run E2 (persist_base_resume) for this profile first"
        )

    # The race this closes: two callers (a double-click, a reload mid-
    # render, batch and a human hitting the same pair) both see
    # existing is None above and both reach here. Only one INSERT into
    # variant_claims (db/models.py's claim_variant()) can win; the loser
    # raises AlreadyProcessingError instead of running the ladder a
    # second time and racing the other on the job_resume_variants insert
    # below, which used to crash with a real UNIQUE constraint failure.
    now = datetime.now(UTC)
    now_iso = now.isoformat()
    stale_cutoff = (now - timedelta(seconds=STALE_CLAIM_SECONDS)).isoformat()
    if not claim_variant(ctx.conn, job_id, profile, claimed_by, now_iso, stale_cutoff):
        raise AlreadyProcessingError(
            f"(job_id={job_id}, profile={profile!r}) is already being processed"
        )

    try:
        # Re-check after claiming: the caller that held the claim before
        # us may have finished (inserted the variant, released the
        # claim) in the gap between our first check above and winning
        # the claim just now. Without this, we'd still run the whole
        # ladder for nothing and hit the same UNIQUE constraint on the
        # insert below.
        existing = get_job_resume_variant(ctx.conn, job_id, profile)
        if existing is not None:
            return existing

        required = (
            json.loads(analysis.required_keywords) if analysis.required_keywords else []
        )
        preferred = (
            json.loads(analysis.preferred_keywords)
            if analysis.preferred_keywords
            else []
        )

        out_dir = _VARIANTS_OUT_ROOT / str(job_id) / profile
        result = patch.run_ladder(
            full_bank=ctx.full_bank,
            profile=profile,
            identity=ctx.identity,
            section_order=ctx.profile_configs[profile].section_order,
            out_dir=out_dir,
            required_keywords=required,
            preferred_keywords=preferred,
            llm_config=ctx.llm_config,
            local_client=ctx.local_client,
        )

        selection_hash = _selection_hash(result.bank)
        reused = find_job_resume_variant_by_hash(
            ctx.conn, base_resume.id, selection_hash
        )
        docx_path = reused.docx_path if reused else str(result.docx_path)
        pdf_path = reused.pdf_path if reused else str(result.pdf_path)

        bullet_ids = [b.id for role in result.bank.roles for b in role.bullets]
        created_at = datetime.now(UTC).isoformat()

        variant_id = insert_job_resume_variant(
            ctx.conn,
            JobResumeVariant(
                job_id=job_id,
                profile=profile,
                base_resume_id=base_resume.id,
                patch_tiers_applied=json.dumps(result.tiers_applied),
                bullet_ids=json.dumps(bullet_ids),
                selection_hash=selection_hash,
                docx_path=docx_path,
                pdf_path=pdf_path,
                score=result.rubric_result.score,
                coverage=result.rubric_result.measurements.get("coverage"),
                front_load=result.rubric_result.measurements.get("front_load"),
                passed=result.rubric_result.passed,
                review_status="pending",
                created_at=created_at,
            ),
        )

        if result.rubric_result.deficits:
            insert_rubric_results(
                ctx.conn,
                [
                    RubricResultRow(
                        job_resume_variant_id=variant_id,
                        rule_id=deficit.rule,
                        passed=False,
                        measurement=None,
                        detail=deficit.detail,
                        evaluated_at=created_at,
                    )
                    for deficit in result.rubric_result.deficits
                ],
            )

        # D43 (P4): log every still-missing required keyword, unconditional
        # on result.rubric_result.passed (a keyword can be individually
        # missing even when overall coverage clears R001's 0.70 bar) and on
        # D42's soft/hard classification (that split governs whether a human
        # can approve the variant, not whether a gap gets recorded). Never
        # touches review_status/accepted -- see docs/decisions.md D43.
        still_missing = measure.missing_keywords(result.bank, required)
        if still_missing:
            insert_gap_ledger_entries(
                ctx.conn,
                [
                    GapLedgerRow(
                        profile=profile,
                        keyword=keyword,
                        job_id=job_id,
                        first_logged_at=created_at,
                    )
                    for keyword in still_missing
                ],
            )

        ctx.conn.commit()
    finally:
        # Always released, success or failure (including an exception
        # raised mid-ladder), so a crash never leaves this pair stuck
        # "processing" for longer than it takes the next caller to hit
        # STALE_CLAIM_SECONDS -- see that constant's own comment above.
        release_claim(ctx.conn, job_id, profile)

    return get_job_resume_variant(ctx.conn, job_id, profile)


def approve(
    ctx: QueueContext, variant: JobResumeVariant, *, override_soft_failure: bool = False
) -> int:
    """Human review decision: approved. Creates the applications row
    (deliberately not created earlier, at pending_review time -- see
    docs/decisions.md's F1 entry on why is_already_applied() requires
    this). autonomy_level defaults to 0 (most manual); Phase G's G1
    computes a real ceiling but nothing here consumes it yet, a
    deliberately separate decision -- see D42 in docs/decisions.md.

    D42: a variant that fails the rubric is not silently approvable.
    R001-only ("soft", spec 08's P4 language) requires the caller to
    explicitly pass override_soft_failure=True, which also marks the
    variant accepted=True. Any other hard rule (R003/.../R013, "hard")
    is never overridable -- override_soft_failure does not bypass it."""
    if not variant.passed:
        hard_failures = [r.rule_id for r in get_rubric_results(ctx.conn, variant.id)]
        if has_unrecoverable_rubric_failure(hard_failures):
            raise HardRubricFailureError(
                f"variant {variant.id} fails a non-R001 hard rule "
                f"({hard_failures}); cannot be approved as-is"
            )
        if not override_soft_failure:
            raise UnacknowledgedSoftFailureError(
                f"variant {variant.id} fails R001 (coverage) only; pass "
                "override_soft_failure=True to approve anyway"
            )

    now = datetime.now(UTC).isoformat()
    accepted = True if not variant.passed else None
    update_review_status(ctx.conn, variant.id, "approved", now, accepted=accepted)
    application_id = insert_application(
        ctx.conn,
        Application(
            job_id=variant.job_id,
            resume_variant_id=variant.id,
            autonomy_level=0,
            status="queued",
        ),
    )
    ctx.conn.commit()
    return application_id


def reject(ctx: QueueContext, variant: JobResumeVariant) -> None:
    now = datetime.now(UTC).isoformat()
    update_review_status(ctx.conn, variant.id, "rejected", now)
    ctx.conn.commit()


def list_queue(conn: sqlite3.Connection) -> list[QueueEntry]:
    return list_pending_review_queue(conn)
