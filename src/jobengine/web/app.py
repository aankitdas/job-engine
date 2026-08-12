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
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from jobengine.db.migrate import DEFAULT_DB_PATH, connect
from jobengine.db.models import (
    Job,
    get_job_analysis,
    get_job_by_id,
    get_job_resume_variant,
    get_rubric_results,
    list_existing_variant_pairs,
)
from jobengine.llm.router import load_config as load_llm_config
from jobengine.pipeline.filter import (
    load_filter_config,
    matches_profiles,
    passes_all_filters,
)
from jobengine.pipeline.relevance import load_relevance_config, passes_relevance_floor
from jobengine.profiles.config import load_profile_config
from jobengine.queue import orchestrate
from jobengine.resume.bank import load_bank
from jobengine.resume.render import load_identity

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# How far back GET / looks for newly-matched-but-not-yet-triggered
# pairs. Matches B3's own "300-500 survivors/day" framing rather than
# scanning the whole historical jobs table on every page load.
_LIST_WINDOW_DAYS = 7

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


def _recent_open_jobs(conn) -> list[Job]:
    cutoff = (datetime.now(UTC) - timedelta(days=_LIST_WINDOW_DAYS)).isoformat()
    rows = conn.execute(
        "SELECT * FROM jobs WHERE first_seen_at >= ? AND closed_at IS NULL", (cutoff,)
    ).fetchall()
    return [Job(**dict(row)) for row in rows]


def _new_pairs(ctx: orchestrate.QueueContext) -> list[tuple[Job, str]]:
    """(job, profile) pairs that survive B3's full filter chain
    (passes_all_filters: title match, US location, seniority,
    employment type, citizenship/clearance, already-applied) AND C4's
    relevance floor, but have never been triggered into a
    job_resume_variant at all -- the "not yet reviewed" links on the
    list page. Gated per-job on passes_all_filters() first;
    matches_profiles() is then called again only for jobs that already
    cleared every other check, to get the actual list of matched
    profiles to iterate (passes_all_filters() itself only returns a
    bool, not which profiles matched). passes_relevance_floor() is
    per-(job, profile), so it runs inside that per-profile loop, after
    matches_profiles() -- a job can clear the floor for one matched
    profile and not another."""
    existing = list_existing_variant_pairs(ctx.conn)
    pairs = []
    for job in _recent_open_jobs(ctx.conn):
        if not passes_all_filters(ctx.conn, job, ctx.filter_config):
            continue
        for profile in matches_profiles(job, ctx.filter_config):
            if (job.id, profile) in existing:
                continue
            if not passes_relevance_floor(
                ctx.conn, job.id, profile, ctx.relevance_config
            ):
                continue
            pairs.append((job, profile))
    return pairs


@app.get("/")
def queue_list(
    request: Request,
    ctx: orchestrate.QueueContext = Depends(get_ctx),  # noqa: B008
):
    entries = orchestrate.list_queue(ctx.conn)
    new_pairs = _new_pairs(ctx)
    return templates.TemplateResponse(
        request, "queue_list.html", {"entries": entries, "new_pairs": new_pairs}
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

    job = get_job_by_id(ctx.conn, job_id)
    analysis = get_job_analysis(ctx.conn, job_id, profile)
    rubric_results = get_rubric_results(ctx.conn, variant.id)
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
        },
    )


def _resume_static_url(pdf_path: str | None) -> str | None:
    """variant.pdf_path is a path like "resume/rendered/variants/1/
    software_engineer/x.pdf"; the StaticFiles mount at /resume serves
    the resume/ directory's contents directly, so the URL is the same
    path with the leading "resume/" stripped."""
    if pdf_path is None:
        return None
    prefix = "resume/"
    if pdf_path.startswith(prefix):
        return "/resume/" + pdf_path[len(prefix) :]
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
):
    variant = _variant_or_404(ctx, job_id, profile)
    orchestrate.approve(ctx, variant)
    return RedirectResponse(url="/", status_code=303)


@app.post("/jobs/{job_id}/{profile}/reject")
def reject(
    job_id: int,
    profile: str,
    ctx: orchestrate.QueueContext = Depends(get_ctx),  # noqa: B008
):
    variant = _variant_or_404(ctx, job_id, profile)
    orchestrate.reject(ctx, variant)
    return RedirectResponse(url="/", status_code=303)
