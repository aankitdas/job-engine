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

Deliberately does NOT call queue/orchestrate.py's ensure_reviewed() or
the patch ladder (D3/D4): that stays F1's lazy per-click trigger,
unchanged (see orchestrate.py's own module docstring). This module only
makes relevance scoring and extraction real batch steps; rendering a
candidate resume still only happens the first time a reviewer opens a
specific queue detail page.

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
    Run,
    get_job_by_id,
    get_relevance_score,
    has_job_analysis,
    list_unscored_open_jobs,
    record_run,
)
from jobengine.llm.router import load_config as load_llm_config
from jobengine.llm.schemas import LLMConfig
from jobengine.pipeline.extract import analyze_job
from jobengine.pipeline.filter import FilterConfig, load_filter_config
from jobengine.pipeline.relevance import (
    RelevanceConfig,
    load_relevance_config,
    score_job,
)
from jobengine.profiles.config import ProfileConfig, load_profile_config
from jobengine.resume.bank import DEFAULT_BANK_PATH, Bank, load_bank

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
        )
        print(
            f"candidates={result.candidate_jobs} "
            f"relevance_pairs={result.relevance_scored_pairs} "
            f"floor_clearing_jobs={result.floor_clearing_jobs} "
            f"extraction_jobs={result.extraction_scored_jobs}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    _main()
