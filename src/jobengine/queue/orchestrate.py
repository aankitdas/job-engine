"""F1's lazy-trigger orchestration: turns a real (job, profile) pair
into a persisted, reviewable job_resume_variant. See the F1 plan
(docs/decisions.md) and specs/00-data-model.md/specs/08-rubric.md for
the schema this writes to.

No batch/cron orchestrator here by design (confirmed via AskUserQuestion
during F1 planning): the first reviewer to open a (job, profile) pair
that has no scored resume yet is what triggers extraction (C3) and the
patch ladder (D3/D4), right then, live. A second visit to the same pair
is a pure read, zero new model calls, zero new rendering.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jobengine.db.models import (
    Application,
    JobResumeVariant,
    QueueEntry,
    RubricResultRow,
    find_job_resume_variant_by_hash,
    get_job_analysis,
    get_job_by_id,
    get_job_resume_variant,
    get_rubric_results,
    insert_application,
    insert_job_resume_variant,
    insert_rubric_results,
    latest_base_resume,
    list_pending_review_queue,
    update_review_status,
)
from jobengine.llm.schemas import LLMConfig
from jobengine.pipeline.extract import analyze_job
from jobengine.pipeline.filter import FilterConfig
from jobengine.pipeline.relevance import RelevanceConfig
from jobengine.profiles.config import ProfileConfig
from jobengine.resume.bank import Bank
from jobengine.resume.render import Identity
from jobengine.rubric import patch
from jobengine.rubric.rules import has_unrecoverable_rubric_failure

_VARIANTS_OUT_ROOT = Path("resume/rendered/variants")


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


def _selection_hash(bank: Bank) -> str:
    bullet_ids = [b.id for role in bank.roles for b in role.bullets]
    return hashlib.sha256(json.dumps(bullet_ids).encode()).hexdigest()


def ensure_reviewed(ctx: QueueContext, job_id: int, profile: str) -> JobResumeVariant:
    """Idempotent lazy-trigger entry point. A second call for the same
    (job_id, profile) does zero extraction/patch work and just returns
    the already-persisted row, regardless of its review_status."""
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

    required = (
        json.loads(analysis.required_keywords) if analysis.required_keywords else []
    )
    preferred = (
        json.loads(analysis.preferred_keywords) if analysis.preferred_keywords else []
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
    reused = find_job_resume_variant_by_hash(ctx.conn, base_resume.id, selection_hash)
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

    ctx.conn.commit()
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
