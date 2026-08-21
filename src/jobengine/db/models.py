"""Pydantic models and typed accessors for the job-engine schema.

No business logic here. See specs/00-data-model.md for the schema this
mirrors.
"""

import sqlite3
from typing import NamedTuple

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


class BaseResume(BaseModel):
    id: int | None = None
    profile: str
    version: int
    selection: str
    section_order: str
    docx_path: str | None = None
    pdf_path: str | None = None
    rubric: str | None = None
    generated_at: str
    retired_at: str | None = None


class JobResumeVariant(BaseModel):
    id: int | None = None
    job_id: int
    profile: str
    base_resume_id: int
    patch_tiers_applied: str | None = None
    bullet_ids: str | None = None
    selection_hash: str
    docx_path: str | None = None
    pdf_path: str | None = None
    score: float | None = None
    coverage: float | None = None
    front_load: float | None = None
    passed: bool | None = None
    accepted: bool | None = None
    review_status: str = "pending"
    reviewed_at: str | None = None
    created_at: str


class GapLedgerRow(BaseModel):
    id: int | None = None
    profile: str
    keyword: str
    job_id: int
    first_logged_at: str


class RubricResultRow(BaseModel):
    id: int | None = None
    job_resume_variant_id: int
    rule_id: str
    passed: bool
    measurement: float | None = None
    detail: str | None = None
    evaluated_at: str


class Application(BaseModel):
    id: int | None = None
    job_id: int
    resume_variant_id: int
    autonomy_level: int = 0
    status: str
    submitted_at: str | None = None
    payload_path: str | None = None
    screenshot_path: str | None = None
    confirmation_path: str | None = None
    notes: str | None = None


class QueueEntry(BaseModel):
    """One row for F1's queue list view: a job_resume_variant joined
    with its job. Presentation-shaped, not a schema table."""

    variant_id: int
    job_id: int
    profile: str
    title: str
    company_slug: str
    score: float | None = None
    passed: bool | None = None
    review_status: str


class ApplicationEntry(BaseModel):
    """One row for GET /'s "Approved" section: an applications row
    joined with its job and job_resume_variant. applications, not
    review_status='approved', is authoritative for "what have I applied
    to" -- pipeline/filter.py's is_already_applied() already keys off
    this table, and it carries submission-specific fields
    job_resume_variants doesn't. Presentation-shaped, not a schema
    table."""

    application_id: int
    job_id: int
    profile: str
    title: str
    company_slug: str
    apply_url: str | None = None
    docx_path: str | None = None
    status: str


class RelevanceScore(BaseModel):
    job_id: int
    profile: str
    score: float
    seniority_match: str | None = None
    keyword_hits: str | None = None
    disqualifiers: str | None = None
    one_line: str | None = None
    selected: int = 0
    model: str | None = None
    scored_at: str


class RankableScore(NamedTuple):
    job_id: int
    score: float
    first_seen_at: str


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


def get_job_by_id(conn: sqlite3.Connection, job_id: int) -> Job | None:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    return Job(**dict(row))


def get_job_analysis(
    conn: sqlite3.Connection, job_id: int, profile: str
) -> JobAnalysis | None:
    row = conn.execute(
        "SELECT * FROM job_analysis WHERE job_id = ? AND profile = ?",
        (job_id, profile),
    ).fetchone()
    if row is None:
        return None
    return JobAnalysis(**dict(row))


def has_job_analysis(conn: sqlite3.Connection, job_id: int) -> bool:
    """Any profile's row counts: analyze_job() (C3) makes one LLM call
    per job and fans it out to every matched profile in that same call,
    so "any row exists" already means "this job's extraction is done,"
    not just done for one profile."""
    row = conn.execute(
        "SELECT 1 FROM job_analysis WHERE job_id = ? LIMIT 1", (job_id,)
    ).fetchone()
    return row is not None


