# Decision Record

Revision 2.

---

**D1. Query ATS APIs directly instead of scraping aggregators.**
Greenhouse and Ashby publish free unauthenticated JSON. Scraping means
proxies, 429s, and constant breakage for worse data.

**D2. Company slugs are a maintained registry, not a search.**
Neither API supports cross-company search. Curated seed plus bulk harvest,
validated weekly, dead slugs marked rather than retried.
Addendum (B1): `source` is `seed` \| `harvest` \| `manual`, three distinct
provenances, not two; a manually-`add`ed company is not folded into `seed`.
Bulk harvest itself (Common Crawl CDX scan) is deferred, not built; `seed`
+ `add` + `validate` are enough for B1. `registry seed`/`add` insert new
companies only (`INSERT OR IGNORE`) and never touch an existing row, so a
company `validate` has already promoted to `active` cannot be silently
reset to `unverified` by re-running seed.
Addendum (B2): spec 04's "if content_hash changed, record an edit event"
has no backing table anywhere in the 16-table schema; the `runs` table is
a per-sync-run summary (id, stage, counts, errors), not a per-job event
log. Confirmed by asking rather than inventing a table or dropping the
requirement: an edit is a `logging.info()` line plus a count in that
sync run's `runs.counts.edited`, not a new row anywhere. Revisit only if
a durable per-job edit history turns out to be needed downstream (e.g. for
showing "this JD changed since you last looked" in the review queue).

