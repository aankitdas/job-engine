"""C4: relevance pre-filter, "stage 2.5" in docs/architecture.md's
pipeline. See specs/06-relevance-filter.md and specs/07-model-eval.md's
Task 1.

One local LLM call per (job, profile) the job's title could plausibly
match (unlike C3's extract_keywords(), which is one call per job, fanned
out to many job_analysis rows -- relevance genuinely differs per profile,
required_keywords doesn't). Input is the JD (truncated) plus a compact
profile card: target titles, top corpus keywords, seniority band,
location rules. Never the bullet bank itself (spec 06: this stage judges
the job, not bullet fit).

Reuses jobengine.llm.router unchanged: "relevance" is already a
first-class Stage (llm/schemas.py), already routed "local" and
fallback "skip" in config/llm.toml, and LocalProvider.call() already
sets think=False unconditionally regardless of stage. Nothing new to
wire up there.

Hard disqualifiers (spec 06: "code decides") are matched in Python
against the model's own returned `disqualifiers` strings, using the same
phrase_matches() word-boundary/substring logic pipeline/filter.py uses
for JD text -- a different input, same matching semantics.

This module is also a runnable `python -m jobengine.pipeline.relevance
{score,calibrate}` CLI, per spec 06's literal invocation, unlike
extract.py/filter.py which have none.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, NamedTuple

import yaml
from pydantic import BaseModel, Field

from jobengine.db.migrate import DEFAULT_DB_PATH, connect
from jobengine.db.models import (
    Job,
    ModelEval,
    RankableScore,
    RelevanceScore,
    Run,
    insert_model_eval,
    list_relevance_scores_for_cutoff,
    record_run,
    update_relevance_selection,
    upsert_relevance_score,
)
from jobengine.llm import router
from jobengine.llm.router import load_config as load_llm_config
from jobengine.llm.schemas import LLMCallResult, LLMConfig
from jobengine.pipeline.filter import (
    FilterConfig,
    load_filter_config,
    matches_profiles,
    passes_all_filters,
    phrase_matches,
)
from jobengine.profiles.brief import top_corpus_keywords
from jobengine.profiles.config import ProfileConfig, load_profile_config
from jobengine.resume.bank import DEFAULT_BANK_PATH, KNOWN_PROFILES, Bank, load_bank
from jobengine.resume.render import DEFAULT_IDENTITY_PATH

DEFAULT_RELEVANCE_CONFIG_PATH = Path("config/relevance.yaml")

_CHARS_PER_TOKEN = 4
_DEFAULT_TOKEN_BUDGET = 6000

_RELEVANCE_PROMPT = """You are screening a job posting for fit against one target profile.

{profile_card}

Score this job's relevance to the profile above from 0 (no fit) to 100 \
(excellent fit).
seniority_match: "under" if the role is below this candidate's level, \
"match" if appropriate, "over" if it requires more seniority than an \
individual contributor (e.g. manager/director/VP titles).
keyword_hits: which of the profile's top skills/keywords actually \
appear in this JD.
disqualifiers: explicit hard blockers only (e.g. "requires active \
security clearance", "must be EU-based", "10+ years required"), empty \
list if none.
one_line: one sentence explaining the score.