def list_unscored_open_jobs(conn: sqlite3.Connection, window_days: int) -> list[Job]:
    """Open jobs (closed_at IS NULL) first seen within window_days with
    no relevance_scores row for any profile yet -- the incremental
    candidate set pipeline/batch.py's daily orchestrator scans, so a job
    already scored by a prior run is never re-sent to the LLM by a later
    one. Relies on score_job()'s own atomic per-call fan-out (every
    currently matched profile is scored in one call, never partially)
    for "has any row" to also mean "has every row it should." Ordered by
    (first_seen_at, id) for deterministic batch processing order, not
    SQLite's unspecified default."""
    rows = conn.execute(
        """
        SELECT * FROM jobs j
        WHERE j.closed_at IS NULL
        AND j.first_seen_at >= datetime('now', ?)
        AND NOT EXISTS (
            SELECT 1 FROM relevance_scores r WHERE r.job_id = j.id
        )
        ORDER BY j.first_seen_at, j.id
        """,
        (f"-{window_days} days",),
    ).fetchall()
    return [Job(**dict(row)) for row in rows]


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


def insert_base_resume(conn: sqlite3.Connection, base_resume: BaseResume) -> int:
    """Append-only, like outcomes/model_evals: a new version is a new row,
    never an update to a prior one (spec 09: "Versioned, never
    overwritten. Keep at least the previous two versions live.")."""
    cursor = conn.execute(
        """
        INSERT INTO base_resumes (
            profile, version, selection, section_order, docx_path, pdf_path,
            rubric, generated_at, retired_at
        ) VALUES (
            :profile, :version, :selection, :section_order, :docx_path, :pdf_path,
            :rubric, :generated_at, :retired_at
        )
        RETURNING id
        """,
        base_resume.model_dump(exclude={"id"}),
    )
    return cursor.fetchone()[0]


def latest_base_resume_version(conn: sqlite3.Connection, profile: str) -> int:
    """0 if no base_resumes row exists yet for this profile, so callers can
    always write `version=latest_base_resume_version(conn, profile) + 1`
    uniformly, including the very first one."""
    row = conn.execute(
        "SELECT MAX(version) AS v FROM base_resumes WHERE profile = ?", (profile,)
    ).fetchone()
    return row["v"] or 0


def latest_base_resume(conn: sqlite3.Connection, profile: str) -> BaseResume | None:
    """The full latest row (id included), for callers like queue/orchestrate.py
    that need the FK, not just the version number latest_base_resume_version()
    returns."""
    row = conn.execute(
        "SELECT * FROM base_resumes WHERE profile = ? ORDER BY version DESC LIMIT 1",
        (profile,),
    ).fetchone()
    if row is None:
        return None
    return BaseResume(**dict(row))


def insert_job_resume_variant(
    conn: sqlite3.Connection, variant: JobResumeVariant
) -> int:
    """Append-only: one row per (job_id, profile), enforced by
    idx_job_resume_variants_job_profile in schema.sql, not by this
    function. Callers (queue/orchestrate.py) check
    get_job_resume_variant() first; a duplicate insert here is a caller
    bug, not something this function silently upserts around."""
    cursor = conn.execute(
        """
        INSERT INTO job_resume_variants (
            job_id, profile, base_resume_id, patch_tiers_applied, bullet_ids,
            selection_hash, docx_path, pdf_path, score, coverage, front_load,
            passed, accepted, review_status, reviewed_at, created_at
        ) VALUES (
            :job_id, :profile, :base_resume_id, :patch_tiers_applied, :bullet_ids,
            :selection_hash, :docx_path, :pdf_path, :score, :coverage, :front_load,
            :passed, :accepted, :review_status, :reviewed_at, :created_at
        )
        RETURNING id
        """,
        variant.model_dump(exclude={"id"}),
    )
    return cursor.fetchone()[0]


def get_job_resume_variant(
    conn: sqlite3.Connection, job_id: int, profile: str
) -> JobResumeVariant | None:
    row = conn.execute(
        "SELECT * FROM job_resume_variants WHERE job_id = ? AND profile = ?",
        (job_id, profile),
    ).fetchone()
    if row is None:
        return None
    return JobResumeVariant(**dict(row))


