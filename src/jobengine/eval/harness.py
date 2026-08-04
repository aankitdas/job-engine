"""Spec 07 eval harness: orchestrates task runs against the real db and a
given model, writes results to model_evals.
"""

import sqlite3
from typing import Any

from jobengine.eval import report
from jobengine.eval.tasks import keyword_extraction
from jobengine.llm.schemas import LLMConfig


async def run_all(
    conn: sqlite3.Connection,
    model: str,
    llm_config: LLMConfig,
    *,
    local_client: Any | None = None,
) -> None:
    """Runs every implemented eval task and writes results to model_evals.

    Only Task 2 (keyword extraction) exists today. Task 1 (relevance
    scoring) is C4's scope and isn't wired in here yet; Task 3 (P3
    rephrase quality) is spec 07's optional task, deferred until P3 fires
    often enough to matter.
    """
    task2 = await keyword_extraction.run(conn, llm_config, local_client=local_client)
    report.print_task2_report(task2)
    report.write_task2_model_evals(conn, model, task2)
