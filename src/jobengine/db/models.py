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