def find_job_resume_variant_by_hash(
    conn: sqlite3.Connection, base_resume_id: int, selection_hash: str
) -> JobResumeVariant | None:
    """The file-reuse lookup: is there already a rendered docx/pdf for
    this exact (base_resume_id, selection_hash) pair, from some other
    job? See D-something in docs/decisions.md and schema.sql's comment
    above idx_job_resume_variants_job_profile for why this is an
    app-level lookup rather than the table's row-uniqueness constraint."""
    row = conn.execute(
        "SELECT * FROM job_resume_variants "
        "WHERE base_resume_id = ? AND selection_hash = ? LIMIT 1",
        (base_resume_id, selection_hash),
    ).fetchone()
    if row is None:
        return None
    return JobResumeVariant(**dict(row))


def update_review_status(
    conn: sqlite3.Connection,
    variant_id: int,
    status: str,
    reviewed_at: str,
    accepted: bool | None = None,
) -> None:
    """accepted defaults to None (leave untouched, via COALESCE) so the
    existing 4-positional-arg callers (reject(), approve()'s clean path)
    don't clobber it. D42: approve()'s soft-failure override path passes
    accepted=True."""
    conn.execute(
        "UPDATE job_resume_variants SET review_status = ?, reviewed_at = ?, "
        "accepted = COALESCE(?, accepted) WHERE id = ?",
        (status, reviewed_at, accepted, variant_id),
    )


def insert_rubric_results(
    conn: sqlite3.Connection, results: list[RubricResultRow]
) -> None:
    conn.executemany(
        """
        INSERT INTO rubric_results (
            job_resume_variant_id, rule_id, passed, measurement, detail, evaluated_at
        ) VALUES (
            :job_resume_variant_id, :rule_id, :passed, :measurement, :detail, :evaluated_at
        )
        """,
        [r.model_dump(exclude={"id"}) for r in results],
    )


def get_rubric_results(
    conn: sqlite3.Connection, job_resume_variant_id: int
) -> list[RubricResultRow]:
    rows = conn.execute(
        "SELECT * FROM rubric_results WHERE job_resume_variant_id = ?",
        (job_resume_variant_id,),
    ).fetchall()
    return [RubricResultRow(**dict(row)) for row in rows]


def insert_gap_ledger_entries(
    conn: sqlite3.Connection, rows: list[GapLedgerRow]
) -> None:
    """D43 (P4): one plain INSERT per real (job, profile, keyword)
    occurrence, no dedup/UNIQUE -- see queue/orchestrate.py's P4 site and
    docs/decisions.md D43 for why: the useful query (uncovered keywords
    ranked by distinct job count) needs one row per occurrence."""
    conn.executemany(
        """
        INSERT INTO gap_ledger (profile, keyword, job_id, first_logged_at)
        VALUES (:profile, :keyword, :job_id, :first_logged_at)
        """,
        [r.model_dump(exclude={"id"}) for r in rows],
    )


def insert_application(conn: sqlite3.Connection, application: Application) -> int:
    """Created only on review approval (queue/orchestrate.py never calls
    this) -- see docs/decisions.md's F1 entry for why applications rows
    don't exist for pending/rejected review state: is_already_applied()
    (pipeline/filter.py) checks for any applications row regardless of
    status, so creating one earlier than a real approval would silently
    corrupt that already-shipped B3 filter."""
    cursor = conn.execute(
        """
        INSERT INTO applications (
            job_id, resume_variant_id, autonomy_level, status, submitted_at,
            payload_path, screenshot_path, confirmation_path, notes
        ) VALUES (
            :job_id, :resume_variant_id, :autonomy_level, :status, :submitted_at,
            :payload_path, :screenshot_path, :confirmation_path, :notes
        )
        RETURNING id
        """,
        application.model_dump(exclude={"id"}),
    )
    return cursor.fetchone()[0]


def list_pending_review_queue(conn: sqlite3.Connection) -> list[QueueEntry]:
    rows = conn.execute(
        """
        SELECT
            v.id AS variant_id, v.job_id AS job_id, v.profile AS profile,
            j.title AS title, j.company_slug AS company_slug,
            v.score AS score, v.passed AS passed, v.review_status AS review_status
        FROM job_resume_variants v
        JOIN jobs j ON j.id = v.job_id
        WHERE v.review_status = 'pending'
        ORDER BY v.created_at DESC
        """
    ).fetchall()
    return [QueueEntry(**dict(row)) for row in rows]


