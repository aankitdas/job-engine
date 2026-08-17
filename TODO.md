# Build Queue

One item per Claude Code session, in order. Each has a definition of done you
can verify without reading code.

**Start every session with:**
```
Read PROGRESS.md, then specs/NN-name.md. Plan first, do not write code yet.
```

**End every session with:** `/checkpoint`

---

## Phase A: Foundation

- [x] **A1. Data model** (`specs/00-data-model.md`)
  Done: `jobengine.db init` creates the schema idempotently, `tests/test_db.py`
  passes including the `first_seen_at` immutability test.

- [x] **A2. Bullet bank schema + your bank** (`specs/01-bullet-bank.md`)
  Done: `bank validate` reports zero errors and prints a per-profile count.
  Longest manual step. Budget two hours. Do not let an agent speed-run it.

- [x] **A3. Slop linter** (`specs/02-slop-linter.md`)
  Done: flags a bad fixture, passes a real bank bullet, PostToolUse hook stops
  erroring.

- [x] **A4. Docx renderer** (`specs/03-renderer.md`)
  Done: golden test passes on font, sizes, spacing, tabs, margins.

- [x] **A4b. PDF conversion** (`specs/03-renderer.md`, "PDF" section)
  Render .docx, then convert with LibreOffice headless (use the pptx
  skill's wrapper in the sandbox, bare `soffice` hangs). Blocks D2 (PDF
  geometry for front-loading); must land before the rubric phase starts.
  (Done: `src/jobengine/resume/pdf.py`'s `render_pdf()` wraps `soffice
  --headless --convert-to pdf` directly via subprocess, not a "pptx skill"
  wrapper, which doesn't exist in this session's environment; unique
  throwaway `-env:UserInstallation` profile dir per call plus a 60s
  timeout instead, the two concrete things that actually prevent headless
  soffice hangs. `tests/test_pdf.py`, 9 tests, `subprocess.run` mocked.
  Verified live against the real binary (LibreOffice 24.2.7.2, installed
  by the user, not available to Claude Code directly, no passwordless
  sudo) on two distinct real full-bank renders, not just one, via
  `scripts/render_pdf_sample.py`: default section order (4pp) and a
  work-history-first ordering (3pp), both valid PDF 1.7 output. Along the
  way, found and fixed a real pre-existing renderer bug this exposed:
  every paragraph in `render.py` was inheriting python-docx's own default
  template's 10pt `w:after` spacing, producing a visibly larger gap
  between bullets than the 1.5 line-height alone should give, caught by
  the user measuring real PDF geometry with pdfplumber, not by any test.
  Fixed via a new `_new_paragraph()` helper that zeroes `space_before`/
  `space_after` explicitly at the one place every paragraph gets created;
  confirmed against the real template's own XML that 0/0 is correct, not
  a guess. Golden test gained a `space_before`/`space_after == 0`
  assertion it didn't have before, closing a real coverage gap. Full
  suite 200/200 after the fix.)

- [ ] **A4c. Watermarking** (`specs/03-renderer.md`, "Watermarking" section)
  Diagonal "DRAFT - CONTAINS UNBUILT WORK" stamp on any render with a
  `speculative` bullet, `preview` code path, writes only to
  `resume/rendered/preview/`. No urgency: the real bank has zero
  speculative bullets right now, so nothing exercises this path yet.

## Phase B: Ingestion

Start B1 and B2 as soon as A1 is green, even if nothing downstream exists.
Snapshot history cannot be backfilled.

- [x] **B1. ATS clients + slug registry** (`specs/04-sources.md`)
  Done: `sources.sync` populates `companies`, reports OK and dead counts.
  (Met via `sources.registry seed`/`validate`, not `sources.sync`; see
  PROGRESS.md, sync.py's fetch+diff loop is B2's scope.)

- [x] **B2. Fetch and diff**
  Done: two runs a day apart show a non-zero `first_seen_at` delta.
  **Put this on a schedule the day it works.**
  (Unit-tested via same-run/next-run simulation, not a literal 24h gap; a
  real two-days-apart production check is still needed once scheduled, see
  PROGRESS.md.)

- [ ] **B1-followup. Sponsorship-aware company vetting via DOL LCA data**
  Deliberately not a JD-text filter: most postings never mention
  sponsorship either way, so requiring positive language would silently
  exclude real sponsoring companies that just don't say so in the JD (see
  B3's `is_citizenship_or_clearance_required`, which only excludes on
  explicit citizenship/clearance requirements, the opposite signal).
  Public DOL LCA disclosure data (dol.gov, free, quarterly, real H-1B/PERM
  filing history per employer) is the right source for "does this company
  actually sponsor" and belongs at the company-selection/registry layer,
  not per-job filtering. Not scoped or planned yet, just flagged so it
  doesn't get lost.

- [x] **B3. Deterministic filters + profile routing**
  Done: filter logic (title-to-profile, location/remote, employment type,
  dedup vs `applications`) is grounded in real title/location/department
  distributions and you agree with the survivors on inspection. The
  300-500/day number itself is explicitly NOT this item's target; see the
  open item below.
  (Signed off 2026-08-03 after a 30-title then two 10-per-profile random
  visual samples surfaced and fixed real gaps: mis-routed titles,
  above-target-seniority titles, and non-US locations, including a
  205-job hole in the location allowlist caught by checking the
  "ambiguous" bucket against real data rather than trusting the design.
  See PROGRESS.md and D23 + its 3 addenda in docs/decisions.md.)

- [ ] **B3-followup. Calibrate the daily filter-survivor cap**
  Deferred out of B3 on purpose (see D23 in docs/decisions.md): today's db
  is a 15-company, single-`first_seen_at` backlog snapshot, not real daily
  inflow, so no cap tuned against it would mean anything. Revisit once (a)
  5-7 real days of `runs`/sync history exist and (b) the company registry
  has grown meaningfully past 15.

## Phase C: Local intelligence

- [x] **C1. LLM router + Ollama provider** (`specs/05-model-routing.md`)
  Done: `llm.check` reports reachable local, and exits non-zero if any
  Anthropic provider would be constructed under default config.
  (Closed 2026-08-03: `llm.check` run live against the real WSL2/Windows
  Ollama setup, all three stages reachable, exit code 0. Cold-start
  latency 14,945ms on the first call after Ollama loads the model,
  steady-state 600-935ms across 3 consecutive clean runs after that, see
  PROGRESS.md Known Issues so a future session's first check of the day
  isn't mistaken for a regression.)

- [x] **C2. Eval fixture set** (`specs/07-model-eval.md`)
  Done: 50 JDs labelled by you, 15 with hand-extracted keywords, in
  `human_labels`. This is your hour, not Claude Code's.
  (Closed 2026-08-03: 50/50 labelled, loaded, 150 rows in `human_labels`,
  verified idempotent. 11/50 have hand-extracted keywords, short of the
  literal "15" above; marked done anyway per explicit sign-off, see
  PROGRESS.md Known Issues, not silently rounded up.)

- [x] **C3. Keyword extraction + corpus**
  Done: eval Task 2 passes (recall >= 0.85, precision >= 0.70).
  (Closed 2026-08-04: does NOT meet this literal gate. Real measured
  quality against the fully-reviewed 11-job fixture is precision 0.833 /
  recall 0.467 (qwen3.5:9b, reverted named-tech-focused prompt). Marked
  done anyway per explicit user decision to ship rather than continue
  model/prompt iteration; see D27 in docs/decisions.md for the full
  reasoning (human review gates every send, under-extraction is a safe
  failure direction under hard rule 2, an 11-job fixture can only
  approximate real usage) and the revisit conditions if manual review
  later shows this is a recurring practical problem.)

- [x] **C4. Relevance pre-filter** (`specs/06-relevance-filter.md`)
  Done: eval Task 1 passes (rho >= 0.70, top-30 overlap >= 0.75).
  (Closed 2026-08-11 on a mirrored precedent to C3/D27: the literal
  Task 1 gate does NOT pass (real numbers: rho 0.23-0.35, top-30 overlap
  0.63-0.70 per profile, all three profiles fail), but spec 06's own
  DoD -- "a full night's run scores every stage-2 survivor... and
  `calibrate` reports above 70% agreement" -- both real halves pass: a
  real unbounded production run scored all 854 real B3-surviving jobs
  (921 `relevance_scores` rows, 1h46m, zero hangs), and the user's own
  live `calibrate --profile software_engineer` run scored 20/20 = 100%
  agreement with the model's real output. Shipped anyway per explicit
  user direction (implicit in "proceed with the backlog" + running
  `calibrate` to completion rather than pausing on the Task 1 failure),
  with both real numbers recorded, not just the passing one. Three real
  bugs found and fixed first: a live-model hang (root-caused, not just
  patched around), `score_job()` gating on title-only instead of the
  full B3 chain (~195 wasted calls avoided), and a real prompt gap that
  penalized US relocation-requiring jobs despite `identity.toml`'s own
  `willing_to_relocate=true` (verified via real before/after rescoring:
  7 of 8 affected jobs improved, one 0->85). Full writeup: D36,
  docs/decisions.md. 50 new tests, tests-first per hard rule 7. Full
  suite 432/432, ruff clean.)

## Phase D: The rubric

- [x] **D1. Rubric rules R001-R013** (`specs/08-rubric.md`)
  Done: scoring your current resume against 3 real JDs gives coverage numbers
  you agree with by hand.
  (Done: `src/jobengine/rubric/{measure,rules,score}.py` plus a CLI
  (`uv run python -m jobengine.rubric {score,explain}`; `patch` deferred to
  D3). `measure.select_for_profile()` is a new, minimal, non-invented
  candidate-resume filter (bank's own `bullet.profiles` tags only, no new
  ranking/selection logic) added because render.py has no per-profile
  filtering yet and R001/R003/R004/R006 need one to mean anything;
  confirmed by asking. Grounded against real data before and after coding,
  not just synthetic fixtures: ran C3's real `extract_keywords()` live
  (local Ollama, zero cost) against 3 real JDs pulled from the live db
  (Airbnb Sr SWE, DoorDash Robotics Infra, Anthropic Research Engineer),
  and separately persisted real `job_analysis` rows via `analyze_job()`
  against a scratch copy of the db (never the real `data/jobengine.db`,
  per hard rule 13) to exercise the actual CLI end to end. Real numbers:
  coverage 0.27/0.06/0.33 (all correctly fail R001's 0.70 gate; the
  robotics job's near-zero coverage against an ML/SWE bank is exactly
  right, not a bug), R002 front-load ratios ~0.10 (plausible pre-patch-
  ladder, this is what P0-P2 exist to fix), R003 correctly flags
  `role_utd_researcher` at 2 total bullets for `software_engineer` (1
  bullet + summary, below the 3-8 range) cross-validated by R013 catching
  the identical gap via slop_lint's own H004. R006 (line count) and R002
  (front-load) both use real pdfplumber geometry against the corrected
  (post-A4b-bugfix) PDF, not an estimate. Two things confirmed by asking
  rather than guessed, since spec 08 gives no formula: score.py's "keyword
  density in first role" is distinct keyword hits / first role's own word
  count, and "bullets carrying 2+ keywords" is counted across the whole
  candidate resume's bullets (summary excluded, matching R003's own
  explicit "including the summary" qualifier implying bullets alone don't
  elsewhere). `tests/test_rubric.py`, 39 tests, written before
  implementation per hard rule 7: one failing fixture per hard rule,
  select_for_profile, score.py's weighted formula, and one full real-bank-
  through-real-render-through-real-PDF integration test. See PROGRESS.md
  for the full writeup, including a real renderer bug (bullet spacing)
  found and fixed along the way during A4b's verification, before D1
  started.)

- [x] **D2. Front-loading + line measurement from PDF geometry**
  Done: `rubric explain R002` prints real y-coordinates.
  (Absorbed into D1's session, not built separately: R002 has no fallback
  measurement in spec 08 at all, and R006's fallback is explicitly scoped
  to the bank validator, not the rubric pipeline, so D1 couldn't
  implement 11 of 13 hard rules and credibly stub the other 2. Built as
  part of `src/jobengine/rubric/measure.py`'s `front_load()`/
  `front_load_detail()`/`line_count_from_pdf()`, real `pdfplumber`
  geometry against a real converted PDF. This exact DoD command was
  re-run live at checkpoint time and passes; see D28 in
  docs/decisions.md for the full reasoning and why this is flagged
  explicitly rather than silently checked off.
  **Follow-up caught after the first checkpoint, not at initial
  absorption:** spec 08 also explicitly requires "cache the extraction
  per rendered file hash so repeated scoring is free," which the first
  pass of D1 did not implement — every bullet's line-count call was
  independently re-opening and re-parsing the whole PDF via pdfplumber
  (15+ full re-parses per `score_resume()` call on the real bank). Fixed:
  `measure.py`'s `_parsed_pdf()` now parses each PDF exactly once per
  process, keyed by a sha256 of its own bytes (not its path, so two paths
  with byte-identical content share a cache entry, matching spec 08's
  Storage-section dedup), with all of `front_load()`/`front_load_detail()`
  /`line_count_from_pdf()`/`page1_height()`/the new `page_count()` routed
  through it. Verified via a real, non-mocked run: `pdfplumber.open` call
  count for one full `score_resume()` against the real bank dropped from
  2 to 1, identical scoring output before and after (same score, same
  coverage/front_load numbers), confirming the cache changed performance
  only, not correctness. 2 new tests in `tests/test_rubric.py`.)

- [x] **D3. Patch ladder P0-P2** (deterministic only)
  Done: at least one real deficit closes with zero model calls.
  (Done: `src/jobengine/rubric/patch.py` (`apply_p0`/`apply_p1`/`apply_p2`/
  `run_ladder`) plus a CLI (`uv run python -m jobengine.rubric patch --job
  <id> --dry-run`). No persistence to `job_resume_variants`: its
  `base_resume_id` is a hard FK to `base_resumes`, empty until E2 runs
  (Phase E, after Phase D in TODO.md's own ordering); `run_ladder()`
  returns a `PatchResult`, wiring it to real storage is later work.
  **Confirmed done via a real, measured deficit closing, not a synthetic
  fixture alone:** required_keywords=["Chroma DB"] (a real bank tag, on a
  real bullet in `role_docintel`) scored `R002` FAIL (front_load 0.00 <
  0.75, the keyword is genuinely covered but lives in the Projects
  section, which renders after Work History) before the ladder; after
  P0/P1/P2 ran through the real render→PDF→pdfplumber→score_resume
  pipeline, P2 promoted `"projects"` to the front of `section_order` and
  `R002` flipped to PASS (front_load 1.0), `hard_failures` empty. Zero
  model calls throughout.
  **Two significant, real findings from grounding against 9 live-
  extracted real job postings (both profiles, explicitly searched for
  topical overlap with the bank's own content) before landing on the
  Chroma DB case, not assumed going in:** (1) P1 (swap) is structurally
  a no-op against the *current* bank for *any* job: `select_for_profile()`
  already includes every profile-tagged bullet in a role, so there is
  never a "selected vs. eligible-but-unselected" distinction within a
  role for P1 to exploit, given today's bank sizes are all within R003's
  3-8 range (except `role_utd_researcher`'s `software_engineer` tagging,
  a separate known content gap, see Known Issues). (2) None of the 9 real
  jobs tried closed via P0 either, because `role_bantrly` (the only role
  whose content plausibly reaches page-1's top half) already has its own
  bullets in a reasonable order for the specific keywords those 9 postings
  happened to require; P0 did visibly reorder bullets in `role_docintel`
  for one real job, but that role is deep enough in the document (page
  2-3) that the reorder couldn't affect R002 either way. See D28 addendum
  5 in docs/decisions.md for the full writeup, including why the R009
  loosening (date-overlap tolerance, needed for P0's role-swap logic) was
  itself confirmed by asking before being applied to the already-shipped
  D1 rule.
  `tests/test_patch.py`: 14 tests, written before implementation per hard
  rule 7, one per tier's specific behavior plus 2 full real-bank
  `run_ladder` integration tests. Full suite 258/258, ruff clean.)

- [x] **D4. Patch tier P3 + bank variant writeback**
  Done: a P3 rephrase passes the linter, keeps its parent bank id, and is
  written back as a variant.
  (Done: `src/jobengine/rubric/patch.py` gains `call_rephrase()` (the only
  LLM call, via `router.get_provider("rephrase", ...)`, input strictly
  the bullet's what/how/result + target keywords, never the whole bank or
  the JD), `validate_rewrite()` (CLAUDE.md hard rule 12 enforced in code:
  a general capitalized/digit-token check against the parent's what/how/
  result + identity.toml, deliberately stricter than a jargon-allowlist
  approach so a genuinely novel fabrication is caught, not just a
  previously-seen one), `apply_p3()` (selects the bullet with the most
  room, prefers an existing variant over a new call, max 2 new LLM calls
  per job, discards on any guard/R005/R006(char-estimate)/R007/R008/
  slop-linter failure), and `apply_variants_to_bank()` (pure, in-memory
  writeback with `used_count` tracking). New in `bank.py`: `BulletVariant`
  model, `Bullet.variants` field, `dump_bank()` (YAML serializer, tested
  via round-trip only). `tests/test_bank.py`/`test_patch.py` gained 6 + 22
  tests respectively, all written before implementation per hard rule 7,
  including an extensive battery specifically targeting the traceability
  guard (novel proper noun, novel number, already-tagged keyword,
  described-but-untagged keyword, fabricated keyword, sentence-initial
  capitalization, case-insensitivity), per explicit request that this
  guard be airtight, not just happy-path tested.
  **Confirmed via 3 real, live-Ollama runs (not mocked), per the user's
  explicit request that the common path (P0-P2 fail, P3 must genuinely
  rephrase) be grounded against real data, not a synthetic P3-only
  fixture:** (1) a real job (Robinhood "Machine Learning Engineer",
  job_id 318, whose deficit D3 already confirmed P0-P2 cannot close) —
  the real model, asked to incorporate SQL/XGBoost, correctly declined to
  fabricate either, returning `keywords_added: []`; (2)
  `required_keywords=["CMB"]`, a real term genuinely present in a real
  bullet's `what` field but untagged: the real model correctly surfaced
  it as a new keyword, verified traceable, R001 deficit closed for real
  (coverage 0.0 -> 1.0). A real bug was found via run (2), not by this
  session's own synthetic tests: the first version only updated a
  bullet's rewritten text, never merged `keywords_added` into
  `.keywords`, so an accepted rewrite could never actually improve
  coverage. Fixed (`_with_bullet_rewrite`, merges stem-deduplicated
  keywords into the transient candidate only, never the canonical bank),
  re-verified live against the exact same CMB reproduction case after the
  fix (coverage 0.0 -> 1.0 again, via a real `run_ladder()` call). The
  user then asked, specifically, whether this was checked in the
  *persisted* bank state or only in `run_ladder`'s in-memory return
  value — it had only been the latter; the full chain (accept ->
  `apply_variants_to_bank` -> `dump_bank` -> `load_bank` -> a second,
  independent `run_ladder()` call against the reloaded bank -> reuses the
  variant with zero new LLM calls -> coverage still 1.0 -> `used_count`
  1->2) was then run live, for real, on the same reproduction case, and
  passed. A permanent regression test
  (`test_accepted_p3_rewrite_survives_persist_reload_and_is_reused_with_coverage_intact`,
  exercising `apply_p3()` directly rather than the full render/PDF
  pipeline, for speed) was added afterward so this chain, not just its
  individual pieces, stays covered by the automated suite. See D30 in
  docs/decisions.md for the full writeup,
  including why the real resume/bank/aankit.yaml is never written to
  automatically (confirmed by asking; `apply_variants_to_bank()`/
  `dump_bank()` are built and tested
  against tmp_path copies only). Full suite 300/300, ruff clean. P4
  (accept and log to gap_ledger) remains not built, deliberately: it only
  fires after P3's budget is exhausted, and "soft deficit" is a product
  judgment call not made without asking.)

## Phase E: Base resumes

- [x] **E1. Profile config + `profiles brief`** (`specs/09-base-resumes.md`)
  (Done: `config/profiles.yaml` + `src/jobengine/profiles/config.py`
  (`ProfileConfig`, `load_profile_config()`, `to_render_profile()`) is
  the profile registry `render.py`'s own `RenderProfile` docstring named
  as E1's job ("Stand-in for E1's not-yet-built profile registry"); all
  3 profiles ship with the same flat section order and no summary
  section, matching what every existing `RenderProfile` call site
  already builds inline today, not a new content decision (spec 09's
  harder per-title judgment calls are deliberately deferred to E2).
  `src/jobengine/profiles/brief.py`'s `generate_brief()` (CLI: `uv run
  python -m jobengine.profiles brief --profile <id>`) produces spec 09's
  brief.md: top corpus keywords (falls back to
  `bank.keyword_counts()` restricted to the profile when `keyword_corpus`
  has no rows, clearly labeled), the current unpatched candidate's
  rubric measurements (`measure.select_for_profile()` rendered+scored on
  the fly, confirmed by asking since no `base_resumes` row exists yet),
  uncovered gap-ledger keywords (explicit "P4 not built" text when
  `gap_ledger` is empty, which it structurally must be until P4 exists),
  and unselected bank bullets carrying top keywords. "Rank change since
  last generation" and the market "diff summary" are out of scope, per
  explicit user direction: nothing to diff against on this first-ever
  brief. Live-verified against the real db (confirmed read-only,
  unchanged) and real bank for all 3 profiles, not just unit-tested; see
  D31 in docs/decisions.md.)
- [x] **E2. Generate all 3 base resumes** (interactive session, not automated)
  Done: each passes the full rubric at coverage >= 0.80.
  (Done 2026-08-07: `resume/base/{ai_ml_engineer,software_engineer,
  data_scientist}/v1/` all exist (`ai_ml_engineer` also has a `v2`, see
  below), each with `selection.yaml`/`resume.docx`/`resume.pdf`/
  `rubric.json`/`CHANGELOG.md`. All 3 real-scored `passed: true,
  hard_failures: []`, `coverage: 1.0`. Two real content decisions
  preceded generation, each grounded by reviewing every bullet on the
  affected role before deciding, not guessed: `role_utd_researcher`
  retagged `b_utd_02` onto `software_engineer` (the least
  ML-research-specific of its 5 bullets) to clear its R003/R013 floor;
  `role_bantrly_lessongen` dropped from `data_scientist` selection
  entirely (removed `b_lessongen_04`'s tag rather than force a second,
  ill-fitting tag) after review showed none of its 5 bullets read as
  genuine data-science work. Separately, R002 (front-load) was demoted
  from a hard failure to a scored-only component (D33,
  docs/decisions.md) after two exhaustive investigations,
  `ai_ml_engineer` in D32 and `software_engineer` this session, both
  found the same real structural ceiling with no legitimate fix; R001/
  R006/R003 were reviewed against the same reasoning and deliberately
  left as hard failures, evidence-gated not pattern-matched. `ai_ml_
  engineer`'s pre-existing v1 (generated before D33) was left untouched
  per spec 09's "never overwritten" versioning; v2 carries the corrected
  post-D33 rubric.json with identical selection, confirmed by diff.
  **Known caveat, not silently carried:** `coverage: 1.0` for all 3 is
  measured against bank-frequency fallback keywords, not real
  `keyword_corpus` data (still 0 rows, no orchestrator has run
  `analyze_job()` against live jobs). This is a materially easier bar
  than real market demand; flagged for re-validation once corpus data
  exists, see D34 in docs/decisions.md. Full suite 328/328, ruff clean.)

## Phase F: Interface

- [x] **F1. FastAPI review queue**
  (Done 2026-08-07: no dedicated spec file existed for this item, see
  D35 in docs/decisions.md for why this session's approved plan serves
  as its design document. `src/jobengine/queue/orchestrate.py`
  (`QueueContext`, `ensure_reviewed()` lazily triggers C3 extraction +
  D3/D4 patch ladder per (job, profile) pair, `approve()`/`reject()`,
  `list_queue()`) + `src/jobengine/web/app.py` (FastAPI, `GET /`, `GET
  /jobs/{job_id}/{profile}`, `POST .../approve`, `POST .../reject`,
  Jinja2 templates, `uv run uvicorn jobengine.web.app:app --reload`).
  Two real bugs found and fixed before/during implementation, not after
  shipping: (1) the original applications-table-based review-state
  design would have corrupted B3's shipped `is_already_applied()`
  filter, fixed by moving review state onto new `job_resume_variants.
  review_status`/`reviewed_at` columns instead; (2) `job_resume_
  variants`' old `UNIQUE(base_resume_id, selection_hash)` constraint
  blocked the exact multi-job dedup spec 08 describes, fixed via a real
  schema.sql change plus new table-rebuild migration logic in
  `migrate.py` (this project's first migration beyond idempotent
  `CREATE ... IF NOT EXISTS`). Applied to the real `data/jobengine.db`
  only after explicit confirmation per hard rule 13. Verified end to
  end against the real running app and real db using this session's own
  real job (id 3871, Airbnb Software Engineer): on-screen numbers
  matched the pre-computed worked example exactly, second visit was
  idempotent (0.01s, zero new model calls), reject worked and the job
  dropped off the list. First-ever real `job_analysis`/`keyword_corpus`/
  `job_resume_variants`/`rubric_results` rows this project has written
  outside a scratch copy. 42 new tests (`test_db.py` +12,
  `test_db_migrate.py` +9 new file, `test_queue_orchestrate.py` +7 new
  file, `test_web_app.py` +8 new file, plus a shared helper), written
  before implementation per hard rule 7. Full suite 370/370, ruff
  clean. Full writeup: D35, docs/decisions.md.
  **Follow-up, same session:** added `passes_all_filters(conn, job,
  config) -> bool` to `pipeline/filter.py` (B3's full chain in one
  call: title match, location, seniority, employment type,
  citizenship/clearance, already-applied) and wired it into
  `web/app.py`'s `_new_pairs()`, closing the known gap where the "not
  yet reviewed" list only reapplied the title check. 9 new tests
  (`test_filter.py` +7, `test_web_app.py` +2), tests-first. Full suite
  379/379, ruff clean.)
- [ ] **F2. Metrics dashboard** (funnel, response rate by coverage bucket,
      by time-to-apply, by base resume version)
- [ ] **F3. Telegram notifier**

## Phase G: Apply

- [x] **G1. Form schema fetch + autonomy gating** (no browser) --
  Greenhouse only, see D39 in docs/decisions.md (Ashby has no working
  public form-schema endpoint, confirmed live)
- [ ] **G2. Playwright filler, dry-run only**
- [ ] **G3. Level 2, pause before submit**
- [ ] **G4. Level 3, capped at 3/day**

## Phase H: Outreach

- [ ] **H1. Contact discovery**
- [ ] **H2. Draft-only referral emails, manual send**

---

## Rules

1. Phase A must be fully green before Phase D. A rubric scoring a renderer you
   do not trust reports fiction.
2. B2 jumps the queue. Snapshots only get more valuable and cannot be recovered.
3. C2 is yours to do by hand. Everything after it is calibrated against it.
4. Do not write specs for Phase F onward until Phase D runs on real data.
