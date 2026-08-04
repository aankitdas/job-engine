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

- [ ] **A4b. PDF conversion** (`specs/03-renderer.md`, "PDF" section)
  Render .docx, then convert with LibreOffice headless (use the pptx
  skill's wrapper in the sandbox, bare `soffice` hangs). Blocks D2 (PDF
  geometry for front-loading); must land before the rubric phase starts.

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

- [ ] **C4. Relevance pre-filter** (`specs/06-relevance-filter.md`)
  Done: eval Task 1 passes (rho >= 0.70, top-30 overlap >= 0.75).

## Phase D: The rubric

- [ ] **D1. Rubric rules R001-R013** (`specs/08-rubric.md`)
  Done: scoring your current resume against 3 real JDs gives coverage numbers
  you agree with by hand.

- [ ] **D2. Front-loading + line measurement from PDF geometry**
  Done: `rubric explain R002` prints real y-coordinates.

- [ ] **D3. Patch ladder P0-P2** (deterministic only)
  Done: at least one real deficit closes with zero model calls.

- [ ] **D4. Patch tier P3 + bank variant writeback**
  Done: a P3 rephrase passes the linter, keeps its parent bank id, and is
  written back as a variant.

## Phase E: Base resumes

- [ ] **E1. Profile config + `profiles brief`** (`specs/09-base-resumes.md`)
- [ ] **E2. Generate all 3 base resumes** (interactive session, not automated)
  Done: each passes the full rubric at coverage >= 0.80.

## Phase F: Interface

- [ ] **F1. FastAPI review queue**
- [ ] **F2. Metrics dashboard** (funnel, response rate by coverage bucket,
      by time-to-apply, by base resume version)
- [ ] **F3. Telegram notifier**

## Phase G: Apply

- [ ] **G1. Form schema fetch + autonomy gating** (no browser)
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
