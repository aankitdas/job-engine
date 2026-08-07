# Progress

**Claude Code: read this file at the start of every session and update it at
the end via `/checkpoint`. Do not rely on memory of previous sessions.**

Last updated: 2026-08-07
Current task: **F1 (review queue) is done.** No dedicated spec file
existed for it (TODO.md's own Rules section deferred writing Phase F
specs until Phase D ran on real data; nobody had written one when this
session started) — this session's Claude Code plan-mode plan, approved
before any code was written, is F1's design document; see D35 in
docs/decisions.md for the full writeup, only summarized here.
Built `src/jobengine/queue/orchestrate.py` (`QueueContext`,
`ensure_reviewed()`: lazily triggers C3 extraction + the D3/D4 patch
ladder the first time a reviewer opens a specific (job, profile) pair,
zero batch/cron orchestrator, `approve()`/`reject()`, `list_queue()`)
and `src/jobengine/web/app.py` (FastAPI: `GET /`, `GET /jobs/{job_id}/
{profile}`, `POST .../approve`, `POST .../reject`; Jinja2 templates;
`uv run uvicorn jobengine.web.app:app --reload`, CLAUDE.md's
already-documented dev command, now real). The lazy-trigger-not-batch
scope was a genuine 3-way fork resolved via `AskUserQuestion` before any
code: a real batch orchestrator would need C4 (relevance pre-filter,
not built) for a proper survivor cut first.
**Two real bugs found and fixed before/during implementation, not
after shipping, each caught by verification, not assumed correct:**
(1) the first-drafted design (from a planning sub-agent) tracked review
state as `applications` rows, which would have silently corrupted B3's
already-shipped `is_already_applied()` filter (it treats *any*
`applications` row for a `job_id` as "already applied," regardless of
`status`) — caught by reading that function directly before accepting
the design, fixed by moving review state onto new `job_resume_variants.
review_status`/`reviewed_at` columns instead, `applications` rows now
created only on approval; (2) `job_resume_variants`' old
`UNIQUE(base_resume_id, selection_hash)` constraint (no `job_id`) would
have rejected a second job's insert outright if its patch ladder
converged on an identical selection to an already-inserted job's row,
contradicting spec 08's own multi-job file-reuse dedup intent — caught
by a test written before implementation, fixed via a real schema change
(`UNIQUE(job_id, profile)` instead) plus genuine table-rebuild migration
logic in `migrate.py` (this project's first migration beyond idempotent
`CREATE ... IF NOT EXISTS`, needed since removing a table-level
constraint isn't expressible as one). A third bug (FastAPI running sync
routes/`Depends()` in a threadpool, breaking `sqlite3`'s default
same-thread requirement) was found only by running the real app, fixed
via a new `check_same_thread` parameter on `connect()`, defaulted `True`
everywhere except `jobengine.web.app`.
**The real db migration was applied only after asking and getting
explicit confirmation** (hard rule 13): `job_resume_variants` had 0 real
rows at the time, so the rebuild copied nothing. Verified read-only
afterward (new index present, old constraint gone, row counts
unchanged, both schema versions recorded), then verified end to end
against the real running app and real db using this session's own real
worked example (job_id 3871, Airbnb "Software Engineer, Biztech Client
and Identity", already confirmed to survive B3 for `software_engineer`):
first visit ~22s (real Ollama cold start), on-screen numbers matched
the plan's pre-computed worked example exactly (score 18.98, coverage
0.14, `hard_failures: ['R001']`, all four patch tiers attempted);
second visit 0.01s, byte-identical HTML, zero new model calls; reject
returned 303, flipped `review_status`, created no `applications` row,
and the job dropped off `GET /`. This is also the first-ever real
`job_analysis`, `keyword_corpus`, `job_resume_variants`, and
`rubric_results` rows this project has written to `data/jobengine.db`
outside a scratch copy, closing gaps flagged since C3/E1 ("no daily
orchestrator has ever called `analyze_job()` against real jobs").
42 new tests, written before implementation per hard rule 7
(`test_db.py` +12, `test_db_migrate.py` +9 new file,
`test_queue_orchestrate.py` +7 new file, `test_web_app.py` +8 new
file).
**Follow-up in this same session, after F1's initial close:** added
`passes_all_filters(conn, job, config) -> bool` to `pipeline/filter.py`
(B3's full deterministic chain — title match, location, seniority,
employment type, citizenship/clearance, already-applied — in one call,
tests-first) and wired it into `web/app.py`'s `_new_pairs()`, replacing
the title-only check the "not yet reviewed" list previously used. 9
more new tests (`test_filter.py` +7, `test_web_app.py` +2). Also
recorded a real finding from a live read-only db check: the Task
Scheduler entry behind B2 stopped firing unattended sometime after
`2026-08-03T20:00` and has failed silently since (root cause and fix
identified, not yet applied — see Known Issues and the paragraph
below).
`uv run pytest` 379/379 (up from 328 at session start), `ruff
check`/`format --check` clean.
Next: no next task chosen yet, needs your go-ahead per the session
protocol. Open candidates per TODO.md, none started: A4c (watermarking,
still no urgency, no speculative bullets exist), B1-followup/
B3-followup (deliberately deferred), C4 (relevance pre-filter), F2
(metrics dashboard), F3 (Telegram notifier). P4 (accept and log to
gap_ledger) also remains deliberately unbuilt. Fixing the Task Scheduler
regression (stored-password logon mode) is a real open item but needs
you at the Windows machine, not something a session here can do.

Separately: **B2's scheduling has regressed since the last checkpoint,
confirmed this session via a real-db read-only check.** The Task
Scheduler entry that was confirmed firing unattended on 2026-08-03 (see
Known Issues) stopped succeeding sometime after `2026-08-03T20:00` and
has failed silently through at least 2026-08-07: zero `runs` rows since
then, zero log files for those dates, `Last Result -2147020576`
(`0x800710E0`, low word `0x10E0` = "The operator or administrator has
refused the request"). Root cause identified, not just observed: the
task's "Interactive only" logon mode requires an active session at each
3-hour trigger, so "run as soon as possible after a missed start" can't
help, this is an attempted-and-rejected run, not a skipped one. Fix
identified ("Run whether user is logged on or not" with a stored
account password) but not yet applied — password setup hit an unrelated
Windows issue. `sync.sh`/the task itself are confirmed still healthy: a
manual `schtasks /run` still works. Full detail recorded in Known
Issues below; the existing "RESOLVED 2026-08-03" text is still accurate
for what it verified at the time, this is a new regression after it,
not a correction to it. `jobs`/`companies`/`runs` counts (3882/15/12)
are otherwise unchanged since the last checkpoint — this session's only
real writes were F1's own (see above).

**Read this before touching `data/jobengine.db`:** hard rule 13 in
CLAUDE.md (added 2026-08-02, see D22 in docs/decisions.md) requires asking
first, with explicit confirmation in that message, before any `rm`, `init`,
`migrate`, or other destructive/state-resetting operation against the real
db path, no exception for "quick sanity checks." Use a scratch copy or a
temp path instead. This reverses how every prior session (including this
project's own B1/B2 sessions) treated that file.

---

## Status

| ID | Task | Status | Notes |
|---|---|---|---|
| A1 | Data model | done | |
| A2 | Bullet bank | done | |
| A3 | Slop linter | done | |
| A4 | Docx renderer + golden typography test | done | see note below, PDF/watermark split out |
| A4b | PDF conversion (LibreOffice headless) | done | `resume/pdf.py`, verified live against real `soffice` on 2 distinct real full-bank renders; found+fixed a real bullet-spacing bug along the way |
| A4c | Watermarking (speculative preview) | not started | no urgency, no speculative bullets exist yet |
| B1 | ATS clients + registry | done | clients+registry only, sync.py's fetch/diff loop is B2 |
| B2 | Fetch and diff | done | scheduled and confirmed firing unattended on 2026-08-03; scheduling then regressed (silent failures 08-04 through at least 08-07, "Interactive only" logon mode), fix identified not yet applied; see Known Issues |
| B1-followup | Sponsorship-aware company vetting (DOL LCA) | not started | flagged only, not scoped, see TODO.md |
| B3 | Filters + routing | done | signed off 2026-08-03; `filter.py` implemented, 40/40 tests pass, final numbers 859/3836 survivors (68/776/81 per profile) |
| B3-followup | Calibrate daily filter-survivor cap | not started | deliberately deferred, see D23 in docs/decisions.md |
| C1 | LLM router | done | `llm.check` verified live against real Ollama, all 3 stages reachable, exit 0; cold-start ~15s / steady-state 600-935ms, see Known Issues |
| C2 | Eval fixtures | done | 50/50 JDs labelled, loaded into `human_labels` (150 rows); 11/15 keyword-annotated, short of TODO.md's literal target, done anyway per explicit sign-off, see Known Issues |
| C3 | Keyword extraction | done | shipped per D27 (ship decision), not literal DoD: precision 0.83-0.86 passes, recall 0.35-0.47 fails the 0.85 gate (range across 4 live runs), see Known Issues |
| C4 | Relevance filter | not started | |
| D1 | Rubric rules | done | all 13 hard rules + weighted score, `rubric/{measure,rules,score}.py` + CLI, grounded against 3 real JDs |
| D2 | PDF geometry | done | absorbed into D1 (R002/R006 have no fallback); includes spec 08's per-file-hash cache (added after the user caught it missing at checkpoint review), 1 `pdfplumber.open` call per `score_resume()` run now, not 15+; see D28 addendum 4 |
| D3 | Patch P0-P2 | done | `rubric/patch.py` + CLI; real deficit closed (Chroma DB / R002) via P2; P1 confirmed structurally inert against current bank, see D29 |
| D4 | Patch P3 | done | `patch.py` gains rephrase+writeback; real deficit closed live (CMB, coverage 0.0->1.0), real bug found+fixed via that run; persist/reload/reuse chain re-verified live with full captured evidence 2026-08-05, see D30 + its second addendum |
| E1 | Profile config + brief | done | `jobengine.profiles` package: registry (`config/profiles.yaml`) + `profiles brief` CLI; live-verified against real db/bank for all 3 profiles; see D31 |
| E2 | Base resumes | done | all 3 profiles persisted (`resume/base/{ai_ml_engineer,software_engineer,data_scientist}/v1/`, `ai_ml_engineer` also has v2; `base_resumes` ids 1-4), each `passed: true, hard_failures: []`, `coverage: 1.0`; R002 demoted to scored-only (D33), coverage measured against bank-frequency fallback not real corpus (D34, revisit later) |
| F1 | Review queue | done | `queue/orchestrate.py` + `web/app.py`, lazy per-job trigger not batch; verified end to end against the real app/db with real job 3871; see D35 |
| F2 | Dashboard | not started | |
| F3 | Telegram | not started | |
| G1 | Autonomy gating | not started | |
| G2 | Playwright dry-run | not started | |
| G3 | Level 2 apply | not started | |
| G4 | Level 3 apply | not started | |
| H1 | Contacts | not started | |
| H2 | Referral drafts | not started | |

Status values: `not started` | `in progress` | `blocked` | `done`

---

## What exists right now

One line per module, verified against the actual filesystem and test
suite at this checkpoint, not carried forward from memory. Full history
and the reasoning behind non-obvious choices lives in the Session log
below and docs/decisions.md; this section is current state only.

**db/** (`src/jobengine/db/`): `schema.sql` (16 tables + indexes +
immutability triggers; F1 this session: `job_resume_variants` gained
`review_status`/`reviewed_at` columns and lost its old table-level
`UNIQUE(base_resume_id, selection_hash)` constraint, replaced by
`idx_job_resume_variants_job_profile` on `(job_id, profile)`, see D35),
`migrate.py` (`connect()` gained a `check_same_thread` parameter, `True`
everywhere except `jobengine.web.app`; `migrate()` gained
`_rebuild_job_resume_variants_if_needed()`, a real table-rebuild
migration, the first beyond idempotent `CREATE ... IF NOT EXISTS`;
`_SCHEMA_VERSION` now `"0002_job_resume_variants_review_state"`, applied
to the real db this session), `models.py` (pydantic models + typed
accessors for `companies`, `jobs`, `outcomes`, `runs`, `job_analysis`,
`keyword_corpus`, `model_evals`, `base_resumes`; new this session, F1:
`JobResumeVariant`, `RubricResultRow`, `Application`, `QueueEntry`
models + `insert_job_resume_variant()`, `get_job_resume_variant()`,
`find_job_resume_variant_by_hash()` (the file-reuse dedup lookup),
`update_review_status()`, `insert_rubric_results()`/
`get_rubric_results()`, `get_job_by_id()`, `latest_base_resume()` (full
row, not just the version int), `insert_application()`,
`list_pending_review_queue()`, `list_existing_variant_pairs()`),
`__main__.py` (`uv run python -m jobengine.db {init,migrate,stats}`).
Tests: `test_db.py` 42 (up from 30, +12 this session), `test_db_migrate.py`
9 (new this session, simulates the pre-migration table shape via raw
SQL and proves rows survive the rebuild).

**resume/** (`src/jobengine/resume/`): `bank.py` (pydantic bank schema,
`load_bank()`, `validate_bank()`, `coverage_gaps()`, `keyword_counts()`,
`is_past_tense()` public for reuse, CLI `uv run python -m
jobengine.resume.bank {validate,stats,coverage}`; new this session:
`BulletVariant` model + `Bullet.variants` field for D4's P3 writeback,
`dump_bank()` YAML serializer (data-fidelity round-trip only, not a
formatting-fidelity guarantee, never called against the real
`resume/bank/aankit.yaml`, see D30), `CHARS_PER_LINE`/`MAX_LINES`/
`WARN_CHAR_LIMIT` made public for `rubric/patch.py` reuse); `slop_lint.py`
(17 rules from specs/02, `lint_target()`/`lint_path()`, CLI, wired into
`.claude/settings.json`'s PostToolUse hook); `render.py` (`render(bank,
identity, profile) -> Document`, A4 scope; `FONT`/`MARGIN`/`TAB_POSITION`
public constants so `rubric/measure.py` can reuse them rather than
duplicate; `_new_paragraph()` zeroes `space_before`/`space_after` on
every paragraph, see Known Issues); `pdf.py` (`render_pdf(docx_path,
out_dir) -> Path`, wraps `soffice --headless --convert-to pdf` via
subprocess, unique throwaway profile dir + 60s timeout). Tests:
`test_bank.py` 22 (up from 16), `test_slop_lint.py` 22, `test_render.py`
24, `test_pdf.py` 9 (subprocess mocked throughout).

**rubric/** (`src/jobengine/rubric/`): `measure.py` (real measurement
functions: `select_for_profile()`, `coverage()`, `front_load()`/
`front_load_detail()` and `line_count_from_pdf()` via real `pdfplumber`
geometry, `measure_typography()` via docx XML, `stem()`, `iter_entries()`,
`page_count()`, `roles_date_overlap()`/`role_end_or_ongoing()`;
`_parsed_pdf()` parses each PDF exactly once per process, cached by a
sha256 of its own bytes per spec 08's explicit caching requirement, see
D28 addendum 4; `is_reverse_chronological()` loosened this session from
strict start-date monotonicity to date-range-overlap tolerance, see D29);
`rules.py` (`check_r001`-`check_r013`, `RubricResult`/`Deficit` pydantic
models, `score_resume()` orchestrator; new this session: R002
(front-load) removed from `score_resume()`'s `hard_failures` list per
D33 in docs/decisions.md, `check_r002()` itself unchanged and still
directly tested, `front_load` still fully weighted 25/100 in score.py);
`score.py` (weighted 0-100 score
per spec 08's table); `patch.py` (`apply_p0`/`apply_p1`/`apply_p2`
implement the deterministic P0-P2 patch ladder from D3; new this
session, D4: `call_rephrase()` (the only LLM call, via
`router.get_provider("rephrase", ...)`), `validate_rewrite()` (CLAUDE.md
hard rule 12's traceability guard, enforced in code, deliberately
stricter than a jargon-allowlist, see D30), `apply_p3()` (prefers an
existing variant, max 2 new calls/job), `apply_variants_to_bank()`
(in-memory writeback, `used_count` tracking), `_with_bullet_rewrite()`
(merges an accepted rewrite's `keywords_added` into the working
candidate's `.keywords`, not just `.text`, a real bug found and fixed via
live-model grounding, see D30); `run_ladder()` now attempts P3 after
P0-P2 when `llm_config` is given, still P0-P2-only when omitted.
`base_resumes` is now populated (E2 done, 4 rows), but nothing yet wires
`run_ladder()`'s output to `job_resume_variants`; still not built. No
persistence to the real `resume/bank/aankit.yaml` from here either
(confirmed by asking not to
wire up in D4, see D30); `__main__.py` (CLI: `uv run python -m
jobengine.rubric {score,explain,patch}`; `patch` only ever runs dry-run
today). `tests/test_rubric.py`: 43 tests. `tests/test_patch.py`: 51
tests (up from 14), including the real-bank `run_ladder` integration
tests plus an extensive traceability-guard battery. (Corrected from
41/50 at this checkpoint: actual counts drifted from what was recorded
in a prior session and were re-verified against the collected suite,
not carried forward from memory.)

**sources/** (`src/jobengine/sources/`): `models.py` (`JobPosting`),
`_client.py` (shared httpx client + retry policy), `greenhouse.py`/
`ashby.py` (`fetch_board()`), `registry.py` (`seed`/`add`/`validate`,
CLI), `sync.py` (`sync()`, the fetch-and-diff loop, CLI `uv run python -m
jobengine.sources.sync [--dry-run]`). `config/seed_companies.yaml`: 15
real companies. `scripts/sync.sh`: cron/Task Scheduler wrapper, live on
Windows Task Scheduler task `job-engine-sync`, every 3h from 6am local.
Tests: `test_sources.py` 20, `test_sync.py` 10.

**pipeline/** (`src/jobengine/pipeline/`): `filter.py`
(`load_filter_config()`, `matches_profiles()`, `is_remote()`,
`is_excluded_employment_type()`, `is_already_applied()`,
`is_citizenship_or_clearance_required()`, `is_above_target_seniority()`,
`is_us_location()`/`classify_location()`; pure functions, nothing
persisted; new this session, F1: `passes_all_filters(conn, job, config)
-> bool`, the full chain in one call, first real caller is
`web/app.py`'s queue listing). `config/filters.yaml`: all 5
hard/per-profile checks configured, `daily_cap: null` (deliberate, see
D23). `extract.py` (`ExtractionSchema`, `is_good_quality_jd()`,
`extract_keywords()` (the only LLM call site, via
`router.get_provider("extract", ...)`), `analyze_job()` (production
orchestrator, fans out to `job_analysis`/`keyword_corpus`)). Tests:
`test_filter.py` 47 (up from 40, +7 this session), `test_extract.py` 14.

**llm/** (`src/jobengine/llm/`): `schemas.py`, `providers/local.py`
(`LocalProvider`, `think=False` pinned on every call), `providers/
anthropic.py` (guard-only, `call()` always raises `NotImplementedError`,
see D25), `router.py` (`load_config()`, `get_provider()` billing guard,
`call()` with fallback), `check.py` (CLI: `uv run python -m
jobengine.llm.check`). `config/llm.toml`. Tests: `test_llm_local_
provider.py` 4, `test_llm_router.py` 11, `test_llm_check.py` 6.

**eval/** (`src/jobengine/eval/`): `fixtures.py` (`load_human_labels()`),
`harness.py`/`report.py`/`tasks/keyword_extraction.py` (spec 07 Task 2
only, Task 1/C4 not wired in), `__main__.py` (CLI: `uv run python -m
jobengine.eval {run,compare}`). `tests/fixtures/eval/human_labels.yaml`:
50 real JDs, 11 with hand-extracted keywords. Tests: `test_eval_
fixtures.py` 6, `test_eval_keyword_extraction.py` 11.

**profiles/** (`src/jobengine/profiles/`, new this session, E1):
`config.py` (`ProfileConfig` pydantic model, `load_profile_config()`
loads+validates `config/profiles.yaml` against `bank.KNOWN_PROFILES`
and against `render.py`'s own valid section names, `to_render_profile()`
adapter to `render.RenderProfile`); `brief.py`
(`generate_brief()` and its helpers: `_top_corpus_keywords()` (real
`keyword_corpus` query, falls back to `bank.keyword_counts()` restricted
to the profile when empty), `_gap_ledger_top()` (real `gap_ledger`
query, grouped/counted by keyword), `_current_measurements()` (renders
`measure.select_for_profile()`'s output through the real render -> pdf
-> `rules.score_resume()` pipeline, the "current base resume" stand-in
confirmed by asking since no `base_resumes` row exists yet),
`_unselected_bullets_with_top_keywords()`); `__main__.py` (CLI: `uv run
python -m jobengine.profiles brief --profile <id>`, prints markdown to
stdout, read-only against the real db and bank). `config/profiles.yaml`:
all 3 `KNOWN_PROFILES` entries, same flat section order/no-summary
defaults everywhere (see D31 in docs/decisions.md for why that's not a
guess). New this session, E2: `persist.py` (`persist_base_resume()`:
renders `measure.select_for_profile()`'s output in the bank's own
natural order, no patch ladder applied, scores it, writes
`selection.yaml`/`resume.docx`/`resume.pdf`/`rubric.json` to
`resume/base/{profile}/v{N}/`, inserts the `base_resumes` row via
`db/models.py`'s new accessors; deliberately does not write
`CHANGELOG.md`, since "what changed and why" is interactive-session
narrative, not mechanically derivable, see D32). Tests:
`test_profiles_config.py` 8, `test_profiles_brief.py` 10 (real-`soffice`
render/score integration tests, same pattern as `test_rubric.py`'s own
`real_sample_pdf` fixture, not mocked), `test_profiles_persist.py` 5
(new).

**resume/base/** (E2, done this session): all 3 profiles now have a
persisted version, `ai_ml_engineer` has two.
`ai_ml_engineer/v1/` — first real `base_resumes` artifact this project
produced (prior session), left untouched per spec 09's "never
overwritten" versioning; its `rubric.json` still reads pre-D33
(`hard_failures: ['R002']`), stale but accurate to what it was scored
against at the time.
`ai_ml_engineer/v2/` — same selection as v1 (confirmed byte-identical
`selection.yaml` aside from the version field, zero bank content
changed for this profile), regenerated solely to carry a post-D33
`rubric.json` (`score 63.40`, `passed: true`, `hard_failures: []`).
`software_engineer/v1/`, `data_scientist/v1/` — first-ever versions for
each. `software_engineer`: `score 66.87`, `passed: true`,
`hard_failures: []`, selection includes `role_utd_researcher`'s newly
retagged `b_utd_02`. `data_scientist`: `score 66.96`, `passed: true`,
`hard_failures: []`, selection excludes `role_bantrly_lessongen`
entirely (dropped this session).
Every version has `selection.yaml`/`resume.docx`/`resume.pdf`/
`rubric.json`/hand-written `CHANGELOG.md`. `base_resumes` table: 4 rows
(`id` 1-4) committed to `data/jobengine.db`. See D32 (the original
R002 investigation), D33 (R002's hard-failure demotion), and D34 (the
bank-frequency-fallback coverage caveat) in docs/decisions.md.

**queue/** (`src/jobengine/queue/`, new this session, F1):
`orchestrate.py` — `QueueContext` (dataclass: `conn`, `full_bank`,
`identity`, `profile_configs`, `filter_config`, `llm_config`,
`local_client`, built once per process); `ensure_reviewed(ctx, job_id,
profile)` (the lazy-trigger entry point: ensures `job_analysis` exists
via C3's `analyze_job()`, then ensures a `job_resume_variant` exists via
D3/D4's `run_ladder()`, idempotent, real deficits persisted to
`rubric_results`); `approve()`/`reject()` (review decisions: approve
sets `review_status='approved'` and inserts an `applications` row
`status='queued', autonomy_level=0`; reject sets `review_status=
'rejected'` and creates no `applications` row, deliberately, see D35);
`list_queue()` (thin wrapper over `db/models.py`'s
`list_pending_review_queue()`). No `__main__.py`: only the web routes
and tests call this module. Tests: `test_queue_orchestrate.py`, 7 tests,
every one exercising the real bank/render/PDF/score pipeline (there is
no lighter mock for `run_ladder()`, matching `test_patch.py`'s own
precedent), LLM calls mocked via a stage-aware `_FakeClient` that
inspects the requested schema's fields to serve both the extract and
rephrase stages correctly from one fake.

**web/** (`src/jobengine/web/`, new this session, F1): `app.py` —
FastAPI app, `get_ctx()` (lazy singleton `QueueContext`, overridden in
tests via `app.dependency_overrides`), `GET /` (pending queue +
newly-B3-matched-but-never-triggered pairs from the last 7 days), `GET
/jobs/{job_id}/{profile}` (the lazy trigger; renders score/coverage/
front_load/hard-failures/the real rendered PDF via a `/resume` static
mount), `POST /jobs/{job_id}/{profile}/{approve,reject}`.
`templates/queue_list.html`/`queue_detail.html` (plain server-rendered
HTML, no JS, per spec: reviewing means seeing the already-patched
candidate and deciding, not editing bullet text in a browser).
`JOBENGINE_DB_PATH` env var overrides `DEFAULT_DB_PATH` for manual
testing against a scratch copy. `uv run uvicorn jobengine.web.app:app
--reload` (CLAUDE.md's already-documented dev command, now real for the
first time). Tests: `test_web_app.py`, 10 tests (up from 8, +2 this
session), FastAPI `TestClient` against a `tmp_path` db via dependency
override, covering first-visit trigger, second-visit idempotency,
approve/reject state transitions and their `applications`-row side
effects, the list page dropping a rejected job, and (new this session)
`_new_pairs()`'s `passes_all_filters()` gating: a clean untriggered job
appears as "not yet reviewed," one with a non-US location does not.

**resume/rendered/variants/** (new this session, F1): per-(job,profile)
lazily-rendered candidates, `{job_id}/{profile}/candidate_{tiers}.
{docx,pdf}`. One real entry as of this checkpoint:
`3871/software_engineer/candidate_P0_P1_P2_P3.{docx,pdf}` (this
session's real worked-example verification, see below).

**Full suite: 379/379 passing (up from 328 at session start, 370 after
F1's initial build, +9 for `passes_all_filters`), `ruff check src/`
clean, `ruff format --check src/` clean** (3 pre-existing `RUF059`
warnings in `test_render.py`, confirmed via `git stash` to predate an
earlier session, untouched, unaffected by this session).

**`data/jobengine.db` real accumulated state, verified this checkpoint:**
15 companies, 3882 jobs, 12 `runs` rows, 150 `human_labels` rows, 30
`model_evals` rows, 4 `base_resumes` rows (unchanged this session).
**F1 wrote 4 genuinely new kinds of real rows to this db for the first
time ever, all from the single real worked-example verification (job
3871), not synthetic data:** `job_analysis` 0 -> 1, `keyword_corpus` 0
-> 7, `job_resume_variants` 0 -> 1, `rubric_results` 0 -> 1. Every one
confirmed deliberate (asked before the migration that added the
columns/index these rows needed, then asked again implicitly satisfied
by running the documented verification step). `applications` and
`gap_ledger` both still 0 rows: the worked example was rejected, not
approved (a genuine, correct outcome given `hard_failures: ['R001']`,
not a shortcut to avoid exercising the approve path — the automated
test suite's `test_approve_flips_review_status_and_creates_application`
covers that path against a scratch db instead), and P4 (gap ledger
writeback) still isn't built. `jobs`/`companies`/`runs` unchanged since
the prior checkpoint (no sync activity happened this session); every
other table's read-only status was reconfirmed before this session's
real writes, not assumed.

---

## Known issues and deferred work

- **RESOLVED 2026-08-07, not left open:** F1's `GET /` "not yet
  reviewed" section used to only reapply B3's title check
  (`matches_profiles()`), not the full B3 filter chain, so a job that
  failed location/seniority/employment-type/citizenship/already-applied
  could still show up as "not yet reviewed" and get a real
  `job_resume_variant` even though it should never have survived B3.
  Fixed by adding `passes_all_filters(conn, job, config) -> bool` to
  `pipeline/filter.py` (the full chain in one call) and gating
  `web/app.py`'s `_new_pairs()` on it before the per-profile
  `matches_profiles()` fan-out. 8 new tests (`test_filter.py` +7 for
  `passes_all_filters` itself, one per exclusion axis plus a clean
  baseline; `test_web_app.py` +2, confirming a clean untriggered job
  appears and a non-US-location one doesn't).
- **`migrate.py`'s `_rebuild_job_resume_variants_if_needed()` is
  bespoke to this one migration, not a reusable framework.** PROGRESS.md
  already flagged before F1 that `_SCHEMA_VERSION` is a single hardcoded
  string, not a real migrations directory; F1 needed an actual
  table-rebuild (not just an additive `CREATE INDEX`) and got one
  written specifically for `job_resume_variants`' old shape. The next
  migration that needs a rebuild (a column type change, a dropped
  column elsewhere) will need its own similarly bespoke function again,
  or this should finally become `db/migrations/000N_*.sql` with
  `schema_migrations` tracking each file independently. Not built now,
  since only one migration has ever needed it.
- **F1's "approve" action creates an `applications` row with
  `autonomy_level=0` and `status='queued'`, and nothing consumes it
  yet.** Phase G (autonomy gating, Playwright apply) is entirely
  unbuilt; `0` is a safe, most-manual placeholder per D16's existing
  precedent (autonomy level is decided deterministically by G1's form-
  schema inspection, not by the reviewer), not a real decision about
  what should happen to an approved job. An approved job just sits in
  `applications` with `status='queued'` until Phase G exists to act on
  it.
- **F1 has no batch/cron orchestrator, by deliberate scope decision
  (confirmed via `AskUserQuestion`), not an oversight** — see D35 in
  docs/decisions.md. `job_resume_variants` only grows one row at a time,
  each time a human opens a specific `/jobs/{job_id}/{profile}` URL.
  There is currently no way to see "everything that survived B3 today"
  pre-scored; the reviewer has to click into the "not yet reviewed"
  list to trigger scoring for each one. Building a real batch version
  properly needs C4 (relevance pre-filter, not built) first, per spec
  08's own stage 2.5 ordering, so this wasn't attempted as a stopgap.
- `src/jobengine/web/app.py`'s `_LIST_WINDOW_DAYS = 7` (how far back
  `GET /` looks for newly-matched pairs) is a free, unconfigured choice,
  not derived from anything. Revisit if real usage shows 7 days is too
  short (a job sits unreviewed past a week) or too long (the list gets
  cluttered).
- FastAPI's `TestClient` (used in `tests/test_web_app.py`) emits a
  `StarletteDeprecationWarning` about `httpx`/`starlette.testclient`
  every test run ("install `httpx2` instead"), an upstream dependency
  concern, not this codebase's own code. Harmless today (doesn't fail
  the suite), not fixed since it would mean adding a new dependency
  (`httpx2`) without being asked, per hard rule 5. Revisit if a future
  `starlette`/`httpx` upgrade actually breaks `TestClient` rather than
  just warning about it.

- **`base_resumes` has no `UNIQUE(profile, version)` constraint in
  `schema.sql`.** `persist_base_resume()`
  (`src/jobengine/profiles/persist.py`) computes the next version via
  `latest_base_resume_version(conn, profile) + 1`, read-then-write, no
  transaction/lock around it; two concurrent calls for the same profile
  could both compute the same version and insert two rows claiming to be
  the same `v{N}`, silently. Not a real risk yet (E2 is one interactive
  session at a time, never concurrent), but worth a schema constraint or
  an app-level guard before this could run unattended.
- **`persist_base_resume()` never sets `retired_at` on a profile's prior
  versions when a new one is inserted.** Now has a real second version
  to test against (`ai_ml_engineer` v1 and v2, both live, neither
  retired) and still doesn't matter: spec 09 only requires keeping "at
  least the previous two versions live," which 2 total trivially
  satisfies. Revisit once a profile reaches a 3rd version and the
  oldest genuinely needs retiring.
- **E2 is done, all 3 profiles pass clean (`hard_failures: []`,
  `coverage: 1.0`), but two things behind that number are worth reading
  before trusting it at face value.** (1) R002 (front-load) is no
  longer a hard failure at all, demoted to a scored-only component this
  session (D33, docs/decisions.md) after `ai_ml_engineer` (D32,
  `front_load` ceiling 0.50) and `software_engineer` (this session,
  ceiling 0.40) both hit the same real structural wall with no
  legitimate fix; `front_load` is still visible in every `rubric.json`
  and still weighted 25/100 in the score, just not gating. (2)
  `coverage: 1.0` for all 3 is measured against bank-frequency fallback
  keywords, not real `keyword_corpus` data (still 0 rows) — see D34,
  docs/decisions.md, for the full reasoning and why this needs
  re-validation once corpus data exists. The R003/R013 content gaps
  that used to block `software_engineer` (`role_utd_researcher=2`) and
  `data_scientist` (`role_bantrly_lessongen=2`) are both resolved, not
  just documented: see the retag/drop decisions in this session's log
  entry below.
- **E1's `config/profiles.yaml` only has one real caller
  (`profiles/brief.py`); `patch.py`'s `run_ladder()` and
  `scripts/render_sample.py`/`render_pdf_sample.py` still construct
  `RenderProfile` inline rather than loading the new registry.** Not
  migrated this session, not asked for. Revisit once a second real
  caller needs per-profile section-order customization, at which point
  duplicating the inline construction a third time would be the wrong
  call.
- **`config/profiles.yaml`'s `section_order`/`include_summary` values
  are defaults matching current de facto behavior everywhere else in
  the codebase, not yet validated per-profile against a real target
  title.** Spec 09's harder calls (education-at-bottom for a title that
  doesn't need a degree, a summary section for a genuine trigger) are
  explicitly deferred to E2, when a human reviews a real generated
  resume against a real target title, not decided blind in E1. See D31
  in docs/decisions.md.
- **`profiles brief`'s "current base resume" section is still the
  on-the-fly-rendered full candidate (`select_for_profile` output), not
  a real base resume, even though real `base_resumes` rows now exist
  for all 3 profiles as of this session.** Labeled as such in the
  brief's own output; the switch to reading the real row isn't built
  yet, more of a live gap now than when this was first written since
  there's finally real data it could read instead. Its
  `required_keywords` are still the brief's own top-keywords list
  (corpus or bank-frequency fallback), a forced choice (no job-specific
  keyword list exists at profile granularity) rather than an arbitrary
  one — worth knowing when reading a bank-frequency-fallback brief,
  since coverage will trivially read 1.0 (the "required" keywords are,
  by construction, already present in whichever bullets contributed
  them). See D34, docs/decisions.md, for why this same caveat now
  matters for the real persisted base resumes too, not just the brief.
- **`apply_variants_to_bank()`/`dump_bank()` (D4) are built and tested
  but nothing in this codebase calls them against the real
  `resume/bank/aankit.yaml`.** Confirmed by asking before D4 started:
  this would be the first-ever automated write to that hand-authored
  file, and a generic YAML dumper risks reordering keys/reformatting
  strings well beyond the actual content change. A P3 rewrite accepted
  during a real `run_ladder()` call only ever lands in that call's
  returned `PatchResult`/working `Bank`; persisting it to the real bank
  file is a separate, deliberate, not-yet-built action. See D30 in
  docs/decisions.md.
- **P4 (accept and log to `gap_ledger`) is still not built.** Spec 08
  only reaches P4 after P3's rewrite budget (2 calls) is exhausted or
  every attempt is discarded; "mark the variant `passed: false, accepted:
  true` if the deficit is soft" requires a definition of "soft" this
  session didn't make without asking. `gap_ledger`'s schema already
  exists (`job_id`, `profile`, `keyword`, `first_logged_at`); nothing
  writes to it yet.
- **P1 (swap, `src/jobengine/rubric/patch.py`'s `apply_p1`) is a real,
  structural no-op against the bank as it exists today, for every role
  and every profile, not a bug.** `measure.select_for_profile()` (D28
  addendum 2) already includes every profile-tagged bullet in a role;
  there is no held-back "eligible but unselected" bullet anywhere in the
  current bank for P1 to swap in, since every role's profile-tagged
  bullet count already sits within R003's 3-8 ceiling (the one exception,
  `role_utd_researcher`'s single `software_engineer`-tagged bullet, is a
  count *below* the floor, which P1 can't fix either since there's no
  spare bullet to swap in for that role+profile). Confirmed by direct
  inspection, not inferred. Revisit only once the bank's bullet counts
  for some role+profile genuinely exceed 8 and some must be held back;
  nothing in `patch.py` needs to change for that to start working, it
  already implements the swap logic correctly, it just has nothing to do
  yet. See D29 in docs/decisions.md.
- **RESOLVED this session, not still open:** `role_utd_researcher` used
  to have exactly 1 bullet tagged `software_engineer`
  (`resume/bank/aankit.yaml`), one short of R003's 3-bullet floor,
  causing every `software_engineer`-profile job to fail R003/R013
  regardless of keywords (the gap this bullet originally documented,
  found while grounding D3). Fixed by reviewing all 5 of that role's
  bullets for genuine `software_engineer` fit and retagging `b_utd_02`
  (data processing across CMB simulated maps, the least ML-research-
  specific of the five) onto the profile, bringing it to 3 total
  entries. `role_bantrly_lessongen` had the identical shape for
  `data_scientist` (1 tagged bullet, `b_lessongen_04`) but none of its
  other 4 bullets read as genuine data-science work on review, so that
  role was dropped from `data_scientist` selection entirely instead
  (removed `b_lessongen_04`'s tag rather than force a second, ill-fitting
  one). Both are real, confirmed via live `select_for_profile()` runs
  and `bank validate`, not just described; see this session's log entry
  below for the full before/after detail on each.
- **`job_analysis` and `keyword_corpus` are still 0 rows in the real
  `data/jobengine.db`, and this now blocks `rubric score`/`explain` from
  running against real production data, not just C3's corpus feature.**
  `src/jobengine/rubric/__main__.py`'s `_load_job_keywords()` reads
  `job_analysis` directly and raises a clear `SystemExit` if the
  `(job_id, profile)` row doesn't exist; it deliberately never calls the
  LLM itself (the rubric stays deterministic by construction, D8). This
  session verified the CLI works end to end only against a scratch copy
  of the db (`analyze_job()` run live, real Ollama, real persistence, but
  to a `cp`'d file in the scratchpad, never `data/jobengine.db`). No
  daily-pipeline orchestrator exists yet to populate `job_analysis` for
  real jobs (same gap C3's session flagged, still open); until one does,
  `rubric score` against a real job_id in the real db will always fail
  with that `SystemExit` today.
- `src/jobengine/rubric/measure.py`'s `stem()` is suffix-only
  normalization, not synonym-aware. Confirmed against real C3 output this
  session: "LLM" (a bank keyword tag) and "Large Language Models" (a real
  extracted required keyword) do not match, correctly per spec 08's
  literal "case and stem normalized" wording, but this under-counts
  real coverage in practice. Revisit only if this recurs as a practical
  problem in real usage, same pattern as D27; not fixed preemptively.
- `src/jobengine/rubric/measure.py`'s `measure_typography()` (R010) checks
  font/sizes/margins/tab-stop-position/justify-alignment universally but
  checks line-spacing only against the valid pair (1.15/1.5), not
  positionally validated per exact section. Deliberate scope reduction
  (R010's job is catching drift in an already-rendered document, not
  re-proving what `render.py`'s own golden test already proves at
  construction time), not an oversight; see D28 addendum 3 in
  docs/decisions.md.
- `src/jobengine/rubric/__main__.py`'s `score`/`explain` commands derive
  the docx path from the pdf path via `.with_suffix(".docx")`, requiring
  the two files to sit side by side with matching stems. Works for
  `scripts/render_pdf_sample.py`'s output and this session's manual CLI
  checks; will need a real source of truth (`job_resume_variants.
  docx_path`/`pdf_path` once D3/D4 populate that table) rather than a
  filename convention once real variants exist.
- `measure.select_for_profile()` (new this session, in
  `src/jobengine/rubric/measure.py`) is the only place in the codebase
  that filters bank content by profile. `render.py` itself still has no
  per-profile filtering; nothing in the production pipeline calls
  `select_for_profile()` outside `rubric/`'s own CLI and tests, since E2
  (base resumes) hasn't started. Don't be surprised render() output looks
  untailored if invoked directly.
- **Process note for any future renderer change** (Projects section,
  Publications section, or anything else in `render.py` that touches
  layout): get a manual visual check against a real `.docx` open in Word
  before marking the change done, not just a passing golden test. Two real
  bugs in A4 (the education degree/status line right-aligning via
  hardcoded spaces instead of a tab stop, and the contact line printing
  raw URLs as visible text instead of short hyperlinked labels) both had
  fully passing tests at the time and were only caught by a manual XML/
  visual review after the fact. That's two occurrences, not a one-off, so
  treat golden-test-green as necessary, not sufficient, for any layout
  change. Use `scripts/render_sample.py` (writes to
  `resume/rendered/preview/sample.docx`) to generate something to actually
  look at.
- `src/jobengine/db/models.py` only has typed accessors for `companies`,
  `jobs`, and `outcomes` (what A1's definition of done exercises). The other
  13 tables have schema but no pydantic model/accessor yet; add them
  alongside the phase that first writes to them.
- `schema_migrations` currently only ever records one row
  (`0001_initial`). Fine for now since there's a single schema revision;
  will need real per-migration-file tracking once schema.sql needs a second
  revision.
- FK constraints reference single-column `id` PKs only (jobs, base_resumes,
  job_resume_variants, applications). `contacts.company_slug` and
  `jobs.company_slug` link to `companies`, but `contacts` has no `ats`
  column in the spec, so its link to `companies` (whose PK is composite
  `(slug, ats)`) is not FK-enforced. Matches the spec's literal column list;
  flagging in case that was an oversight in the spec rather than intentional.
- Spec 01's CV-vs-docx conflicts were resolved by asking the user directly
  (reading both `resume/source/Aankit_CV.pdf` and
  `docs/headless-headhunter/template.docx` first) and are now baked into
  `resume/bank/aankit.yaml`: BTech end date is September 2020 (docx wins
  over the CV's Dec 2020), citation count is 140+ (CV wins over the docx's
  130+), the "October 202" typo (docx, SEI Investments role start) resolved
  to October 2021, and both job titles (Bantrly: "AI Engineer", UTD:
  "Machine Learning Researcher") follow the CV, the docx being stale.
- 8 of the CV's 10 "Projects" entries are deliberately not in the bank:
  TinyML Drone, SecureVision, Speculative Decoding, Language Model for
  Low-resource Text Data, Sentiment Classification, Graph-Based Heuristic
  Optimization, Speech Emotion Recognition, and Branch Prediction Analysis
  each have only 1-2 bullets' worth of real material in the CV, below rule
  9's 3-bullet-per-role minimum (summary included). Padding them to 3 would
  mean inventing content, which the hard rules forbid. Only the two
  meatiest, Bantrly Lesson Generator (5 bullets) and Document Intelligence
  Platform (6 bullets), are seeded. Revisit only if more real material
  about the other 8 surfaces (e.g. expanded READMEs), not by inventing
  detail to hit the minimum.
- `Certificate` model in `src/jobengine/resume/bank.py` (`id`, `name`,
  `issuer`, `year`) is a guess at field shape. Spec 01's example only shows
  `certificates: []`, no populated entry to confirm the shape against.
  Revisit when real certificate content is seeded.
- `coverage` command in `bank.py` is real but not yet useful: `keyword_corpus`
  is empty until C3 (keyword extraction) lands, so it will currently report
  "no uncovered keyword_corpus entries" for any profile regardless of the
  bank's actual content.
- slop_lint's W001 (keyword coverage) has the same `keyword_corpus`-is-empty
  problem as `bank coverage` above; real but inert until C3 lands.
- slop_lint's W002 (front-loading) is a documented no-op stub, always emits
  "not yet measurable" since real y-coordinates need D2's PDF geometry.
  Revisit when D2 ships.
- slop_lint's H008 (id traceability) has nothing to meaningfully fail
  against yet outside test fixtures: every current lint target is the bank
  itself, so every id trivially traces to itself. It earns its keep once D4
  starts writing P3 rephrase variants that must keep their parent id.
- `_TECH_JARGON_TERMS` in `slop_lint.py` (H006) is a hand-maintained list of
  about 20 known tool/tech-stack names pulled from the current bank
  content, not exhaustive or auto-derived. Update it by hand when a new
  tool shows up in the bank; see D21 in docs/decisions.md.
- `--changed` mode's lintable-path filter (`_LINTABLE_PATH_RE` in
  `slop_lint.py`) is hardcoded to `resume/bank/*.yaml`, the only lint
  target that exists pre-D4. Extend it once D4 writes variant files
  elsewhere.
- `registry.py`'s `harvest` population path (bulk slug extraction from the
  Common Crawl CDX index, spec 04's ~95k-identifier path) is not built.
  Deferred out of B1 by explicit request; `seed` + `add` + `validate` alone
  satisfy B1's DoD. Revisit as its own item if the 15-company starter seed
  list proves too thin once B2/B3 need real volume.
- `src/jobengine/sources/models.py`'s `JobPosting.content_hash` does not
  exist; hashing for the "did this posting's content change" edit-event
  check in spec 04's sync pseudocode belongs to B2 (the diff logic), not
  B1 (the clients). Don't be surprised it's missing when B2 starts.
- `_client.py`'s `retryable()` uses `wait_exponential(multiplier=0.5,
  max=8)`, deliberately smaller than a typical production backoff, chosen
  so `test_greenhouse_retries_on_5xx_then_succeeds` doesn't add much wall
  time. Spec 04 only says "exponential backoff" with no concrete numbers,
  so this was a free choice, not a spec compromise; revisit if real-world
  5xx behavior from Greenhouse/Ashby suggests otherwise.
- **B2's DoD is only partially verified, and this matters before relying on
  it in production.** Spec 04's literal acceptance criterion is "two sync
  runs a day apart produce a non-zero count of rows with `first_seen_at`
  on the second day," plus `tests/test_sync.py` asserting a second sync of
  unchanged data touches no `first_seen_at`. The second half is real and
  automated: `test_second_sync_of_unchanged_data_does_not_change_first_seen_at`
  and `test_new_posting_on_second_run_gets_its_own_first_seen_at` both
  pass, and were additionally re-verified against the live APIs this
  session (seeded all 15 companies, ran `sync` twice back to back: run 1
  wrote 3834 new jobs across 15 distinct `first_seen_at` timestamps, run 2
  showed `new=0 updated=3834`, and a direct SQL check afterward confirmed
  still exactly 15 distinct `first_seen_at` values, one per company, all
  from run 1). What is **not** verified, and can't be by a unit test or a
  same-session live check: a real *unattended* production execution, not
  triggered by a human. Same category of caveat as A4's golden test
  needing a manual Word check, "tests green" proves the mechanism, not the
  schedule firing on its own. See the next bullet for exactly what's left
  and the check to run tomorrow.
- **Scheduling is built and manually-verified-once; the unattended proof
  is what's left, not the scheduling itself.** Earlier notes in this file
  said scheduling was "unstarted" — that was wrong as of this session and
  is corrected here. What actually exists: Windows Task Scheduler task
  `job-engine-sync`, created via `schtasks /create` (CLI, not the GUI: the
  GUI produced "arguments not valid" errors from how it saved an inline
  `wsl.exe -e bash -lc "..."` argument string, a GUI quirk, not a script
  problem), pointing directly at `C:\Users\aanki\run-sync.bat` with no
  inline arguments. Schedule is every 3 hours starting 6am local time
  (`PT3H` interval, `P1D` duration, so ~6/9/12/15/18/21 local), not twice
  daily as spec 04 originally said; spec 04's "Scheduling" section has
  been rewritten with the reasoning (ATS platforms batch-publish on
  business-hour HR workflows, not a fixed clock time, so polling frequency
  is the reliable lever, not time-of-day, and these are free
  unauthenticated APIs so a shorter interval has no real downside).
  Manually confirmed working once via `schtasks /run`: `runs` row id 6 in
  `data/jobengine.db`, `companies_ok=15`, `updated=3834`, `new=0`,
  `edited=0` (zero drift from the id-5 run right before it). What that
  proves: the `.bat` -> WSL -> `scripts/sync.sh` -> `sync.py` chain works
  end to end when invoked. What it does **not** prove: that Task Scheduler
  actually fires it unattended at its configured trigger times, since
  every `runs` row known at the time (ids 1-6, all
  2026-08-02T22:03-22:27 UTC) was a manual `schtasks /run` during
  setup/debugging, not a real trigger firing.
  **Update, resolved rather than left as an anomaly:** two more `runs`
  rows appeared after id 6 (id 7 at `2026-08-02T22:40:20Z`, id 8 at
  `2026-08-02T22:59:58Z`, both `companies_ok=15 updated=3834 new=0
  edited=0`, same healthy zero-drift shape). Checked both against the live
  system, not left as an unexplained gap: this machine is Central Time,
  CDT (UTC-5) active. Converted to local, id 7 is `17:40:20` (5:40:20 PM),
  which lands nowhere near a trigger boundary, 20 minutes before the next
  one (6pm), so **id 7 is a manual `schtasks /run`**, consistent with ids
  1-6. Id 8 is `17:59:58` (5:59:58 PM), which is within **3 seconds** of
  `schtasks /query /tn job-engine-sync /v`'s own reported `Last Run Time:
  8/2/2026 6:00:01 PM`, on the exact configured 6-hour-of-day trigger
  boundary (6am start, every 3h: 6/9/12/15/18/21). **id 8 is very likely
  the first genuine unattended scheduled firing**, not a manual test: a
  human-typed `schtasks /run` landing within 3 seconds of an exact
  3-hour-grid boundary would be an extraordinary coincidence. Not treated
  as fully conclusive, only strong: this machine's Task Scheduler
  Operational event log (`Microsoft-Windows-TaskScheduler/Operational`,
  checked via `Get-WinEvent -ListLog`) is disabled, so there's no
  per-event log entry that definitively tags a run's trigger type the way
  an enabled operational log would; the conclusion rests on timing
  alignment, not a direct record. `schtasks /query` also reports `Next Run
  Time: 8/2/2026 9:00:00 PM`, so a second same-evening data point is
  available by re-checking `runs` after that time, ideally without anyone
  running `schtasks /run` near it, to get a cleaner sample than id 8's
  (which landed shortly after active manual testing, id 7, rather than
  from a period of total inactivity).
  **Check to run tomorrow:** query `runs` (not `jobs`) grouped by
  `date(started_at)` and hour, `SELECT strftime('%Y-%m-%d %H', started_at)
  AS hour, counts FROM runs WHERE stage = 'sync' ORDER BY started_at` and
  look for six new rows landing on their own near 06/09/12/15/18/21 local,
  with nobody having run `schtasks /run` that day. The `runs` table is the
  right thing to group, not `jobs.first_seen_at` as originally suggested:
  `runs` gets a row on every invocation regardless of outcome, while
  `first_seen_at` clusters only appear at a trigger time if a genuinely
  new posting happened to show up in that specific 3-hour window, quiet
  companies could make a real firing look like a miss if `jobs` is the
  only thing checked. Worth checking both, but treat `runs` as the
  authoritative firing record and `jobs.first_seen_at` clustering as
  corroborating evidence, not the primary signal.
  **RESOLVED 2026-08-03, not left open any longer:** `runs` ids 9 and 10
  landed at `started_at` 04:13:50Z and 14:02:54Z on 2026-08-03, cross-
  referenced by the user against Task Scheduler's own Last Run Time.
  Stronger than the earlier id-8 signal, and not just a timing coincidence
  this time: both carry real non-zero diffs (id 9: `new=2 edited=53
  closed=2`; id 10: `new=10 edited=1 closed=9`, `companies_ok=15` on both),
  the same shape that distinguished a genuine fetch from the zero-drift
  manual re-runs (ids 6-8) the day before. Two independent unattended
  firings with real content changes is the proof this item was waiting on.
  B2 is production-live, not just manually-invokable; TODO.md and the
  Status table above reflect this.
  **REGRESSED 2026-08-07, discovered via a real-db read-only check, not
  left unnoticed:** the confirmed-working schedule above stopped
  succeeding sometime after its own last good run
  (`2026-08-03T20:00:01`) and failed silently through at least
  2026-08-07 — `runs` has zero rows in that window (confirmed via
  `SELECT DATE(first_seen_at)... GROUP BY` on the real db showing only
  2026-08-02/08-03, and `SELECT started_at FROM runs ORDER BY
  started_at DESC LIMIT 10` showing nothing past 08-03T20:00), and zero
  Task Scheduler log files exist for the missed dates either. Task
  Scheduler's own `Last Result` for the task is `-2147020576`
  (`0x800710E0`); the low word `0x10E0` decodes to "The operator or
  administrator has refused the request." Root cause identified, not
  just the symptom: the task's logon mode is "Interactive only," which
  requires an active logged-in session at the exact moment each 3-hour
  trigger fires; every trigger that lands while nobody is logged in gets
  rejected outright, not queued. This is why "start the task as soon as
  possible after a scheduled start is missed" (a setting already
  enabled) doesn't help — that setting recovers a *skipped* trigger
  (e.g., the machine was off), not a trigger that fired and was actively
  *refused*, which is what `0x800710E0` means. Fix identified: switch
  the task's logon mode to "Run whether user is logged on or not" with a
  stored account password, which lets Task Scheduler run it via a
  background service session regardless of whether anyone is logged in.
  **Not yet applied**: setting the stored password hit an unrelated
  Windows issue during setup, not yet resolved. Confirmed this is purely
  a scheduling problem, not a pipeline problem: a manual `schtasks /run`
  still works fine today, meaning `sync.sh`/`sync.py`/the task's own
  command line are all still healthy; only the *unattended* trigger path
  is broken.
  **Consequence for B-followup (daily filter-survivor cap calibration,
  TODO.md):** the real `jobs`/`runs` history has a genuine multi-day
  gap, 2026-08-04 through at least 2026-08-07, with zero organic fetch
  activity, not because there was nothing to fetch but because the
  schedule silently failed to run. When B3-followup eventually
  calibrates a daily survivor cap against real `first_seen_at` history,
  this gap must be excluded or explicitly noted, not averaged over as if
  it were a genuine zero-volume day — doing so would understate real
  daily volume.
- `sync.py`'s CLI (`_main()`) calls `logging.basicConfig(level=logging.INFO)`
  globally, which also turns on `httpx`'s own INFO-level request logging,
  every GET request prints a line. Harmless (stderr noise, not a
  correctness issue) but not intentional CLI polish; narrow the config to
  `jobengine`'s own logger if this gets annoying in practice.
- `sync.py`'s `content_hash` covers only `description` (per spec 00's
  literal column note: "sha256 of description, detects real edits"). A
  title or location change on an otherwise-identical posting will not
  trigger an `edited` count or log line. Read as the spec's intended
  scope, not an oversight; revisit only if a real title-change case turns
  out to matter downstream.
- `config/filters.yaml`'s `exclusion_keywords`/`exclusion_override_keywords`
  only exist for `software_engineer`. `ai_ml_engineer`'s bare "researcher"
  and `data_scientist`'s bare "scientist" aliases have no exclusion list
  yet, even though the real-data check during B3 planning showed both pull
  in some non-target noise (e.g. "People Research Scientist, Recruiting"
  under `data_scientist`). Not fixed because the false-positive rate was
  visibly much smaller than bare "engineer"'s (a handful of titles, not
  hundreds) and no one asked for it; revisit if real usage shows it
  matters more than this first read suggested.
- `filter.py` has no location/country hard filter. `is_remote()` is only a
  resolver (column vs. location-text fallback) used by tests and available
  to callers; nothing in B3 actually excludes a job for being onsite in a
  non-US location. `identity.toml`'s F-1 OPT US-only work authorization
  makes this a real gap for a future pass, not implemented this session
  because it was never asked for, only `is_citizenship_or_clearance_required`
  (JD text) and the employment-type/dedup checks were.
- B3's filter functions still have no CLI entry point
  (`uv run python -m jobengine.pipeline.filter ...`) the way
  `registry`/`sync`/`bank`/`slop_lint` each have one. Nothing in TODO.md's
  B3 DoD requires a CLI, so this still isn't built. **Partially
  addressed, not fully:** F1 (this session) added
  `passes_all_filters(conn, job, config) -> bool`, a real Python callable
  running the full chain (title match + location + seniority +
  employment type + citizenship/clearance + already-applied) in one
  call, and wired it into `web/app.py`'s queue-listing logic — the first
  real caller of the combined chain, not just individual checks in
  isolation. Still no CLI/shell-invokable surface; revisit if a future
  stage needs one outside a Python import.
- TODO.md's B1-followup (DOL LCA-based sponsorship vetting) is flagged
  only, no design work done: not scoped, no data source integration
  started, just a placeholder so the idea isn't lost.
- **C2's `required_keywords` coverage is 11/50, not the ~15 TODO.md and
  spec 07 both call for.** Marked done anyway per explicit user sign-off,
  not silently rounded up or hidden: where it does exist, coverage is
  correctly correlated with real target-profile matches (max relevance
  50-100 on keyword-annotated jobs, 0-30 on the rest, verified directly),
  so the shortfall is in count, not correctness. Revisit only if C3's
  keyword-extraction eval (Task 2, spec 07) turns out to need a larger
  labelled set to produce a stable precision/recall number; not assumed
  necessary preemptively.
- `src/jobengine/eval/` has only `fixtures.py` (the C2 loader). Spec 07's
  module layout also calls for `harness.py`, `tasks/`, and `report.py`;
  none of those exist yet, that's C1/C3/C4's work building the actual
  model-eval harness, not C2's scope (a labelled fixture file plus a way
  to load it).
- `greenhouse.py`'s new `_strip_html` found-tag heuristic (see the code
  comment directly above the function) assumes a Greenhouse `content`
  field is never a genuine mix of literal tags and separately-escaped
  literal text in the same string. Confirmed true for all 2,691 real rows
  checked this session, not a guarantee about future API responses. If
  descriptions ever look wrong again after a Greenhouse API change, that
  assumption is the first thing to check, per the code comment's own
  explicit note.
- **C1's `llm.check` cold-start latency is expected, not a regression
  signal: read this before treating a slow first check of the day as a
  bug.** Verified live by the user against the real WSL2/Windows Ollama
  setup: the *first* call after Ollama has to load the 9B model into VRAM
  took 14,945ms; every call after that, across 3 consecutive clean runs,
  landed at 600-935ms with no per-stage anomaly. Ollama unloads an idle
  model after its own keep-alive window, so the first `llm.check` (or
  first real pipeline run) after any gap, restart, or the start of a new
  day will very likely pay this same one-time cold-start cost again. If a
  future session sees one slow stage followed by fast ones in the same
  run, or a slow run after a period of inactivity, check whether it's just
  this before assuming something regressed.
  Before this live run, this session's own automated coverage was: 21
  tests against a mocked `ollama` client (no real network), plus
  `router.load_config()`'s missing-`OLLAMA_BASE_URL` path manually
  exercised against the real `config/llm.toml` (confirmed it raises the
  intended clear `RuntimeError`, not a parse error), plus one partial live
  check against a deliberately unreachable address (no real Ollama
  involved) that caught and led to fixing a real gap: the `UNREACHABLE`
  detail string was empty because `httpx`'s own connect/timeout exceptions
  often carry no message text, fixed in `check.py`
  (`f"{type(exc).__name__}: {exc}"` instead of bare `str(exc)`). The live
  run against a genuinely reachable Ollama server, described above, is
  what actually closes out C1's DoD.
- `providers/anthropic.py`'s `AnthropicProvider.call()` always raises
  `NotImplementedError`. This is deliberate, not a placeholder to fill in
  casually: see D25 in docs/decisions.md. No stage in spec 05's routing
  table uses the `"api"` tier, and CLAUDE.md hard rule 9 requires stopping
  to ask before a stage is ever wired to a paid call. `ApiConfig` in
  `schemas.py` likewise only has `enabled: bool`, no model name or other
  config, since none of that has been decided yet.
- `jobengine.llm.router.call()` and the providers return an
  `LLMCallResult` envelope but write nothing to the db themselves. No
  `llm_calls`-style table exists in `schema.sql`; per
  specs/00-data-model.md, the token/cost/model accounting columns live on
  the consuming table (`job_analysis`, `relevance_scores`), so persisting
  the envelope is C3/C4's job when those stages call `router.call()`, not
  C1's. Flagging so a future session doesn't go looking for where C1
  wrote its own accounting and conclude something's missing.
- **Update, no longer current:** the line above originally said no
  downstream stage called `jobengine.llm.router` yet. C3's
  `extract_keywords()` (`pipeline/extract.py`) is now the first real
  caller, going through `router.get_provider()` directly rather than
  `router.call()`'s fallback wrapper (a deliberate choice, not an
  oversight of C1's design, see `extract.py`'s own docstring and D26 in
  docs/decisions.md for why the eval harness specifically needs per-job
  failure isolation that `call()`'s "fail" fallback would prevent).
- **C3 shipped against a deliberate quality decision (D27 in
  docs/decisions.md), not spec 07's literal Task 2 gate.** Real measured
  extraction quality, qwen3.5:9b, against the fully-reviewed 11-job
  fixture, averaged over 4 identical-config live runs (the first run's
  numbers alone were not reproducible, see the next bullet): precision
  0.833-0.858 (mean 0.844, passes >= 0.70 in all 4 runs), recall
  0.351-0.467 (mean 0.408, fails >= 0.85 in all 4 runs, never within
  0.38 of it). Two prompt variants and three real fixture bugs were
  tried and measured before concluding further prompt/model iteration on
  this axis has diminishing (in one case, negative) returns; see D26
  addenda 1 and 3 for the full evidence. Not blocking, per D27's explicit
  reasoning (human review gates every send, recall gaps only
  under-extract and can't invent content under hard rule 2, and an
  11-job fixture can only approximate real usage), but a real, known
  quality gap, not a hidden one. Revisit only if manual review of real
  pipeline output later shows this recurring in practice, per D27's
  listed options (next candidate model, a deliberately-asked-about paid
  API call for this one stage, or accepting current quality).
- **Real LLM sampling variance in Task 2's numbers, discovered and
  resolved this session, not a hypothetical caveat.** The first
  shipped-state eval run scored precision 0.833 / recall 0.467; a second,
  immediately-following run with the exact same prompt, fixture, and
  model scored 0.849 / 0.351, a 0.116 recall swing with zero code
  changes, because `LocalProvider` pins `think=False` on every call but
  not `temperature`/`seed`. Caught before it could sit in
  docs/decisions.md as a misleadingly precise single number: ran 2 more
  samples (4 total), updated D27 to cite the real range (precision
  0.833-0.858, recall 0.351-0.467) and mean instead. The qualitative
  conclusion (precision reliably passes, recall reliably fails by a wide
  margin) holds across every sample, so this doesn't change what shipped,
  only how honestly its quality is described. `model_evals`'s most
  recent row by `run_at` now genuinely matches the shipped code (verified
  by diffing `extract.py`'s prompt text against what was in place for
  that run) — this was a real, temporary gap earlier in the session (the
  most recent row was a rejected prompt variant, not the shipped state)
  and is resolved as of this checkpoint, not still open. No schema change
  made to prevent this recurring (e.g. an `is_current` column); if a
  future session edits `extract.py`'s prompt again, re-run `eval run`
  before trusting `compare`'s newest row.
- **`job_analysis` and `keyword_corpus` have zero rows in the real db,
  still.** Only `extract_keywords()` (the raw LLM call) has been
  exercised live this session, via the eval harness; `analyze_job()` (the
  actual production orchestration function that writes to `job_analysis`/
  `keyword_corpus`) has only ever been run in tests against a `tmp_path`
  db, never against `data/jobengine.db`. No daily-pipeline orchestrator
  exists yet to call it for real (that's later phase wiring, D-phase and
  beyond); flagging so a future session doesn't assume the corpus has
  started accumulating just because C3 is marked done.
- **The qualifications-section-only scope boundary used to re-derive
  `human_labels.yaml` drops some real-looking terms that only appear in
  a JD's "what you'll do"/responsibilities text.** Applied consistently
  across all 11 jobs per explicit instruction, not inconsistently, but
  worth knowing about: `job_id` 2545 lost `fine-tuning`/`reinforcement
  learning`, `job_id` 3654 lost `robust evals`/`reward signals`/
  `training data` (arguably its most central, role-defining terms),
  `job_id` 1705 lost `CI/CD`/`cross-compilation`, `job_id` 3267 lost
  `SDLC`, `job_id` 3283 lost `firmware`. If a future session wants
  responsibilities-section content included too, that's a scope change
  to make deliberately, not a bug to fix silently; the current fixture
  is internally consistent under the boundary it was built with.

---

## Decisions made during implementation

- Renamed the scaffolded `src/job_engine` (uv's default from the hyphenated
  project name) to `src/jobengine`, and added
  `[tool.uv.build-backend] module-name = "jobengine"` to pyproject.toml, to
  match the package name used throughout CLAUDE.md/TODO.md/specs. Confirmed
  by asking; not a spec change, no decisions.md entry needed.
- `first_seen_at` immutability (jobs and, per explicit request, companies)
  is enforced with two layers, both in SQL: the upsert's `ON CONFLICT DO
  UPDATE SET` clause omits the column entirely, and a `BEFORE UPDATE`
  trigger on each table raises `RAISE(ABORT, ...)` if any statement still
  tries to change it. Added an addendum to D3 in docs/decisions.md.
- `SummaryBullet` is a separate, lighter pydantic model from `Bullet` (no
  `what`/`how`/`result`/`evidence`/`profiles`), exempt from rules 2 and 4.
  Confirmed by asking; spec 01's own example shows summary without those
  fields.
- Rule 1 (unique ids) is enforced bank-wide, across education, roles,
  summaries, bullets, and publications, not just `bullets[].id` as the rule
  text literally says. Confirmed by asking.
- `KNOWN_PROFILES` (`ai_ml_engineer`, `software_engineer`, `data_scientist`)
  is hardcoded in `bank.py` pending E1's formal profile registry. Confirmed
  by asking.
- Rules 3 (speculative status) and 7 (length estimate) are warnings, not
  hard errors; `validate`'s "zero errors" definition of done is unaffected
  by either. Confirmed by asking.
- Rule 10 ("every keyword appears in at least one bullet, or it is dead
  weight") is not enforced in `validate_bank()`. My first reading (keyword
  must appear verbatim in its own bullet's text) failed when smoke-tested
  against the spec's own `role_bantrly` worked example: its summary is
  tagged `[Python, FastAPI, speech-to-text, LLM]` while Lee's rule requires
  the summary sentence to stay non-technical, so it never names those tools.
  Moved rule 10 to `coverage_gaps()`, checked against `keyword_corpus`
  instead. Confirmed by asking; significant enough that it's also recorded
  as D20 in docs/decisions.md.
- `Role.company`, `.location`, and `.start` are now `str | None = None`
  instead of required, to support `kind: project` entries. Lee's guide
  (pg. 17-18) states projects skip dates and location entirely, unlike
  full_time/internship/research roles where all three are always present;
  the original schema didn't account for that. Not added to
  docs/decisions.md: this is a direct correction to match the guide's own
  stated rule, not a new judgment call.
- slop_lint's lint target schema deliberately mirrors bank.py's shape but
  stays lenient (every field optional/defaulted) instead of reusing
  bank.py's strict `Bank`/`Role`/`Bullet` models directly. A strict model
  would raise a `ValidationError` on a fixture missing its summary before
  slop_lint's own H005 rule ever got a chance to fire; the DoD requires
  "flags a bad fixture," not a stack trace. Confirmed by asking during
  planning.
- S002's banned-vocabulary matching uses light per-word suffix tolerance
  (`streamlin(e|es|ed|ing)`, `leverag(e|es|ed|ing)`, etc.), not literal-only
  matching. Literal-only would miss the exact violation spec 02 itself
  calls out (the CV's own "streamlined"/"spearheaded" bullets, past tense),
  and H003 requires every bullet to open in past tense anyway, so the
  inflected form is the common case in real prose, not the exception.
- H006 (summary jargon) checks keyword leakage specifically: does a
  keyword the role itself declares (summary or bullets, filtered through
  `_TECH_JARGON_TERMS`) appear verbatim in that role's own summary text.
  It is not, and will not become, a general jargon/comprehensibility
  judgment call; hard rule 11 already rules out asking a model to grade
  resume quality, and this stays a plain string check. See D21 in
  docs/decisions.md for the full history (first pass flagged 9 false
  positives against the real bank, narrowed after that). Confirmed by
  asking, twice.
- `lint_path()` takes the ground-truth bank path as a parameter
  (`bank_path`, default `DEFAULT_BANK_PATH`) instead of hardcoding it,
  specifically so H008 could get a real end-to-end test (YAML on disk,
  loaded through the actual loader) against a small fixture bank, not just
  an in-memory fabricated id set.
- `companies.source` CHECK widened to `('seed', 'harvest', 'manual')`
  instead of mapping `registry add`'s manual entries onto `source='seed'`.
  Confirmed by asking; specs/00-data-model.md's column note updated to
  match, `data/jobengine.db` dropped and re-`init`'d (it had zero rows, so
  no migration needed, just a schema.sql edit).
- B1's scope is `greenhouse.py`, `ashby.py`, and `registry.py` (seed, add,
  validate) only, not `sync.py`'s fetch-and-diff loop, even though spec 04
  groups all four under one module and TODO.md's B1 "Done" line literally
  says `sources.sync`. That line is read as shorthand for "the registry
  side of the pipeline reports OK/dead counts," met here via `registry
  validate`; spec 04's own CLI section already lists `registry validate`
  and `sync` as separate commands, and B2's own DoD ("first_seen_at delta
  ... put this on a schedule") is unambiguously about the jobs-diffing
  half. Confirmed by asking (session-start scoping question) before
  writing code, not decided silently.
- Common Crawl harvest (spec 04's bulk slug-extraction path) deferred out
  of B1 entirely, not stubbed. Confirmed by asking; `seed` + `add` +
  `validate` alone satisfy B1's stated DoD.
- Ashby's `ats_job_id` is sourced from the posting's `id` field, which spec
  04's Ashby field list never mentions but the real API returns alongside
  every field the spec does list. Confirmed by asking rather than guessing
  a fallback key (e.g. hashing `title`+`publishedAt`), since `ats_job_id`
  is part of the `jobs` table's uniqueness constraint and getting it wrong
  would silently duplicate or drop rows once B2 wires this up.
- `registry.py`'s `seed()`/`add()` use a dedicated `INSERT OR IGNORE` path
  (`_insert_new_company()`), not `jobengine.db.models.upsert_company`. Not
  a stylistic choice: `upsert_company`'s `ON CONFLICT DO UPDATE` always
  overwrites `status`, so reusing it here would mean every re-run of
  `registry seed` resets already-validated companies back to
  `unverified`, silently destroying `validate`'s accumulated state. Caught
  during planning, not after a bug, and covered by
  `test_seed_is_idempotent_and_does_not_reset_validated_status`.
- A company that 404s stays at whatever status it already had
  (`unverified` or `active`) until its 3rd consecutive failure flips it to
  `dead`; spec 04 only states the status change at the threshold ("mark
  `dead` at 3"), so no intermediate demotion (e.g. `active` -> `unverified`
  on the 1st or 2nd failure) was invented. Not asked separately; read as
  the literal, more conservative interpretation of the spec text rather
  than a judgment call worth interrupting for.
- Spec 04's "if content_hash changed, record an edit event" has no backing
  table anywhere in the 16-table schema (checked specs/00-data-model.md
  and the `runs` table, which is a per-sync-run summary, not a per-job
  log). Confirmed by asking rather than either inventing a new table
  silently or dropping the requirement silently: edit events are a
  `logging.info()` line per changed job plus an `edited` count in that
  sync run's `runs.counts` JSON, no schema change. Significant enough
  (real spec/schema gap, not a stylistic call) that it's also recorded as
  an addendum to D2 in docs/decisions.md.
- `close_missing_jobs()` in `db/models.py` diffs open-job id sets in
  Python and issues one `UPDATE` per missing job (`executemany`), not a
  single `WHERE ats_job_id NOT IN (...)` query. Not asked separately
  (an implementation-robustness call, not a spec ambiguity): a live check
  during this session showed Ashby's real OpenAI board at 752 postings,
  which is fine under most SQLite bound-parameter ceilings today but not a
  bet worth encoding into a query that gets less safe as boards grow;
  diffing two sets and looping avoids the question entirely for about the
  same amount of code.
- `sync()`'s `--dry-run` is implemented as a single code path (the full
  diff always runs and always writes) with the decision deferred to
  `conn.commit()` vs. `conn.rollback()` at the very end, rather than two
  separate branches (one that writes, one that only computes and prints).
  Not asked separately: this was the design already named in the plan
  presented before coding, chosen specifically so there is exactly one
  implementation of the diff logic to keep correct, not two that could
  silently drift apart.
- `data/jobengine.db` is now treated as irreplaceable once B2 landed, not
  scratch state that a live sanity check can freely reset. Every prior
  session (this one's own B1 and B2 work included) reset the real db after
  live-API checks without asking first, on the reasoning that pre-B2 it
  held nothing but refetchable data. That reasoning stopped holding the
  moment `jobs.first_seen_at` started encoding real elapsed-time history:
  a reset now destroys information that cannot be regenerated, and nothing
  in the schema or CLI would even flag it. Confirmed by asking, and
  significant enough to be a hard rule, not just a habit: CLAUDE.md rule
  13 and D22 in docs/decisions.md. Investigated first, before adding the
  rule, whether any test fixture could have caused a prior data loss
  report by silently pointing at the real db path; confirmed none can
  (every `connect()` call in `tests/*.py` passes an explicit `tmp_path`,
  no `conftest.py` exists to inject a shared override, and the only three
  `connect(DEFAULT_DB_PATH)` call sites are the real CLI entry points in
  `db/__main__.py`, `sources/registry.py`, and `sources/sync.py`). The
  actual cause of that particular report was this session's own prior
  live-check resets, not a bug.
- B3's daily-survivor-count target (docs/architecture.md's 300-500/day) is
  deliberately not calibrated against the current db (15 companies, one
  backlog snapshot, single `first_seen_at`). Recorded as D23 in
  docs/decisions.md, significant enough for its own entry since it reverses
  what would otherwise have been the natural approach (fit thresholds to
  hit the number in the spec). Confirmed by asking; the user caught this
  before any thresholds were picked.
- B3 persists nothing: `filter.py` exposes pure functions, not a
  filter-survivor table. Recorded as an addendum to D23 rather than its own
  decision, since it's a direct consequence of the same "don't calibrate
  against stale/small data" reasoning: a persisted snapshot would go stale
  the moment `config/filters.yaml` is tuned again. Confirmed by asking.
- `is_citizenship_or_clearance_required` is a hard exclude across all
  profiles, and B3 deliberately does not attempt general visa-sponsorship
  detection from JD text. Recorded as a second addendum to D23: the
  asymmetry matters (absence of clearance language is neutral, absence of
  sponsorship language is not evidence of anything, since most JDs never
  mention it either way), so a positive-sponsorship-language filter would
  silently punish real sponsoring companies. That question is deferred to
  DOL LCA data at the company-selection layer (TODO.md's new B1-followup
  item), not solved in B3. Confirmed by asking.
- `_phrase_matches()` in `filter.py` applies word-boundary matching to any
  single-word phrase and plain substring matching to any multi-word
  phrase, as a general rule rather than a hardcoded list of "these specific
  words need word boundaries." Not asked separately: this generalizes the
  exact reasoning already confirmed for bare "engineer" (must not match
  inside "engineering") to every other phrase in the config, including
  ones added later, without needing a second hardcoded list kept in sync
  with the YAML.
- `src/jobengine/pipeline/__init__.py` was added as an empty file when
  `filter.py` became the first file in that package, matching the existing
  `db`/`resume`/`sources` convention (each has an empty `__init__.py`)
  rather than leaving `pipeline/` as a bare namespace package like `rubric/`
  currently is. Not asked separately, a direct convention match.
- `greenhouse.py`'s `_strip_html` bug (tag-strip-then-unescape left every
  Greenhouse job's real, double-escaped markup completely unstripped) was
  found by accident, while building C2's fixture excerpts, not something
  this session set out to look for. Fixed with an `html.parser`-based
  extractor plus a found-tag heuristic to reconcile it with an older,
  purely synthetic test case that needed the opposite order; empirically
  verified both before proposing the design and after implementing it,
  including a full sweep confirming 0/2,691 real Greenhouse jobs still
  contain any tag residue post-fix, not just a sample. Backfilled the
  existing 2,691 rows under an explicit, scoped hard-rule-13 exception.
  See D22/D23's addendum in docs/decisions.md.
- C2's `human_labels.keywords` is attached only to a job's max-relevance
  profile(s), not duplicated across every profile the job has any row for.
  See D24 in docs/decisions.md for the full reasoning; significant enough
  (a real schema-shape mismatch between the fixture's one-list-per-job
  design and the table's per-profile keying) to warrant its own decision
  number, not folded into an existing one.
- C1's Anthropic guard is two independent layers (explicit `api_key`
  required at both `AnthropicProvider.__init__` and
  `router.get_provider()`, neither module ever reading `os.environ` for a
  key) and `AnthropicProvider.call()` is a permanent
  `NotImplementedError` stub, not a real client, since no stage in spec
  05's routing table uses the `"api"` tier. Significant enough (directly
  implements CLAUDE.md hard rule 9's "nearly impossible to trigger by
  accident" requirement, and a future session could otherwise mistake the
  stub for an unfinished TODO) to get its own entry: D25 in
  docs/decisions.md.
- Before coding, confirmed two choices with the user rather than guessing:
  (1) `router.load_config()` raises a clear `RuntimeError` if
  `OLLAMA_BASE_URL` is unset, rather than computing a fallback via `ip
  route show default` the way spec 05's WSL2 section shows as a manual
  shell command; (2) this session builds and unit-tests C1 against a
  mocked `ollama` client only, the real `uv run python -m
  jobengine.llm.check` run against live Ollama is left for the user to do
  separately. Not added to docs/decisions.md as their own numbered
  entries: (1) is a small, self-contained implementation choice fully
  captured in `router.py`'s own error message and docstring, and (2) is a
  verification-sequencing choice, not a design decision, same category as
  A4's "manual Word check" process note rather than a D-numbered decision.
- `router.py`/`providers/local.py`/`providers/anthropic.py`'s public
  `call()` methods are `async def`, awaited directly or driven via
  `asyncio.run()` by callers/tests, matching `sources/greenhouse.py`'s and
  `ashby.py`'s precedent for I/O-bound leaf functions. Not
  `sources/sync.py`'s pattern (a sync top-level function wrapping
  `asyncio.run()` internally so callers never touch async): that pattern
  fits a single top-level orchestration entry point, and `router.call()`
  is a leaf function meant to be composed by a future async caller (C3/C4
  processing many jobs), same role as `fetch_board()`, not a top-level
  entry point itself. `check.py`'s `main()` is the one place in this
  package that does wrap with `asyncio.run()`, since it is the actual CLI
  entry point. Not asked separately: a direct convention match, same
  reasoning already applied without asking to `pipeline/__init__.py` in
  the B3 session.
- C3's extraction schema is narrower than `job_analysis`'s full 6-column
  shape (keywords + `tech_stack` only; `jd_quality` computed
  deterministically; `canonical_title`/`seniority` deferred), confirmed
  by asking before coding. `job_analysis` also gained a
  `(job_id, profile)` unique index so re-running extraction upserts
  rather than accumulates history, matching `relevance_scores`, also
  confirmed by asking. See D26 in docs/decisions.md.
- Task 2's eval scoring compares `required_keywords` UNION
  `preferred_keywords` on both sides, not required-only, and
  deliberately excludes `tech_stack` even though it sometimes contains a
  genuinely-missed required skill. Both calls are significant enough,
  and evidence-grounded enough (concrete job_ids, real measured
  precision/recall deltas, not just reasoning), to warrant their own
  decision entries rather than folding into code comments alone: D26
  addenda 1-3 in docs/decisions.md.
- **C3 ships with real extraction quality that does not meet spec 07's
  numeric Task 2 gate (recall 0.351-0.467 across 4 live runs vs. 0.85), a
  deliberate decision, not a silent shortfall.** Confirmed by explicit
  user instruction, with
  reasoning spanning the pipeline's own architecture (human review before
  every send), CLAUDE.md hard rule 2 (under-extraction can't invent
  content, the safe failure direction), and the limits of a static
  fixture eval versus real usage. Recorded as D27 in docs/decisions.md,
  including the revisit conditions and the ordered list of options if
  manual review later shows this matters in practice. TODO.md's C3
  checkbox and the Status table above both reference D27 explicitly
  rather than silently claiming the literal DoD passed.
- `src/jobengine/resume/pdf.py`'s `render_pdf()` does not use "the pptx
  skill's wrapper" spec 03 names for the sandbox: no such skill exists in
  this session's available tools (checked the skill list directly). Used
  a plain `subprocess` wrapper instead (no new dependency), with a unique
  throwaway `-env:UserInstallation` profile dir per call and a 60s
  timeout, the two concrete mitigations for the hang spec 03 warns about.
  Not asked separately: the referenced skill genuinely doesn't exist here,
  there was no real choice to confirm.
- Four decisions from D1 confirmed by asking rather than guessed, all
  recorded as D28 (with 3 addenda) in docs/decisions.md, significant
  enough for their own entries: (1) D1 absorbed D2's scope entirely,
  because R002 has no fallback measurement in spec 08 and R006's fallback
  is explicitly scoped to the bank validator, not the rubric pipeline;
  (2) score.py's "keyword density in first role" and "bullets carrying
  2+ keywords" formulas, which spec 08 names but never defines; (3)
  `measure.select_for_profile()`, a new minimal candidate-resume filter,
  confirmed as deliberately distinct from D3's patch ladder scope; (4)
  two scope reductions in `measure.py` (stem-only keyword matching, no
  synonyms; R010's line-spacing check against a valid pair rather than
  positional validation), both flagged as known limits, not fixed
  preemptively.
- D3's patch ladder (`src/jobengine/rubric/patch.py`) confirmed working
  via a real R002 deficit closing (a real bank keyword, "Chroma DB",
  genuinely covered but positioned in the Projects section; P2 promoted
  that section to the front and R002 flipped from fail to pass, through
  the real render/PDF/pdfplumber/score_resume pipeline, zero model
  calls), plus two significant real findings from grounding against 9
  live-extracted real job postings before landing on that demonstration:
  P1 is structurally inert against the current bank (nothing is ever
  held back by `select_for_profile()` for it to swap in), and none of
  those 9 postings closed via P0 either, since `role_bantrly` (the only
  role reaching page 1's top half) already had reasonable internal
  ordering for what they happened to require. All recorded as D29 in
  docs/decisions.md, including an addendum on why R009's date-overlap
  loosening (needed for P0's role-swap logic, and confirmed by asking
  since it changes an already-shipped D1 rule's semantics) was applied.
- D4's P3 rephrase writeback is deliberately not wired to the real
  `resume/bank/aankit.yaml` (confirmed by asking; `apply_variants_to_bank()`
  /`dump_bank()` tested via tmp_path round-trips only, including the real
  bank loaded read-only and dumped to a tmp_path copy). The traceability
  guard (`validate_rewrite()`) is a general capitalized/digit-token check
  against the parent's what/how/result + identity.toml, deliberately
  stricter than `slop_lint.py`'s `_TECH_JARGON_TERMS` allowlist (which
  could only ever catch a previously-seen fabrication, not a genuinely
  novel one). A real bug was found via live-model grounding, not by this
  session's own synthetic tests: an accepted rewrite's `keywords_added`
  was never merged into the working bullet's `.keywords`, so P3 could
  never actually move `coverage`; fixed and re-verified against the same
  real model. Two live-Ollama runs (not mocked) confirm the mechanism
  end to end: a real job's deficit the model correctly declined to
  fabricate for, and a real deficit (`required_keywords=["CMB"]`) closed
  for real (coverage 0.0 -> 1.0). All recorded as D30 in
  docs/decisions.md.

---

## Session log

(Newest first. Date, task id, what changed, what to do next.)

- 2026-08-07, F1 follow-up (done, same session as F1's initial build):
  Two unrelated items handled back to back.
  (1) Recorded a real B2 scheduling regression, discovered via a
  read-only check against the real db the user ran directly: `runs` has
  zero rows since `2026-08-03T20:00:01`, zero Task Scheduler log files
  for the missed dates, `Last Result -2147020576`
  (`0x800710E0` = "The operator or administrator has refused the
  request"). Root cause: the task's "Interactive only" logon mode
  requires an active session at each 3-hour trigger; "run as soon as
  possible after a missed start" doesn't help since this is a rejected
  attempt, not a skipped one. Fix identified (switch to "Run whether
  user is logged on or not" with a stored password) but not applied —
  password setup hit an unrelated Windows issue. Manual `schtasks /run`
  still works, confirming this is purely a scheduling problem, not a
  pipeline one. Recorded in PROGRESS.md's header, Status table (B2 row),
  and Known Issues (full detail, plus the consequence for B3-followup's
  future daily-cap calibration: 08-04 through at least 08-07 is a real
  gap to exclude, not a genuine zero-volume period).
  (2) Added `passes_all_filters(conn, job, config) -> bool` to
  `src/jobengine/pipeline/filter.py`: B3's full deterministic chain
  (`matches_profiles` + location + seniority + employment type +
  citizenship/clearance + already-applied) in one call, tests-first per
  hard rule 7 (`tests/test_filter.py` +7, one per exclusion axis
  isolated via a title that still matches a profile alias, e.g.
  "Software Engineering Manager" for the seniority case, plus a clean
  baseline and an already-applied case using the real FK chain). Wired
  into `src/jobengine/web/app.py`'s `_new_pairs()`, replacing the
  title-only `matches_profiles()` check the "not yet reviewed" list
  used since F1's initial build (a gap F1's own Known Issues entry had
  already flagged). 2 new `test_web_app.py` tests confirm the wiring
  itself, not just the underlying function: a clean untriggered job
  still appears, a non-US-location one no longer does. One ruff
  SIM103 simplification applied (`return not is_already_applied(...)`
  instead of an explicit `if/return False/return True`).
  Full suite 379/379 (up from 370 after F1's initial close), `ruff
  check`/`format --check` clean.
  Next: no next task chosen yet, needs explicit go-ahead per the session
  protocol.

- 2026-08-07, F1 (done): Planned via Claude Code's plan mode before
  writing any code, per the user's explicit request to see a plan
  grounded against real data first. No F1 spec file existed (TODO.md's
  Rules section deferred writing Phase F specs until Phase D ran on
  real data, which it now has); confirmed this via direct file check
  rather than assuming, and treated the approved plan itself as F1's
  design document.
  Research phase: read `docs/architecture.md`'s pipeline stage list (0-9,
  review is stage 8, downstream of extraction/routing/rubric/patch/
  re-score, upstream of apply), confirmed via `grep`/direct reads that
  nothing in the codebase had ever persisted to `job_resume_variants` or
  `applications` (zero models, zero insert helpers, zero real rows), and
  that no daily orchestrator wires C3 extraction through D3/D4 patching
  against real jobs. Used `AskUserQuestion` on the one genuinely
  consequential scope fork (lazy per-job trigger vs. UI-only assuming a
  future batch job vs. building a real batch orchestrator now); the user
  chose lazy-trigger, since a real batch version needs C4 (relevance
  pre-filter, not built) for a proper survivor cut first.
  Delegated the file-by-file implementation plan to a Plan sub-agent
  with the scope decision and all research findings as fixed context,
  then reviewed its output against the actual codebase before accepting
  it, not verbatim: caught a real bug in its proposal by reading
  `is_already_applied()` (`pipeline/filter.py`) directly — the
  sub-agent's applications-table-based review-state design would have
  silently broken that already-shipped B3 filter (it matches any
  `applications` row for a job_id regardless of `status`). Corrected the
  plan before writing it to the plan file: review state moved onto new
  `job_resume_variants.review_status`/`reviewed_at` columns,
  `applications` rows created only on approval. Plan approved via
  `ExitPlanMode`.
  Implementation followed hard rule 7 (tests before code) end to end,
  file by file: `schema.sql` (new columns, new
  `idx_job_resume_variants_job_profile` index, explanatory comment) ->
  `specs/00-data-model.md`/`specs/08-rubric.md` dedup-wording fix ->
  `tests/test_db.py` (+12) -> `db/models.py` (`JobResumeVariant`,
  `RubricResultRow`, `Application`, `QueueEntry` + 10 new helpers) ->
  ran the new tests, which immediately caught a second real bug the
  plan had underestimated: the old `UNIQUE(base_resume_id,
  selection_hash)` table constraint was still literally present (only a
  new index had been added alongside it, not instead of it), so the
  exact multi-job-shares-a-hash case the fix was meant to allow still
  failed. Removed the old constraint from `schema.sql` for real, which
  meant `migrate.py` now needed a genuine table-rebuild path (SQLite
  can't drop a table-level constraint via `ALTER TABLE`), not just an
  additive `CREATE INDEX` as originally planned — built
  `_rebuild_job_resume_variants_if_needed()` and a dedicated
  `tests/test_db_migrate.py` (9 tests) that reconstructs the real
  pre-migration table shape via raw SQL to prove it. `queue/
  orchestrate.py` (`ensure_reviewed()`/`approve()`/`reject()`/
  `list_queue()`), tests-first (`test_queue_orchestrate.py`, 7 tests,
  all real bank/render/PDF/score, matching `test_patch.py`'s own
  precedent that `run_ladder()` has no lighter mock; a stage-aware
  `_FakeClient` serves both the extract and rephrase stages from one
  fake by inspecting the requested schema's fields, since a naive single
  fixed payload broke once P3 genuinely fired during a real test run).
  `web/app.py` + Jinja2 templates, tests-first (`test_web_app.py`, 8
  tests) — hit and fixed a third real bug only surfaced by running the
  actual FastAPI `TestClient`: sync routes/`Depends()` run in a
  threadpool by default, so a single shared `sqlite3.Connection` crossed
  threads across requests and `sqlite3` rejected it; added a
  `check_same_thread` parameter to `db/migrate.py`'s `connect()`,
  `False` only for the web app, documented as safe for this app's real
  single-operator usage, not a general concurrency claim.
  Full suite 370/370 (up from 328), `ruff check`/`format --check` clean,
  entirely against scratch/`tmp_path` dbs — confirmed before touching
  `data/jobengine.db` at all.
  Asked explicitly, via `AskUserQuestion`, before running the real
  migration (`uv run python -m jobengine.db migrate` against the real
  db), per hard rule 13; proceeded only after explicit confirmation.
  Verified read-only afterward: new index present, old constraint gone,
  `job_resume_variants`/`applications` still 0 rows, `schema_migrations`
  now has both `0001_initial` and the new version. Then verified end to
  end against the real running app (`uv run uvicorn jobengine.web.app:
  app`) and the real db, using this session's own real worked example
  (job_id 3871, Airbnb "Software Engineer, Biztech Client and Identity",
  already confirmed to survive B3 for `software_engineer`): first visit
  ~22s (real Ollama cold start, matches C1's documented latency), the
  real `analyze_job()`/`run_ladder()` ran for real, on-screen numbers
  matched the plan's pre-computed worked example exactly (score 18.98,
  coverage 0.14, `hard_failures: ['R001']`, tiers `['P0','P1','P2',
  'P3']`); second visit 0.01s, byte-identical HTML, zero new model
  calls; `POST .../reject` returned 303, flipped `review_status`,
  created no `applications` row (confirming the filter-conflict fix
  holds for real), and the job dropped off `GET /`. Stopped the dev
  server afterward and reconfirmed `jobs`/`companies` row counts
  unchanged (3882/15), only the intended new tables touched. This is
  the first-ever real `job_analysis`/`keyword_corpus`/
  `job_resume_variants`/`rubric_results` rows this project has written
  to `data/jobengine.db` outside a scratch copy.
  Recorded the full writeup, including all three bugs found and fixed
  during implementation and the real end-to-end verification evidence,
  as D35 in docs/decisions.md.
  Next: no next task chosen yet, needs explicit go-ahead per the
  session protocol. Open candidates per TODO.md: A4c, B1-followup/
  B3-followup, C4, F2 (dashboard), F3 (Telegram). F1's own known gaps
  (no batch orchestrator, `_new_pairs()` only reapplies B3's title
  check) are documented above, not silently left for a future session
  to rediscover.

- 2026-08-07, E2 (done, all 3 profiles): Closed out the 2 remaining
  profiles from the prior session plus a rubric-design change touching
  all 3.
  Showed `software_engineer`'s full pre-edit rubric state first, same
  detail level as the prior session's `ai_ml_engineer` review: `passed:
  false`, `score 66.58`, `hard_failures: ['R002', 'R003', 'R013']`,
  `coverage: 1.0`, `front_load: 0.40`, real per-keyword above/below-fold
  table (page 1 height 792, half 396.0; 4/10 top keywords above the
  fold), and R003/R013 both traced to the same root cause,
  `role_utd_researcher=2` entries.
  Before editing anything, showed all 5 of that role's bullets in full
  (text + keywords + current profile tags), per explicit request to see
  what's available before deciding. Reviewed each for genuine
  `software_engineer` fit: `b_utd_02` (processing/managing 1,600 CMB
  simulated maps across splits) read as data-pipeline engineering, the
  least ML-research-specific of the five (`b_utd_01`/`b_utd_03` read as
  architecture design/publication framing). Retagged `b_utd_02` onto
  `software_engineer` (now `[ai_ml_engineer, data_scientist,
  software_engineer]`). `bank validate`: 0 errors/0 warnings
  (`software_engineer` bullet count 15, up from 14). Re-ran the full
  rubric state: `hard_failures: ['R002']` only, R003/R013 both clear
  (`role_utd_researcher`: 3 entries), `score 66.87`, `front_load`
  unchanged at 0.40 (same top-10 list, retagged bullet's own keywords
  weren't in it).
  User then proposed reclassifying R002 from a hard failure to a
  scored-only component, having hit the same real structural front-load
  ceiling on two profiles now (`ai_ml_engineer` 0.50 in D32,
  `software_engineer` 0.40 here) with no viable fix that doesn't cost
  more than it gains. Asked to see, before any change: how many of the
  other 12 hard rules are genuinely categorical vs. share R002's
  "continuous measurement forced into a threshold" shape. Reviewed all
  13 against spec 08's own text: R001 (coverage) shares the shape
  exactly and has its own continuous scored twin same as R002, and
  spec 08's own P4 text already treats R001 as different-in-kind from
  other hard rules ("skip the job entirely if a hard rule *other than
  R001*..."), independent evidence the shape argument is sound; R006
  (line count) is R002's closest architectural sibling, same
  `pdfplumber`-derived geometry, same soft-convention-as-cutoff shape;
  R003 doesn't share the shape (no continuous twin, its 3-8 bounds
  encode a real structural convention, not a proxy measurement); the
  remaining 9 are genuinely categorical (schema-guaranteed, formatting,
  grammar, ordering, typography, structural, presence checks). Argued
  for demoting R002 only, not R001/R006 too, since only R002 has the
  evidence: two independent, exhaustive investigations (this session's
  and D32's) actually found a real ceiling, versus a plausible argument
  by shape alone for the other two; R001 in particular carries D27's
  existing precedent toward strictness and is the system's only gate
  against a resume that doesn't cover a job's keywords at all. Drafted
  the docs/decisions.md entry for review before writing anything, per
  explicit instruction not to implement yet.
  On approval, applied for real: `rules.py`'s `score_resume()` no
  longer includes `check_r002()` in its `hard_failures` list (the
  function itself is untouched, still directly unit-tested);
  `front_load` stays fully weighted 25/100 in `score.py`, unchanged.
  Wrote **D33** to docs/decisions.md verbatim as drafted and approved.
  Full suite re-run: 328/328 (no regressions, no new tests needed since
  no existing test asserted R002 specifically inside `score_resume()`'s
  integration path, confirmed by grep before editing). Re-ran both
  profiles' full state: `ai_ml_engineer` now `passed: true,
  hard_failures: []` (its only prior failure was R002); `software_engineer`
  now `passed: true, hard_failures: []` too (`front_load: 0.40` still
  visible in measurements, just not gating).
  Showed `data_scientist`'s full rubric state next: `hard_failures:
  ['R003', 'R013']` (R002 no longer a gate as of D33), both tracing to
  `role_bantrly_lessongen=2`, the same shape `role_utd_researcher` had
  for `software_engineer` per the user's own recollection, confirmed
  true by direct inspection before trusting it. Showed all 5 of that
  role's bullets in full; unlike `role_utd_researcher`, none of the
  other 4 (`b_lessongen_02` guardrails/content-safety retry logic,
  `b_lessongen_03` defensive JSON validation, `b_lessongen_05` a Gradio
  UI deployment) read as genuine data-science work, all systems/app
  engineering. Per the user's decision, dropped the role from
  `data_scientist` entirely rather than force an ill-fitting second tag:
  removed `b_lessongen_04`'s `data_scientist` tag (now `[ai_ml_engineer]`
  only). `bank validate`: 0 errors/0 warnings (`data_scientist` bullet
  count 16, down from 17). Confirmed live via `select_for_profile()`
  that `role_bantrly_lessongen` is completely absent from the
  `data_scientist` candidate's role list, not just under-populated (its
  own docstring already guarantees this: a role left with zero tagged
  bullets is dropped, the untagged summary doesn't keep it alive). Full
  rubric state after: `passed: true`, `hard_failures: []`, `score
  66.96` (up from 61.59; page count also dropped 3 -> 2 as a side
  effect, pulling in `score.py`'s page-penalty component beyond just
  the R003/R013 fix).
  Before generating final files, added **D34** to docs/decisions.md at
  the user's request: `coverage: 1.0` across all 3 profiles is measured
  against bank-frequency fallback keywords (`keyword_corpus` still 0
  rows, C3's `analyze_job()` orchestrator has never run against real
  jobs), a materially easier bar than real market demand since a
  keyword the bank never mentions can't appear in its own frequency
  list at all; flagged for re-validation once corpus data exists, not
  presented as a stronger result than it is.
  Generated and persisted all 3 profiles via `persist_base_resume()`.
  Hit a real ambiguity first: `ai_ml_engineer/v1/` already existed from
  the prior session with an identical selection but a now-stale
  `rubric.json` (still showed pre-D33 `hard_failures: ['R002']`), and
  spec 09's versioning model says versions are never overwritten.
  Asked via `AskUserQuestion` rather than guessed, given this both
  writes new files and inserts real db rows; user chose generating a
  new `v2` for `ai_ml_engineer` (confirmed byte-identical
  `selection.yaml` aside from the version field) over leaving v1 stale
  or touching it. `software_engineer`/`data_scientist` got their first
  real `v1`. `base_resumes` table: 4 rows total now (`id` 1-4), `id=1`
  (prior session) untouched, `id` 2/3/4 new this session, all committed
  to the real `data/jobengine.db`. Hand-wrote all 3 `CHANGELOG.md`s
  (`persist.py` deliberately doesn't auto-generate them, narrative
  judgment not mechanically derivable), each documenting its own
  content decision, known R002/coverage caveats, and pointing at
  D32/D33/D34.
  Full suite re-confirmed 328/328, `ruff check` clean, after all bank
  edits and the rules.py change.
  Checked off E2 in TODO.md with the full real-numbers writeup.
  Next: no next task chosen yet, needs explicit go-ahead per the
  session protocol. Open, unstarted candidates per TODO.md: A4c
  (watermarking, still no urgency), B1-followup/B3-followup
  (deliberately deferred), C4 (relevance pre-filter), F1 (review
  queue). P4 (accept and log to `gap_ledger`) also remains deliberately
  unbuilt.

- 2026-08-06, E2 (in progress, `ai_ml_engineer` v1 only): First real E2
  work, end to end for one profile. Diagnosed R002's exact failure
  first, not guessed: which of the brief's top-10 keywords miss the
  page-1-top-half y-cutoff, their real y-coordinates (via
  `measure.front_load_detail()`), and which specific bullet/summary
  carries each (cross-referenced by keyword-tag, not text substring,
  after an initial text-substring version missed summary-tagged
  keywords). Confirmed, by direct inspection: R003's software_engineer/
  data_scientist failures are both "too few" (both `role=2`, below the
  3-bullet floor), and R013 is the identical H004 gap R003 already
  catches, not a separate defect.
  Live-tested every mechanical R002 fix before concluding none of them
  cheaply work, each real-scored via D1's actual `rules.score_resume()`:
  the automatic `run_ladder()` P0-P2 ladder (a real no-op, traced to
  `apply_p0`'s aggregate-score-based role-swap declining by its own
  logic, and `apply_p2` grabbing the first role matching a stem in bank
  order and stopping there, correctly, before ever reaching the
  genuinely-promotable project roles); 3 manual structural overrides
  (role-swap legal under R009's overlap tolerance, section-promote, both
  combined) — all 3 scored *worse* than baseline, proving front_load is
  a fixed-space allocation over a 3-page candidate, not a rank order;
  2 content-cut variants (dropping `role_ju`: a real no-op, its content
  was already past page 1 regardless of position; trimming
  `role_bantrly` to summary+2: a real +1-keyword gain, at the cost of
  `embeddings`).
  Drafted 3 shortened `role_bantrly` bullets (`b_bantrly_02/03/04`),
  verified against the real `validate_rewrite()` guard (0 violations),
  real per-keyword verbatim-vs-D20-reliance checks (correcting the
  user's own initial "D23" misattribution — D23 is the B3 filter-cap
  decision, unrelated; D20 is the actual precedent that keyword tags
  need not appear verbatim in their own bullet's text), and real line
  counts from the renderer. Honest result, not oversold: a
  fact-preserving trim recovers only ~18pt of the ~75pt `cosmology`
  needed (confirmed against a synthetic, explicitly-not-real-content
  truncation probe that did cross the threshold, proving the geometry
  math but not something that could ship as real content).
  Applied the 3 approved drafts for real to `resume/bank/aankit.yaml`
  (**first-ever edit to that hand-authored file**): `bank validate`, 0
  errors/0 warnings. Built `src/jobengine/profiles/persist.py`
  (`persist_base_resume()`) and `db/models.py`'s `BaseResume` model +
  `insert_base_resume()`/`latest_base_resume_version()`, tests first per
  hard rule 7 (9 new tests total: `test_db.py` +4, including a real
  FK-chain test; `test_profiles_persist.py` +5). Ran it for real:
  `resume/base/ai_ml_engineer/v1/` now holds `selection.yaml`/
  `resume.docx`/`resume.pdf`/`rubric.json` (confirmed byte-size-identical
  and page-1-text-identical to the PDF the user had already visually
  reviewed before asking to persist it) plus a hand-written
  `CHANGELOG.md` (not auto-generated, since "what changed and why" is
  interactive-session narrative, not mechanically derivable); the real
  `base_resumes` row (**first-ever write to that table**, `id=1`) is
  committed to `data/jobengine.db`. Verified
  `job_resume_variants.base_resume_id`'s FK against the new row on a
  scratch copy of the real db (`PRAGMA foreign_key_check` clean),
  discarded the copy, no fake data left in the real db.
  Recorded the whole investigation and the final ship decision (R002
  soft-fail, mirrors C3's D27: rubric as directional pressure, not a
  hard gate; the score/failure state travels via the review queue, not
  hidden) as D32 in docs/decisions.md.
  `uv run pytest`: 328/328 (up from 319). `ruff check`/`format --check`:
  clean.
  Next: `software_engineer` and `data_scientist` each need their own E2
  session (each has different rubric gaps — see Known Issues); needs
  explicit go-ahead per the session protocol before starting either. E2
  as a whole stays "in progress," not "done," until all 3 exist.
- 2026-08-05, E1 (done): Built `src/jobengine/profiles/` (`config.py`,
  `brief.py`, `__main__.py`) plus `config/profiles.yaml`, per the user's
  explicit scoping: `profiles brief` producing spec 09's brief.md (top
  corpus keywords, current base resume's rubric measurements, uncovered
  gap-ledger keywords, unselected bank bullets carrying top keywords),
  gracefully degrading rather than crashing when `keyword_corpus` is
  empty. Entered plan mode before writing any code, per TODO.md's own
  session-start instruction and hard rule 6; grounded first, not
  guessed: confirmed `render.py`'s `RenderProfile` docstring already
  names E1 as owning the profile-registry gap, and `rules.score_resume()`
  's docstring already anticipates a caller deciding what "current base
  resume" means, which resolved what would otherwise have been open
  design questions. One real design fork remained (what "current base
  resume's rubric measurements" should show with no `base_resumes` row
  yet, since E2 hasn't run) — asked via AskUserQuestion rather than
  guessed; the user chose rendering+scoring `measure.select_for_profile()`
  's output on the fly as the stand-in, matching D1's own grounding
  shape.
  Corrected two things in the user's own initial framing before coding,
  not silently carried into the design: `keyword_corpus` being empty is
  C3's `analyze_job()` never having been run by a daily orchestrator
  (already flagged under C3 in this file's Known Issues), not C4; and
  D1 built no bank-frequency stand-in for R002 specifically (R002 has no
  fallback at all, D28) — the real reusable precedent for a
  corpus-empty fallback is `bank.keyword_counts()`, already used
  elsewhere by `measure.coverage()`/`missing_keywords()`.
  19 new tests, written before implementation per hard rule 7
  (`tests/test_profiles_config.py` 8, `tests/test_profiles_brief.py`
  10, the latter including real-`soffice` render/score integration
  tests mirroring `test_rubric.py`'s own `real_sample_pdf` pattern, not
  mocked, since a fake PDF byte string can't be parsed by pdfplumber
  anyway). No CLI unit test written, matching this codebase's existing
  convention that no other module's CLI has one either (`bank.py`,
  `rubric/__main__.py`); covered by the live run instead.
  `uv run pytest`: 319/319 (up from 301). `ruff check`/`format --check`:
  clean (also caught and fixed one small formatting drift the tool
  introduced in `profiles/config.py`/`__main__.py` during this session's
  own work, not a separate pre-existing issue this time). Live-verified
  against the real `data/jobengine.db` (read-only, confirmed unchanged:
  `keyword_corpus`/`gap_ledger` still 0 rows, `jobs` still 3882,
  `companies` still 15) and real `resume/bank/aankit.yaml` for all 3
  profiles: `ai_ml_engineer` produced real numbers (`score 63.27`,
  `hard_failures: ['R002']`, `front_load 0.5`, `pages 3`) and honest
  degradation text for both empty tables; `software_engineer`/
  `data_scientist` also produced real, non-empty output (52/55 lines).
  Invalid `--profile` rejected cleanly by argparse (`choices=`, exit 2).
  TODO.md's E1 checkbox checked; docs/decisions.md gained D31 with the
  full writeup, including what's deliberately not built this session
  (`patch.py`/the render scripts still construct `RenderProfile` inline
  rather than loading the new registry; migrating them wasn't asked
  for).
  Next: E2 (generate all 3 base resumes, interactive session) is next
  in TODO.md's order but needs explicit go-ahead per the session
  protocol before starting.
- 2026-08-05, D4 (verification follow-up, no new feature work): The
  user asked a direct, skeptical question: had D30's "re-verified live
  after the fix" and its addendum's "re-verified live... persisted bank
  state" claims actually been re-run in a way that could be shown, or
  just re-asserted as prose. Checked first rather than answered from
  memory: no captured evidence of either claimed run exists anywhere in
  this repo, only narrative paragraphs in docs/decisions.md and
  PROGRESS.md. Initially wrongly concluded Ollama wasn't reachable at
  all in this session's shell (checked `which ollama` and `localhost:
  11434` only); the user pushed back and asked specifically about
  `OLLAMA_BASE_URL` and the WSL2-gateway network path, which turned out
  to be set and reachable the whole time
  (`http://172.18.144.1:11434`, real `qwen3.5:9b-q4_K_M` responding).
  Corrected course and ran the real reproduction. Also caught, before
  running anything, that the user's own framing ("job 318, the exact
  CMB deficit") conflated two separate documented cases: job 318's real
  deficit is SQL/XGBoost (declined, not closed); `required_keywords=
  ["CMB"]` targets an unrelated bullet, `role_utd_researcher`'s
  `b_utd_02`. Flagged this rather than silently running the wrong case
  or silently reproducing the user's mislabeling into permanent docs.
  Ran the real CMB case live end to end via a standalone scratch script
  (`/tmp/.../repro_cmb.py`, not committed, not part of the automated
  suite): confirmed coverage 0.0 before; captured the live model's raw
  parsed response (`text`, `keywords_added=["CMB"]`); re-ran
  `validate_rewrite()` explicitly (`violations == []`); confirmed
  `apply_variants_to_bank()` leaves the canonical bullet's `.keywords`/
  `.text` untouched and appends a new `BulletVariant`; persisted to a
  scratch path (never the real `resume/bank/aankit.yaml`); reloaded;
  ran a second, independent `apply_p3()` call against the reloaded bank
  confirming it reused the persisted variant (`reused_existing_variant=
  True`, zero new LLM calls) with coverage 1.0 on that working
  candidate. Recorded as a "D30 second addendum" in docs/decisions.md,
  explicitly stating the precise mechanism (coverage improvement lives
  on the variant/working candidate, never the canonical bank, which
  measure.coverage() correctly reports as still 0.0) and explicitly
  flagging the one thing this run did *not* re-check live (`used_count`
  1->2 on a second `apply_variants_to_bank()` call, still only covered
  by the FakeClient regression test), rather than overstating scope.
  Also re-ran this session's own lint/test commands rather than trusting
  the last checkpoint's numbers (`uv run pytest`: 301/301; `ruff check
  src/`: clean; `ruff format --check src/`: caught 1 file, `src/
  jobengine/db/models.py`'s `get_job_analysis()`, not reformatted since
  it was added several sessions ago; not caused by this session's own
  changes, but real drift nobody had caught since. Fixed
  (`uv run ruff format src/jobengine/db/models.py`); `pytest` still
  301/301 after.
  No production code changed except that one formatting fix; no new
  tests added. `docs/decisions.md` and `PROGRESS.md` updated; TODO.md
  unchanged (D4's own line there already correctly separated job 318
  from the CMB case, no conflation existed there, only in this
  conversation's own phrasing).
  Next: same as before this follow-up — P4 remains deliberately
  unbuilt; E1/E2 (base resumes) are next in TODO.md's order but need
  explicit go-ahead per the session protocol before starting.
- 2026-08-05, D4 (done): Added P3 (rephrase) and its writeback to
  `src/jobengine/rubric/patch.py`: `call_rephrase()` (the only LLM call,
  input strictly the bullet's what/how/result + target keywords, never
  the whole bank or JD text), `validate_rewrite()` (CLAUDE.md hard rule
  12's traceability guard enforced in code — a general capitalized/digit
  token check against the parent's what/how/result + identity.toml,
  deliberately stricter than a jargon-allowlist so a genuinely novel
  fabrication is caught, not just a previously-seen one, per the user's
  explicit request this guard be airtight, not happy-path only),
  `apply_p3()` (prefers an existing variant over a new call, max 2 new
  calls/job, discards on any guard/prose/slop-linter failure), and
  `apply_variants_to_bank()` (in-memory writeback, `used_count`
  tracking). New in `bank.py`: `BulletVariant`, `Bullet.variants`,
  `dump_bank()` (YAML round-trip, data-fidelity only). Before coding,
  confirmed by asking that D4 would build and test the writeback logic
  but not wire it to the real `resume/bank/aankit.yaml` automatically —
  this would be the first-ever automated write to that hand-authored
  file, mirroring D3's own deferral of `job_resume_variants` persistence.
  `tests/test_bank.py` gained 6 tests, `tests/test_patch.py` gained 22
  (36 total P3-related, most of them the traceability-guard battery:
  novel proper noun, novel number, already-tagged keyword,
  described-but-untagged keyword, fabricated keyword, sentence-initial
  capitalization, case-insensitivity), all written before implementation
  per hard rule 7.
  Per the user's explicit direction to ground the integration test
  against the realistic common path (P0-P2 fail, P3 must genuinely
  rephrase), not a synthetic P3-only fixture: reused job_id 318's real,
  live-extracted required_keywords (already confirmed by D3's own
  grounding not to close via P0-P2) for the automated integration test
  (LLM mocked, matching every other test in this suite), then ran 2
  additional REAL live-Ollama checks (not mocked, not part of the
  automated suite, same split as `llm.check`'s own precedent): (1) the
  real model, asked to incorporate SQL/XGBoost into a bullet with zero
  supporting content, correctly declined to fabricate either and
  returned `keywords_added: []`; (2) `required_keywords=["CMB"]` (a real
  term genuinely present in a real bullet's `what` field but untagged)
  closed for real, coverage 0.0 -> 1.0, verified traceable. Run (2)
  surfaced a real implementation bug neither this session's own tests nor
  run (1) had caught: `_with_bullet_text` only updated the rewritten
  bullet's `.text`, never merged `keywords_added` into `.keywords`, so an
  accepted rewrite could never actually move `coverage` (R001 reads
  `.keywords`, not `.text`). Fixed (`_with_bullet_rewrite`, merges
  stem-deduplicated keywords into the transient working candidate only,
  never the canonical `full_bank`), re-verified live against the same
  CMB reproduction case after the fix (coverage confirmed 0.0 -> 1.0
  again, via `run_ladder()`). **Follow-up caught after that fix, not at
  the initial re-verification:** the user asked specifically whether
  this had been checked in the *persisted* bank state, not just
  `run_ladder`'s in-memory return value — it had not. Ran the full chain
  live for real on the same reproduction case: accept -> `apply_variants_
  to_bank` -> `dump_bank` -> `load_bank` -> a second, independent
  `run_ladder()` call against the reloaded (from-disk) bank -> reuses the
  variant with zero new LLM calls -> coverage still 1.0 -> `used_count`
  1->2. Added a permanent regression test for this exact chain
  afterward (301/301, up from 300), not just the individual pieces each
  already had their own test.
  `uv run pytest` 301/301 passing (was 258 before D4 started); `ruff
  check`/`format --check` clean (same 3 pre-existing `test_render.py`
  findings, untouched). Real db (`data/jobengine.db`) unaffected: all
  live runs used the real bank read-only and never touched the db at all.
  TODO.md's D4 checkbox checked (closing out Phase D entirely), Status
  table updated. See D30 in docs/decisions.md for the full writeup.
  Next: P4 (accept and log to gap_ledger) remains deliberately unbuilt;
  Phase E (E1 profile config, E2 base resumes) is next in TODO.md's
  order, needs your go-ahead before starting per the session protocol.
- 2026-08-05, D3 (done): Built `src/jobengine/rubric/patch.py` (`apply_p0`
  reorders bullets/roles, `apply_p1` swaps in unselected same-role
  candidates, `apply_p2` promotes sections/project-roles, `run_ladder()`
  re-renders/re-PDFs/re-scores after each tier via the real A4b/D1
  pipeline) plus a CLI (`uv run python -m jobengine.rubric patch --job
  <id> --dry-run`). Before coding, confirmed two real design questions by
  asking rather than guessing: (1) P0 does not automatically reorder
  project-section roles (reserved for P2's explicit promote step), and
  (2) R009 (`measure.is_reverse_chronological`, shipped in D1) needed
  loosening from strict start-date monotonicity to date-range-overlap
  tolerance, since the strict version made P0's "sort roles only if
  concurrent" permission inert on every real role pair (no two roles
  share an exact start month, but `role_sei`/`role_unl` genuinely
  overlap). `tests/test_rubric.py` gained 2 tests for the R009 change
  before it was made; `tests/test_patch.py` is new, 14 tests, written
  before implementation per hard rule 7, one per tier's behavior plus 2
  full real-bank `run_ladder` integration tests.
  Spent significant real effort grounding D3's DoD ("at least one real
  deficit closes with zero model calls") against actual data, not a
  synthetic fixture alone: ran live C3 extraction (real Ollama, scratch
  db only, never `data/jobengine.db`) against 9 different real job
  postings across both profiles, deliberately searched across the live db
  for topical overlap with the bank's real strengths (RAG, embeddings,
  speech/audio, document intelligence), not just generic "ML engineer"
  titles. Every one of the 9 showed zero measurable change from the
  ladder, for two distinct, well-understood, now-documented structural
  reasons (D29 in docs/decisions.md): P1 is a real no-op against the
  current bank for any job (`select_for_profile()` never holds anything
  back), and P0 only ever affects R002 within `role_bantrly` (the one
  role reaching page 1's top half), which already had reasonable
  ordering for what those 9 postings happened to need. Rather than force
  a misleading "success" on data that didn't support it, or ship without
  meeting the literal DoD, constructed one clean, honestly-labeled
  demonstration using a single real bank keyword ("Chroma DB", genuinely
  covered, on a real bullet in `role_docintel`, a project role) known to
  be poorly positioned: confirmed R002 fails before the ladder
  (front_load 0.00, keyword lives in the Projects section which renders
  after Work History) and passes after (P2 promotes "projects" to the
  front of section_order, front_load 1.0), measured through the fully
  real pipeline, zero model calls. This satisfies D3's DoD honestly; the
  two structural findings above are recorded as real, current limitations
  of the bank's content and the selection mechanism, not hidden.
  Found and fixed one real bug along the way: `run_ladder()` didn't
  create its `out_dir` before saving the first docx (only `render_pdf()`
  did, called after), caught by running the real 9-job grounding sweep,
  not by the unit tests (fixed, plus a regression test using a
  deliberately non-existent nested directory).
  `uv run pytest` 258/258 passing (was 242 at last checkpoint); `ruff
  check`/`format --check` clean on everything touched (same 3
  pre-existing `test_render.py` findings, confirmed unrelated, untouched).
  TODO.md's D3 checkbox checked, Status table updated. Next: your call on
  D4 (patch tier P3 + bank variant writeback), the next item in TODO.md's
  order, needs explicit go-ahead per the session protocol before starting.
- 2026-08-04, A4b + D1 + D2 (all done): Closed A4b first (TODO.md rule 1
  requires Phase A fully green before Phase D; A4b's own line says it
  "must land before the rubric phase starts"), then planned and built D1
  against real data throughout. A4b: `resume/pdf.py`'s `render_pdf()`
  wraps `soffice --headless` via subprocess (no "pptx skill" available in
  this session, see Decisions), verified live against the real binary on
  2 distinct real full-bank renders; found and fixed a real pre-existing
  renderer bug along the way (every paragraph inheriting python-docx's
  default 10pt `w:after` spacing, caught by the user measuring real PDF
  geometry with pdfplumber, not by any test) via a new `_new_paragraph()`
  helper in `render.py`. D1: built `src/jobengine/rubric/{measure,rules,
  score}.py` plus a CLI, all 13 hard rules from spec 08 plus the weighted
  score. R002/R006 turned out to have no real fallback in spec 08, so D2
  (PDF geometry) got absorbed into D1's implementation rather than staying
  a separate session; D2's own literal DoD (`rubric explain R002` prints
  real y-coordinates) was re-run live at checkpoint time and passes. Four
  design decisions confirmed by asking, all recorded as D28 (3 addenda) in
  docs/decisions.md: D2's absorption, two undefined score-component
  formulas, `select_for_profile()` as a new minimal candidate-resume
  filter, and two deliberate scope reductions (stem-only keyword matching,
  R010's line-spacing check). Grounded against real data twice: before
  coding (live C3 `extract_keywords()` against 3 real JDs pulled from the
  live db) and after (a real `job_analysis` row persisted via `analyze_job
  ()` to a scratch copy of the db, never `data/jobengine.db`, then the
  actual CLI run against it end to end). Real numbers: coverage
  0.27/0.06/0.33 against the 3 real JDs (all correctly fail R001; the
  robotics job's near-zero coverage against an ML/SWE bank is exactly
  right), R003 correctly flagged a real under-provisioned role for
  `software_engineer`, cross-validated by R013 catching the identical gap
  via slop_lint's own H004. `tests/test_rubric.py`: 39 tests, written
  before implementation per hard rule 7, one failing fixture per hard
  rule plus one full real-bank-through-real-render-through-real-PDF
  integration test. Also added `db/models.py`'s `get_job_analysis()`
  (new read accessor) with its own test. `uv run pytest` 240/240 passing;
  `ruff check`/`format --check` clean on everything touched (same 3
  pre-existing `test_render.py` `RUF059` findings, confirmed via `git
  stash` to predate this session, untouched). TODO.md's A4b/D1/D2
  checkboxes all checked. Next: D3 (patch ladder P0-P2, deterministic
  only) is next in TODO.md's order; needs your go-ahead before starting
  per the session protocol.
- 2026-08-04, C3 (done, shipped against D27, not the literal gate): Built
  `pipeline/extract.py` (extraction call via C1's router + job_analysis/
  keyword_corpus persistence) and `eval/{harness,report,tasks/
  keyword_extraction}.py` (spec 07 Task 2: pooled TP/FP/FN, `uv run
  python -m jobengine.eval {run,compare}`), plus a `job_analysis`
  `(job_id, profile)` unique index and matching `db/models.py`
  accessors. 24 new tests (`test_extract.py` 13, `test_eval_keyword_
  extraction.py` 11), all written before implementation per hard rule 7.
  Then ran the real eval live against qwen3.5:9b, 7 times, iterating for
  real: caught and fixed 3 real pre-existing data-quality bugs in the
  original C2-session `human_labels.yaml` fixture (a 4-job duplicate
  copy-pasted keyword list, 2 more jobs with invented/wrong-template
  terms), tried and measured two prompt variants (one real bug fix,
  sentence-fragment extraction; one genuine trade-off, "non-tech skills
  count too," which looked like a win on a noisier fixture but was tried
  and rejected once measured against a clean one), and finally did a
  full exhaustive, source-quoted, human-reviewed re-derivation of all 11
  labeled jobs' `required_keywords` at explicit user request. Every step
  characterized with real isolated tests before being applied broadly
  (a synthetic-JD test falsified one hypothesis about why a specific
  real job was failing before the actual cause, non-technology terms
  read as soft skills, was found and fixed) — same standard as B3's
  inclusion-exclusion reconciliation, applied to model-quality debugging
  instead of filter counts. Final real numbers, on the reverted,
  better-precision prompt against the fully-reviewed fixture: the first
  live run scored precision 0.833 / recall 0.467, but a second identical
  run scored 0.849 / 0.351, real LLM sampling variance
  (`temperature`/`seed` unpinned) rather than a stable point value; ran 2
  more samples (4 total) rather than let one lucky/unlucky number stand
  as *the* answer, giving precision 0.833-0.858 (mean 0.844, passes the
  0.70 gate in all 4 runs) and recall 0.351-0.467 (mean 0.408, fails the
  0.85 gate in all 4 runs, never within 0.38 of it). `model_evals` now
  holds all 10 real keyword_extraction runs from this session (30 rows);
  its most recent row genuinely matches the shipped code, closing what
  was briefly a real gap (the newest row was a rejected prompt variant
  for part of this session). **C3 marked done anyway, per explicit user
  decision (D27 in docs/decisions.md):
  human review gates every resume send, recall gaps only under-extract
  and can't invent content under hard rule 2, and an 11-job fixture can
  only approximate real usage; revisit if manual review of real output
  later shows this recurring in practice, not preemptively.** `uv run
  pytest` 191/191 passing; `ruff check`/`format --check` clean on
  everything touched this session (same pre-existing `test_render.py`/
  `test_slop_lint.py` debt, untouched). TODO.md C3 checked off,
  referencing D27 explicitly rather than the literal numeric DoD. Next:
  your call between C4 (relevance pre-filter, spec 06, Task 1 of the
  same eval harness), B3-followup, or A4b.
- 2026-08-03, C1 (done): The one thing left after the prior entry below,
  the live `uv run python -m jobengine.llm.check` run against a real
  Ollama server, is now done: the user ran it against the real WSL2/
  Windows setup and confirmed all three stages (`relevance`/`extract`/
  `rephrase`) reachable, exit code 0. Cold-start latency 14,945ms on the
  first call (Ollama loading the 9B model into VRAM), steady-state
  600-935ms across 3 consecutive clean runs after that, no per-stage
  anomaly. Recorded prominently in Known Issues, flagged specifically so a
  future session's first check of the day (after any restart or idle
  gap, when Ollama will have unloaded the model again) doesn't get
  mistaken for a regression. TODO.md's C1 checkbox now checked, Status
  table marked `done`. No code changed this entry beyond the prior one;
  `uv run pytest` still 167/167 passing, `ruff check`/`format --check`
  still clean on everything this session touched (pre-existing
  `test_render.py` `RUF059`/formatting debt untouched, same as every
  prior checkpoint). Next: your call between C3 (keyword extraction, now
  unblocked with both real human_labels and a real, live-verified
  router), B3-followup, or A4b.
- 2026-08-03, C1 (built, not yet done): Planned against specs/05-model-
  routing.md and PROGRESS.md before writing any code; confirmed with the
  user that the plan must set `think=False` explicitly on every local
  Ollama call (never a Modelfile default) and that the Anthropic billing
  guard must be nearly impossible to trigger by accident per CLAUDE.md
  hard rule 9. Built `src/jobengine/llm/` (`schemas.py`, `providers/
  {local,anthropic}.py`, `router.py`, `check.py`) and `config/llm.toml`
  (new file, mirrors spec 05's TOML block plus a `[llm.api] enabled =
  false` section the guard needs). `LocalProvider.call()` sets `think`
  and `format=schema.model_json_schema()` on one call site, backed by
  `test_call_sets_think_false_explicitly`. The Anthropic guard is two
  independent layers (explicit `api_key` required at both
  `AnthropicProvider.__init__` and `router.get_provider()`, neither
  module ever reading `ANTHROPIC_API_KEY` or any other env var), verified
  by a test that sets `ANTHROPIC_API_KEY` in the environment and confirms
  construction is still refused; `AnthropicProvider.call()` itself is a
  permanent `NotImplementedError` stub since no stage uses that tier. See
  D25 in docs/decisions.md. Before coding, asked and got two explicit
  answers: missing `OLLAMA_BASE_URL` raises a clear config error rather
  than auto-computing a fallback, and this session builds against a
  mocked `ollama` client only, with the real `uv run python -m
  jobengine.llm.check` run against live Ollama left for the user. 21 new
  tests (`test_llm_local_provider.py`, `test_llm_router.py`,
  `test_llm_check.py`), all passing; `uv run pytest` 167/167 passing;
  `ruff check`/`format --check` clean on everything touched this session
  (the pre-existing 3 `RUF059` findings in `test_render.py` are untouched,
  not introduced here). Manually confirmed `router.load_config()`'s
  missing-env-var path against the real `config/llm.toml` (raises the
  intended `RuntimeError`, not a parse error). **Not done:** the real
  `llm.check` run against a reachable Ollama server, which is what
  TODO.md's literal C1 DoD line asks for; Status table marks C1 `in
  progress`, TODO.md's checkbox left unchecked, until that happens. Next:
  run `uv run python -m jobengine.llm.check` yourself, then your call
  between C3 (keyword extraction, now unblocked with both real
  human_labels and a real router), B3-followup, or A4b.
- 2026-08-03, C2 (done) + unplanned greenhouse.py bug fix and backfill:
  Built C2's scaffolding (`tests/fixtures/eval/human_labels.yaml` seeded
  from 50 real JDs, `src/jobengine/eval/fixtures.py`'s `load_human_labels`,
  `tests/test_eval_fixtures.py`, 6 tests written before implementation, all
  passed on the first real attempt). While building the fixture's
  description excerpts, discovered every Greenhouse-sourced job's stored
  `description` contained raw, unstripped HTML markup: Greenhouse's real
  `content` field double-escapes its own markup, and the existing
  `_strip_html`'s tag-strip-then-unescape order (a deliberate B1 fix for a
  different, purely synthetic edge case) left the revealed tags completely
  unstripped once unescaped. Stopped and surfaced this before proceeding,
  rather than working around it locally; user directed a real fix.
  Verified empirically, before proposing anything, that a naive single-pass
  fix could not satisfy both the old synthetic test and the newly-found
  real case simultaneously, then designed and confirmed a found-tag
  heuristic that does (100% of 2,691 real Greenhouse jobs are
  double-escaped with zero mixed cases, which is what makes the heuristic
  safe). Fixed in `greenhouse.py` with an `html.parser`-based extractor, no
  new dependency; 2 new tests added, the original synthetic test unchanged
  and still passing. Backfilled all 2,691 affected rows
  (`description`/`content_hash` only) under an explicit, narrowly-scoped
  hard-rule-13 exception: showed a 3-4 sample before/after diff first,
  including one with nested `<h4>`/`<ul>`/`<li>` structure, got explicit
  go-ahead, then ran the full backfill and verified via a full before/
  after snapshot of every column on all 3,846 rows (not a sample) that
  exactly 2,691 changed, all Greenhouse, zero Ashby rows touched, zero
  columns other than the two intended ones changed anywhere. Recorded as
  a D22/D23 addendum in docs/decisions.md.
  Regenerated the fixture file once with full JD text instead of an
  800-char excerpt (renamed `description_excerpt` -> `description`),
  matched and merged by `job_id` so the 7 labels already filled in at that
  point survived, verified programmatically. Ran a completeness/sanity
  check at the user's request (all-non-null check, required_keywords
  correlation with relevance, per-profile distribution, flat-score
  flagging) that caught 3 real data-entry typos (`"90S"`/`"0S"`/`"70S"`,
  string not int) before they could reach the loader; fixed by hand after
  confirming intended values with the user. Final state: all 50 JDs fully
  labelled (zero nulls, zero malformed values), loaded into the real
  `human_labels` table (150 rows, verified idempotent on re-run), 11 of 50
  have `required_keywords` (short of TODO.md's literal "~15", marked done
  anyway per explicit sign-off, flagged in Known Issues rather than
  silently rounded up). D24 added to docs/decisions.md for the
  keyword-to-max-relevance-profile mapping design.
  `uv run pytest` 146/146 passing; `ruff check`/`format --check` clean on
  `src/` (same pre-existing `tests/test_render.py`/`tests/test_slop_lint.py`
  debt, untouched, not in scope). TODO.md C2 checked off. Next: your call
  between C1 (LLM router), C3 (keyword extraction, now unblocked with real
  human_labels to calibrate against), B3-followup, or A4b.
- 2026-08-03, B3 (done) + B2 (unattended-firing proof resolved): Took the
  previous session's implemented-but-unsigned-off B3 through two rounds of
  real-data-grounded fixes, both triggered by random visual sampling the
  user asked for specifically to eyeball fit, not by anything a test
  caught. Round 1 (30 titles, 10 per profile): added `ai_ml_engineer`'s
  and `data_scientist`'s missing `exclusion_keywords` (caught "User
  Researcher, AI Evaluations" and "People Research Scientist, Recruiting"
  slipping through bare "researcher"/"scientist"; the latter only ever
  matched `data_scientist`, so adding the list to `ai_ml_engineer` alone
  as literally instructed would not have fixed it, caught by checking
  before implementing), `software_engineer`'s "success engineer"/"customer
  engineer" exclusions (caught "AI Success Engineer"), a new cross-profile
  `is_above_target_seniority` hard exclude with no override list (caught a
  Pinterest "Manager II" title), and a new cross-profile `is_us_location`
  hard remote-OR-US requirement, `classify_location()` returning a
  distinguishable `"ambiguous_unparseable"` for garbage/unrecognized
  location text instead of silently passing or failing. Building the
  location allowlist from the real distinct `location_raw` values (725 of
  them, pulled and shown before writing code) surfaced a real design gap
  mid-implementation: the initial version left 205 jobs stuck in
  "ambiguous" because bare city names with no state suffix ("San
  Francisco" alone, 148 of those) weren't recognized; fixed by adding
  `us_major_city_names`, re-verified the ambiguous bucket dropped to 18,
  all genuine garbage (`location_raw` literally "N/A"/"LOCATION"/"AMER").
  Also corrected the user's stated premise that "APAC"/"Greater China
  Region"/"Southern Europe" had been seen in a sample: none of the three
  exist anywhere in the real dataset (checked directly); added them to
  `non_us_signals` anyway per explicit request, flagged as unverified.
  17 new tests for round 1, then 3 more (checking job id 2942 directly
  rather than assuming a hypothesized gap) confirmed no bug there. `uv run
  pytest` 138/138 passing (98 pre-existing + 40 in `test_filter.py`); ruff
  clean on `src/`. **B3 signed off, TODO.md and Status table marked
  done.** Recorded as D23 addendum 3 in docs/decisions.md. Separately,
  found (not caused: read-only connections only, verified) that the real
  db had grown from 3834 to 3846 jobs and `runs` from 8 to 10 rows since
  the last checkpoint, with the two new `runs` rows landing on 2026-08-03
  with real non-zero diffs; the user cross-referenced this against Task
  Scheduler's own Last Run Time and confirmed both were genuine unattended
  firings, resolving B2's last open item (the previous session's id-8
  signal was suggestive but not conclusive; these two, with real diffs and
  an independent cross-reference, are). Next: your call between
  B3-followup, A4b, or C1.
- 2026-08-02, B3 (implemented, not yet marked done): Built
  `src/jobengine/pipeline/filter.py` (`matches_profiles`, `is_remote`,
  `is_excluded_employment_type`, `is_already_applied`,
  `is_citizenship_or_clearance_required`) and `config/filters.yaml`, per
  TODO.md's B3 item. Before writing any code, pulled real distributions
  from the live 3834-job/15-company db (title word frequency, exact-title
  frequency, location/remote split, department breakdown) and simulated
  naive filters against them rather than trusting docs/architecture.md's
  placeholder alias lists; the user then explicitly stopped a hardcoded
  daily-volume target from being derived from that same data (backlog
  snapshot, not daily inflow, see new D23 in docs/decisions.md). Iterated
  the title-alias config through several real-data-driven rounds: adding
  the spec's original phrase-only aliases (17.5% naive match), then bare
  "engineer"/"scientist"/"researcher" (31.5%, but with real mis-routing:
  Security Engineer, IT Support Engineer, Forward Deployed Engineer all
  matched `software_engineer`), then `exclusion_keywords` +
  `exclusion_override_keywords` to fix the mis-routing without losing the
  recall gain (27.9% naive, "Forward Deployed Software Engineer" still
  matches via the "software" override). Wrote `tests/test_filter.py` (23
  tests) before implementation per hard rule 7, confirmed all-red on
  `ModuleNotFoundError` (verified via `--collect-only`, and confirmed the
  failure was specifically the missing module and not a real bug: the
  `pipeline` namespace package imports fine, `ast.parse` finds no syntax
  errors in the test file). Implementation passed 21/23 on the first
  attempt; the other 2 were a test-fixture bug (missing `companies` seed
  row for `jobs.company_slug`'s FK), not a `filter.py` bug, fixed in the
  fixture. Caught and corrected a real self-inconsistency in my own
  reporting: an intermediate summary presented employment/citizenship
  exclusion counts (27, 57) computed against the full 3834-job dataset
  right next to a table about the 1071-job alias-matched subset, which
  does not arithmetically reconcile; the user caught this and asked for
  the derivation shown, not asserted. Recomputed with explicit
  inclusion-exclusion set arithmetic (`|A| - |A∩E| - |A∩C| + |A∩E∩C| =
  1071 - 6 - 16 + 0 = 1049`), confirmed it matches the direct set
  computation. **Final numbers** (ai_ml_engineer/software_engineer/
  data_scientist): 85/952/90, 1049/3834 total (27.4%). `uv run pytest`
  121/121 passing (98 pre-existing + 23 new); `ruff check`/`format --check`
  clean on `src/` (the pre-existing 3 `RUF059` findings and 2 unformatted
  files remain `tests/test_render.py`/`tests/test_slop_lint.py` debt from
  before this session, untouched, not in scope). Also added TODO.md's new
  B1-followup item (DOL LCA sponsorship-aware company vetting, deliberately
  out of scope for B3 itself: JD text alone can't distinguish "doesn't
  sponsor" from "just didn't mention it") and specs/04-sources.md's "Open
  item" note on the deferred daily-cap calibration.
  **Not done yet, on purpose:** TODO.md's B3 definition of done requires
  "you agree with the survivors on inspection," and that explicit
  agreement has not been given this session, only the numbers have been
  shown and reconciled. Status table marks B3 `in progress`, not `done`,
  until that happens. Next: get sign-off on the B3 numbers, then pick
  between B3-followup, A4b, or C1.
- 2026-08-02, infra/safety (checkpoint verification, no code changes):
  Re-verified full state: `uv run pytest` 98/98 passing, `ruff
  check`/`format --check` clean on everything touched this project's B1/B2
  work (the 3 `RUF059` findings and 2 unformatted files remain the same
  pre-existing `tests/test_render.py`/`tests/test_slop_lint.py` debt from
  before this session, still untouched). Corrected two stale claims this
  file made earlier in the day: scheduling is not "unstarted", Windows
  Task Scheduler task `job-engine-sync` exists (`schtasks /create`, every
  3h from 6am local, pointed at `C:\Users\aanki\run-sync.bat`), and
  spec 04's Scheduling section was rewritten to match, with the
  batch-publish-timing-vs-polling-frequency reasoning behind the 3h
  interval. Read-only checked the real `data/jobengine.db` (per hard rule
  13, no writes) and found `runs` grew from 6 to 8 rows since the last
  checkpoint (ids 7-8, 22:40:20 and 22:59:58 UTC, both healthy
  `companies_ok=15 updated=3834 new=0 edited=0`). Did not read this as
  proof of unattended firing: the ~13-20 minute gaps between ids 6-7-8
  don't match the configured 3-hour interval, so these still look like
  continued manual/debugging invocations. Named the concrete check for
  tomorrow in Known Issues: query `runs` (not `jobs.first_seen_at`, which
  can false-negative on a quiet 3-hour window) for six rows landing on
  their own near 06/09/12/15/18/21 local with nobody running `schtasks
  /run` that day. Next: your call between B3, A4b, or waiting out the
  unattended-firing check before treating B2 as fully production-live.
- 2026-08-02, infra/safety (not a TODO.md item): Added `scripts/sync.sh`
  (bash wrapper: cd into repo, `PATH`/venv setup for cron/Task Scheduler
  environments, `uv run python -m jobengine.sources.sync`, timestamped log
  to `data/logs/sync-YYYY-MM-DD.log`), `chmod +x`'d and verified by running
  it from `/tmp` to confirm the cd-into-repo logic is caller-cwd-agnostic.
  Investigated a report that the real `data/jobengine.db` was found empty
  with no `init`/`migrate` in shell history: confirmed the test suite
  structurally cannot be the cause (every `connect()` call across
  `tests/*.py` passes an explicit `tmp_path`, no `conftest.py` exists, the
  only real-path `connect(DEFAULT_DB_PATH)` call sites are the three CLI
  entry points), and that the actual cause was this session's own prior
  live-API sanity-check resets during B1 and B2, narrated in the moment
  but never asked about first. Added CLAUDE.md hard rule 13 and D22 in
  docs/decisions.md: no destructive operation against the real
  `data/jobengine.db` path without asking first and getting explicit
  confirmation, use a scratch/temp path for exploratory checks instead.
  This reverses the working assumption every prior session, including
  this one's own B1/B2 work, operated under. As of this checkpoint the
  real db holds 15 companies, 3834 jobs, and 6 `runs` rows (verified
  read-only, not touched this session); likely from a manual run of the
  pipeline or `scripts/sync.sh` outside this session's own tool calls,
  now left alone under the new rule rather than reset "back to clean."
  `uv run pytest` 98/98 passing; nothing new introduced to `ruff check`
  (the 3 `RUF059` findings and 2 unformatted files are the same
  pre-existing `tests/test_render.py`/`tests/test_slop_lint.py` debt noted
  in prior checkpoints, still untouched, still not this session's scope).
  Next: your call between B3, A4b, or actually wiring `scripts/sync.sh`
  into cron/Windows Task Scheduler so B2 becomes production-live instead
  of just manually-invokable.
- 2026-08-02, B2 (done): Implemented `src/jobengine/sources/sync.py`
  (`sync()`, per-company fetch+diff, `--dry-run` CLI) and three new
  `db/models.py` accessors (`list_active_companies`, `record_run` +
  `Run` model, `close_missing_jobs`). `tests/test_sync.py` (10 tests,
  written and confirmed all-red on `ImportError` before implementation)
  covers both halves of spec 04's literal DoD by name
  (`test_second_sync_of_unchanged_data_does_not_change_first_seen_at`,
  `test_new_posting_on_second_run_gets_its_own_first_seen_at`) plus edit
  detection, closed_at set/clear (including the free reopen-on-upsert
  behavior), per-company failure isolation, dry-run write suppression, and
  the new `runs` table. All 10 passed on the first implementation attempt.
  Resolved one real spec/schema gap by asking before coding: "record an
  edit event" (spec 04) has no backing table, so it's a log line + a
  `runs.counts.edited` count, not a new table (see D2 addendum in
  docs/decisions.md). Also re-verified end to end against the live APIs,
  not just mocked tests: seeded all 15 real companies, ran `sync` twice
  back to back (3834 jobs, run 1 all-new, run 2 `new=0 updated=3834`), and
  confirmed by direct SQL query that only 15 distinct `first_seen_at`
  values exist afterward, one per company, none moved between runs.
  **What's still open, not silently treated as done:** the real
  two-syncs-a-day-apart production check (can't be simulated in a single
  session or a unit test) and putting `sync.py` on an actual schedule,
  both spec 04 requirements, tracked in Known Issues, not yet started.
  `uv run pytest` 98/98 passing; `ruff check`/`format --check` clean on
  everything touched this session. TODO.md B2 checked off with a note that
  its "two runs a day apart" clause is unit-simulated, not literally
  time-separated yet. Next: your call between B3 (filters + routing,
  unblocked now that jobs actually populate) and A4b (PDF conversion,
  unblocked, blocks D2), or scheduling B2 first since it's now the thing
  standing between "code done" and "actually running."
- 2026-08-02, B1 (done): Implemented `src/jobengine/sources/{models,
  _client,greenhouse,ashby,registry}.py` and `tests/test_sources.py` (18
  tests, written and confirmed all-red on `ImportError` before
  implementation per hard rule 7's spirit, even though `sources/` isn't
  literally in that rule's `pipeline/`, `resume/`, `rubric/` list). Widened
  `companies.source` CHECK to `('seed', 'harvest', 'manual')` (schema.sql +
  specs/00-data-model.md), confirmed by asking, `data/jobengine.db` dropped
  and re-`init`'d since it had zero rows. Seeded `config/seed_companies.yaml`
  with 15 real companies and verified it end to end against the live
  Greenhouse/Ashby APIs, not just mocked tests: `registry seed` +
  `registry validate` against a scratch db, 14/15 active on the first
  guess, `doordash` 404'd and was actually `doordashusa`, fixed in the seed
  file itself before finalizing. Caught one real bug via the tests
  themselves (not post-hoc): Greenhouse's HTML-to-plaintext conversion was
  unescaping entities before stripping tags, so an escaped `&lt;fast&gt;`
  became a literal `<fast>` that the tag-stripper then ate as if it were a
  real tag; fixed by reversing the order. Explicitly scoped B1 down to
  clients + registry only (not `sync.py`'s fetch-and-diff loop, that's B2)
  and deferred the Common Crawl harvest path entirely, both confirmed by
  asking before writing code. `uv run pytest` 88/88 passing; `ruff
  check`/`format --check` clean on everything touched this session (3
  pre-existing `RUF059` findings in `tests/test_render.py` are unrelated,
  not introduced here, left alone). TODO.md B1 checked off with a note on
  the `sources.sync`-vs-`registry validate` DoD wording gap. Next: your
  call between B2 (fetch-and-diff, unblocked, `sources/` now exists) and
  A4b (PDF conversion, unblocked, blocks D2) per the session protocol's
  one-task-at-a-time rule.
- 2026-08-02, A3 (done): Implemented `src/jobengine/resume/slop_lint.py`
  (lenient `LintTarget` schema, `Report` with errors/warnings/fatal,
  `lint_target`/`lint_path`, full CLI) and `tests/test_slop_lint.py` (22
  tests, one fixture per rule plus two clean-pass tests, written and
  confirmed all-red before implementation per hard rule 7). Wired
  `.claude/settings.json`'s `PostToolUse` hook (`Edit|Write` to
  `slop_lint --changed`), verified manually with simulated hook stdin
  JSON: a clean edit exits 0, an unrelated file is silently skipped, an
  injected violation exits 2. Renamed bank.py's `_is_past_tense`/
  `_IRREGULAR_PAST_TENSE_VERBS` to public so H003 shares the exact
  heuristic instead of duplicating it. Running the linter against the real
  bank (not just synthetic fixtures) surfaced a real design gap: H006 as
  first scoped (jargon = any of a role's declared keywords) flagged 9
  false positives on plain domain nouns (cosmology, automation,
  optimization, financial services, ...) in roles seeded during A2.
  Narrowed H006 to an explicit `_TECH_JARGON_TERMS` allowlist of actual
  tool/tech-stack proper nouns; confirmed by asking, recorded as D21.
  `resume/bank/aankit.yaml` now lints clean (exit 0, only the expected
  W002 stub warning). `uv run pytest` 46/46 passing, `ruff
  check`/`format --check` clean. TODO.md A3 checked off; its definition of
  done (bad fixture flagged, real bank bullet passes, PostToolUse hook
  stops erroring) is met against the real bank and a real simulated hook
  invocation, not just unit tests. Next: A4, docx renderer
  (specs/03-renderer.md).
- 2026-08-02, verification: Ran `/checkpoint` again with no code changes
  since the entry below. Re-verified: `uv run pytest` 24/24 passing, `ruff
  check`/`format --check` clean, `bank validate` still 0 errors/0 warnings
  on the real `resume/bank/aankit.yaml` (ai_ml_engineer 24, data_scientist
  17, software_engineer 14 bullets). No `slop_lint` module exists yet
  (`src/jobengine/resume/` only has `bank.py`), so A3 is confirmed not
  started, not just marked that way. PROGRESS.md/TODO.md/docs/decisions.md/
  pyproject.toml remain uncommitted; nothing new to commit. Next: A3, slop
  linter (specs/02-slop-linter.md).
- 2026-08-02, verification: Ran `/checkpoint` again with no code changes
  since the entry below. Re-verified: `uv run pytest` 24/24 passing, `ruff
  check`/`format --check` clean, `bank validate` still 0 errors/0 warnings
  on the real `resume/bank/aankit.yaml` (ai_ml_engineer 24, data_scientist
  17, software_engineer 14 bullets). PROGRESS.md/TODO.md/docs/decisions.md/
  pyproject.toml remain uncommitted; nothing new to commit. Next: A3, slop
  linter (specs/02-slop-linter.md).
- 2026-08-02, A2 (done): Seeded `resume/bank/aankit.yaml` for real: 2
  education entries, 5 work/research roles from the CV (Bantrly, UTD
  Machine Learning Researcher, SEI Investments, Nebraska-Lincoln, Jadavpur
  University), 4 publications with real evidence URLs pulled from the CV
  PDF's actual hyperlinks (GitHub orgs, NSF award page, IEEE/Frontiers/MDPI
  DOIs), rather than defaulting everything to "internal". Explicitly
  confirmed with the user that 8 of the CV's 10 "Projects" entries
  (TinyML Drone, SecureVision, Speculative Decoding, and 5 others) stay out
  since 1-2 CV bullets each can't clear rule 9's 3-bullet minimum without
  inventing content; only the two meatiest, Bantrly Lesson Generator and
  Document Intelligence Platform, got seeded, also with real GitHub/HF
  Spaces evidence links. That required a schema fix first: `Role.company`,
  `.location`, `.start` were required fields with no way to express Lee's
  rule that projects skip dates/location, so made all three
  `str | None = None` (test added). Also caught and fixed a gap from the
  prior session: `requires_degree_profiles` was never actually checked
  against `KNOWN_PROFILES` despite being in the original plan (test added).
  `uv run python -m jobengine.resume.bank validate` on the real bank: 0
  errors, 0 warnings, ai_ml_engineer 24 / data_scientist 17 /
  software_engineer 14 bullets. `uv run pytest` 24/24 passing, `ruff
  check`/`format --check` clean. TODO.md A2 checked off; its definition of
  done (`bank validate` zero errors, per-profile count) is met on the real
  file, not just a sample. Next: A3, slop linter (specs/02-slop-linter.md).
- 2026-08-02, A2 (in progress): Got the user's resolution on all four
  spec-01 CV-vs-docx conflicts: BTech end date is September 2020 (docx),
  citation count is 140+ (CV), the SEI role's typo'd start date is October
  2021, and both job titles (Bantrly: "AI Engineer", UTD: "Machine Learning
  Researcher") follow the CV, the docx being stale. Seeding
  `resume/bank/aankit.yaml` is no longer blocked on anything but doing the
  work. Next: seed the bank content itself, bullet by bullet, from the CV.
- 2026-08-02, A2 (in progress): Corrected a wrong assumption from the prior
  entry below: `docs/headless-headhunter/template.docx` is Aankit's actual
  docx resume (title, dates, and citation count all differ from the CV), not
  just Lee's blank formatting template. Read it with python-docx and pulled
  the exact conflicting values (see Known Issues above). The real blocker on
  seeding `resume/bank/aankit.yaml` was never a missing source, it's that
  only the user can say which value is correct for each conflict.
- 2026-08-02, A2 (in progress): Built `src/jobengine/resume/bank.py`
  (models, `load_bank`, `validate_bank` for rules 1-9, `coverage_gaps` for
  rule 10, `keyword_counts`, the `validate`/`stats`/`coverage` CLI) and
  `tests/test_bank.py` (22 tests). Asked and confirmed four schema-level
  ambiguities in spec 01 before coding (summary as a lighter model, id
  uniqueness scoped bank-wide, profile set hardcoded pending E1, rules 3/7
  as warnings not errors). Smoke-tested the CLI against the spec's own
  `role_bantrly` example: it initially failed 5 rule-10 checks, which
  showed my first reading of rule 10 was wrong (see D20 in
  docs/decisions.md); moved rule 10 out of `validate_bank` into
  `coverage_gaps`, re-tested, now 0 errors/0 warnings on that example.
  `uv run pytest` 22/22 passing, `ruff check`/`format --check` clean. Not
  done: `resume/bank/aankit.yaml` itself doesn't exist, so `bank validate`
  on its default path currently raises `FileNotFoundError`. Next: seed the
  real bank content, which needs your resolution of the CV-vs-docx
  conflicts spec 01 flags (BTech end date, citation count, the "October
  202" typo, per-profile title overrides) before it can proceed.
- 2026-08-02, verification: Ran `/checkpoint` with no new code changes this
  session. Re-verified A1's definition of done still holds: `uv run pytest`
  8/8 passing, `ruff check`/`format --check` clean, filesystem matches the
  entries below. PROGRESS.md/TODO.md/docs/decisions.md/pyproject.toml
  remain uncommitted from the A1 session; nothing new to commit. Next: A2,
  bullet bank schema + bank content (specs/01-bullet-bank.md).
- 2026-08-02, A1: Implemented the full schema (16 tables + indexes),
  migrate.py, models.py with companies/jobs/outcomes accessors, and the
  `jobengine.db` CLI. Enforced `first_seen_at` immutability on both `jobs`
  and `companies` via SQL triggers, plus outcomes append-only triggers.
  Renamed `src/job_engine` to `src/jobengine` to match the specs (asked
  first). 8 tests in tests/test_db.py pass; `ruff check`/`format --check`
  clean; CLI (`init`/`migrate`/`stats`) verified manually against
  `data/jobengine.db`. Next: A2, bullet bank schema + bank content
  (specs/01-bullet-bank.md) — budget two hours, don't let this run
  unattended per TODO.md's own warning.
