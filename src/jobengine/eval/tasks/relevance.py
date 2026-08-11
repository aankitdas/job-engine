"""Spec 07 Task 1: relevance scoring eval. Spearman rank correlation and
top-30 set overlap against human_labels.relevance, per profile -- rho and
overlap are only meaningful within one ranked list, so results are never
pooled across profiles the way Task 2's TP/FP/FN are.

Calls jobengine.pipeline.relevance.score_relevance() directly, the exact
same call C4's production path uses, not a duplicate prompt/provider --
same reasoning Task 2 already documents for calling extract_keywords()
directly rather than the full per-job orchestrator: eval needs to score
the exact labeled profile regardless of whether B3's title routing would
independently reach it, and needs per-row exception isolation so one bad
call doesn't abort the rest.

Only profiles with at least one labeled relevance row appear in
Task1Report.by_profile -- a profile with zero labeled rows contributes
nothing meaningful to rho/overlap and is left out rather than reported as
a degenerate n=0 entry.
"""

from __future__ import annotations

import math
import sqlite3
from typing import Any, NamedTuple

from jobengine.eval.fixtures import PROFILES
from jobengine.llm.schemas import LLMConfig
from jobengine.pipeline.filter import FilterConfig
from jobengine.pipeline.relevance import (
    RelevanceConfig,
    RelevanceSchema,
    build_profile_card,
    is_hard_disqualified,
    render_profile_card,
    score_relevance,
)
from jobengine.profiles.config import ProfileConfig
from jobengine.resume.bank import Bank

TASK = "relevance"


class ProfileTaskResult(NamedTuple):
    profile: str
    n: int
    schema_failures: int
    spearman_rho: float
    top30_overlap: float


class Task1Report(NamedTuple):
    by_profile: list[ProfileTaskResult]


def _labeled_jobs_by_profile(
    conn: sqlite3.Connection,
) -> dict[str, list[tuple[int, str, int]]]:
    by_profile: dict[str, list[tuple[int, str, int]]] = {}
    for profile in PROFILES:
        rows = conn.execute(
            "SELECT h.job_id, j.description, h.relevance "
            "FROM human_labels h JOIN jobs j ON j.id = h.job_id "
            "WHERE h.profile = ? AND h.relevance IS NOT NULL "
            "ORDER BY h.job_id",
            (profile,),
        ).fetchall()
        if rows:
            by_profile[profile] = [
                (r["job_id"], r["description"], r["relevance"]) for r in rows
            ]
    return by_profile


def _ranks(values: list[float]) -> list[float]:
    """Average rank for ties, ascending."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def _spearman_rho(xs: list[float], ys: list[float]) -> float:
    """Rank-transform + Pearson on ranks, ties averaged. No scipy/numpy
    dependency (hard rule 5): this is the entire computation, ~20 lines."""
    n = len(xs)
    rx, ry = _ranks(xs), _ranks(ys)
    mean_rx, mean_ry = sum(rx) / n, sum(ry) / n
    cov = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(n))
    var_x = sum((v - mean_rx) ** 2 for v in rx)
    var_y = sum((v - mean_ry) ** 2 for v in ry)
    if var_x == 0 or var_y == 0:
        return float("nan")
    return cov / math.sqrt(var_x * var_y)


def _top_k_overlap(
    human_scores: list[float], model_scores: list[float], job_ids: list[int], k: int
) -> float:
    n = len(job_ids)
    if k <= 0 or n == 0:
        return float("nan")
    top_human = set(sorted(range(n), key=lambda i: -human_scores[i])[:k])
    top_model = set(sorted(range(n), key=lambda i: -model_scores[i])[:k])
    return len(top_human & top_model) / k


async def run(
    conn: sqlite3.Connection,
    filter_config: FilterConfig,
    relevance_config: RelevanceConfig,
    llm_config: LLMConfig,
    bank: Bank,
    *,
    profile_registry: dict[str, ProfileConfig] | None = None,
    local_client: Any | None = None,
) -> Task1Report:
    jobs_by_profile = _labeled_jobs_by_profile(conn)
    results: list[ProfileTaskResult] = []

    for profile, rows in jobs_by_profile.items():
        card_text = render_profile_card(
            build_profile_card(conn, bank, profile, filter_config, profile_registry)
        )
        human_scores: list[float] = []
        model_scores: list[float] = []
        job_ids: list[int] = []
        schema_failures = 0

        for job_id, description, human_score in rows:
            try:
                call = await score_relevance(
                    description or "", card_text, llm_config, local_client=local_client
                )
                parsed = RelevanceSchema.model_validate(call.output)
            except Exception:  # noqa: BLE001 - one bad call must not abort
                # the rest; it counts toward schema_failures instead.
                schema_failures += 1
                continue

            final_score = (
                0.0
                if is_hard_disqualified(
                    parsed.disqualifiers, relevance_config.disqualifier_blocklist
                )
                else float(parsed.relevance)
            )
            human_scores.append(float(human_score))
            model_scores.append(final_score)
            job_ids.append(job_id)

        n = len(model_scores)
        rho = _spearman_rho(model_scores, human_scores) if n >= 2 else float("nan")
        k = min(30, n)
        overlap = _top_k_overlap(human_scores, model_scores, job_ids, k=k)

        results.append(
            ProfileTaskResult(
                profile=profile,
                n=n,
                schema_failures=schema_failures,
                spearman_rho=rho,
                top30_overlap=overlap,
            )
        )

    return Task1Report(by_profile=results)
