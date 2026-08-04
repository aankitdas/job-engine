"""Pydantic models and typed accessors for the job-engine schema.

No business logic here. See specs/00-data-model.md for the schema this
mirrors.
"""

import sqlite3

from pydantic import BaseModel


class Company(BaseModel):
    slug: str
    ats: str
    name: str
    status: str
    source: str
    first_seen_at: str
    last_ok_at: str | None = None
    last_checked_at: str | None = None
    consecutive_failures: int = 0


class Job(BaseModel):
    id: int | None = None
    ats: str
    company_slug: str
    ats_job_id: str
    title: str
    location_raw: str | None = None
    remote: int | None = None
    department: str | None = None
    url: str | None = None
    apply_url: str | None = None
    compensation_raw: str | None = None
    description: str | None = None
    content_hash: str | None = None
    ats_date: str | None = None
    first_seen_at: str
    last_seen_at: str
    closed_at: str | None = None
    raw_json: str | None = None


class Outcome(BaseModel):
    id: int | None = None
    application_id: int
    status: str
    occurred_at: str
    note: str | None = None


class Run(BaseModel):
    id: int | None = None
    stage: str
    started_at: str
    ended_at: str | None = None
    counts: str | None = None
    cost_usd: float | None = None
    errors: str | None = None


class JobAnalysis(BaseModel):
    id: int | None = None
    job_id: int
    profile: str
    canonical_title: str | None = None
    seniority: str | None = None
    required_keywords: str | None = None
    preferred_keywords: str | None = None
    tech_stack: str | None = None
    jd_quality: str | None = None
    keyword_hash: str | None = None
    analyzed_at: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float


class ModelEval(BaseModel):
    id: int | None = None
    model: str
    task: str
    metric: str
    value: float
    passed: bool
    fixture_version: str | None = None
    run_at: str


def upsert_company(conn: sqlite3.Connection, company: Company) -> None:
    """Insert a company, or update it on (slug, ats) conflict.

    first_seen_at is intentionally absent from the SET clause: a re-sync of
    an existing company must never move it. The trg_companies_first_seen_at_immutable
    trigger backstops this against any other write path.
    """
    conn.execute(
        """
        INSERT INTO companies (
            slug, ats, name, status, source, first_seen_at,
            last_ok_at, last_checked_at, consecutive_failures
        ) VALUES (
            :slug, :ats, :name, :status, :source, :first_seen_at,
            :last_ok_at, :last_checked_at, :consecutive_failures
        )
        ON CONFLICT (slug, ats) DO UPDATE SET
            name = excluded.name,
            status = excluded.status,
            source = excluded.source,
            last_ok_at = excluded.last_ok_at,
            last_checked_at = excluded.last_checked_at,
            consecutive_failures = excluded.consecutive_failures
        """,
        company.model_dump(),
    )


def upsert_job(conn: sqlite3.Connection, job: Job) -> int:
    """Insert a job, or update it on (ats, company_slug, ats_job_id) conflict.

    first_seen_at is intentionally absent from the SET clause: a re-sync of
    an existing job must never move it, regardless of what value the caller
    computed. The trg_jobs_first_seen_at_immutable trigger backstops this
    against any other write path.
    """
    cursor = conn.execute(
        """
        INSERT INTO jobs (
            ats, company_slug, ats_job_id, title, location_raw, remote,
            department, url, apply_url, compensation_raw, description,
            content_hash, ats_date, first_seen_at, last_seen_at, closed_at,
            raw_json
        ) VALUES (
            :ats, :company_slug, :ats_job_id, :title, :location_raw, :remote,
            :department, :url, :apply_url, :compensation_raw, :description,
            :content_hash, :ats_date, :first_seen_at, :last_seen_at, :closed_at,
            :raw_json
        )
        ON CONFLICT (ats, company_slug, ats_job_id) DO UPDATE SET
            title = excluded.title,
            location_raw = excluded.location_raw,
            remote = excluded.remote,
            department = excluded.department,
            url = excluded.url,
            apply_url = excluded.apply_url,
            compensation_raw = excluded.compensation_raw,
            description = excluded.description,
            content_hash = excluded.content_hash,
            ats_date = excluded.ats_date,
            last_seen_at = excluded.last_seen_at,
            closed_at = excluded.closed_at,
            raw_json = excluded.raw_json
        RETURNING id
        """,
        job.model_dump(exclude={"id"}),
    )
    return cursor.fetchone()[0]


def get_job(
    conn: sqlite3.Connection, ats: str, company_slug: str, ats_job_id: str
) -> Job | None:
    row = conn.execute(
        "SELECT * FROM jobs WHERE ats = ? AND company_slug = ? AND ats_job_id = ?",
        (ats, company_slug, ats_job_id),
    ).fetchone()
    if row is None:
        return None
    return Job(**dict(row))


def get_company(conn: sqlite3.Connection, slug: str, ats: str) -> Company | None:
    row = conn.execute(
        "SELECT * FROM companies WHERE slug = ? AND ats = ?",
        (slug, ats),
    ).fetchone()
    if row is None:
        return None
    return Company(**dict(row))


