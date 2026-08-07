# Spec 00: Data Model

## Goal
SQLite schema, migrations, and typed accessors. No business logic.

## Module
`src/jobengine/db/` with `schema.sql`, `migrate.py`, `models.py` (pydantic).

## Principles
- Raw API payloads are stored verbatim alongside parsed fields. When parsing
  is wrong we re-parse from `raw_json` instead of re-fetching.
- Outcomes are an append-only event log, never a mutable status column.
- Every LLM call records tokens and computed cost.

## Tables

### companies
| col | type | notes |
|---|---|---|
| slug | TEXT | PK with `ats` |
| ats | TEXT | `greenhouse` \| `ashby` |
| name | TEXT | from API response |
| status | TEXT | `active` \| `dead` \| `unverified` |
| source | TEXT | `seed` \| `harvest` \| `manual` |
| first_seen_at | TEXT | ISO8601 UTC |
| last_ok_at | TEXT | last successful fetch |
| last_checked_at | TEXT | |
| consecutive_failures | INTEGER | mark `dead` at 3 |

### jobs
| col | type | notes |
|---|---|---|
| id | INTEGER | PK |
| ats | TEXT | |
| company_slug | TEXT | |
| ats_job_id | TEXT | unique with (ats, company_slug) |
| title | TEXT | as posted |
| location_raw | TEXT | |
| remote | INTEGER | nullable, Ashby only |
| department | TEXT | nullable |
| url | TEXT | |
| apply_url | TEXT | |
| compensation_raw | TEXT | nullable |
| description | TEXT | plain text |
| content_hash | TEXT | sha256 of description, detects real edits |
| ats_date | TEXT | `updated_at` or `publishedAt` |
| **first_seen_at** | TEXT | **computed by us, never from API** |
| last_seen_at | TEXT | bump every run it still appears |
| closed_at | TEXT | set when it disappears from the board |
| raw_json | TEXT | verbatim |

### job_analysis
job_id, profile, canonical_title, seniority, required_keywords (JSON array),
preferred_keywords (JSON), tech_stack (JSON), jd_quality (`good` | `bad`, per
Lee: does it have a Requirements/Qualifications bullet section), keyword_hash
(sha256 of sorted required_keywords, used for clustering), analyzed_at, model,
input_tokens, output_tokens, cost_usd. Unique on (job_id, profile); a re-run
upserts in place rather than accumulating history, matching
`relevance_scores`/`human_labels`. `canonical_title` and `seniority` are not
populated by C3 (no ground truth to grade them against yet); left `NULL`
until a later phase actually consumes and can validate them.

### keyword_corpus
profile, keyword, occurrences, first_seen_at, last_seen_at.
PK (profile, keyword). This accumulates Lee's 10-to-15-JD keyword list
automatically as a byproduct of running daily.

### clusters
id, profile, keyword_hash, job_count, created_at.

### base_resumes
id, profile, version, selection (JSON ordered bullet ids), section_order (JSON),
docx_path, pdf_path, rubric (JSON measurements at generation), generated_at,
retired_at. Never overwritten; the dashboard compares response rates across
versions.

### job_resume_variants
id, job_id, profile, base_resume_id, patch_tiers_applied (JSON), bullet_ids
(JSON ordered), selection_hash, docx_path, pdf_path, score, coverage,
front_load, passed, accepted, review_status, reviewed_at, created_at.
Row uniqueness is (job_id, profile): every job gets its own row. Dedup on
(base_resume_id, selection_hash) is file-level reuse only, applied by the
caller before rendering: two jobs whose patches produce identical
selections skip a redundant render and point their own rows at the same
already-rendered docx/pdf. (F1 found the earlier wording ambiguous: the
table's row uniqueness and the file-reuse dedup key are not the same
thing, and job_id must stay on every row regardless of which file it
points at.)

### rubric_results
id, job_resume_variant_id, rule_id, passed, measurement (REAL), detail,
evaluated_at. One row per rule per evaluation, so the dashboard can show which
rules fail most often across the corpus.

### relevance_scores
job_id, profile, score, seniority_match, keyword_hits (JSON), disqualifiers
(JSON), one_line, selected (INTEGER), model, scored_at.
Unselected jobs keep their scores for the dashboard and for spare-capacity days.

### human_labels
job_id, profile, relevance, keywords (JSON), labelled_at.
The eval fixture set. Small, hand-made, and the calibration reference for every
model question.

### model_evals
id, model, task, metric, value, passed, fixture_version, run_at.

### gap_ledger
id, profile, keyword, job_id, first_logged_at.
Query: uncovered keywords ranked by distinct job count.

### applications
id, job_id, resume_variant_id, autonomy_level (0-3), status, submitted_at,
payload_path, screenshot_path, confirmation_path, notes.

### outcomes
id, application_id, status (`submitted` | `rejected` | `screen` | `onsite` |
`offer` | `ghosted`), occurred_at, note. Append only.

### contacts
id, company_slug, name, title, email, email_confidence, source, hook,
contacted_at, notes.

### runs
id, stage, started_at, ended_at, counts (JSON), cost_usd, errors (JSON).

## Indexes
`jobs(first_seen_at)`, `jobs(company_slug, ats)`, `jobs(content_hash)`,
`job_analysis(keyword_hash, profile)`, `outcomes(application_id, occurred_at)`.

## CLI
```
uv run python -m jobengine.db init
uv run python -m jobengine.db migrate
uv run python -m jobengine.db stats
```

## Definition of done
`init` creates the schema idempotently; `tests/test_db.py` covers insert,
upsert-on-conflict for jobs (must not clobber `first_seen_at`), and the
outcomes append-only constraint.