**D3. `first_seen_at` is computed by us.**
Greenhouse `updated_at` is not a post date. Snapshot history cannot be
backfilled, so ingestion ships first.
Addendum (A1): enforced in SQL, not just in the upsert code that computes
it. Both `jobs` and `companies` have a `BEFORE UPDATE` trigger that aborts
any statement changing an already-set `first_seen_at`. The upsert's `DO
UPDATE SET` clause also omits the column, so the trigger is a backstop, not
the only line of defense against a future bug in a raw `UPDATE`.

**D4. SQLite. The spreadsheet is an export, not a system of record.**

**D5. Resume content is data; rendering is deterministic.**
Addendum (A4): confirmed both directions of this hold in `render.py`.
`Education.status` is treated as a literal opaque string the renderer just
prints, e.g. via a tab stop to the right margin; it never computes "Status
- Graduated" vs. a date itself, or does any date math on it. The bank
content decides what displays, the renderer only lays it out. This is also
why `resume/bank/aankit.yaml`'s BTech entry can carry `status: "Sept 2020"`
instead of spec 01's stated 3-year rule ("year if within 3 yrs, else
'Status - Graduated'") without that being a bug: it's the same kind of
personal content call as the other CV-vs-docx conflicts resolved during A2
seeding (BTech end date, citation count, the "October 202" typo), just
expressed directly in the bank's `status` field rather than in PROGRESS.md's
known-issues log. Confirmed by asking; do not "fix" it to match the rule in
a future session that re-reads spec 01 literally.

**D6. The anti-slop rule is a linter, not a prompt instruction.**
Wired as a PostToolUse hook so failures feed back automatically.
Addendum (A3): implemented as `.claude/settings.json`'s `PostToolUse` hook,
matcher `Edit|Write`, command `uv run python -m jobengine.resume.slop_lint
--changed`. `--changed` mode reads the hook's stdin JSON for
`tool_input.file_path` and is a silent no-op (exit 0) for anything outside
`resume/bank/*.yaml`, the only lint target that exists before D4 writes
patched variants. Exit code 2 (errors, or the E999 fatal block) is what
triggers Claude Code's automatic feedback; warnings alone never block, and
the hook deliberately does not pass `--strict`, so the currently-inert
W001/W002 stubs don't nag every edit.

**D7. Per job title, not per application.** [supersedes the old per-job
tailoring design]
Lee states directly that applying fast with a title-customized resume beats
customizing per application. Three base resumes, regenerated monthly. This is
faithful to the methodology and it is also what makes the system free.

**D8. The critic is a deterministic rubric, not an LLM judge.**
Every criterion Lee states is mechanically checkable: keyword coverage,
keyword position on page one, bullet counts, one period, three lines, past
tense, no first person, reverse chronological, typography. A rubric evaluates
these exactly, instantly, and for free. An LLM judge would be slower, cost
money, and have opinions where we want measurements.
Reverse if: we find a quality dimension that matters to callbacks and is
genuinely not computable. Test that against real outcome data, not intuition.

**D9. Patches are a ladder, cheapest first.**
Reorder, then swap, then promote, then rephrase. Most deficits close on free
deterministic selection because the bank is larger than any rendered resume.

**D10. P3 rephrases are written back to the bank as variants.**
The system accumulates working phrasings and calls the model less over time.

**D11. No paid API call in the daily loop.**
Local inference for relevance and extraction, deterministic everything else.
Prose generation happens in interactive sessions covered by the Pro plan.

**D12. Never set `ANTHROPIC_API_KEY` in the shell profile.**
Claude Code prioritizes that key over subscription auth and silently moves
interactive sessions onto metered billing. If an API path is ever needed,
scope the variable to that one process.

**D13. Local is a cost optimization, never a correctness dependency.**
Every stage must be able to run without a GPU. That is what happens when
compute moves to a VPS.

**D14. Constrained decoding over model selection.**
Schema enforcement at the decoder makes malformed JSON impossible, so models
are chosen on judgment quality alone.

**D15. `identity.toml` is locked and read-only.**
Work authorization, EEO, and salary answers are looked up verbatim, never
generated.

**D16. Assisted apply by default, full auto as an earned per-job level.**
Neither ATS exposes candidate-side submission, so submission means browser
automation. Autonomy level is decided deterministically from the form schema,
which both APIs expose before a browser opens.

**D17. Telegram, not WhatsApp.**
WhatsApp Cloud API needs Meta business verification, a dedicated number, and
per-message billing. The Notifier interface keeps it swappable.

**D18. No fabricated experience in outbound files.**
The resume goes out before any "I'll build it later" project exists, and once
the model may invent, no bullet is trustworthy. Gap ledger instead.

**D19. Outreach is capped and hooked.**
Cap 2-3 per week, require a specific hook, human review before send, personal
Gmail.

**D20. Bullet bank keywords are corpus-matching tags, not a promise the exact
word appears in that bullet's sentence.**
Spec 01's rule 10 ("every keyword appears in at least one bullet, or it is
dead weight") reads like a per-bullet text-match check, but that
interpretation fails on the spec's own worked example: `role_bantrly`'s
summary is tagged with FastAPI/Python while Lee's rule requires the summary
sentence itself to stay non-technical. `validate_bank()` does not check rule
10. `coverage_gaps()` does instead, against `keyword_corpus`, once C3
populates it.

**D21. Slop linter's H006 (summary jargon) checks keyword leakage against a
maintained tool list, not "any bank keyword" and not general jargon
judgment.**
Spec 02's H006 text ("flags any token in a configurable jargon list not also
present in a plain-English allowlist") could mean a lot of things. First
implementation treated every keyword a role declares (summary or bullets) as
jargon, modeled on `role_bantrly`'s own summary avoiding FastAPI/Python/LLM.
Running the linter against the real bank, not just synthetic fixtures,
surfaced 9 false positives in roles seeded during A2: cosmology, automation,
optimization, financial services, and similar plain domain nouns are also
tagged as keywords (they do double duty as rule 10's ATS coverage tags), and
a summary is supposed to say them. Narrowed H006 to an explicit
`_TECH_JARGON_TERMS` set in slop_lint.py of actual tool/tech-stack proper
nouns (Python, FastAPI, LLM, Docker, ...), exact match case-insensitive.
This is deliberately a hand-maintained list, not a heuristic. It is also
deliberately not a general "is this jargon-y" judgment call: hard rule 11
already rules out asking a model to grade resume quality, and there is no
deterministic general-purpose jargon detector to fall back on. Update the
list by hand when a new tool lands in the bank; revisit the narrow scope
only if a real jargon leak surfaces through a word that was never in the
list, not by trying to make the check smarter. Confirmed by asking, twice
(once for the keyword-leakage framing, once for the tech-list narrowing).

**D22. `data/jobengine.db` is irreplaceable once B2 is live, not scratch
state.**
Before B2, the db held only what a fresh `seed`/`sync` could regenerate, so
resetting it during a live sanity check was harmless, and happened more
than once during B1 and B2's own sessions ("wiping the db back to empty" /
"DB wiped clean again"), narrated in the moment but never asked about
first. Once B2 landed, `jobs.first_seen_at` encodes real elapsed-time
history (when a posting actually first appeared) that cannot be
reconstructed after the fact; deleting or re-initing the real db destroys
that history silently; nothing in the schema or the CLI would even notice.
Confirmed by asking: any destructive operation (`rm`, `init`, `migrate`, or
equivalent) against the real `data/jobengine.db` path requires asking
first and getting explicit confirmation in that message, no exceptions for
"just a quick check." Exploratory or live-API sanity checks use a scratch
copy or a temp path instead (see hard rule 13 in CLAUDE.md). This reverses
the working assumption every prior session operated under; do not fall
back to the old "reset it, it's just fetched data" habit out of momentum.

**D23. The 300-500/day filter-survivor target (docs/architecture.md stage 2,
TODO.md's B3 line) is deferred, not calibrated against the current
database.**
At B3 planning time the real `jobs` table held 3,834 rows across only 15
companies, all sharing a single `first_seen_at` (2026-08-02), because B2 has
only ever run as one backlog fetch, never as a real day-over-day diff. That
data answers "what fraction of the current stock matches a given title/
location rule" but not "how many new postings survive filters per day": the
former is a snapshot of accumulated backlog across 15 companies, the latter
depends on daily inflow across the eventual 150-300-company seed list (spec
04), a population this data cannot speak to. Picking a concrete daily cap
or tuning filter strictness to hit 300-500 against today's numbers would be
fitting a threshold to the wrong distribution. B3's filters (title-to-profile
routing, location/remote rules, employment type, dedup against
`applications`) are grounded in today's real title/location/department
distributions instead, with thresholds in config, and the survivor cap left
as a generous, non-binding default. Revisit the 300-500 number itself once
(a) at least 5-7 real days of `runs`/`jobs.first_seen_at` history exist, and
(b) the company registry has grown meaningfully past 15. Tracked as an open
TODO.md item, not silently picked. Confirmed by asking (user flagged this
directly rather than letting a session infer a number from the backlog).

**D23 addendum: B3 persists nothing, `filter.py` exposes a pure
`matches_profiles(job)` function.**
The schema has no dedicated "filter survivor" table; `job_analysis` exists
but its other columns (`canonical_title`, `required_keywords`, `tech_stack`,
etc.) belong to C3/D1, not B3. Considered writing bare `(job_id, profile)`
rows into `job_analysis` now, but rejected: `config/filters.yaml`'s alias
lists are actively being tuned against real data as gaps surface (the bare
"Engineer"/"Scientist"/"Researcher" additions this same session moved the
naive match rate from 17.5% to 31.5%), and a persisted snapshot would go
silently stale the moment the config changes again, with nothing to signal
that a `job_analysis` row reflects an old config version. At the current
data volume (3,834 rows) recomputing live costs nothing, so there is no
performance reason to persist either. `filter.py`'s `matches_profiles(job)
-> list[str]` is called live by whichever downstream stage needs it (C3,
C4, the dashboard), not batched into a table. Confirmed by asking; revisit
only if volume grows enough that live recomputation becomes measurably
slow, not preemptively.

**D23 addendum 2: citizenship/clearance is a hard exclude across all
profiles, and B3 does NOT attempt general visa-sponsorship detection.**
`is_citizenship_or_clearance_required(description)` checks JD text for
explicit citizenship/clearance/export-control language ("must be a US
citizen", "security clearance", "ITAR", "export control", "US Person") and
excludes the job outright, independent of `matches_profiles`'s per-profile
routing: a clearance requirement is a hard eligibility mismatch against
`identity.toml`'s F-1 OPT authorization regardless of which profile the
title would otherwise match. Deliberately not paired with a positive
sponsorship-language filter: most JDs never mention sponsorship either
way, so requiring positive language ("we sponsor visas") would silently
exclude real sponsoring companies that simply don't say so, which is worse
than doing nothing. That question (does this company actually sponsor) is
deferred to a separate, later task using DOL LCA disclosure data at the
company-selection/registry layer, not per-job JD text, tracked as
TODO.md's B1-followup. Confirmed by asking.

**D23 addendum 3: seniority and US-location are both hard excludes across
all profiles, added after a visual sample check, not planned upfront.**
`is_above_target_seniority(title)` excludes any title containing
"manager"/"director"/"head of"/"vp"/"vice president"/"chief"
(word-boundary), no override list: unlike "forward deployed" needing
"software" as an escape hatch, no title shape exists where a management/
executive title should still count as an IC target role. Caught a Pinterest
"Manager II, Machine Learning Engineering" posting slipping through in a
random 30-title sample the user asked for specifically to eyeball fit, not
from a spec requirement; the same sample also caught "AI Success Engineer"
(customer-facing, not core software) and "User Researcher, AI Evaluations"
(UX research, not ML), both fixed via `exclusion_keywords` on their
respective profiles rather than a new mechanism.

`is_us_location(job)` is a hard remote-OR-US requirement, not an exclusion
list like the others: `is_remote(job)` passes regardless of location text
(remote-anywhere vs. remote-US-only isn't distinguishable from the ATS
data available, a known limitation, not solved here); otherwise
`location_raw` must match a US signal (state abbreviation only when
comma-prefixed, to avoid "OR"/"IN" colliding with English conjunctions;
full state names; a handful of bare major-city names found by actually
checking what a first pass left in the "ambiguous" bucket rather than
assuming the state-code rules were enough, since "San Francisco" alone,
with no state suffix, turned out to be 148 real jobs). Delaware ("DE") is
deliberately excluded from the state-code list: it collides with
Germany's ISO country code, which appears for real in this data ("Berlin,
DE"); no genuine Delaware posting exists in the dataset today (checked
directly), so this costs zero real recall now. A `location_raw` value that
matches neither a US nor a recognized non-US signal (garbage like "N/A",
"LOCATION", "AMER") is excluded but distinguishable via
`classify_location()`'s `"ambiguous_unparseable"` return value, logged
rather than silently defaulted either direction. All of this confirmed by
asking, iteratively, as each gap surfaced from real data rather than
designed in one pass upfront.

**D22/D23 addendum: explicit hard-rule-13 exception granted for a scoped
`description`/`content_hash` backfill on all 2,691 Greenhouse rows.**
D22 and hard rule 13 in CLAUDE.md require asking first, with explicit
confirmation in that message, before any destructive or state-resetting
write to the real `data/jobengine.db`. This was exactly that: asked
first, confirmed explicitly, and scoped tightly before touching anything.

Root cause: `greenhouse.py`'s `_strip_html` had an ordering bug (tags
stripped before entities were unescaped) that left every Greenhouse job's
stored `description` containing raw HTML markup instead of plain text,
discovered while building C2's eval fixture excerpts, not something this
session went looking for. Fixed with an `html.parser`-based extractor (see
the code comment above `_strip_html` in `greenhouse.py` for the full
design and its one known limitation). Two new tests
(`test_greenhouse_strips_double_escaped_real_markup`,
`test_greenhouse_plain_text_content_passes_through_unchanged`) added
alongside the existing literal-escaped-text test, which still passes
unchanged.

The backfill itself: `UPDATE jobs SET description = ?, content_hash = ?
WHERE id = ?` for all 2,691 Greenhouse rows, `content_hash` recomputed
from the newly-cleaned `description` via the same `sha256` convention
`sync.py`'s `_content_hash` already uses, so the next sync's edit
detection compares against the corrected baseline instead of flooding
every Greenhouse job as "edited" on its next fetch. New values were
computed from `raw_json`'s original `content` field, not from the
already-polluted stored `description`, to avoid compounding whatever
damage the old bug had already done. A 3-4 sample before/after diff
(short, long, and one with nested `<h4>`/`<ul>`/`<li>` list structure) was
shown and confirmed correct before the full run.

Why this qualifies for the exception D22 anticipates: `first_seen_at`,
`last_seen_at`, `closed_at`, and `raw_json` were not in the `UPDATE`'s
column list at all, so none of the elapsed-time history D22 exists to
protect was ever at risk by construction, not just by care. Verified
after running, not just assumed: full before/after snapshot of every
column on all 3,846 rows (not a sample) confirmed exactly 2,691 rows
changed, all with `ats='greenhouse'`, zero `ats='ashby'` rows touched at
all, and zero columns other than `description`/`content_hash` changed on
any row. A local backup copy of the pre-backfill db was also kept in the
scratchpad directory as an extra safety net, separate from the real path.

**D24. C2's eval fixture attaches `required_keywords` to the
max-relevance profile(s) only, not to every profile a job matches.**
`tests/fixtures/eval/human_labels.yaml` asks the human labeller for one
flat `required_keywords` list per job, but `human_labels` is keyed
`(job_id, profile)`, same as `job_analysis` and `keyword_corpus`
elsewhere in this schema: keywords are a per-profile concept everywhere
else they appear. Rather than duplicate the same keyword list onto every
profile row for a job regardless of fit, or force the labeller into
per-profile keyword lists (more labelling burden for no clear benefit,
since a JD's required keywords don't change based on which profile is
asking), `load_human_labels()` computes each job's highest relevance
score across the three profiles and attaches keywords only to whichever
profile(s) tie for that maximum. A keyword list only makes sense in the
context of the profile the JD actually matches; attaching it to a
near-zero-relevance profile row would be meaningless. Confirmed by
verifying real data supports this: on the 11 real keyword-annotated jobs,
max relevance ranges 50-100 (mean 83.3), vs. 0-30 (mean 3.4) on the 39
without, so the correlation this design assumes actually holds.
