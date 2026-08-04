"""Spec 07 Task 2: keyword extraction eval. Precision/recall against the
hand-extracted keyword lists in human_labels, pooled across all labeled
jobs (TP/FP/FN summed, not per-job ratios averaged), so the report can
show the same real set-arithmetic standard B3 used.

The comparison is required_keywords UNION preferred_keywords on both
sides, not required_keywords alone. Required-vs-preferred is not a
scoring boundary: a real JD's own "Requirements" vs "Preferred
qualifications" split is inconsistent between postings (see D26 in
docs/decisions.md for the concrete case that forced this, job_id 2246),
and the fixture only ever asked for one merged list per job.

tech_stack is deliberately, permanently excluded from the model's
predicted set. This is a settled decision, not a per-job judgment call:
see D26 addendum 2 for the full reasoning and the quantified cost/benefit
(job_id 3283) behind it. Short version: tech_stack is a genuinely
different scope ("every tool named anywhere in the posting") from
required/preferred ("qualifications for this role"), not just another
unreliable split like required-vs-preferred was, so merging it in would
trade a small number of recovered true positives for a much larger
volume of real false positives. Do not re-litigate this per job; if a
specific job's tech_stack clearly contains a missed required skill,
that's a known, accepted, bounded gap (or a candidate for a future
prompt-clarity fix), not a reason to reopen the scoring boundary here.

Calls jobengine.pipeline.extract.extract_keywords() directly, the exact
same call C3's production path uses, not a duplicate prompt/provider
built for eval purposes. This is why per-job failures are caught here
rather than left to router.call()'s fallback: extract's fallback is
"fail" in config/llm.toml, correct for the daily pipeline (can't proceed
without keywords) but wrong for a 15-job eval loop, which needs to survive
one bad call and count it toward schema_validity_rate instead of aborting
the whole run.
"""

import json
import sqlite3
from typing import Any, NamedTuple

from jobengine.llm.schemas import LLMConfig
from jobengine.pipeline.extract import ExtractionSchema, extract_keywords

TASK = "keyword_extraction"


class Task2Report(NamedTuple):
    attempted: int
    schema_failures: int
    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def schema_validity_rate(self) -> float:
        if not self.attempted:
            return 0.0
        return (self.attempted - self.schema_failures) / self.attempted


def _normalize(keywords: list[str]) -> set[str]:
    return {kw.strip().lower() for kw in keywords if kw.strip()}


def _labeled_jobs(conn: sqlite3.Connection) -> list[tuple[int, str, list[str]]]:
    """The real labeled fixture set: (job_id, description, labeled_keywords).
    labeled_keywords is human_labels.keywords, one merged required+preferred
    list per job (see this module's docstring).

    A job's keywords may be attached to more than one human_labels row on
    a relevance tie (see D24 in docs/decisions.md); deduped by job_id so
    each labeled job is graded exactly once, not once per tied profile.
    """
    rows = conn.execute(
        "SELECT h.job_id, j.description, h.keywords "
        "FROM human_labels h JOIN jobs j ON j.id = h.job_id "
        "WHERE h.keywords IS NOT NULL "
        "ORDER BY h.job_id"
    ).fetchall()
    seen: dict[int, tuple[int, str, list[str]]] = {}
    for row in rows:
        if row["job_id"] in seen:
            continue
        seen[row["job_id"]] = (
            row["job_id"],
            row["description"],
            json.loads(row["keywords"]),
        )
    return list(seen.values())


async def run(
    conn: sqlite3.Connection,
    llm_config: LLMConfig,
    *,
    local_client: Any | None = None,
) -> Task2Report:
    jobs = _labeled_jobs(conn)
    tp = fp = fn = 0
    schema_failures = 0

    for _job_id, description, labeled_keywords in jobs:
        try:
            result = await extract_keywords(
                description or "", llm_config, local_client=local_client
            )
            extracted = ExtractionSchema.model_validate(result.output)
        except Exception:  # noqa: BLE001 - one bad call must not abort the
            # other 14; it counts toward schema_validity_rate instead.
            schema_failures += 1
            continue

        extracted_set = _normalize(
            extracted.required_keywords + extracted.preferred_keywords
        )
        labeled_set = _normalize(labeled_keywords)
        tp += len(extracted_set & labeled_set)
        fp += len(extracted_set - labeled_set)
        fn += len(labeled_set - extracted_set)

    return Task2Report(
        attempted=len(jobs), schema_failures=schema_failures, tp=tp, fp=fp, fn=fn
    )
