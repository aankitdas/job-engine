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
    us_informal_city_abbreviations: list[str] = []
    us_major_city_names: list[str] = []
    non_us_signals: list[str] = []


class CitizenshipClearanceConfig(BaseModel):
    exclude_phrases: list[str]


class SeniorityConfig(BaseModel):
    exclude_title_keywords: list[str]


class EmploymentTypeConfig(BaseModel):
    exclude_ashby_types: list[str]
    exclude_title_keywords: list[str]


class FilterConfig(BaseModel):
    profiles: dict[str, ProfileFilterConfig]
    location: LocationConfig
    seniority: SeniorityConfig
    citizenship_clearance: CitizenshipClearanceConfig
    employment_type: EmploymentTypeConfig
    daily_cap: int | None = None


# The 50 US states plus DC, as 2-letter abbreviations, matched only when
# immediately preceded by a comma ("City, ST") to avoid colliding with
# ordinary English words that happen to be valid state codes (OR, IN) when
# they appear mid-sentence rather than after a place name.
#
# Delaware ("DE") is deliberately excluded: it collides with Germany's ISO
# country code, which appears for real in this data ("Berlin, DE",
# "Hamburg, DE"). No genuine Delaware location exists anywhere in the
# current 3834-job dataset (checked directly), so excluding it costs zero
# real recall today; revisit only if a real Delaware posting needs
# distinguishing from a German one.
US_STATE_ABBREVIATIONS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO",
    "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR",
    "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI",
    "WY", "DC",
}  # fmt: skip

US_STATE_FULL_NAMES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming", "District of Columbia",
]  # fmt: skip

US_COUNTRY_TOKENS = ["united states", "usa", "u.s.a", "u.s.", "us"]

_STATE_CODE_PATTERN = re.compile(
    r",\s*(" + "|".join(sorted(US_STATE_ABBREVIATIONS)) + r")\b", re.IGNORECASE
)


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


def is_above_target_seniority(title: str, config: FilterConfig) -> bool:
    title_lower = title.lower()
    return any(
        _phrase_matches(keyword, title_lower)
        for keyword in config.seniority.exclude_title_keywords
    )


def _has_us_signal(text_lower: str, config: FilterConfig) -> bool:
    if _STATE_CODE_PATTERN.search(text_lower):
        return True
    if any(_phrase_matches(name, text_lower) for name in US_STATE_FULL_NAMES):
        return True
    if any(_phrase_matches(token, text_lower) for token in US_COUNTRY_TOKENS):
        return True
    if any(
        _phrase_matches(abbrev, text_lower)
        for abbrev in config.location.us_informal_city_abbreviations
    ):
        return True
    return any(
        _phrase_matches(name, text_lower)
        for name in config.location.us_major_city_names
    )


def _has_non_us_signal(text_lower: str, config: FilterConfig) -> bool:
    return any(
        _phrase_matches(signal, text_lower) for signal in config.location.non_us_signals
    )


def classify_location(job: Job, config: FilterConfig) -> str:
    """Returns one of "remote", "us_match", "non_us_match", "empty_location",
    or "ambiguous_unparseable". The last two are the cases callers should
    log rather than silently drop: an unrecognized location_raw value is
    not evidence either way, so it must be visible, not defaulted.
    """
    if is_remote(job, config):
        return "remote"
    if not job.location_raw or not job.location_raw.strip():
        return "empty_location"
    text_lower = job.location_raw.lower()
    if _has_us_signal(text_lower, config):
        return "us_match"
    if _has_non_us_signal(text_lower, config):
        return "non_us_match"
    return "ambiguous_unparseable"


def is_us_location(job: Job, config: FilterConfig) -> bool:
    return classify_location(job, config) in ("remote", "us_match")