def list_active_companies(conn: sqlite3.Connection) -> list[Company]:
    rows = conn.execute("SELECT * FROM companies WHERE status = 'active'").fetchall()
    return [Company(**dict(row)) for row in rows]


def close_missing_jobs(
    conn: sqlite3.Connection,
    ats: str,
    company_slug: str,
    seen_ats_job_ids: set[str],
    closed_at: str,
) -> int:
    """Set closed_at on every open job for this company not in seen_ats_job_ids.

    Diffs the id sets in Python and updates one row per missing job instead
    of a single `NOT IN (...)` query: a large board (Ashby's OpenAI listing
    ran 750+ postings during B1's live check) risks SQLite's per-statement
    bound-parameter ceiling with a single IN/NOT IN clause, and chunking
    that clause is more code than just diffing two id sets directly.
    """
    open_ids = {
        row[0]
        for row in conn.execute(
            "SELECT ats_job_id FROM jobs "
            "WHERE ats = ? AND company_slug = ? AND closed_at IS NULL",
            (ats, company_slug),
        ).fetchall()
    }
    missing = open_ids - seen_ats_job_ids
    if not missing:
        return 0
    conn.executemany(
        "UPDATE jobs SET closed_at = ? "
        "WHERE ats = ? AND company_slug = ? AND ats_job_id = ?",
        [(closed_at, ats, company_slug, job_id) for job_id in missing],
    )
    return len(missing)


def insert_outcome(conn: sqlite3.Connection, outcome: Outcome) -> int:
    cursor = conn.execute(
        """
        INSERT INTO outcomes (application_id, status, occurred_at, note)
        VALUES (:application_id, :status, :occurred_at, :note)
        RETURNING id
        """,
        outcome.model_dump(exclude={"id"}),
    )
    return cursor.fetchone()[0]


def record_run(conn: sqlite3.Connection, run: Run) -> int:
    cursor = conn.execute(
        """
        INSERT INTO runs (stage, started_at, ended_at, counts, cost_usd, errors)
        VALUES (:stage, :started_at, :ended_at, :counts, :cost_usd, :errors)
        RETURNING id
        """,
        run.model_dump(exclude={"id"}),
    )
    return cursor.fetchone()[0]


def upsert_job_analysis(conn: sqlite3.Connection, analysis: JobAnalysis) -> int:
    """Insert a job's analysis, or replace it on (job_id, profile) conflict.

    A re-run overwrites the prior analysis rather than accumulating
    history, matching relevance_scores'/human_labels' convention
    (idx_job_analysis_job_profile in schema.sql is the unique index this
    relies on; job_analysis has no composite primary key).
    """
    cursor = conn.execute(
        """
        INSERT INTO job_analysis (
            job_id, profile, canonical_title, seniority, required_keywords,
            preferred_keywords, tech_stack, jd_quality, keyword_hash,
            analyzed_at, model, input_tokens, output_tokens, cost_usd
        ) VALUES (
            :job_id, :profile, :canonical_title, :seniority, :required_keywords,
            :preferred_keywords, :tech_stack, :jd_quality, :keyword_hash,
            :analyzed_at, :model, :input_tokens, :output_tokens, :cost_usd
        )
        ON CONFLICT (job_id, profile) DO UPDATE SET
            canonical_title = excluded.canonical_title,
            seniority = excluded.seniority,
            required_keywords = excluded.required_keywords,
            preferred_keywords = excluded.preferred_keywords,
            tech_stack = excluded.tech_stack,
            jd_quality = excluded.jd_quality,
            keyword_hash = excluded.keyword_hash,
            analyzed_at = excluded.analyzed_at,
            model = excluded.model,
            input_tokens = excluded.input_tokens,
            output_tokens = excluded.output_tokens,
            cost_usd = excluded.cost_usd
        RETURNING id
        """,
        analysis.model_dump(exclude={"id"}),
    )
    return cursor.fetchone()[0]


def upsert_keyword_corpus_entry(
    conn: sqlite3.Connection, profile: str, keyword: str, seen_at: str
) -> None:
    """Bump a keyword's occurrence count for a profile, or insert it at
    occurrences=1 if new. first_seen_at is set once, on insert, and never
    moves afterward; last_seen_at always advances to seen_at.
    """
    conn.execute(
        """
        INSERT INTO keyword_corpus (profile, keyword, occurrences, first_seen_at, last_seen_at)
        VALUES (:profile, :keyword, 1, :seen_at, :seen_at)
        ON CONFLICT (profile, keyword) DO UPDATE SET
            occurrences = occurrences + 1,
            last_seen_at = excluded.last_seen_at
        """,
        {"profile": profile, "keyword": keyword, "seen_at": seen_at},
    )


def insert_model_eval(conn: sqlite3.Connection, model_eval: ModelEval) -> int:
    cursor = conn.execute(
        """
        INSERT INTO model_evals (model, task, metric, value, passed, fixture_version, run_at)
        VALUES (:model, :task, :metric, :value, :passed, :fixture_version, :run_at)
        RETURNING id
        """,
        model_eval.model_dump(exclude={"id"}),
    )
    return cursor.fetchone()[0]
