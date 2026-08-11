"""Spec 07 eval harness: orchestrates task runs against the real db and a
given model, writes results to model_evals.
"""

import sqlite3
from typing import Any

from jobengine.eval import report
from jobengine.eval.tasks import keyword_extraction
from jobengine.eval.tasks import relevance as relevance_task
from jobengine.llm.schemas import LLMConfig
from jobengine.pipeline.filter import FilterConfig
from jobengine.pipeline.relevance import RelevanceConfig
from jobengine.resume.bank import Bank


async def run_all(
    conn: sqlite3.Connection,
    model: str,
    llm_config: LLMConfig,
    filter_config: FilterConfig,
    relevance_config: RelevanceConfig,
    bank: Bank,
    *,
    local_client: Any | None = None,
) -> None:
    """Runs every implemented eval task and writes results to model_evals.

    Task 1 (relevance scoring, C4) and Task 2 (keyword extraction, C3)
    both run here. Task 3 (P3 rephrase quality) is spec 07's optional
    task, deferred until P3 fires often enough to matter.
    """
    task1 = await relevance_task.run(
        conn,
        filter_config,
        relevance_config,
        llm_config,
        bank,
        local_client=local_client,
    )
    report.print_task1_report(task1)
    report.write_task1_model_evals(conn, model, task1)

    task2 = await keyword_extraction.run(conn, llm_config, local_client=local_client)
    report.print_task2_report(task2)
    report.write_task2_model_evals(conn, model, task2)
