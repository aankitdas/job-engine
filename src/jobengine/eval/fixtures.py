"""C2 eval fixture loader. See specs/07-model-eval.md and specs/00-data-model.md's
human_labels table. This module only loads the hand-labelled fixture YAML into
human_labels; no relevance scorer, keyword extractor, or comparison logic lives
here, that's the harness/tasks/report work spec 07 describes separately.
"""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel

DEFAULT_HUMAN_LABELS_PATH = Path("tests/fixtures/eval/human_labels.yaml")

PROFILES = ("ai_ml_engineer", "software_engineer", "data_scientist")


class RelevanceLabels(BaseModel):
    ai_ml_engineer: int | None = None
    software_engineer: int | None = None
    data_scientist: int | None = None


class HumanLabelEntry(BaseModel):
    job_id: int
    title: str
    company: str
    description: str
    relevance: RelevanceLabels
    required_keywords: list[str] | None = None


def load_human_labels(
    conn: sqlite3.Connection, path: Path = DEFAULT_HUMAN_LABELS_PATH
) -> int:
    """Reads the human-labelled eval fixture YAML and writes rows into
    human_labels (job_id, profile, relevance, keywords, labelled_at).

    A job entry with every profile's relevance still null (not yet
    labelled) is skipped entirely, not written as a junk row. Within a
    labelled job, only profiles with a non-null relevance get a row.
    required_keywords is a single flat list per job, but human_labels is
    keyed per (job_id, profile) like the rest of this schema
    (job_analysis, keyword_corpus), so it's attached only to whichever
    profile(s) have that job's highest relevance score, ties included;
    a keyword list only makes sense in the context of the profile the
    JD actually matches, not one it scored near zero on.

    Safe to re-run as the fixture gets filled in over multiple sittings:
    rows are upserted on the (job_id, profile) primary key, so a later run
    with revised scores updates in place rather than erroring or
    duplicating.

    Returns the number of rows written (inserted or updated).
    """
    with open(path) as f:
        raw = yaml.safe_load(f)
    entries = [HumanLabelEntry(**item) for item in raw]

    labelled_at = datetime.now(UTC).isoformat()
    written = 0
    for entry in entries:
        relevance_by_profile = {
            profile: value
            for profile, value in entry.relevance.model_dump().items()
            if value is not None
        }
        if not relevance_by_profile:
            continue

        max_relevance = max(relevance_by_profile.values())
        top_profiles = {
            profile
            for profile, value in relevance_by_profile.items()
            if value == max_relevance
        }

        for profile, relevance in relevance_by_profile.items():
            keywords = None
            if entry.required_keywords is not None and profile in top_profiles:
                keywords = json.dumps(entry.required_keywords)
            conn.execute(
                """
                INSERT INTO human_labels (job_id, profile, relevance, keywords, labelled_at)
                VALUES (:job_id, :profile, :relevance, :keywords, :labelled_at)
                ON CONFLICT (job_id, profile) DO UPDATE SET
                    relevance = excluded.relevance,
                    keywords = excluded.keywords,
                    labelled_at = excluded.labelled_at
                """,
                {
                    "job_id": entry.job_id,
                    "profile": profile,
                    "relevance": relevance,
                    "keywords": keywords,
                    "labelled_at": labelled_at,
                },
            )
            written += 1

    conn.commit()
    return written