def list_existing_variant_pairs(conn: sqlite3.Connection) -> set[tuple[int, str]]:
    """Every (job_id, profile) pair that already has a job_resume_variant
    row, any review_status. Used by the queue list route to tell which
    B3-surviving pairs are genuinely new (never triggered) versus
    already pending/approved/rejected, so a decided job doesn't
    reappear as "new" once it's been reviewed."""
    rows = conn.execute("SELECT job_id, profile FROM job_resume_variants").fetchall()
    return {(row["job_id"], row["profile"]) for row in rows}


def list_applications(conn: sqlite3.Connection) -> list[ApplicationEntry]:
    """Every applications row, joined to its job and job_resume_variant,
    for GET /'s "Approved" section. Deliberately unscoped by any date
    window (unlike _recent_open_jobs()/_new_pairs() in web/app.py): an
    approved-but-unsubmitted job must not silently age out of this list,
    that is the exact problem this section exists to fix."""
    rows = conn.execute(
        """
        SELECT
            a.id AS application_id, a.job_id AS job_id, v.profile AS profile,
            j.title AS title, j.company_slug AS company_slug,
            j.apply_url AS apply_url, v.docx_path AS docx_path,
            a.status AS status
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        JOIN job_resume_variants v ON v.id = a.resume_variant_id
        ORDER BY a.id DESC
        """
    ).fetchall()
    return [ApplicationEntry(**dict(row)) for row in rows]


def upsert_relevance_score(conn: sqlite3.Connection, score: RelevanceScore) -> None:
    """Insert or replace on (job_id, profile) conflict, matching
    upsert_job_analysis's convention. No RETURNING id: relevance_scores'
    primary key is the (job_id, profile) composite itself (schema.sql),
    no surrogate id column, same shape as upsert_company's (slug, ats)
    conflict target."""
    conn.execute(
        """
        INSERT INTO relevance_scores (
            job_id, profile, score, seniority_match, keyword_hits,
            disqualifiers, one_line, selected, model, scored_at
        ) VALUES (
            :job_id, :profile, :score, :seniority_match, :keyword_hits,
            :disqualifiers, :one_line, :selected, :model, :scored_at
        )
        ON CONFLICT (job_id, profile) DO UPDATE SET
            score = excluded.score,
            seniority_match = excluded.seniority_match,
            keyword_hits = excluded.keyword_hits,
            disqualifiers = excluded.disqualifiers,
            one_line = excluded.one_line,
            selected = excluded.selected,
            model = excluded.model,
            scored_at = excluded.scored_at
        """,
        score.model_dump(),
    )


def get_relevance_score(
    conn: sqlite3.Connection, job_id: int, profile: str
) -> RelevanceScore | None:
    row = conn.execute(
        "SELECT * FROM relevance_scores WHERE job_id = ? AND profile = ?",
        (job_id, profile),
    ).fetchone()
    if row is None:
        return None
    return RelevanceScore(**dict(row))


def list_relevance_scores_for_cutoff(
    conn: sqlite3.Connection, profile: str
) -> list[RankableScore]:
    """Every scored row for a profile, joined to jobs for the
    first_seen_at tiebreak select_top_n() needs (relevance_scores itself
    has no first_seen_at column)."""
    rows = conn.execute(
        """
        SELECT r.job_id AS job_id, r.score AS score, j.first_seen_at AS first_seen_at
        FROM relevance_scores r JOIN jobs j ON j.id = r.job_id
        WHERE r.profile = ?
        """,
        (profile,),
    ).fetchall()
    return [RankableScore(r["job_id"], r["score"], r["first_seen_at"]) for r in rows]


def update_relevance_selection(
    conn: sqlite3.Connection, profile: str, selected_job_ids: set[int]
) -> None:
    """Resets selected=0 for every row of this profile, then sets
    selected=1 for exactly selected_job_ids. Idempotent and safe to
    re-run after a daily_cap change or a rescoring: a job that was
    selected before but isn't in this run's top-N is demoted, not left
    stale."""
    conn.execute(
        "UPDATE relevance_scores SET selected = 0 WHERE profile = ?", (profile,)
    )
    if selected_job_ids:
        conn.executemany(
            "UPDATE relevance_scores SET selected = 1 WHERE job_id = ? AND profile = ?",
            [(job_id, profile) for job_id in selected_job_ids],
        )
