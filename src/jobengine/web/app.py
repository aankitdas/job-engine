"""F1's FastAPI review queue. `uv run uvicorn jobengine.web.app:app
--reload` (CLAUDE.md's documented dev command). Points at the real
data/jobengine.db by default; set JOBENGINE_DB_PATH to point at a
scratch copy instead for manual testing, per hard rule 13's spirit.

Reviewing means seeing the already-patched candidate (real rendered
docx/pdf from run_ladder()) and approving or rejecting it -- not editing
bullet text in a browser. That's deliberately out of scope: a web-form
edit path can't enforce CLAUDE.md hard rule 12's traceability guarantee
the way patch.py's validate_rewrite() does.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from jobengine.db.migrate import DEFAULT_DB_PATH, connect
from jobengine.db.models import (
    get_job_analysis,
    get_job_by_id,
    get_job_resume_variant,
    get_rubric_results,
    list_applications,
    list_claims,
)
from jobengine.llm.router import load_config as load_llm_config
from jobengine.pipeline.batch import WINDOW_DAYS as _LIST_WINDOW_DAYS
from jobengine.pipeline.batch import list_candidate_pairs
from jobengine.pipeline.filter import load_filter_config
from jobengine.pipeline.relevance import load_relevance_config
from jobengine.profiles.config import load_profile_config
from jobengine.queue import orchestrate
from jobengine.resume.bank import load_bank
from jobengine.resume.render import load_identity
from jobengine.rubric.rules import RULE_INFO, has_unrecoverable_rubric_failure

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# How far back GET / looks for newly-matched-but-not-yet-triggered
# pairs. Matches B3's own "300-500 survivors/day" framing rather than
# scanning the whole historical jobs table on every page load. Imported
# from pipeline/batch.py (aliased to this module's original name) so the
# daily batch orchestrator scans the exact same window this page reads,
# not two independently-hardcoded copies of "7" -- see D38 in
# docs/decisions.md.

app = FastAPI(title="job-engine review queue")


def _db_path() -> Path:
    override = os.environ.get("JOBENGINE_DB_PATH")
    return Path(override) if override else DEFAULT_DB_PATH


def _build_context() -> orchestrate.QueueContext:
    conn = connect(_db_path(), check_same_thread=False)
    return orchestrate.QueueContext(
        conn=conn,
        full_bank=load_bank(),
        identity=load_identity(),
        profile_configs=load_profile_config(),
        filter_config=load_filter_config(),
        llm_config=load_llm_config(),
        relevance_config=load_relevance_config(),
    )


_singleton_ctx: orchestrate.QueueContext | None = None


def get_ctx() -> orchestrate.QueueContext:
    """A single QueueContext per process, built lazily on first use (not
    at import time, so importing this module for tests never touches
    the real db/bank/config unless a route actually runs). Overridden in
    tests via app.dependency_overrides[get_ctx]."""
    global _singleton_ctx
    if _singleton_ctx is None:
        _singleton_ctx = _build_context()
    return _singleton_ctx


if Path("resume").is_dir():
    app.mount("/resume", StaticFiles(directory="resume"), name="resume")


@app.get("/")
def queue_list(
    request: Request,
    ctx: orchestrate.QueueContext = Depends(get_ctx),  # noqa: B008
):
    entries = orchestrate.list_queue(ctx.conn)
    # F1-followup: candidate pairs (B3 filters + C4 relevance floor,
    # no job_resume_variant yet) split into "processing" (an active
    # variant_claims row -- pipeline/batch.py's prefetch stage or a
    # concurrent web request is rendering it right now) and "queued"
    # (a candidate, nothing working on it yet). list_candidate_pairs()
    # is the same function pipeline/batch.py's own prefetch stage draws
    # from -- one definition of "candidate," not two.
    candidate_pairs = list_candidate_pairs(
        ctx.conn, ctx.filter_config, ctx.relevance_config, _LIST_WINDOW_DAYS
    )
    claims = list_claims(ctx.conn)
    processing_pairs = [
        (job, profile)
        for job, profile in candidate_pairs
        if (job.id, profile) in claims
    ]
    queued_pairs = [
        (job, profile)
        for job, profile in candidate_pairs
        if (job.id, profile) not in claims
    ]
    applications = list_applications(ctx.conn)
    docx_urls = {
        a.application_id: _resume_static_url(a.docx_path) for a in applications
    }
    return templates.TemplateResponse(
        request,
        "queue_list.html",
        {
            "entries": entries,
            "queued_pairs": queued_pairs,
            "processing_pairs": processing_pairs,
            "applications": applications,
            "docx_urls": docx_urls,
        },
    )


@app.get("/jobs/{job_id}/{profile}")
def queue_detail(
    request: Request,
    job_id: int,
    profile: str,
    ctx: orchestrate.QueueContext = Depends(get_ctx),  # noqa: B008
):
    try:
        variant = orchestrate.ensure_reviewed(ctx, job_id, profile)
    except orchestrate.JobNotFoundError:
        raise HTTPException(status_code=404, detail="job not found") from None
    except orchestrate.NoBaseResumeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except orchestrate.AlreadyProcessingError:
        # Someone else (the prefetch batch, or another request for this
        # same pair) is already running the ladder -- do not run it
        # again and race the insert. 202: request understood, not done
        # yet, come back shortly.
        return templates.TemplateResponse(
            request,
            "processing.html",
            {"job_id": job_id, "profile": profile},
            status_code=202,
        )

    job = get_job_by_id(ctx.conn, job_id)
    analysis = get_job_analysis(ctx.conn, job_id, profile)
    rubric_results = get_rubric_results(ctx.conn, variant.id)
    hard_block = False
    needs_override = False
    if not variant.passed:
        # D42: computed here (not just at approve()) so the failure state
        # is surfaced the moment the page loads, not only after a failed
        # approve attempt.
        failing_rules = [r.rule_id for r in rubric_results]
        hard_block = has_unrecoverable_rubric_failure(failing_rules)
        needs_override = not hard_block
    return templates.TemplateResponse(
        request,
        "queue_detail.html",
        {
            "job": job,
            "profile": profile,
            "variant": variant,
            "analysis": analysis,
            "rubric_results": rubric_results,
            "pdf_url": _resume_static_url(variant.pdf_path),
            "docx_url": _resume_static_url(variant.docx_path),
            "hard_block": hard_block,
            "needs_override": needs_override,
            "rule_info": RULE_INFO,
        },
    )


def _resume_static_url(path: str | None) -> str | None:
    """Not PDF-specific despite call sites: variant.pdf_path/docx_path
    are both paths like "resume/rendered/variants/1/software_engineer/
    x.pdf"; the StaticFiles mount at /resume serves the resume/
    directory's contents directly, so the URL is the same path with the
    leading "resume/" stripped."""
    if path is None:
        return None
    prefix = "resume/"
    if path.startswith(prefix):
        return "/resume/" + path[len(prefix) :]
    return None


def _variant_or_404(ctx: orchestrate.QueueContext, job_id: int, profile: str):
    variant = get_job_resume_variant(ctx.conn, job_id, profile)
    if variant is None:
        raise HTTPException(
            status_code=404, detail="no reviewed variant for this (job, profile) yet"
        )
    return variant


@app.post("/jobs/{job_id}/{profile}/approve")
def approve(
    job_id: int,
    profile: str,
    ctx: orchestrate.QueueContext = Depends(get_ctx),  # noqa: B008
    override_soft_failure: bool = Form(False),
):
    variant = _variant_or_404(ctx, job_id, profile)
    try:
        orchestrate.approve(ctx, variant, override_soft_failure=override_soft_failure)
    except (
        orchestrate.HardRubricFailureError,
        orchestrate.UnacknowledgedSoftFailureError,
    ) as exc:
        # Backstop only: the detail page never normally offers a way to
        # trigger these (D42) -- a hard failure gets no approve form at
        # all, and a soft failure's only approve form already carries
        # override_soft_failure=true.
        raise HTTPException(status_code=409, detail=str(exc)) from None
    # D44: redirect back to the detail page, not "/" -- an approved job
    # disappears from both list sections (list_pending_review_queue()
    # only returns 'pending'; list_existing_variant_pairs() excludes any
    # reviewed pair from "not yet reviewed" too), so "/" would strand the
    # reviewer with no path back to the apply URL/resume they just
    # earned. See docs/decisions.md D44.
    return RedirectResponse(url=f"/jobs/{job_id}/{profile}", status_code=303)


@app.post("/jobs/{job_id}/{profile}/reject")
def reject(
    job_id: int,
    profile: str,
    ctx: orchestrate.QueueContext = Depends(get_ctx),  # noqa: B008
):
    variant = _variant_or_404(ctx, job_id, profile)
    orchestrate.reject(ctx, variant)
    return RedirectResponse(url="/", status_code=303)
