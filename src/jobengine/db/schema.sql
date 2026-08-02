-- Job Engine schema. See specs/00-data-model.md.
-- All statements are idempotent (IF NOT EXISTS) so `init` can run repeatedly.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS companies (
    slug                  TEXT NOT NULL,
    ats                   TEXT NOT NULL CHECK (ats IN ('greenhouse', 'ashby')),
    name                  TEXT NOT NULL,
    status                TEXT NOT NULL CHECK (status IN ('active', 'dead', 'unverified')),
    source                TEXT NOT NULL CHECK (source IN ('seed', 'harvest', 'manual')),
    first_seen_at         TEXT NOT NULL,
    last_ok_at            TEXT,
    last_checked_at       TEXT,
    consecutive_failures  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (slug, ats)
);

CREATE TABLE IF NOT EXISTS jobs (
    id                INTEGER PRIMARY KEY,
    ats               TEXT NOT NULL,
    company_slug      TEXT NOT NULL,
    ats_job_id        TEXT NOT NULL,
    title             TEXT NOT NULL,
    location_raw      TEXT,
    remote            INTEGER,
    department        TEXT,
    url               TEXT,
    apply_url         TEXT,
    compensation_raw  TEXT,
    description       TEXT,
    content_hash      TEXT,
    ats_date          TEXT,
    first_seen_at     TEXT NOT NULL,
    last_seen_at      TEXT NOT NULL,
    closed_at         TEXT,
    raw_json          TEXT,
    UNIQUE (ats, company_slug, ats_job_id),
    FOREIGN KEY (company_slug, ats) REFERENCES companies (slug, ats)
);

CREATE TABLE IF NOT EXISTS job_analysis (
    id                  INTEGER PRIMARY KEY,
    job_id              INTEGER NOT NULL REFERENCES jobs (id),
    profile             TEXT NOT NULL,
    canonical_title     TEXT,
    seniority           TEXT,
    required_keywords   TEXT,
    preferred_keywords  TEXT,
    tech_stack          TEXT,
    jd_quality          TEXT CHECK (jd_quality IN ('good', 'bad')),
    keyword_hash        TEXT,
    analyzed_at         TEXT,
    model               TEXT,
    input_tokens        INTEGER,
    output_tokens       INTEGER,
    cost_usd            REAL
);

CREATE TABLE IF NOT EXISTS keyword_corpus (
    profile        TEXT NOT NULL,
    keyword        TEXT NOT NULL,
    occurrences    INTEGER NOT NULL DEFAULT 0,
    first_seen_at  TEXT NOT NULL,
    last_seen_at   TEXT NOT NULL,
    PRIMARY KEY (profile, keyword)
);

