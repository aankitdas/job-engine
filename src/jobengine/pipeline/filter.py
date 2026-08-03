"""B3: deterministic filters + profile routing. See specs/04-sources.md's
"Open item" section and D23 (plus its two addenda) in docs/decisions.md.

No filter-survivor table is persisted: every function here is pure and is
meant to be called live by whichever downstream stage needs it, so a config
edit (config/filters.yaml) never leaves stale results behind.
"""

import json
import re
import sqlite3
from pathlib import Path

import yaml
from pydantic import BaseModel

from jobengine.db.models import Job

DEFAULT_FILTERS_PATH = Path("config/filters.yaml")


class ProfileFilterConfig(BaseModel):
    title_aliases: list[str]
    exclusion_keywords: list[str] = []
    exclusion_override_keywords: list[str] = []


class LocationConfig(BaseModel):
    remote_synonyms: list[str]


class CitizenshipClearanceConfig(BaseModel):
    exclude_phrases: list[str]


class EmploymentTypeConfig(BaseModel):
    exclude_ashby_types: list[str]
    exclude_title_keywords: list[str]


class FilterConfig(BaseModel):
    profiles: dict[str, ProfileFilterConfig]
    location: LocationConfig
    citizenship_clearance: CitizenshipClearanceConfig
    employment_type: EmploymentTypeConfig
    daily_cap: int | None = None


def load_filter_config(path: Path = DEFAULT_FILTERS_PATH) -> FilterConfig:
    with open(path) as f:
        data = yaml.safe_load(f)
    return FilterConfig(**data)


def _phrase_matches(phrase: str, text_lower: str) -> bool:
    """A single-word phrase matches on word boundaries, so "engineer" does not
    match inside "engineering". A multi-word phrase matches as a plain
    substring, since its own spaces already delimit word boundaries.
    """
    phrase = phrase.lower()
    if " " not in phrase:
        return re.search(rf"\b{re.escape(phrase)}\b", text_lower) is not None
    return phrase in text_lower


def matches_profiles(job: Job, config: FilterConfig) -> list[str]:
    title_lower = job.title.lower()
    matched = []
    for profile, profile_config in config.profiles.items():
        if not any(
            _phrase_matches(alias, title_lower)
            for alias in profile_config.title_aliases
        ):
            continue
        hit_exclusion = any(
            _phrase_matches(keyword, title_lower)
            for keyword in profile_config.exclusion_keywords
        )
        overridden = any(
            _phrase_matches(keyword, title_lower)
            for keyword in profile_config.exclusion_override_keywords
        )
        if hit_exclusion and not overridden:
            continue
        matched.append(profile)
    return matched


def is_remote(job: Job, config: FilterConfig) -> bool:
    if job.remote is not None:
        return bool(job.remote)
    if not job.location_raw:
        return False
    location_lower = job.location_raw.lower()
    return any(
        _phrase_matches(synonym, location_lower)
        for synonym in config.location.remote_synonyms
    )


def is_excluded_employment_type(job: Job, config: FilterConfig) -> bool:
    if job.ats == "ashby" and job.raw_json:
        try:
            raw = json.loads(job.raw_json)
        except json.JSONDecodeError:
            raw = {}
        if raw.get("employmentType") in config.employment_type.exclude_ashby_types:
            return True
    title_lower = job.title.lower()
    return any(
        _phrase_matches(keyword, title_lower)
        for keyword in config.employment_type.exclude_title_keywords
    )


def is_already_applied(conn: sqlite3.Connection, job_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM applications WHERE job_id = ? LIMIT 1", (job_id,)
    ).fetchone()
    return row is not None


def is_citizenship_or_clearance_required(
    description: str | None, config: FilterConfig
) -> bool:
    if not description:
        return False
    description_lower = description.lower()
    return any(
        _phrase_matches(phrase, description_lower)
        for phrase in config.citizenship_clearance.exclude_phrases
    )