Job description:
{description}"""


class RelevanceSchema(BaseModel):
    relevance: int = Field(ge=0, le=100)
    seniority_match: Literal["under", "match", "over"]
    keyword_hits: list[str]
    disqualifiers: list[str]
    one_line: str


class RelevanceConfig(BaseModel):
    disqualifier_blocklist: list[str] = []
    freshness_window_days: int | None = None


def load_relevance_config(
    path: Path = DEFAULT_RELEVANCE_CONFIG_PATH,
) -> RelevanceConfig:
    with open(path) as f:
        return RelevanceConfig(**yaml.safe_load(f))


class ProfileCard(NamedTuple):
    profile: str
    display_name: str | None
    target_titles: list[str]
    top_keywords: list[str]
    seniority_band: str
    location_rules: str


def _willing_to_relocate(identity_path: Path) -> bool:
    """identity.toml's [preferences].willing_to_relocate, read-only
    (hard rule 1: never write to identity.toml). Defaults to False (the
    conservative reading) if the file or field is absent, rather than
    assuming relocation willingness that was never actually stated."""
    if not identity_path.exists():
        return False
    raw = tomllib.loads(identity_path.read_text())
    return bool(raw.get("preferences", {}).get("willing_to_relocate", False))


def build_profile_card(
    conn: sqlite3.Connection,
    bank: Bank,
    profile: str,
    filter_config: FilterConfig,
    profile_registry: dict[str, ProfileConfig] | None = None,
    *,
    limit: int = 30,
    identity_path: Path = DEFAULT_IDENTITY_PATH,
) -> ProfileCard:
    pc = filter_config.profiles[profile]
    top = top_corpus_keywords(conn, bank, profile, limit=limit)
    seniority_band = (
        "Individual contributor roles only. Not: "
        + ", ".join(filter_config.seniority.exclude_title_keywords)
        + "."
    )
    if _willing_to_relocate(identity_path):
        location_rules = (
            "Must be US-based. Remote roles and on-site roles anywhere in "
            "the US are acceptable, including roles that require "
            "relocating to a specific US city or region -- that is not a "
            "disqualifier, the candidate is open to relocating anywhere "
            "in the US. Only an on-site role located outside the US is a "
            "disqualifier."
        )
    else:
        location_rules = (
            "Must be US-based or remote. On-site outside the US is a disqualifier."
        )
    display_name = (
        profile_registry[profile].display_name
        if profile_registry and profile in profile_registry
        else None
    )
    return ProfileCard(
        profile=profile,
        display_name=display_name,
        target_titles=list(pc.title_aliases),
        top_keywords=[kw for kw, _ in top.keywords],
        seniority_band=seniority_band,
        location_rules=location_rules,
    )


def render_profile_card(card: ProfileCard) -> str:
    name = card.display_name or card.profile
    lines = [
        f"Profile: {name}",
        f"Target titles include: {', '.join(card.target_titles)}",
        "Top skills/keywords this candidate's resume already covers: "
        + ", ".join(card.top_keywords),
        f"Seniority: {card.seniority_band}",
        f"Location requirement: {card.location_rules}",
    ]
    return "\n".join(lines)


def _truncate_to_token_budget(
    description: str, max_tokens: int = _DEFAULT_TOKEN_BUDGET
) -> str:
    """Approximate: no tokenizer dependency exists in this repo (hard
    rule 5 blocks adding one without asking). ~4 chars/token, same class
    of estimate this codebase already relies on elsewhere (exact token
    counts are only known after a call, from Ollama's own count)."""
    max_chars = max_tokens * _CHARS_PER_TOKEN
    return description[:max_chars]


def is_hard_disqualified(disqualifiers: list[str], blocklist: list[str]) -> bool:
    return any(
        phrase_matches(phrase, disqualifier.lower())
        for disqualifier in disqualifiers
        for phrase in blocklist
    )


async def score_relevance(
    description: str,
    profile_card_text: str,
    config: LLMConfig,
    *,
    local_client: Any | None = None,
) -> LLMCallResult:
    """Wrapped in an explicit application-level timeout (config.local.
    timeout_s, the same number already configured for the underlying
    ollama client) as defense-in-depth for the real nightly batch
    (~400 calls): a single call that never returns must not stall the
    whole run indefinitely. Confirmed via a real, escalating live-Ollama
    test during C4 planning/rollout (1500 up to the full 6000-char JD /
    30-keyword card, this module's actual RelevanceSchema) that a real
    call completes in 5-16s at every size tried, not hours -- this
    timeout is insurance for an unusual case, not a routinely-hit path."""
    provider = router.get_provider("relevance", config, local_client=local_client)
    prompt = _RELEVANCE_PROMPT.format(
        description=_truncate_to_token_budget(description),
        profile_card=profile_card_text,
    )
    return await asyncio.wait_for(
        provider.call(
            stage="relevance",
            messages=[{"role": "user", "content": prompt}],
            schema=RelevanceSchema,
        ),
        timeout=config.local.timeout_s,
    )


async def score_job(
    conn: sqlite3.Connection,
    job: Job,
    filter_config: FilterConfig,
    relevance_config: RelevanceConfig,
    llm_config: LLMConfig,
    bank: Bank,
    *,
    profile_registry: dict[str, ProfileConfig] | None = None,
    local_client: Any | None = None,
) -> list[tuple[int, str]]:
    """Per-job orchestrator, mirrors extract.py's analyze_job() shape:
    gated on B3's full filter chain first (title match AND location AND
    seniority AND employment type AND citizenship/clearance AND not
    already applied -- passes_all_filters(), not matches_profiles()
    alone), skipping the LLM entirely on any failure. This module is
    meant to score "every job surviving stage 2" (spec 06); a job whose
    title happens to match but fails another B3 check was never a real
    stage-2 survivor and must not reach the LLM. matches_profiles() is
    then called again only for the per-profile fan-out (which profiles
    to score against), since passes_all_filters()'s other checks are
    job-level, not profile-specific. One LLM call PER matched profile,
    not one call fanned out to many rows like analyze_job() -- relevance
    genuinely differs per profile, required_keywords doesn't."""
    if not passes_all_filters(conn, job, filter_config):
        return []
    profiles = matches_profiles(job, filter_config)

    scored_at = datetime.now(UTC).isoformat()
    results: list[tuple[int, str]] = []
    for profile in profiles:
        card = build_profile_card(conn, bank, profile, filter_config, profile_registry)
        call = await score_relevance(
            job.description or "",
            render_profile_card(card),
            llm_config,
            local_client=local_client,
        )
        parsed = RelevanceSchema.model_validate(call.output)
        final_score = (
            0.0
            if is_hard_disqualified(
                parsed.disqualifiers, relevance_config.disqualifier_blocklist
            )
            else float(parsed.relevance)
        )

        upsert_relevance_score(
            conn,
            RelevanceScore(
                job_id=job.id,
                profile=profile,
                score=final_score,
                seniority_match=parsed.seniority_match,
                keyword_hits=json.dumps(parsed.keyword_hits),
                disqualifiers=json.dumps(parsed.disqualifiers),
                one_line=parsed.one_line,
                selected=0,
                model=call.model,
                scored_at=scored_at,
            ),
        )
        results.append((job.id, profile))

    conn.commit()
    return results


def select_top_n(rows: list[RankableScore], daily_cap: int | None) -> set[int]:
    """daily_cap is None today, deliberately (config/filters.yaml, D23 in
    docs/decisions.md: never calibrated against real day-over-day
    inflow, only a single-snapshot backlog exists). When None, every
    scored row is selected -- the cut is genuinely undefined until a
    real cap is calibrated, not an invented placeholder N."""
    if daily_cap is None:
        return {r.job_id for r in rows}
    ranked = sorted(rows, key=lambda r: (-r.score, r.first_seen_at))
    return {r.job_id for r in ranked[:daily_cap]}


def apply_relevance_cutoff(
    conn: sqlite3.Connection, profile: str, daily_cap: int | None
) -> int:
    rows = list_relevance_scores_for_cutoff(conn, profile)
    selected = select_top_n(rows, daily_cap)
    update_relevance_selection(conn, profile, selected)
    conn.commit()
    return len(selected)


# ---------------------------------------------------------------------------
# CLI: uv run python -m jobengine.pipeline.relevance {score,calibrate}
# ---------------------------------------------------------------------------


def _db_path() -> Path:
    """JOBENGINE_DB_PATH overrides DEFAULT_DB_PATH, same override this
    project already uses for web/app.py -- lets score/calibrate be
    pointed at a scratch copy for validation without touching the real
    data/jobengine.db (hard rule 13)."""
    override = os.environ.get("JOBENGINE_DB_PATH")
    return Path(override) if override else DEFAULT_DB_PATH


def _cmd_score(args: argparse.Namespace) -> int:
    conn = connect(_db_path())
    filter_config = load_filter_config()
    relevance_config = load_relevance_config()
    llm_config = load_llm_config()
    bank = load_bank(DEFAULT_BANK_PATH)
    profile_registry = load_profile_config()

    query = "SELECT * FROM jobs WHERE closed_at IS NULL"
    if relevance_config.freshness_window_days is not None:
        query += (
            f" AND first_seen_at >= datetime('now', "
            f"'-{relevance_config.freshness_window_days} days')"
        )
    if args.limit:
        query += f" LIMIT {int(args.limit)}"

    rows = conn.execute(query).fetchall()
    scored = 0
    started_at = datetime.now(UTC).isoformat()
    for row in rows:
        job = Job(**dict(row))
        asyncio.run(
            score_job(
                conn,
                job,
                filter_config,
                relevance_config,
                llm_config,
                bank,
                profile_registry=profile_registry,
            )
        )
        scored += 1

    selected_by_profile = {}
    for profile in filter_config.profiles:
        selected_by_profile[profile] = apply_relevance_cutoff(
            conn, profile, filter_config.daily_cap
        )

    record_run(
        conn,
        Run(
            stage="relevance",
            started_at=started_at,
            ended_at=datetime.now(UTC).isoformat(),
            counts=json.dumps(
                {"scored": scored, "selected_by_profile": selected_by_profile}
            ),
        ),
    )
    conn.commit()
    conn.close()
    print(f"scored {scored} jobs; selected: {selected_by_profile}")
    return 0


def _stratified_sample(rows: list, n: int) -> list:
    """Evenly-spaced indices across a score-sorted list, per spec 06's
    "samples 20 scored jobs across the range" -- not random.sample."""
    if len(rows) <= n:
        return rows
    step = len(rows) / n
    return [rows[int(i * step)] for i in range(n)]


def _cmd_calibrate(args: argparse.Namespace) -> int:
    conn = connect(_db_path())
    rows = conn.execute(
        """
        SELECT r.job_id, r.score, r.one_line, j.title
        FROM relevance_scores r JOIN jobs j ON j.id = r.job_id
        WHERE r.profile = ?
        ORDER BY r.score ASC
        """,
        (args.profile,),
    ).fetchall()
    if not rows:
        print(f"No relevance_scores rows yet for profile {args.profile!r}.")
        conn.close()
        return 1

    sample = _stratified_sample(rows, args.n)
    agree = 0
    for row in sample:
        print(f"\n{row['title']}  |  score={row['score']:.0f}  |  {row['one_line']}")
        answer = input("Agree? [y/n]: ").strip().lower()
        if answer.startswith("y"):
            agree += 1

    rate = agree / len(sample)
    print(f"\n{agree}/{len(sample)} = {rate:.1%} agreement (threshold 70%)")
    print("PASS" if rate >= 0.70 else "FAIL")

    insert_model_eval(
        conn,
        ModelEval(
            model=load_llm_config().local.model,
            task="relevance_calibration",
            metric="agreement_rate",
            value=rate,
            passed=rate >= 0.70,
            fixture_version=None,
            run_at=datetime.now(UTC).isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return 0 if rate >= 0.70 else 1


def main() -> None:
    parser = argparse.ArgumentParser(prog="jobengine.pipeline.relevance")
    subparsers = parser.add_subparsers(dest="command", required=True)

    score_parser = subparsers.add_parser("score")
    score_parser.add_argument("--limit", type=int, default=None)

    calibrate_parser = subparsers.add_parser("calibrate")
    calibrate_parser.add_argument(
        "--profile", required=True, choices=sorted(KNOWN_PROFILES)
    )
    calibrate_parser.add_argument("--n", type=int, default=20)

    args = parser.parse_args()
    if args.command == "score":
        raise SystemExit(_cmd_score(args))
    else:
        raise SystemExit(_cmd_calibrate(args))


if __name__ == "__main__":
    main()
