"""C3: keyword extraction. See specs/00-data-model.md's job_analysis/
keyword_corpus tables and specs/07-model-eval.md's Task 2.

One LLM call per job, not per (job, profile): required_keywords is a
property of the JD text itself, independent of which profile is reading
it (spec 05's own frequency estimate, 30-60 calls per night, only makes
sense per-job). job_analysis still gets one row per profile the job
matches, fanned out from the single extraction result, matching every
other per-profile table's convention.

Only required_keywords, preferred_keywords, and tech_stack are asked of
the model. canonical_title, seniority, and jd_quality are deliberately
left out of the schema: jd_quality is Lee's literal "has a Requirements/
Qualifications section" rule, a structural check with no judgment call in
it, so it is computed in plain Python (is_good_quality_jd), not asked of
the model. canonical_title/seniority have no ground truth in human_labels
to grade them against yet and are left NULL until a later phase actually
consumes and can validate them.
"""

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from jobengine.db.models import (
    Job,
    JobAnalysis,
    upsert_job_analysis,
    upsert_keyword_corpus_entry,
)
from jobengine.llm import router
from jobengine.llm.schemas import LLMCallResult, LLMConfig
from jobengine.pipeline.filter import FilterConfig, matches_profiles

_QUALITY_SECTION_RE = re.compile(
    r"(requirements|qualifications|what you.ll bring|what we.re looking for|"
    r"minimum qualifications|preferred qualifications)",
    re.IGNORECASE,
)

_EXTRACTION_PROMPT = """Extract keywords from this job description.

Each keyword must be a short, atomic term: a single technology, tool, \
language, framework, platform, methodology, or skill name (1-3 words), \
never a full sentence, clause, or requirement description.

Correct:   "Python", "Kubernetes", "distributed systems", "AWS"
Incorrect: "8+ years of software engineering experience",
           "Strong proficiency in backend technologies (Python, Java)",
           "ability to write and review code"

If a sentence names several technologies together (e.g. "experience with
Python, Java, or Go"), extract each one as its own separate keyword, not
as one combined phrase. Do not extract years-of-experience, soft skills,
or generic qualifications (e.g. "communication skills", "5+ years") as
keywords at all.

required_keywords: technologies/skills explicitly stated as required or
must-have.
preferred_keywords: technologies/skills described as nice-to-have, a
plus, or preferred.
tech_stack: every specific tool, language, framework, or platform named
anywhere in the posting.

Use the job description's own wording for each term. Do not invent terms
it does not use.

Job description:
{description}"""


class ExtractionSchema(BaseModel):
    required_keywords: list[str]
    preferred_keywords: list[str]
    tech_stack: list[str]


def is_good_quality_jd(description: str | None) -> bool:
    """Lee's rule: a JD is "good" if it has a real Requirements/
    Qualifications section, not just marketing prose. A structural check,
    not a judgment call, so it stays deterministic Python rather than an
    LLM output field (CLAUDE.md: "everything mechanical is mechanical").
    """
    if not description:
        return False
    return _QUALITY_SECTION_RE.search(description) is not None


def _keyword_hash(keywords: list[str]) -> str:
    return hashlib.sha256(json.dumps(sorted(keywords)).encode()).hexdigest()


async def extract_keywords(
    description: str,
    config: LLMConfig,
    *,
    local_client: Any | None = None,
) -> LLMCallResult:
    """The only place this module talks to an LLM: goes through C1's
    router (never constructs an ollama client of its own), which sets
    think=False on every call regardless of caller.
    """
    provider = router.get_provider("extract", config, local_client=local_client)
    return await provider.call(
        stage="extract",
        messages=[
            {
                "role": "user",
                "content": _EXTRACTION_PROMPT.format(description=description),
            }
        ],
        schema=ExtractionSchema,
    )


async def analyze_job(
    conn,
    job: Job,
    filter_config: FilterConfig,
    llm_config: LLMConfig,
    *,
    local_client: Any | None = None,
) -> list[int]:
    """Analyzes a job once and fans the result out to job_analysis/
    keyword_corpus for every profile it matches. A job matching no
    profile skips the LLM call entirely, not just the persistence.
    """
    profiles = matches_profiles(job, filter_config)
    if not profiles:
        return []

    result = await extract_keywords(
        job.description or "", llm_config, local_client=local_client
    )
    extracted = ExtractionSchema.model_validate(result.output)
    quality = "good" if is_good_quality_jd(job.description) else "bad"
    analyzed_at = datetime.now(UTC).isoformat()
    keyword_hash = _keyword_hash(extracted.required_keywords)

    row_ids = []
    for profile in profiles:
        row_ids.append(
            upsert_job_analysis(
                conn,
                JobAnalysis(
                    job_id=job.id,
                    profile=profile,
                    required_keywords=json.dumps(extracted.required_keywords),
                    preferred_keywords=json.dumps(extracted.preferred_keywords),
                    tech_stack=json.dumps(extracted.tech_stack),
                    jd_quality=quality,
                    keyword_hash=keyword_hash,
                    analyzed_at=analyzed_at,
                    model=result.model,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cost_usd=result.cost_usd,
                ),
            )
        )
        # Only required_keywords feeds the corpus: it's the list that
        # actually gates a resume match (spec 07: "a missed required
        # keyword silently costs you a match"). preferred_keywords/
        # tech_stack are stored on job_analysis but don't dilute it.
        for keyword in extracted.required_keywords:
            upsert_keyword_corpus_entry(conn, profile, keyword, analyzed_at)

    conn.commit()
    return row_ids