CREATE TABLE IF NOT EXISTS clusters (
    id            INTEGER PRIMARY KEY,
    profile       TEXT NOT NULL,
    keyword_hash  TEXT NOT NULL,
    job_count     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS base_resumes (
    id             INTEGER PRIMARY KEY,
    profile        TEXT NOT NULL,
    version        INTEGER NOT NULL,
    selection      TEXT NOT NULL,
    section_order  TEXT NOT NULL,
    docx_path      TEXT,
    pdf_path       TEXT,
    rubric         TEXT,
    generated_at   TEXT NOT NULL,
    retired_at     TEXT
);

CREATE TABLE IF NOT EXISTS job_resume_variants (
    id                  INTEGER PRIMARY KEY,
    job_id              INTEGER NOT NULL REFERENCES jobs (id),
    profile             TEXT NOT NULL,
    base_resume_id      INTEGER NOT NULL REFERENCES base_resumes (id),
    patch_tiers_applied TEXT,
    bullet_ids          TEXT,
    selection_hash      TEXT NOT NULL,
    docx_path           TEXT,
    pdf_path            TEXT,
    score               REAL,
    coverage            REAL,
    front_load          REAL,
    passed              INTEGER,
    accepted            INTEGER,
    created_at          TEXT NOT NULL,
    UNIQUE (base_resume_id, selection_hash)
);

CREATE TABLE IF NOT EXISTS rubric_results (
    id                      INTEGER PRIMARY KEY,
    job_resume_variant_id   INTEGER NOT NULL REFERENCES job_resume_variants (id),
    rule_id                 TEXT NOT NULL,
    passed                  INTEGER NOT NULL,
    measurement             REAL,
    detail                  TEXT,
    evaluated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relevance_scores (
    job_id         INTEGER NOT NULL REFERENCES jobs (id),
    profile        TEXT NOT NULL,
    score          REAL NOT NULL,
    seniority_match TEXT,
    keyword_hits   TEXT,
    disqualifiers  TEXT,
    one_line       TEXT,
    selected       INTEGER NOT NULL DEFAULT 0,
    model          TEXT,
    scored_at      TEXT NOT NULL,
    PRIMARY KEY (job_id, profile)
);

CREATE TABLE IF NOT EXISTS human_labels (
    job_id       INTEGER NOT NULL REFERENCES jobs (id),
    profile      TEXT NOT NULL,
    relevance    REAL,
    keywords     TEXT,
    labelled_at  TEXT NOT NULL,
    PRIMARY KEY (job_id, profile)
);

CREATE TABLE IF NOT EXISTS model_evals (
    id              INTEGER PRIMARY KEY,
    model           TEXT NOT NULL,
    task            TEXT NOT NULL,
    metric          TEXT NOT NULL,
    value           REAL NOT NULL,
    passed          INTEGER NOT NULL,
    fixture_version TEXT,
    run_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gap_ledger (
    id              INTEGER PRIMARY KEY,
    profile         TEXT NOT NULL,
    keyword         TEXT NOT NULL,
    job_id          INTEGER NOT NULL REFERENCES jobs (id),
    first_logged_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applications (
    id                 INTEGER PRIMARY KEY,
    job_id             INTEGER NOT NULL REFERENCES jobs (id),
    resume_variant_id  INTEGER NOT NULL REFERENCES job_resume_variants (id),
    autonomy_level     INTEGER NOT NULL CHECK (autonomy_level BETWEEN 0 AND 3),
    status             TEXT NOT NULL,
    submitted_at       TEXT,
    payload_path       TEXT,
    screenshot_path    TEXT,
    confirmation_path  TEXT,
    notes              TEXT
);

CREATE TABLE IF NOT EXISTS outcomes (
    id            INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications (id),
    status        TEXT NOT NULL CHECK (
        status IN ('submitted', 'rejected', 'screen', 'onsite', 'offer', 'ghosted')
    ),
    occurred_at   TEXT NOT NULL,
    note          TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
    id              INTEGER PRIMARY KEY,
    company_slug    TEXT NOT NULL,
    name            TEXT,
    title           TEXT,
    email           TEXT,
    email_confidence REAL,
    source          TEXT,
    hook            TEXT,
    contacted_at    TEXT,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY,
    stage      TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    counts     TEXT,
    cost_usd   REAL,
    errors     TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_first_seen_at ON jobs (first_seen_at);
CREATE INDEX IF NOT EXISTS idx_jobs_company_ats ON jobs (company_slug, ats);
CREATE INDEX IF NOT EXISTS idx_jobs_content_hash ON jobs (content_hash);
CREATE INDEX IF NOT EXISTS idx_job_analysis_keyword_hash_profile ON job_analysis (keyword_hash, profile);
CREATE INDEX IF NOT EXISTS idx_outcomes_application_occurred ON outcomes (application_id, occurred_at);

-- first_seen_at is computed by us and immutable once set (see specs/00-data-model.md
-- and docs/decisions.md D3). Enforced here, not in Python, so no future caller --
-- upsert, migration, or manual fix-up -- can silently clobber it. The jobs/companies
-- upsert statements already omit first_seen_at from their SET clause; these triggers
-- are the backstop for any other write path.
CREATE TRIGGER IF NOT EXISTS trg_jobs_first_seen_at_immutable
BEFORE UPDATE ON jobs
FOR EACH ROW WHEN NEW.first_seen_at IS NOT OLD.first_seen_at
BEGIN
    SELECT RAISE(ABORT, 'first_seen_at is immutable once set');
END;

CREATE TRIGGER IF NOT EXISTS trg_companies_first_seen_at_immutable
BEFORE UPDATE ON companies
FOR EACH ROW WHEN NEW.first_seen_at IS NOT OLD.first_seen_at
BEGIN
    SELECT RAISE(ABORT, 'first_seen_at is immutable once set');
END;

-- outcomes is an append-only event log (docs/architecture.md, "Storage").
CREATE TRIGGER IF NOT EXISTS trg_outcomes_no_update
BEFORE UPDATE ON outcomes
BEGIN
    SELECT RAISE(ABORT, 'outcomes is append-only, update not allowed');
END;

CREATE TRIGGER IF NOT EXISTS trg_outcomes_no_delete
BEFORE DELETE ON outcomes
BEGIN
    SELECT RAISE(ABORT, 'outcomes is append-only, delete not allowed');
END;
