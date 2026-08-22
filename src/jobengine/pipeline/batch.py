"""F1's daily batch orchestrator: stages 2.5 (relevance) and 3
(extraction) in docs/architecture.md's pipeline table, run as one
scheduled step instead of never running as a batch at all. See D38 in
docs/decisions.md.

Before this module, C4 relevance scoring only ever ran via
pipeline/relevance.py's manual `score` CLI or an interactive scratch
script, and C3 extraction only ever ran lazily inside
queue/orchestrate.py's ensure_reviewed(), triggered by a human opening
one specific (job, profile) URL. Neither ran on a schedule, so
web/app.py's passes_relevance_floor() gate spent its entire life
failing open on every job synced since the last manual run -- a real
job could sit unscored, unfiltered, indefinitely. This module closes
that gap.

Also runs queue/orchestrate.py's ensure_reviewed() (F1-followup, the
"score and review" prefetch stage): every (job, profile) pair that
clears B3's filters and C4's relevance floor but has no
job_resume_variant yet gets its patch ladder run here, ahead of a human
ever opening the detail page, instead of blocking that request. Shares
ensure_reviewed() itself with the web app's on-demand fallback (never a
second copy of the check-then-render-then-insert logic) and claims each
pair before rendering it (db/models.py's variant_claims,
STALE_CLAIM_SECONDS in orchestrate.py) so this stage and a concurrent
web request can never both render the same pair. A pair whose profile
has no base_resumes row yet (NoBaseResumeError) or that's already
claimed by something else (AlreadyProcessingError) is skipped for this
run, not treated as a batch failure.

C3 extraction runs only for a job once at least one of its scored
profiles clears C4's min_relevance_score floor. job_analysis/
keyword_corpus have exactly one consumer today (ensure_reviewed()'s
lazy trigger), and that trigger is only ever reached for floor-clearing
(job, profile) pairs, since passes_relevance_floor() gates which pairs
even appear on the queue list (web/app.py's _new_pairs()). Extracting
keywords for a job nothing downstream will read would be real, wasted
LLM cost -- see D38's cost/coverage tradeoff note for what this means
for keyword_corpus specifically.

Incremental by construction, not a config flag: list_unscored_open_jobs()
and has_job_analysis() (db/models.py) skip any job already scored or
already analyzed, so a job is never re-sent to the LLM by a later run,
however large the open-jobs backlog grows. Contrast with
pipeline/relevance.py's own `score` CLI, which rescans every open job on
every invocation by design (a deliberate manual/one-off tool, e.g. after
a prompt change) -- this module is what the scheduler calls instead.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from jobengine.db.migrate import DEFAULT_DB_PATH, connect
from jobengine.db.models import (
    Job,
    Run,
    get_job_by_id,
    get_relevance_score,
    has_job_analysis,
    list_existing_variant_pairs,
    list_recent_open_jobs,
    list_unscored_open_jobs,
    record_run,
)
from jobengine.llm.router import load_config as load_llm_config
from jobengine.llm.schemas import LLMConfig
from jobengine.pipeline.extract import analyze_job
from jobengine.pipeline.filter import (
    FilterConfig,
    load_filter_config,
    matches_profiles,
    passes_all_filters,
)
from jobengine.pipeline.relevance import (
    RelevanceConfig,
    load_relevance_config,
    passes_relevance_floor,
    score_job,
)
from jobengine.profiles.config import ProfileConfig, load_profile_config
from jobengine.queue import orchestrate
from jobengine.resume.bank import DEFAULT_BANK_PATH, Bank, load_bank
from jobengine.resume.render import Identity, load_identity

logger = logging.getLogger(__name__)

# Matches web/app.py's own review-queue window: this module exists to
# make that window's relevance floor real before a human ever loads
# GET /, so the two must scan the same span of newly-synced jobs.
# Single source of truth lives here (pipeline layer, lower than web);
# web/app.py imports this rather than hardcoding its own copy.
WINDOW_DAYS = 7


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class BatchResult:
    candidate_jobs: int
    relevance_scored_pairs: int
    floor_clearing_jobs: int
    extraction_scored_jobs: int
    variants_rendered: int = 0


def list_candidate_pairs(
    conn: sqlite3.Connection,
    filter_config: FilterConfig,
    relevance_config: RelevanceConfig,
    window_days: int = WINDOW_DAYS,
) -> list[tuple[Job, str]]:
    """(job, profile) pairs that survive B3's full filter chain
    (passes_all_filters) and C4's relevance floor (passes_relevance_floor)
    but have no job_resume_variant yet -- the review queue's "not yet
    reviewed" set. Single source of truth for both this module's own
    render stage below and web/app.py's queue-list page (moved out of
    that module's former _new_pairs(), which duplicated this exact logic
    with no shared definition of "candidate" between the two), matching
    WINDOW_DAYS' own single-source-of-truth precedent (D38). Gated
    per-job on passes_all_filters() first; matches_profiles() is then
    called again only for jobs that already cleared every other check,
    since passes_all_filters() itself only returns a bool, not which
    profiles matched. passes_relevance_floor() is per-(job, profile), so
    it runs inside the per-profile loop, after matches_profiles() -- a
    job can clear the floor for one matched profile and not another."""
    existing = list_existing_variant_pairs(conn)
    pairs: list[tuple[Job, str]] = []
    for job in list_recent_open_jobs(conn, window_days):
        if not passes_all_filters(conn, job, filter_config):
            continue
        for profile in matches_profiles(job, filter_config):
            if (job.id, profile) in existing:
                continue
            if not passes_relevance_floor(conn, job.id, profile, relevance_config):
                continue
            pairs.append((job, profile))
    return pairs


def run_daily_batch(
    conn: sqlite3.Connection,
    filter_config: FilterConfig,
    relevance_config: RelevanceConfig,
    llm_config: LLMConfig,
    bank: Bank,
    *,
    window_days: int = WINDOW_DAYS,
    profile_registry: dict[str, ProfileConfig] | None = None,
    local_client: Any | None = None,
    identity: Identity | None = None,
) -> BatchResult:
    started_at = _now()
    candidates = list_unscored_open_jobs(conn, window_days)

    relevance_scored_pairs = 0
    floor_clearing_job_ids: set[int] = set()
    for job in candidates:
        pairs = asyncio.run(
            score_job(
                conn,
                job,
                filter_config,
                relevance_config,
                llm_config,
                bank,
                profile_registry=profile_registry,
                local_client=local_client,
            )
        )
        relevance_scored_pairs += len(pairs)
        for job_id, profile in pairs:
            score = get_relevance_score(conn, job_id, profile)
            if (
                score is not None
                and score.score >= relevance_config.min_relevance_score
            ):
                floor_clearing_job_ids.add(job_id)

    extraction_scored_jobs = 0
    for job_id in floor_clearing_job_ids:
        if has_job_analysis(conn, job_id):
            continue
        job = get_job_by_id(conn, job_id)
        row_ids = asyncio.run(
            analyze_job(conn, job, filter_config, llm_config, local_client=local_client)
        )
        if row_ids:
            extraction_scored_jobs += 1

    # F1-followup: render every candidate pair's patch ladder now, ahead
    # of a human ever opening its detail page. Shares ensure_reviewed()
    # with the web app's on-demand fallback rather than duplicating the
    # check-then-render-then-insert logic; claimed_by="batch" is a
    # debug-only tag on the variant_claims row, plays no role in the
    # claim/reclaim mechanics themselves.
    qctx = orchestrate.QueueContext(
        conn=conn,
        full_bank=bank,
        identity=identity or load_identity(),
        profile_configs=profile_registry or load_profile_config(),
        filter_config=filter_config,
        llm_config=llm_config,
        relevance_config=relevance_config,
        local_client=local_client,
    )
    variants_rendered = 0
    for job, profile in list_candidate_pairs(
        conn, filter_config, relevance_config, window_days
    ):
        try:
            orchestrate.ensure_reviewed(qctx, job.id, profile, claimed_by="batch")
            variants_rendered += 1
        except orchestrate.NoBaseResumeError:
            logger.warning(
                "no base_resumes row for profile %r yet; skipping job %s",
                profile,
                job.id,
            )
        except orchestrate.AlreadyProcessingError:
            logger.info(
                "job %s/%s already claimed elsewhere; skipping this run",
                job.id,
                profile,
            )

    ended_at = _now()
    record_run(
        conn,
        Run(
            stage="daily_batch",
            started_at=started_at,
            ended_at=ended_at,
            counts=json.dumps(
                {
                    "candidate_jobs": len(candidates),
                    "relevance_scored_pairs": relevance_scored_pairs,
                    "floor_clearing_jobs": len(floor_clearing_job_ids),
                    "extraction_scored_jobs": extraction_scored_jobs,
                    "variants_rendered": variants_rendered,
                }
            ),
        ),
    )
    conn.commit()
    return BatchResult(
        candidate_jobs=len(candidates),
        relevance_scored_pairs=relevance_scored_pairs,
        floor_clearing_jobs=len(floor_clearing_job_ids),
        extraction_scored_jobs=extraction_scored_jobs,
        variants_rendered=variants_rendered,
    )


def _main() -> None:
    parser = argparse.ArgumentParser(prog="jobengine.pipeline.batch")
    parser.add_argument("--window-days", type=int, default=WINDOW_DAYS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    conn = connect(DEFAULT_DB_PATH)
    try:
        result = run_daily_batch(
            conn,
            load_filter_config(),
            load_relevance_config(),
            load_llm_config(),
            load_bank(DEFAULT_BANK_PATH),
            window_days=args.window_days,
            profile_registry=load_profile_config(),
            identity=load_identity(),
        )
        print(
            f"candidates={result.candidate_jobs} "
            f"relevance_pairs={result.relevance_scored_pairs} "
            f"floor_clearing_jobs={result.floor_clearing_jobs} "
            f"extraction_jobs={result.extraction_scored_jobs} "
            f"variants_rendered={result.variants_rendered}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    _main()
