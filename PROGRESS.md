# Progress

**Claude Code: read this file at the start of every session and update it at
the end via `/checkpoint`. Do not rely on memory of previous sessions.**

Last updated: 2026-08-02
Current task: A4b (PDF conversion, specs/03-renderer.md "PDF" section), not started

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
| B1 | ATS clients + registry | not started | |
| B2 | Fetch and diff | not started | |
| B3 | Filters + routing | not started | |
| C1 | LLM router | not started | |
| C2 | Eval fixtures | not started | human task |
| C3 | Keyword extraction | not started | |
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

---

## Session log

(Newest first. Date, task id, what changed, what to do next.)

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
