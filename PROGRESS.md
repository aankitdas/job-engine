# Progress

**Claude Code: read this file at the start of every session and update it at
the end via `/checkpoint`. Do not rely on memory of previous sessions.**

Last updated: 2026-08-04
Current task: C3 (keyword extraction + corpus) is **done, shipped against
a deliberate quality decision, not against spec 07's literal numeric
gate**. Real measured extraction quality (qwen3.5:9b, the reverted
named-tech-focused prompt) against the fully human-reviewed 11-job
`human_labels.yaml` fixture: **precision 0.833 (passes >= 0.70), recall
0.467 (fails >= 0.85)**. The decision to ship anyway, not keep iterating,
is recorded as D27 in docs/decisions.md: every resume goes through human
review before it's sent (architecture.md stage 8, strictly before stage
9 "apply"), recall gaps only under-extract (never invent content, the
safe failure direction under hard rule 2), and an 11-job fixture can only
approximate real usage. Revisit only if manual review of real pipeline
output later shows this is a recurring practical problem, not
preemptively; D27 lists the options in order (next candidate model, a
deliberately-asked-about paid API call for this one stage, or accepting
current quality) if that happens.
Built this session: `src/jobengine/pipeline/extract.py` (the extraction
call + job_analysis/keyword_corpus persistence, reusing C1's router
directly per CLAUDE.md hard rule 8) and `src/jobengine/eval/{harness,
report,tasks/keyword_extraction}.py` (spec 07's Task 2 harness, pooled
TP/FP/FN, `uv run python -m jobengine.eval {run,compare}`). Also, along
the way, found and fixed 3 real pre-existing data-quality bugs in the
`human_labels.yaml` fixture from the original C2 session (see D26 in
docs/decisions.md) and did a full exhaustive, source-quoted, human-
reviewed re-derivation of all 11 labeled jobs' `required_keywords`, now
the cleanest ground truth this project has had.
Next: your call between C4 (relevance pre-filter, spec 06, the other
half of spec 07's eval harness, Task 1), B3-followup, or A4b.

Separately: B2's unattended-overnight proof is now **resolved**. Windows
Task Scheduler task `job-engine-sync` fired on its own twice on 2026-08-03
(`runs` ids 9 and 10, `started_at` 04:13:50Z and 14:02:54Z, both with real
non-zero diffs: id 9 `new=2 edited=53 closed=2`, id 10 `new=10 edited=1
closed=9`), cross-referenced against Task Scheduler's own Last Run Time by
the user. Real diffs (not just a re-run of unchanged data) are themselves
corroborating: a manual debug re-run minutes apart, like ids 6-8 the
previous day, showed zero drift, while these two show genuine new/edited/
closed content, consistent with independent scheduled fetches rather than
a human retriggering the same run. See Known Issues, this item is marked
resolved there, not deleted, so the reasoning stays visible.

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
| A4b | PDF conversion (LibreOffice headless) | not started | blocks D2 |
| A4c | Watermarking (speculative preview) | not started | no urgency, no speculative bullets exist yet |
| B1 | ATS clients + registry | done | clients+registry only, sync.py's fetch/diff loop is B2 |
| B2 | Fetch and diff | done | scheduled and confirmed firing unattended on its own on 2026-08-03; see Known Issues, item resolved |
| B1-followup | Sponsorship-aware company vetting (DOL LCA) | not started | flagged only, not scoped, see TODO.md |
| B3 | Filters + routing | done | signed off 2026-08-03; `filter.py` implemented, 40/40 tests pass, final numbers 859/3836 survivors (68/776/81 per profile) |
| B3-followup | Calibrate daily filter-survivor cap | not started | deliberately deferred, see D23 in docs/decisions.md |
| C1 | LLM router | done | `llm.check` verified live against real Ollama, all 3 stages reachable, exit 0; cold-start ~15s / steady-state 600-935ms, see Known Issues |
| C2 | Eval fixtures | done | 50/50 JDs labelled, loaded into `human_labels` (150 rows); 11/15 keyword-annotated, short of TODO.md's literal target, done anyway per explicit sign-off, see Known Issues |
| C3 | Keyword extraction | done | shipped per D27 (ship decision), not literal DoD: precision 0.833 passes, recall 0.467 fails the 0.85 gate, see Known Issues |
| C4 | Relevance filter | not started | |
| D1 | Rubric rules | not started | |
| D2 | PDF geometry | not started | |
| D3 | Patch P0-P2 | not started | |
| D4 | Patch P3 | not started | |
| E1 | Profile brief | not started | |
| E2 | Base resumes | not started | human-in-loop |
| F1 | Review queue | not started | |
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

- `src/jobengine/db/schema.sql`: full DDL for all 16 tables in
  specs/00-data-model.md plus indexes and immutability/append-only triggers.
- `src/jobengine/db/migrate.py`: `connect()` (opens the sqlite3 connection,
  turns on `PRAGMA foreign_keys`), `init()` (idempotent schema apply),
  `migrate()` (applies schema + records `schema_migrations`), `stats()`
  (row counts per table).
- `src/jobengine/db/models.py`: pydantic models `Company`, `Job`, `Outcome`,
  and typed accessors `upsert_company`, `upsert_job`, `get_company`,
  `get_job`, `insert_outcome`. No accessors yet for the other 13 tables;
  those get added when the phase that needs them lands (B1 for companies
  detail, D-phase for rubric/variant tables, etc.).
- `src/jobengine/db/__main__.py`: `uv run python -m jobengine.db {init,migrate,stats}`.
- `tests/test_db.py`: 8 tests, including the required first_seen_at
  immutability test for jobs and (per explicit request) the matching one
  for companies, plus the outcomes append-only constraint.
- `src/jobengine/resume/bank.py`: pydantic models (`Bank`, `Role`, `Bullet`,
  `SummaryBullet`, `Education`, `Certificate`, `Publication`, `Meta`),
  `load_bank()`, `validate_bank()` (rules 1, 2, 4, 5, 6, 8, 9 as hard errors,
  plus a `requires_degree_profiles`/`title`/`profiles` referential-integrity
  check against `KNOWN_PROFILES`; rules 3 and 7 as warnings that don't fail
  `validate`), `coverage_gaps()` (rule 10, checked against the
  `keyword_corpus` table, not per-bullet text), `keyword_counts()`, and the
  CLI (`uv run python -m jobengine.resume.bank
  {validate,stats --by-keyword,coverage --profile}`). `Role.company`,
  `.location`, and `.start` are optional, since Lee's rule is that
  `kind: project` entries skip dates and location entirely.
- `resume/bank/aankit.yaml`: the real seeded bank. 2 education entries, 7
  roles (Bantrly, UTD Machine Learning Researcher, SEI Investments,
  Nebraska-Lincoln, Jadavpur University, plus 2 `kind: project` entries for
  the Bantrly Lesson Generator and Document Intelligence Platform projects),
  28 bullets total, 4 publications. `bank validate` passes 0 errors, 0
  warnings. Per-profile bullet counts: ai_ml_engineer 24, data_scientist 17,
  software_engineer 14.
- `tests/test_bank.py`: 24 tests, one failing fixture per rule plus
  id-uniqueness, profile-referential-integrity, project-role-optional-fields,
  and coverage-gap cases. `bank.py`'s past-tense heuristic is now public
  (`is_past_tense`, `IRREGULAR_PAST_TENSE_VERBS`) so slop_lint's H003 reuses
  it exactly instead of a second copy.
- `src/jobengine/resume/slop_lint.py`: a lenient pydantic mirror of bank.py's
  Bank/Role/Bullet shape (`LintSummary`, `LintBullet`, `LintRole`,
  `LintTarget`, all fields optional/defaulted) so a structural problem
  (missing summary, dangling id) comes back as a lint `Issue` instead of a
  `ValidationError` with no rule code. `Report` has three buckets
  (`errors`, `warnings`, `fatal`) plus `.ok`. `lint_target()` is the core
  in-memory check; `lint_path()` loads a target YAML plus a ground-truth
  bank YAML (`bank_path`, default `DEFAULT_BANK_PATH`) for H008's id
  cross-reference. Implements all 17 rules from specs/02 (S001-S006,
  H001-H008, W001-W003) plus the E999 fatal hard block on `speculative`
  bullets outside `--preview`. CLI: `uv run python -m
  jobengine.resume.slop_lint {<path>|--changed} [--preview] [--json]
  [--strict] [--profile]`.
- `tests/test_slop_lint.py`: 22 tests, one failing fixture per rule
  (H008 covered twice: an isolated in-memory check and an end-to-end one
  through the real YAML loader with a genuinely dangling id against a small
  fixture bank), plus two clean-pass tests (a synthetic target and the real
  `role_bantrly` role from `resume/bank/aankit.yaml`, so that test doubles
  as a bank regression check).
- `.claude/settings.json`: new, checked in (unlike `settings.local.json`,
  which is gitignored). Wires `PostToolUse` on `Edit|Write` to `uv run
  python -m jobengine.resume.slop_lint --changed`. See D6's addendum in
  docs/decisions.md for the exit-code contract.
- `src/jobengine/resume/render.py`: **A4 only, not spec 03's full scope.**
  Built: `Identity` (`load_identity()` reads `identity.toml`, read-only,
  never written to), `RenderProfile` (a stand-in for E1's not-yet-built
  profile registry, `section_order` + `include_summary`/`summary_text`),
  and `render(bank, identity, profile) -> Document`, an in-memory
  python-docx `Document`. Every run/paragraph gets explicit direct
  formatting from a `_TYPOGRAPHY` table (no Word paragraph styles, no
  inherited defaults) covering all 7 typography rows in spec 03's table,
  the single 7.5in right tab stop, 720-twip margins, left not justified,
  profile-driven section order, the summary-section trigger, "to Present"
  for current roles, no date line for `kind: project` roles, and
  publication author-run bolding. `_add_right_tab_paragraph()` is the one
  shared mechanism for every line that needs text pinned to the 7.5in right
  margin (job title/date, education degree/status); both go through it, so
  there's exactly one implementation of "right-aligned via a tab stop" to
  get right, not two. `Education.status` is a literal opaque string
  `render()` just prints, never date-computed (no "3-year rule" logic
  anywhere in this module; that's the bank content's call, see D5's
  addendum in docs/decisions.md). The contact line's LinkedIn/GitHub/
  Portfolio/Scholar are real docx hyperlink relationships (short label
  text, e.g. "LinkedIn", never the raw URL as visible text), built via
  `_add_hyperlink_run()`: python-docx has no high-level write API for
  hyperlinks, so this adds the run normally through the same
  `_set_run_style()` everything else uses, then moves its `<w:r>` element
  inside a `<w:hyperlink r:id="...">` pointing at a relationship added via
  `part.relate_to()`. Phone and email stay plain black text, matching the
  template. **Not built**: PDF conversion (A4b) and
  speculative-bullet watermarking (A4c), both real sections of spec 03,
  tracked as separate TODO.md items rather than silently folded into "A4
  done." `render()` never opens or writes `resume/templates/golden.docx`;
  every document is built fresh via `docx.Document()`, so rule 6 (never
  mutate the template) holds by construction.
- `tests/test_render.py`: 24 tests. Typography per semantic role checked
  against `_EXPECTED`, a table hand-transcribed from spec 03's own
  typography table plus raw XML pulled directly from
  `docs/headless-headhunter/template.docx` (confirmed byte-identical to
  `resume/templates/golden.docx`), independent of `render.py` and never
  generated by calling `render()` itself, specifically to avoid a
  circular golden test. No physical `tests/fixtures/golden.docx` fixture
  exists; that's a deliberate deviation from spec 03's literal wording,
  confirmed by asking. Structural rules (section order, summary trigger,
  project no-dates, current-role "to Present", template immutability)
  covered on a small synthetic bank; one dedicated test renders the real
  `resume/bank/aankit.yaml` end to end for the literal golden-test DoD.
  `test_education_date_uses_tab_stop_not_hardcoded_spaces` uses a
  deliberately long degree/field/institution string to catch a real bug an
  XML review caught post-hoc: the education line originally right-aligned
  its status via hardcoded spaces, not a tab stop, so long degree text
  wrapped unpredictably instead of staying pinned to the margin. Fixed by
  routing education through the same `_add_right_tab_paragraph()` helper
  the job-title/date line already used correctly. A second real spec 03
  gap found the same way (XML review, not a failing test): the contact
  line printed raw URLs as plain visible text instead of short hyperlinked
  labels, contradicting both the typography note ("phone, email, and link
  runs which may be blue") and the template's own example (short labels,
  not full URLs). `test_contact_line_links_are_real_hyperlinks_not_url_text`,
  `test_contact_line_phone_and_email_are_plain_text_not_links`,
  `test_contact_hyperlink_runs_are_blue_underlined_arial_12pt`, and
  `test_no_raw_url_text_anywhere_in_document` cover it, on both the
  synthetic bank and the real-bank golden test.
- `scripts/render_sample.py`: manual dry-run, calls `render()` against the
  real bank/identity/default profile (same input as the golden test) and
  writes to `resume/rendered/preview/sample.docx` for visual inspection in
  Word. This is the only way to actually eyeball the output right now;
  spec 03's own DoD ("opening the output in Word side by side with the
  user's template shows no visible difference except the three deliberate
  fixes") is a manual check nothing in this repo can run for you.

- `src/jobengine/sources/models.py`: `JobPosting`, the normalized pydantic
  model both ATS clients return. Not yet mapped onto the `jobs` table;
  that mapping (plus `content_hash` computation and the diff loop) is B2.
- `src/jobengine/sources/_client.py`: shared `httpx.AsyncClient` factory
  (20s timeout, descriptive User-Agent), a process-wide
  `asyncio.Semaphore(10)` concurrency cap, and `retryable()`, a `tenacity`
  decorator (3 attempts, exponential backoff, retries only on 5xx/timeout,
  reraises immediately on anything else including 404) shared by both
  clients so the retry policy is defined once.
- `src/jobengine/sources/greenhouse.py` and `ashby.py`: each exposes
  `async fetch_board(slug, *, transport=None) -> list[JobPosting]`. The
  `transport` kwarg exists solely so tests can inject `httpx.MockTransport`
  without a real network call. Greenhouse strips tags before unescaping
  HTML entities, not the other way around, an ordering bug the tests caught
  immediately (unescaping first turns an escaped `&lt;fast&gt;` into a
  literal `<fast>` that the tag-stripping regex then eats as if it were a
  real tag). Ashby filters out `isListed: false` postings and uses the
  posting's `id` field for `ats_job_id`, which spec 04's Ashby field list
  omits but the real API returns; confirmed by asking before assuming.
- `src/jobengine/sources/registry.py`: `seed()`, `add()`, `validate()`, plus
  a self-hosted CLI (`uv run python -m jobengine.sources.registry
  {seed,add,validate}`). `seed`/`add` both go through
  `_insert_new_company()`, an `INSERT OR IGNORE`, deliberately not
  `jobengine.db.models.upsert_company`: that helper's `ON CONFLICT DO
  UPDATE` unconditionally overwrites `status`, so re-running `seed` against
  an already-`active` company would silently reset it back to
  `unverified`, destroying validation history. `validate()` buckets each
  probe into `active_ok` / `active_zero` / `dead` / `retry` per spec 04's
  four cases and takes an optional `fetchers` dict so tests can inject fake
  async fetchers instead of mocking HTTP transport for status-transition
  logic. A company that 404s does not flip to `dead` until the 3rd
  consecutive failure; below that threshold its status is left exactly as
  it was (spec 04 only specifies the status change at the threshold).
- `config/seed_companies.yaml`: 15 real companies (Stripe, Airbnb,
  DoorDash, Pinterest, Discord, Robinhood, Figma, Brex, Notion, Ramp,
  Linear, Anthropic, OpenAI, Scale AI, Cohere), not just test fixtures.
  Verified against the live Greenhouse/Ashby APIs during this session
  (`registry seed` + `registry validate` against a scratch db, not just
  mocked tests): 14 of 15 resolved on the first guess, `doordash` 404'd and
  turned out to be `doordashusa`, fixed in the file itself. This is a small
  starter set, not the real 150-300 list spec 04 calls for; expand by hand.
- `src/jobengine/sources/sync.py`: `sync(conn, dry_run=False, fetchers=None)
  -> RunSummary`, the fetch-and-diff loop from spec 04. Iterates
  `companies.status='active'` (via new `list_active_companies()` in
  `db/models.py`), fetches each board through B1's clients, and for every
  posting: looks up the existing row's `content_hash` via `get_job()`
  first (needed to detect edits before it's overwritten), maps
  `JobPosting` to `db.models.Job` (`content_hash = sha256(description_plain
  or "")`), and calls `upsert_job()` with `first_seen_at=now()`
  unconditionally on every call, new or existing. That's safe only because
  `upsert_job`'s `ON CONFLICT DO UPDATE` already omits `first_seen_at` from
  its SET list (built in A1); `sync.py` adds no new immutability logic of
  its own, it just relies on what's already there. A changed
  `content_hash` on an existing row is `logging.info()`'d and counted in
  `edited`, not written as a new table row (confirmed by asking, no
  edit-log table exists in the 16-table schema; see docs/decisions.md D2's
  addendum). Per-company fetch failures (dead slug, exhausted retries) are
  caught, logged, and skip only that company; one bad board never aborts
  the run, and a failed company's existing jobs are left untouched by the
  close-missing-jobs step since we never got a valid response to diff
  against. `--dry-run` is not a second code path: the full diff always
  runs and always writes, `dry_run` only decides `conn.commit()` vs.
  `conn.rollback()` at the very end, so there is exactly one implementation
  of the diff logic. One free, non-obvious side effect worth knowing about:
  because every posting still present in a fetch gets `closed_at=None`
  explicitly, and `upsert_job`'s SET clause already includes `closed_at =
  excluded.closed_at`, a job that closes on one sync and reappears on a
  later one automatically un-closes with no special-case code; this falls
  directly out of the existing upsert, `sync.py` doesn't add reopen logic.
  Every `sync()` call writes exactly one row to the new `runs` table
  (`stage='sync'`, `counts` JSON of new/updated/edited/closed/
  companies_ok/companies_failed, `errors` JSON list of per-company
  failure strings) via a new `record_run()` accessor, before the
  commit/rollback decision, so a dry run's `runs` row is rolled back too.
  CLI: `uv run python -m jobengine.sources.sync [--dry-run]`.
- `db/models.py` gained three accessors for B2: `list_active_companies()`,
  `record_run()` (new `Run` pydantic model), and `close_missing_jobs()`.
  **`close_missing_jobs` diffs id sets in Python and issues one `UPDATE`
  per missing job via `executemany`, not a single batched `WHERE
  ats_job_id NOT IN (...)` query.** Deliberate: a single `IN`/`NOT IN`
  clause risks SQLite's per-statement bound-parameter ceiling on a large
  board (Ashby's real OpenAI listing was 752 postings during this
  session's live check, comfortably within most limits today but not a
  bet worth making as boards grow), and chunking that clause into safe
  batches would be more code than just diffing two Python sets and looping
  the updates. Only ever iterates over what's actually missing (typically
  a handful of closed postings per company per run), so the loop is cheap
  in practice.
- `companies.source` CHECK constraint widened from `('seed', 'harvest')` to
  `('seed', 'harvest', 'manual')` in `schema.sql`, plus the matching column
  note in specs/00-data-model.md, so `registry add`'s manually-registered
  companies get their own source value instead of being folded into
  `seed`. `data/jobengine.db` had zero rows in `companies`/`jobs` at the
  time (verified before touching it), so this was a drop-and-`db init`,
  not a real migration; no `schema_migrations` bump needed since there was
  no data to migrate.
- `scripts/sync.sh`: bash wrapper for the cron/Task Scheduler entry spec 04
  calls for ("Scheduling"). `cd`s into the repo via `${BASH_SOURCE[0]}`
  (works regardless of caller's cwd, verified by running it from `/tmp`),
  prepends `~/.local/bin` to `PATH` and sources `.venv/bin/activate` since
  a cron/Task Scheduler environment often lacks both, then runs `uv run
  python -m jobengine.sources.sync`, appending timestamped stdout/stderr to
  `data/logs/sync-YYYY-MM-DD.log`. `chmod +x`'d. Now actually invoked by
  Windows Task Scheduler task `job-engine-sync` (created via `schtasks
  /create`, points at `C:\Users\aanki\run-sync.bat` with no inline
  arguments, every 3h from 6am local); see Known Issues for what's still
  unverified about that.
- **`data/jobengine.db` currently holds real accumulated state: 15
  companies, 3834 jobs, 8 `runs` rows, 0 `applications`** (re-verified
  read-only this checkpoint via plain `SELECT COUNT(*)` on all four
  tables; unchanged from the last checkpoint, so no new activity happened
  between the two). Not modified this session, per the hard rule below.
  Grew for real since: see the unattended-firing resolution in Known
  Issues, `runs` is now 10 rows and `jobs` is now 3846 (was 3834), both
  from genuine scheduled fetches, not manual re-runs.
- `config/filters.yaml`: B3's filter/routing config, now covering all five
  hard/per-profile checks. Per-profile `title_aliases` (grounded against
  real title distributions, not just docs/architecture.md's placeholder
  table: bare "engineer"/"scientist"/"researcher" added on top of the
  spec's original phrase-only aliases), matching `exclusion_keywords`/
  `exclusion_override_keywords` on all three profiles now, not just
  `software_engineer` (added `ai_ml_engineer`'s and `data_scientist`'s
  after a visual sample caught "User Researcher, AI Evaluations" and
  "People Research Scientist, Recruiting" slipping through bare
  "researcher"/"scientist"; "success engineer"/"customer engineer" added
  to `software_engineer`'s list after the same sample caught "AI Success
  Engineer"), a new `seniority.exclude_title_keywords` (cross-profile hard
  exclude, no override list, added after the same sample caught a
  Pinterest "Manager II" title), `location.remote_synonyms` plus new
  `us_informal_city_abbreviations`/`us_major_city_names`/`non_us_signals`
  (backing `is_us_location`, see below), `citizenship_clearance.
  exclude_phrases` (hard exclude across all profiles), and
  `employment_type` (Ashby's structured `raw_json.employmentType` field
  plus a Greenhouse title-text fallback). `daily_cap: null`, a deliberate
  non-target placeholder, not a tuned number; see D23 in docs/decisions.md
  and its 3 addenda.
  **`non_us_signals`' "apac"/"greater china"/"southern europe" entries are
  unverified against real data, not confirmed-working**: added on
  explicit request, but no job in the current 3846-job dataset contains
  any of the three (checked directly), so nothing exercises that code path
  today. Harmless if wrong (worst case, a job with one of these in
  `location_raw` gets classified `ambiguous_unparseable` instead of
  `non_us_match`, still excluded either way, just logged differently), but
  flagging so "in the config" isn't mistaken for "proven correct."
- `src/jobengine/pipeline/filter.py`: `load_filter_config()`,
  `matches_profiles(job, config) -> list[str]`, `is_remote()`,
  `is_excluded_employment_type()`, `is_already_applied(conn, job_id)`,
  `is_citizenship_or_clearance_required(description, config)`,
  `is_above_target_seniority(title, config)`, `is_us_location(job,
  config)`, and `classify_location(job, config) -> str` (returns
  `"remote"`/`"us_match"`/`"non_us_match"`/`"empty_location"`/
  `"ambiguous_unparseable"`; `is_us_location` is just `classify_location(..)
  in ("remote", "us_match")`, kept separate so callers can log the
  ambiguous/empty cases instead of only getting a bare bool). All pure
  functions, nothing persisted: no filter-survivor table exists or is
  written to (`job_analysis`'s other columns belong to C3/D1); downstream
  stages call these live. One shared `_phrase_matches()` helper used by
  every check (word-boundary match for single-word phrases so "engineer"
  doesn't match inside "engineering", plain substring for multi-word
  phrases). `US_STATE_ABBREVIATIONS`/`US_STATE_FULL_NAMES` are hardcoded
  Python constants (not YAML), matching the `_TECH_JARGON_TERMS`/
  `IRREGULAR_PAST_TENSE_VERBS` precedent in `slop_lint.py`/`bank.py`: a
  fixed 50-state geography list isn't a tunable threshold. `DE` (Delaware)
  is deliberately left out of the state-code set; see D23 addendum 3.
- `tests/test_filter.py`: 40 tests (grew from 23 across two rounds, all
  written before their matching implementation per hard rule 7, all
  passed on the first real implementation attempt once written). Covers
  every function above, including the seniority word-boundary guarantee
  ("Senior"/"Staff" titles explicitly confirmed NOT excluded) and
  `is_us_location`'s remote-short-circuit, comma-gated state-code
  matching, bare-city-name matching, and the empty/garbage-location
  logging path (`classify_location(...) == "ambiguous_unparseable"`
  asserted directly, not just the bool).
- **Final signed-off match-rate numbers against the real db** (3836 jobs
  at signoff time; ai_ml_engineer/software_engineer/data_scientist):
  post-alias-match 83/963/90 (1057 total); minus employment (6), minus
  citizenship (16), minus seniority (18), minus non-US location (158,
  down from an initial 345 before the location-allowlist gap fix) =
  **final 68/776/81 (859 total)**. Verified via 4-set inclusion-exclusion
  on the restricted intersections (`|A∩E|=6, |A∩C|=16, |A∩S|=18,
  |A∩L|=163`): union size 198 both by direct set computation and by the
  signed inclusion-exclusion sum, `1057 - 198 = 859`, matching the
  sequential stage-by-stage result exactly. Two real gaps were caught and
  fixed by checking actual output against real data mid-session, not
  found by the tests: a 205-job hole in the location allowlist (bare
  "San Francisco" alone, no state suffix, was 148 of those jobs) found by
  inspecting what the `"ambiguous_unparseable"` bucket actually contained
  instead of trusting the design, and the ai_ml_engineer/data_scientist
  exclusion-keyword profile mismatch described above. This remains a
  snapshot of what fraction of the current ~15-company stock matches the
  filter logic, not a daily-volume figure (D23 still applies).
- `src/jobengine/sources/greenhouse.py`'s `_strip_html`: rewritten from a
  regex tag-strip to an `html.parser`-based extractor, fixing a real bug
  found while building C2's fixture excerpts (not something this session
  went looking for): every Greenhouse job's `content` field is double-HTML-
  escaped in practice (`&lt;h2&gt;...&lt;/h2&gt;`, no literal tag anywhere),
  and the old code's tag-strip-then-unescape order left that markup
  completely unstripped in `jobs.description`. The new `_strip_html` feeds
  the raw string to an `HTMLParser` subclass that tracks whether it saw a
  genuine tag; if it did (matches the older, purely synthetic "real tag
  plus a separately-escaped literal-text mention" test case), it trusts
  that pass; if it didn't (matches 100% of real Greenhouse data, verified
  directly across all 2,691 jobs), it unescapes once and re-parses,
  correctly revealing and stripping the real markup. No new dependency.
  See the code comment above `_strip_html` for the one known limitation
  (the found-tag heuristic assumes a field is never a genuine mix of both
  patterns; true for 100% of real data checked, not a logical guarantee)
  and D22/D23's addendum in docs/decisions.md for the full writeup. 2 new
  tests added (double-escaped real markup, plain-text passthrough); the
  original synthetic test still passes unchanged.
- **All 2,691 existing Greenhouse rows in `data/jobengine.db` were
  backfilled** with the corrected `description` (recomputed from
  `raw_json`'s original `content`, not from the already-polluted stored
  value) and a matching recomputed `content_hash`. Explicit hard-rule-13
  exception granted and recorded (D22/D23 addendum): scoped to exactly
  those two columns, `first_seen_at`/`last_seen_at`/`closed_at`/`raw_json`
  never in the `UPDATE`'s column list. Verified after running via a full
  before/after snapshot of every column on all 3,846 rows that existed at
  the time, not a sample: exactly 2,691 changed, all `ats='greenhouse'`,
  zero `ats='ashby'` rows touched, zero columns other than the two
  intended ones changed anywhere.
- `src/jobengine/eval/` (new package, `fixtures.py` only so far;
  `harness.py`/`tasks/`/`report.py` from spec 07's module layout are not
  built, that's C1/C3/C4's work, not C2's): `load_human_labels(conn, path)
  -> int`, a pure loader with no scorer/extractor/comparison logic.
  `required_keywords` is one flat list per job in the YAML but
  `human_labels` is keyed `(job_id, profile)` like the rest of this schema
  (`job_analysis`, `keyword_corpus`), so the loader attaches the keyword
  list only to whichever profile(s) have that job's highest relevance
  score, not to every profile a job merely scored above zero on. Upserts
  on the `(job_id, profile)` primary key, so re-running as the fixture
  gets filled in over multiple sittings updates in place rather than
  erroring or duplicating; verified directly, not just by test, running
  the loader twice against the real filled-in file left `human_labels` at
  150 rows both times.
- `tests/fixtures/eval/human_labels.yaml`: the real C2 fixture, 50 real
  JDs. Regenerated once mid-session to swap `description_excerpt` (an
  800-char truncation) for the full JD text under a plain `description`
  field, matched and merged by `job_id` so the 7 labels already filled in
  at that point survived the regeneration (verified programmatically, not
  eyeballed). **Now fully labelled**: all 50 have non-null relevance
  scores for all three profiles, 11 of the 50 have hand-extracted
  `required_keywords` (short of the spec's "~15" target, see Known
  Issues), loaded into the real `human_labels` table, 150 rows. A
  completeness check caught 3 real data-entry typos ("90S"/"0S"/"70S",
  string not int, all on `ai_ml_engineer`, all three consecutive job_ids)
  before they could reach the loader; fixed by hand after the user
  confirmed the intended values.
- `tests/test_eval_fixtures.py`: 6 tests, written before implementation
  per hard rule 7's spirit, all passed on the first real implementation
  attempt (one test-fixture FK issue along the way, the same
  `companies`/`jobs`-seeding gap `test_filter.py` hit earlier, fixed in
  the fixture not the loader). Covers: a filled profile writes correctly,
  an all-null job is skipped entirely (never written as a junk row), null
  `required_keywords` doesn't break anything, keywords attach only to the
  max-relevance profile, a re-run with revised scores updates in place
  rather than duplicating, and a mixed batch only counts labelled
  profiles. Deliberately uses small hand-written YAML fixtures, not the
  real 50-job file, so these test the loader's logic directly rather than
  depending on how much of the real file happens to be labelled at any
  given time.

- `src/jobengine/llm/` (new package, C1): `schemas.py` (`LocalConfig`,
  `RoutingConfig`, `FallbackConfig`, `ApiConfig`, `LLMConfig` pydantic
  models mirroring `config/llm.toml`'s shape, plus `LLMCallResult`, the
  per-call accounting envelope: stage, provider, model, input/output
  tokens, duration_ms, cost_usd, output. This module writes to no table;
  the envelope is returned to whichever stage calls it, and C3/C4 persist
  whichever fields their own table has columns for, per
  specs/00-data-model.md's `job_analysis`/`relevance_scores` column
  lists), `providers/local.py` (`LocalProvider`, wraps
  `ollama.AsyncClient`; `call()` always passes `think=False` and
  `format=schema.model_json_schema()` explicitly on every request, one
  call site, no Modelfile default relied on; accepts an injectable
  `client` kwarg so tests never hit a real network, same DI pattern
  `sources/greenhouse.py` already uses for `httpx.MockTransport`),
  `providers/anthropic.py` (`AnthropicProvider`, guard-only, see D25 in
  docs/decisions.md: constructor requires an explicit `api_key`, never
  reads `os.environ`, and `call()` always raises `NotImplementedError`,
  since no stage in spec 05's routing table uses it), `router.py`
  (`load_config()` reads `config/llm.toml` via `tomllib` matching
  `render.py`'s `identity.toml` precedent, expanding `${OLLAMA_BASE_URL}`
  by hand and raising a clear `RuntimeError` if unset rather than
  computing a fallback; `get_provider()` is the billing guard's second,
  independent layer, refusing `"api"`-tier construction unless
  `config.llm.api.enabled` and an explicit `api_key` were both given to
  that call; `call()` applies the configured fallback (`skip`/`fail`)
  only around a constructed provider's `.call()`, never around
  `get_provider()` itself, so a refused Anthropic construction always
  raises regardless of the stage's fallback setting), and `check.py`
  (`uv run python -m jobengine.llm.check`, per-stage provider/
  reachability/latency, exits non-zero if any stage's provider would
  resolve to a constructed `AnthropicProvider` under the loaded config).
  All of `router.py`/`providers/*.py`'s public calls are `async def`
  (matching `sources/greenhouse.py`/`ashby.py`'s precedent for I/O-bound
  leaf functions meant to be awaited by a caller or driven via
  `asyncio.run()` in tests, not `sources/sync.py`'s pattern of a sync
  top-level function wrapping `asyncio.run()` internally; `check.py`'s
  `main()` is the one place that wraps with `asyncio.run()`, since it's
  the actual CLI entry point). No new dependency: `ollama` was already in
  `pyproject.toml`, unused until this session.
- `config/llm.toml`: new, mirrors spec 05's TOML block exactly
  (`[llm.local]`, `[llm.routing]`, `[llm.fallback]`) plus a `[llm.api]
  enabled = false` section spec 05's example block doesn't show but the
  billing guard needs something to check; no API key in this file, ever.
- `tests/test_llm_local_provider.py` (7 tests): `think=False` present on
  every call, `format=` carries the schema's JSON schema, `options.num_ctx`
  matches the configured context window, and the returned envelope has
  `cost_usd == 0.0` with real token counts from the (faked) response.
- `tests/test_llm_router.py` (13 tests): `load_config()`'s env-var
  expansion and its clear-error-on-missing-var path (against a real
  written-to-`tmp_path` `llm.toml`, not just in-memory config objects);
  `get_provider()`'s guard in all four combinations (local tier always
  works; api tier refused when disabled; api tier refused when enabled but
  no key passed; api tier constructs only with both); a dedicated test
  that sets a real `ANTHROPIC_API_KEY` env var and confirms construction
  is still refused, the literal "nearly impossible to trigger by
  accident" property from CLAUDE.md hard rule 9; `call()`'s skip/fail
  fallback behavior; and that a billing-guard `RuntimeError` from
  `get_provider()` is never swallowed by a stage's `"skip"` fallback.
- `tests/test_llm_check.py` (6 tests): exercises `_check_stage`/`_run`
  directly with a monkeypatched `get_provider`, not a real Ollama server,
  covering refused/reachable/unreachable per-stage outcomes and the
  overall exit-code assertion (0 when no stage would construct
  `AnthropicProvider`, 1 when one would, including the defensive case
  where `get_provider` is monkeypatched to return one despite the default
  config, since that should never happen in practice but `check.py` must
  still catch it if it ever did).
- **`uv run python -m jobengine.llm.check` verified live**, by the user,
  against the real WSL2/Windows Ollama setup: all three stages
  (`relevance`/`extract`/`rephrase`) reachable, exit code 0. Cold-start
  latency 14,945ms on the first call after Ollama loads the model into
  memory, steady-state 600-935ms on repeat calls after that, confirmed by
  3 consecutive clean runs with no per-stage anomaly. See Known Issues for
  why the cold-start number is expected, not a regression signal.

- `src/jobengine/pipeline/extract.py` (new, C3): `ExtractionSchema`
  (`required_keywords`, `preferred_keywords`, `tech_stack`; deliberately
  narrower than `job_analysis`'s 6 LLM-populated columns, see D26 in
  docs/decisions.md, `canonical_title`/`seniority` left `NULL` pending a
  later phase that can validate them), `is_good_quality_jd()` (Lee's
  "has a Requirements/Qualifications section" rule, deterministic regex,
  not an LLM judgment call), `extract_keywords()` (the only place this
  module talks to an LLM, goes through `router.get_provider("extract",
  ...)` directly, never constructs its own `ollama` client, confirmed by
  a test that inspects the module's own source text), and `analyze_job()`
  (the production orchestration function: one LLM call per job regardless
  of matched-profile count, since `required_keywords` doesn't depend on
  profile; fans out to one `job_analysis` row per profile the job matches
  via B3's `matches_profiles()`, and feeds only `required_keywords`,
  never `preferred_keywords`/`tech_stack`, into `keyword_corpus`). The
  extraction prompt (`_EXTRACTION_PROMPT`) went through two real
  iterations this session and was reverted back to the original,
  narrower, named-technology-focused wording; see D26 addenda 1 and 3 for
  the measured evidence both ways. `job_analysis` gained a new
  `CREATE UNIQUE INDEX idx_job_analysis_job_profile ON job_analysis
  (job_id, profile)` in `schema.sql` (additive, applied against the real
  db while the table held zero rows) so `db/models.py`'s new
  `upsert_job_analysis()` can `ON CONFLICT` correctly; a re-run of
  extraction for a job replaces its prior analysis rather than
  accumulating history, matching `relevance_scores`'/`human_labels`'
  convention. Also new in `db/models.py`: `JobAnalysis`/`ModelEval`
  pydantic models, `upsert_keyword_corpus_entry()` (increments
  `occurrences`, `first_seen_at` fixed on insert, `last_seen_at` always
  advances), `insert_model_eval()`.
- `tests/test_extract.py` (13 tests, written before implementation per
  hard rule 7): `think=False` on this call path too (inherited from C1
  but independently tested, not just assumed); one LLM call per job
  regardless of matched-profile count; a job matching zero profiles skips
  the LLM call entirely, not just the persistence; `job_analysis` gets
  one row per matched profile with identical `required_keywords`; a
  re-run upserts rather than duplicates; `keyword_corpus` occurrence
  counts accumulate correctly across two jobs sharing a keyword.
- `src/jobengine/eval/tasks/keyword_extraction.py`, `report.py`,
  `harness.py`, `__main__.py` (new, fleshing out spec 07's module layout,
  previously only `fixtures.py` existed): Task 2 only (Task 1 is C4's
  scope, not wired in yet, an explicit `# TODO C4` marker in
  `harness.py`, not a silent gap). `keyword_extraction.run()` pools
  TP/FP/FN across all labeled jobs (not per-job ratios averaged) and
  calls `jobengine.pipeline.extract.extract_keywords()` directly, the
  exact same call C3's production path uses, deliberately bypassing
  `router.call()`'s fallback wrapper so one bad call doesn't abort the
  other jobs in the eval loop. The predicted set for scoring is
  `required_keywords` UNION `preferred_keywords` on both sides (not
  required-only, and not including `tech_stack`); see D26 addenda 2 for
  why these are two different, non-symmetric calls, both closed, not to
  be re-litigated per job. `report.py`'s `fixture_version` is a sha256 of
  the fixture YAML's own bytes, computed at run time, not a hand-
  maintained version string. CLI: `uv run python -m jobengine.eval
  {run --model <name>, compare}`.
- `tests/test_eval_keyword_extraction.py` (11 tests): a hand-built
  scenario with known TP/FP/FN counts asserting exact precision/recall
  values, not just a threshold check; schema-failure resilience (one bad
  job doesn't abort the other 14); the required/preferred union and the
  tech_stack exclusion, each with a dedicated test; `fixture_version`
  hashing; `model_evals` row shape.
- **`tests/fixtures/eval/human_labels.yaml` is, as of this session, the
  cleanest ground truth this project has had**, per explicit user
  request to fully re-review it. All 11 keyword-labelled jobs (of 50
  total; the fixture's still-11-not-15 shortfall is C2's original,
  already-flagged gap, unchanged this session, see Known Issues) were
  re-derived from scratch: exhaustively pulled from each JD's real
  qualifications-style sections only (Requirements/Minimum requirements/
  Preferred/Nice to Have/"you might thrive if"-type bullets, explicitly
  excluding "what you'll do"/responsibilities text even where it names
  real skills, a deliberate scope boundary, not an oversight, see Known
  Issues for which jobs lost real-looking terms because of it), with an
  inline YAML comment on every term group quoting the exact source
  sentence, human-reviewed against a side-by-side old-vs-new summary
  table before being finalized. Along the way this also caught and fixed
  3 real pre-existing data-quality bugs from the original C2 labeling
  session, independent of anything this session did: `job_id` 2732/2809/
  3267/3283 originally shared one verbatim copy-pasted generic AI/ML
  keyword list (including on a job with nothing to do with ML, "Camera
  Software Engineer, Consumer Devices"), and `job_id` 1705/2545 each had
  invented or copy-pasted terms that don't appear anywhere in their real
  JD text. See D26 in docs/decisions.md for the full history.
- **Real, live model_evals history from this session (21 rows, 7 runs, 3
  metrics each), all `qwen3.5:9b-q4_K_M`/`keyword_extraction`**, tracking
  every fixture/prompt fix in order: 0.079/0.079 (original prompt, buggy
  fixture) -> 0.250/0.158 (atomic-terms prompt fix) -> 0.358/0.279 (fixed
  the 4-job duplicate-list bug) -> 0.530/0.534 (merged required+preferred
  scoring, fixed 2 more data bugs) -> 0.380/0.681 ("non-tech skills"
  prompt variant, same fixture) -> **0.833/0.467 (original prompt,
  against the fully-reviewed fixture, the row that matches the code as
  shipped)** -> 0.612/0.498 ("non-tech skills" variant re-tested against
  the clean fixture, tried and rejected, see D26 addendum 3). **The
  `model_evals` table's most recent row by `run_at` is the rejected
  0.612/0.498 variant, not the 0.833/0.467 shipped state**, since
  `model_evals` is an append-only log with no column marking which row
  matches the current code; flagged in Known Issues so a future
  `compare` doesn't get read as "current" by recency alone.

---

## Known issues and deferred work

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
- B3's filter functions are exercised end to end against the real
  3834-job db only via the one-off scratch scripts run during this
  session (deleted after use, not checked in); there is no CLI entry
  point yet (`uv run python -m jobengine.pipeline.filter ...`) the way
  `registry`/`sync`/`bank`/`slop_lint` each have one. Nothing in TODO.md's
  B3 DoD requires a CLI, so this wasn't built, but downstream stages (C3,
  C4) will need *some* callable surface; revisit when one of them actually
  needs to invoke this from outside a Python import.
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
  fixture: precision 0.833 (passes), recall 0.467 (fails the 0.85 gate
  by a wide margin). Two prompt variants and three real fixture bugs were
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
- **`model_evals`'s most recent row by `run_at` does not match the
  extraction quality actually shipped.** The table is an append-only log
  of every eval run (21 rows, 7 runs, this session), and the very last
  run tried and rejected the "non-tech skills" prompt variant
  (precision 0.612 / recall 0.498) before `extract.py` was reverted back
  to the shipped state (precision 0.833 / recall 0.467, the second-to-
  last run). Nothing in the schema marks which row corresponds to the
  code currently in the repo. `uv run python -m jobengine.eval compare`
  will show the rejected variant's numbers as the newest row; don't read
  "most recent" as "current" without cross-checking `extract.py`'s actual
  prompt text or re-running `eval run` fresh. A future session (or a
  schema column, `is_current` or similar) could fix this properly; not
  done here since it wasn't asked for and the workaround (re-run to get
  a fresh, unambiguous number) is cheap.
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
  numeric Task 2 gate (recall 0.467 vs. 0.85), a deliberate decision, not
  a silent shortfall.** Confirmed by explicit user instruction, with
  reasoning spanning the pipeline's own architecture (human review before
  every send), CLAUDE.md hard rule 2 (under-extraction can't invent
  content, the safe failure direction), and the limits of a static
  fixture eval versus real usage. Recorded as D27 in docs/decisions.md,
  including the revisit conditions and the ordered list of options if
  manual review later shows this matters in practice. TODO.md's C3
  checkbox and the Status table above both reference D27 explicitly
  rather than silently claiming the literal DoD passed.

---

## Session log

(Newest first. Date, task id, what changed, what to do next.)

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
  instead of filter counts. Final real numbers: precision 0.833 (passes
  the 0.70 gate), recall 0.467 (fails the 0.85 gate) against the fully-
  reviewed fixture, on the reverted, better-precision prompt. **C3 marked
  done anyway, per explicit user decision (D27 in docs/decisions.md):
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
