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

**D25. C1's Anthropic guard is two independent layers, and
`AnthropicProvider.call()` is a permanent stub that always raises
`NotImplementedError`, not a real client.** CLAUDE.md hard rule 9 says an
accidental paid call must be nearly impossible, not merely discouraged, and
spec 05's routing table has no stage that routes to `"api"` today (the
monthly base-resume stage uses interactive Claude Code directly, not this
router). Layer one: `providers/anthropic.py`'s `AnthropicProvider.__init__`
requires an explicit `api_key` argument and the module never reads
`os.environ` anywhere, so there is no code path in that file that could
pick up a stray `ANTHROPIC_API_KEY`. Layer two: `router.get_provider()`
separately refuses to construct it unless `config.llm.api.enabled is True`
**and** a caller passes `api_key` explicitly to that specific function
call; `router.py` also never reads `os.environ` for a key. The two guards
are deliberately redundant, not layered for defense-in-depth alone: either
one alone would already stop the default config from ever constructing the
provider, confirmed by
`test_get_provider_never_reads_anthropic_api_key_from_environment` in
`tests/test_llm_router.py`, which sets `ANTHROPIC_API_KEY` in the test
environment and confirms construction is still refused.

Since no stage needs it yet, `AnthropicProvider.call()` was not
implemented at all beyond the guard scaffolding: it always raises
`NotImplementedError` with a message pointing back at hard rule 9 ("stop
and ask"). `ApiConfig` in `schemas.py` also only has `enabled: bool`, no
model name or other real config, since none of that has been decided.
Not confirmed by asking as its own question this session (the two
`AskUserQuestion` exchanges before coding covered the missing-env-var
behavior and live-vs-mocked verification, not this); this follows directly
from hard rule 9's own literal wording and spec 05's routing table having
zero `"api"` stages, so it wasn't treated as a separate ambiguity worth
interrupting for. Revisit only when a real stage is deliberately added
that needs a paid call, which per hard rule 9 requires stopping and asking
first, not a design this module should silently grow toward.

**D26. C3's Task 2 eval scores against required_keywords UNION
preferred_keywords, not required_keywords alone; the required/preferred
split stays in `ExtractionSchema` for the pipeline's own use but is not a
scoring boundary in the eval.** Originally scored required_keywords only,
matching spec 07's literal wording ("precision and recall against your
hand-extracted lists") and the fixture's single `required_keywords`
field. Live-run investigation of a genuine failure (qwen3.5:9b scored
precision 0.358 / recall 0.279 against the 11 real labeled jobs, both far
under the 0.70/0.85 gates) surfaced the concrete case that forced this
change: `job_id` 2246 (Stripe, Staff SWE API Platform)'s own JD text
splits into "Minimum requirements" and "Preferred qualifications"
sections, and the original hand label put `on-call`/`incident
response`/`serverless` in `required_keywords` even though the JD's own
structure places them under Preferred. The model correctly extracted
them, just filed them under `preferred_keywords`, and a required-only
comparison scored that as three false negatives. Different real JDs
structure their qualifications sections inconsistently (two tiers, three
tiers, no explicit split at all), so a strict required-vs-preferred
scoring boundary was measuring section-header inconsistency across
postings, not extraction quality. `tech_stack` stays excluded from the
predicted set: it is scoped to "every tool named anywhere in the
posting" (broader than any qualifications section), so including it
would inflate false positives against a label that was never meant to
cover background-prose mentions.

Re-reviewing the 11 labeled jobs under the simpler rule (union of
required- and preferred-style qualification content, exhaustively listed,
still excluding a JD's genuine bonus/"Nice to have" tier where one exists
separately from its main preferred section) surfaced two more real,
pre-existing data-quality bugs in `tests/fixtures/eval/human_labels.yaml`,
independent of the required/preferred issue and predating this session:
`job_id` 1705 (DoorDash robotics infrastructure) had invented
profile-category terms (`data scientist`, `engineering manager`,
`machine learning`) that appear nowhere in that JD's actual text, and
`job_id` 2545 (Anthropic, Research Engineer/Knowledge Team, an
information-retrieval/RAG role) had a generic Anthropic-safety-flavored
keyword list (`RLHF`, `RLAIF`, `constitutional AI`, `AI ethics`, ...)
copy-pasted in, none of which appear in that specific posting either.
Both fixed the same way as the 4-job duplicate-list bug caught earlier
this session (see the D22/D23 addendum above): by reading each real JD
directly and re-deriving the list from its actual text, not guessed.
Confirmed by asking before re-scoring: the user explicitly requested
Claude re-extract these by hand rather than doing it themselves. `job_id`
2246 was left unchanged (its content was already correct, only the
scoring boundary was wrong).

**D26 addendum 1: `_EXTRACTION_PROMPT`'s "Correct" examples now include a
non-technology skill/practice term, not named tools only.** Isolated
testing (a synthetic JD snippet, not the real fixture, tested first per
explicit request) found the model was dropping legitimate required
skills like `technical consulting` and `solutions architecture` outright,
while extracting `distributed systems`/`API design` from an identically-
shaped "N+ years of X, Y, Z" sentence right next to it. This ruled out
the original hypothesis (years-of-experience instruction swallowing the
whole clause) and pointed at a narrower one instead: the model was
implicitly narrowing "keyword" to mean "named tool," dropping or
misfiling role/discipline terms that aren't a specific technology.
Fixed by adding `"technical consulting"`, `"solutions architecture"`,
`"incident response"`, `"financial risk modeling"` alongside
`"Python"`/`"Kubernetes"`/`"AWS"` in the prompt's own "Correct" list,
plus an explicit line distinguishing "non-technical" (a valid keyword)
from "generic/personal trait" (not one, e.g. "communication skills").
Confirmed on the same synthetic snippet before touching the real
fixture, then spot-checked against two real jobs: `job_id` 3267 improved
on both precision and recall (TP 1->3, FN 5->3); `job_id` 2246 improved
on precision only, its other 6 missing keywords (`api design`,
`abstractions`, `frameworks`, `client libraries`, `infrastructure`,
`on-call`) are a different, still-open gap this fix does not touch.
**Net pooled effect across all 11 jobs was a real trade, not a clean
win**: recall rose substantially (0.534 -> 0.681, TP 62->79, FN 54->37)
but precision fell (0.530 -> 0.380, FP 55->129) by more than recall
gained, because loosening "keyword = named tool only" made the model
more liberal broadly, not only for the specific terms the fix targeted.
Reported to the user as a mixed result, not overstated as a win; left
as-is pending the user's direction on whether to tighten precision back
up or accept the trade and move on.

**D26 addendum 2: `tech_stack` exclusion from Task 2 scoring is final,
not a per-job judgment call, and the reasoning is not symmetric with the
required/preferred merge above.** required_keywords and
preferred_keywords are the *same scope* (both qualification-framed for
the role), just split inconsistently by the model, which is why merging
them was safe. `tech_stack` is a *different scope* by its own schema
definition ("every tool named anywhere in the posting," not
"qualifications for this role"), so merging it in would conflate two
genuinely different categories, not just paper over another unreliable
split. Quantified before deciding, not asserted: `job_id` 3283's real
`tech_stack` output has 27 items, of which exactly 2
(`sensor drivers`, `video encode`) are legitimate misfiled required
skills; the other 25 are implementation-detail nouns from the "what
you'll do" bullets (`power sequencing`, `capture scripts`, `debugging
utilities`, the company name, ...) that no reasonable hand label would
ever call a required keyword. Of that job's 7 real misses, only those 2
trace to tech_stack; the other 5 are genuine gaps. Including all of
`tech_stack` would recover a small, bounded number of true positives per
job at the cost of a much larger volume of real false positives, the
opposite of the required/preferred merge's risk profile. Accepted as a
known, bounded source of recall drag rather than fixed by widening the
scoring: the model occasionally filing a genuinely-required skill under
`tech_stack` instead of `required`/`preferred` is a prompt-clarity gap,
same category as addendum 1 above, not a scoring-boundary problem.
Revisit with a targeted prompt fix (not a scoring change) only if this
turns out to matter at a scale beyond the 2-item case observed here.

**D26 addendum 3: `_EXTRACTION_PROMPT` keeps the original, narrower
named-tech-focused wording. The "non-tech skills count too" variant from
addendum 1 was tried, measured against a clean ground truth, and
reverted — this closes the prompt-iteration question with real evidence,
not left open.** All of addendum 1's fixture issues (the 4-job duplicate-
list bug, `job_id` 1705/2545's invented/copy-pasted terms, the
required/preferred merge, and finally a fully exhaustive, per-job,
source-quoted re-review of all 11 labeled jobs, human-reviewed) are now
resolved; `tests/fixtures/eval/human_labels.yaml` is the cleanest ground
truth this project has had. Both prompt variants were re-run against this
same stable fixture, back to back, with nothing else changed, specifically
to settle addendum 1's still-open question with an apples-to-apples
comparison:

| | Original prompt (named tech only) | "non-tech skills" variant |
|---|---|---|
| TP / FP / FN | 105 / 21 / 120 | 112 / 71 / 113 |
| Precision | **0.833** (passes the >=0.70 gate) | 0.612 (fails) |
| Recall | 0.467 | 0.498 |
| schema_validity_rate | 1.000 | 1.000 |

The variant's extra permissiveness barely moved recall (+7 TP out of 120
misses, +0.031) while tripling false positives (21 -> 71), dropping
precision out of a passing gate. This is a materially worse trade-off
than addendum 1's own measurement against the pre-cleanup fixture (there,
the same variant moved recall 0.534 -> 0.681 for a comparable precision
cost) — evidence that the variant's apparent win earlier in the session
was partly an artifact of a noisier, less exhaustive ground truth, not a
stable property of the prompt itself. Reverted to the original wording,
kept for its outright-better precision and comparable recall. Neither
variant clears Task 2's bar (recall 0.467-0.498 against a 0.85 gate, on
this now much larger and more exhaustive 225-term label set); the
remaining gap is a real recall shortfall against genuinely exhaustive
ground truth, not a scoring-boundary or fixture-quality artifact, and
that reframes what "next" means for C3: further prompt micro-iteration on
this same axis has demonstrably diminishing (here, negative) returns, so
the next real lever is a different candidate model (spec 07's list:
`granite4:8b`, `qwen3:8b`, `mistral:7b-v0.3`), not another prompt tweak.

**D27. C3 ships with qwen3.5:9b's real measured extraction quality
against the fully-reviewed 11-job `human_labels.yaml` fixture, which
does not meet spec 07's original Task 2 gates (recall >= 0.85,
precision >= 0.70). This is a deliberate decision to stop iterating and
ship, not a silent miss of the DoD.**

**Quality is a range, not a single number, and this decision was updated
once already to reflect that, not left citing one lucky (or unlucky)
sample.** The shipped prompt/fixture/model combination was run 4 times
back to back with nothing else changed, to check whether the first
number was representative; `LocalProvider` pins `think=False` but not
`temperature`/`seed`, so real LLM sampling variance shows up run to run:

| Run | Precision | Recall |
|---|---|---|
| 1 | 0.833 | 0.467 |
| 2 | 0.849 | 0.351 |
| 3 | 0.858 | 0.431 |
| 4 | 0.835 | 0.382 |
| **Range** | 0.833-0.858 | 0.351-0.467 |
| **Mean** | **0.844** | **0.408** |

The variance is real but doesn't change the qualitative conclusion:
precision clears its 0.70 gate in all 4 runs (range comfortably above
the bar), and recall misses its 0.85 gate in all 4 runs, never within
0.38 of it even at its best sample. `model_evals` holds all 10 real
`keyword_extraction` runs from this session (30 rows, 3 metrics each);
the most recent row by `run_at` is always the latest live sample of the
actual shipped state, not a stale or rejected prompt variant, since this
table is queried directly (`uv run python -m jobengine.eval compare`)
rather than reconstructed from this paragraph.
See D26 addendum 3 for the full model/prompt-iteration record this
decision follows from — two prompt variants and three real
fixture-quality bugs were tried and measured before concluding further
iteration on this axis has diminishing returns.

Three reasons, not one, support shipping rather than continuing to chase
the numeric gate:

(a) **Every resume this pipeline produces goes through human review
before anything is sent** (`docs/architecture.md`'s pipeline, stage 8,
"review, manual, Telegram + web," strictly before stage 9, "apply, by
autonomy level"). Extraction errors are caught downstream by a human
before they can cause harm, not silently acted on. This is structurally
different from, say, a rubric bug that could silently mis-score a
resume with no human in the loop before submission.

(b) **Recall gaps are under-extraction, and under-extraction cannot
produce invented content**, only a less-optimally-tailored resume (a
real bank bullet that could have been surfaced for a match doesn't get
selected/promoted). This is the safe failure direction given CLAUDE.md
hard rule 2 ("Never invent resume content... Uncovered JD keywords go to
the gap ledger, not into a new bullet") and the schema's own gap_ledger
table, which exists specifically to log uncovered keywords rather than
fabricate coverage for them. A false-positive-heavy failure mode
(hallucinated keywords driving fabricated bullet content) would be a much
harder call to ship on; recall-heavy failure is not that.

(c) **An 11-job synthetic fixture, however carefully hand-reviewed, is
still an approximation.** Real-world usage against live daily job
postings, followed by real manual review of the resumes it produces, is
the only way to find out whether qwen3.5:9b's actual extraction quality
is a practical problem or not; a static fixture eval can bound the
question but can't settle it.

**Revisit only if manual review of real pipeline output reveals
extraction quality as a recurring practical issue**, not preemptively.
At that point the options, in the order they should be tried: (1) the
next candidate model in spec 07's list (`granite4:8b`, then `qwen3:8b`,
then `mistral:7b-v0.3`) against the same fixture and, more importantly,
against real recurring failures observed in review; (2) a cheap paid API
call specifically for the extraction stage only — flagged explicitly as
breaking the zero-cost daily-loop design this whole project is built
around (`docs/architecture.md`: "no paid API call in the daily loop";
CLAUDE.md hard rule 9: "the daily pipeline is zero-cost by design... if
you believe a stage needs a paid call, stop and ask"), so this option
requires deliberately stopping and asking, never a default fallback;
(3) accepting current quality as sufficient, which is already this
decision's starting position and may simply get re-confirmed. Confirmed
by asking; this is the user's call, not inferred from a general
"good enough" heuristic.

---

**D28. D1's rubric absorbed D2's scope, because R002/R006 can't be real
hard rules without real PDF geometry.**
TODO.md lists D2 ("Front-loading + line measurement from PDF geometry")
as a separate build-queue item after D1 ("Rubric rules R001-R013, the
deterministic scorer, not the patch ladder yet"). While grounding D1's
plan against real data before writing code, it became clear this split
doesn't actually work: R002 (front-loading) has no fallback measurement
in spec 08 at all, and R006's (line-count) only fallback is explicitly
scoped to "the bank validator can run without a render," not the rubric
pipeline itself ("Use option 1 [PDF] in the pipeline"). A rubric that
implements 11 of 13 hard rules and stubs the other 2 isn't a rubric you
can trust, so `src/jobengine/rubric/measure.py`'s `front_load()`,
`front_load_detail()`, and `line_count_from_pdf()` were built as part of
D1, using real `pdfplumber` geometry against a real converted PDF, not
placeholder logic deferred to a later session.

Confirmed after the fact, not before: D2's own literal definition of
done ("`rubric explain R002` prints real y-coordinates") was re-run live
against real data at checkpoint time and passes today. D2 is marked done
in TODO.md as a consequence of D1's implementation, not because a
separate D2 session happened. Flagging this explicitly rather than
silently checking D2's box: a future session searching for "where D2's
work landed" should look in D1's rubric module, not expect a separate
D2-labeled diff or session.

**D28 addendum: two rubric formulas confirmed by asking, since spec 08
gives no formula for either.** Spec 08's Score table names five weighted
components but only spells out a method for the first (coverage) and
implicitly the last (page penalty); "keyword density in the first role"
(15 pts) and "bullets carrying two or more keywords" (10 pts) have no
stated formula. Confirmed rather than guessed: density is distinct
target-keyword stem hits (summary text included) divided by the first
role's own word count, a true density, not a coverage ratio scoped to
the first role. The multi-keyword-bullet fraction is computed across the
whole candidate resume's bullets, explicitly excluding the per-role
summary from both the numerator and denominator: R003's own rule text
("3 to 8 bullets **including the summary**") spells out that qualifier
exactly when it wants the summary counted as a bullet, which reads as
this component's "bullets" meaning real bullets only when the qualifier
is absent.

**D28 addendum 2: `select_for_profile()` is a new, deliberately minimal
candidate-resume filter, confirmed by asking, not an extension of D3's
scope.** `render.py` had no notion of "which bullets belong to profile
X's resume" before this session; it renders every bullet in the bank
regardless of the bullet's own `profiles` tag. Checking real per-profile
bullet counts during D1's grounding pass surfaced that several roles
drop to zero bullets under a naive tag filter (e.g. `role_sei` for both
`ai_ml_engineer` and `software_engineer`), which R003 (a hard rule) would
then fail on trivially for every job scored against that profile. Rather
than leave R001/R002/R003/R004/R006 untestable against anything
realistic, `measure.select_for_profile(bank, profile)` filters each
role's bullets to the ones already tagged for that profile and drops any
role left with zero bullets entirely. This reuses only bank data that
already exists (`bullet.profiles`, populated since A2); it does not rank,
score, or choose among competing bullets, which is what makes it
distinct from D3's patch ladder (P0 reorders, P1 swaps between
candidates, P2 promotes) rather than a preview of it. Confirmed by
asking before building.

**D28 addendum 3: two known, deliberate scope reductions in `measure.py`,
not oversights.** (1) `measure.stem()` is suffix-only normalization
("case and stem normalized" per spec 08's literal text), not a real
stemmer and not synonym-aware; grounding against real C3 extraction
output during this session showed it correctly missing a match between
"LLM" and "Large Language Models" (different stems, same real-world
skill). Left as-is, matching D27's own precedent for extraction-quality
gaps: revisit only if this recurs as a practical problem in real usage,
not preemptively. (2) `measure.measure_typography()` (R010) checks font,
sizes, margins, tab-stop position, and justify-alignment universally
across every paragraph, but checks line-spacing only against the valid
pair (1.15 header / 1.5 body), not positionally validated per exact
section the way `render.py`'s own golden test does at construction time.
R010's job in the rubric is catching drift in an already-rendered
document (a bad manual edit, a future P3 rewrite), not re-proving what
the golden test already proves at render time, so this scope reduction
was a deliberate call, not a gap found by accident.

**D28 addendum 4: the first pass of D1/D2's absorption missed a real,
explicit spec 08 requirement, caught at checkpoint review rather than
during implementation.** Spec 08's Front-loading measurement section
says "cache the extraction per rendered file hash so repeated scoring is
free"; the initial `measure.py` had no caching at all, meaning
`rules.score_resume()`'s per-bullet call to `line_count_from_pdf()`
independently re-opened and fully re-parsed the whole PDF via
`pdfplumber` for every bullet and summary in the candidate resume (15+
full re-parses for one `score_resume()` call against the real bank).
This was found by the user asking, at the next checkpoint, whether D2
had any remaining work beyond the literal DoD line, not by an initial
oversight check during D1 itself — worth recording as a reminder that a
narrow DoD line passing is not the same as a spec section being fully
implemented. Fixed: `measure._parsed_pdf()` parses a given PDF exactly
once per process, cached by a sha256 of the file's own bytes (not its
path, so two different paths pointing at byte-identical content, e.g.
the Storage section's `job_resume_variants` dedup case, share one cache
entry); `front_load()`, `front_load_detail()`, `line_count_from_pdf()`,
`page1_height()`, and a new `page_count()` all route through it, with a
bounded (32-entry, simple oldest-in eviction, not a true LRU) cache dict
rather than an unbounded one. Verified with a real, non-mocked call
count: `pdfplumber.open` calls for one full `score_resume()` run against
the real bank dropped from 2 (down from what would have been 15+ pre-fix)
to 1, with identical scoring output before and after, confirming the
change affected performance only, not correctness.

---

**D29. D3's patch ladder (P0-P2) confirmed working via a real deficit
closing, and two significant, real limitations of the *current* bank
found while grounding it, not assumed going in.**

`src/jobengine/rubric/patch.py` implements P0 (reorder), P1 (swap), and
P2 (promote) exactly as specified, all deterministic, zero model calls.
`run_ladder()` re-renders and re-scores through D1's real pipeline after
every tier, per spec 08's "every tier re-runs the full rubric afterward."

**The real closure that satisfies D3's DoD:** `required_keywords =
["Chroma DB"]` (a real bank tag, on a real bullet in `role_docintel`, a
project role) scored R002 FAIL before any patching (front_load 0.00 <
0.75: the keyword is genuinely covered, `coverage` is 1.0, but lives in
the Projects section, which renders after Work History in the
`section_order` used throughout this session). After running P0/P1/P2
through the real render → real PDF (A4b) → real pdfplumber geometry →
`score_resume()` pipeline, P2 promoted `"projects"` to the front of
`section_order`, and R002 flipped to PASS (front_load 1.0), with
`hard_failures` empty. This is `["Chroma DB"]` deliberately chosen as a
single real, already-covered-but-poorly-positioned bank keyword, not a
full job's live-extracted `required_keywords` list, after the two
findings below made clear why no organically-sampled real job closed via
the ladder. Confirmed by direct measurement, not asserted: `passed` flips
from `False` to `True`, `hard_failures` from `["R002"]` to `[]`, in the
same process, same code path, same real files.

**Finding 1: P1 (swap) is structurally a no-op against the bank as it
exists today, for any job, not a bug in P1's logic.** `measure.
select_for_profile()` (D28 addendum 2) already includes *every*
profile-tagged bullet in a role; it is an all-or-nothing filter, not a
ranked top-N selection. That means there is never a "selected vs.
eligible-but-currently-unselected" distinction within a role for P1 to
exploit, because nothing is ever held back, for any role, for any
profile, given the bank's current bullet counts (all within R003's 3-8
range except `role_utd_researcher`'s single `software_engineer`-tagged
bullet, a separate known content gap, see Known Issues). Verified
directly: for every role and every profile, the set of profile-tagged
bullets equals the set select_for_profile() returns, with nothing left
over. P1 will start doing real work automatically the day any role
accumulates more profile-tagged bullets than R003's ceiling allows for
that profile; nothing in patch.py needs to change for that to happen.

**Finding 2: across 9 real, live-extracted job postings (both
`ai_ml_engineer` and `software_engineer`, explicitly searched across the
live db for topical overlap with the bank's actual strengths: RAG,
embeddings, speech/audio, document intelligence, not just generic "ML
engineer" titles), none closed a deficit via P0-P2.** Two independent,
well-understood structural reasons, not one: (a) Finding 1 above rules
out P1 entirely; (b) `role_bantrly` is the only role whose content
plausibly reaches page 1's top half (confirmed: a required-keywords list
of just `["embeddings"]`, covered only by that role's 5th and last
bullet, already scored front_load 1.0 *before* any patching at all,
meaning the role's rendered content already sits entirely within the
front-loaded region regardless of internal bullet order), and none of
the 9 real postings' required keywords happened to both (i) exist in the
bank at all and (ii) be positioned sub-optimally *within* that one role.
P0 did visibly reorder two bullets in `role_docintel` for one real
posting (job 467, a real Airbnb LLM fine-tuning role), but `role_docintel`
renders on page 2-3, so no bullet reorder within it can affect R002
either way. This is a real, current-content limitation, not a patch
ladder defect: P0/P2 both fired correctly and did real, verifiable work
the moment a keyword's actual position (Chroma DB, in Projects) gave them
something to fix.

**D29 addendum: R009's date-overlap loosening (measure.
is_reverse_chronological, see its own docstring) was confirmed by asking
before being applied, since it changes the semantics of an already-
shipped, signed-off D1 hard rule, not something to reinterpret silently.**
The original strict start-date-monotonic check meant P0's "sort roles
only if two are concurrent" permission was inert on every pair in the
real bank (no two roles share an exact start month), since even
genuinely overlapping roles (`role_sei` 2021-10 to 2023-08, `role_unl`
2021-05 to 2023-06) have different start dates. Confirmed: redefine a
violation as a role appearing before an earlier, non-overlapping role,
not merely a different start date. Two genuinely overlapping roles may
now appear in either order without failing R009, matching the natural
meaning of "concurrent" in resume-writing. Also confirmed by asking,
separately: P0 does not automatically reorder project roles relative to
each other (they have no R009 constraint at all, but "no constraint"
isn't the same as "any order is fine to reshuffle automatically, with no
review gate, based purely on per-job keyword score"); that kind of
visible reordering stays P2's explicit, coarser "promote" step, per
D3's confirmed scope.

---

**D30. D4's P3 (rephrase) writeback is built and tested but deliberately
not wired to the real resume/bank/aankit.yaml, and the traceability guard
is stricter than spec 08's literal text, both confirmed by asking.**

`apply_variants_to_bank()` (in `src/jobengine/rubric/patch.py`) returns a
new, in-memory `Bank` with accepted P3 rewrites recorded as
`BulletVariant` entries (new `bank.py` model, `used_count` incremented on
reuse); `dump_bank()` (new `bank.py` function) serializes a `Bank` back
to YAML, tested only via round-trip against tmp_path copies, including
the real `resume/bank/aankit.yaml` loaded read-only and dumped to a
tmp_path copy (never the real file). Nothing in this codebase calls
`dump_bank()` against the real file. Confirmed by asking before building
D4 at all: this is the first time anything in this project would
automatically write to a hand-authored source file (A2's own note: "the
longest manual step... do not let an agent speed-run it"), and a generic
YAML dumper reordering keys or reformatting strings would drown a real
content change in unreviewable noise. Persisting a real variant to the
real bank is a separate, deliberate, future action.

**The traceability guard (`validate_rewrite`, CLAUDE.md hard rule 12) is
deliberately stricter than spec 08's literal wording in places, not a
loophole-closing afterthought.** `slop_lint.py`'s `_TECH_JARGON_TERMS` (a
~20-term hand-maintained allowlist) was considered and rejected as the
detection mechanism: it can only catch a fabrication that happens to
already be on that list, not a genuinely novel one, which is exactly the
failure mode hard rule 12 exists to prevent. Implemented instead as a
general token check: any word starting uppercase or any digit run, in
the rewrite, that isn't the bullet's own opening word (always capitalized
by sentence position, never a new claim) and doesn't appear anywhere in
the parent's what/how/result or identity.toml, is rejected. This will
reject some legitimate rewrites a looser check would allow (e.g. a
freshly-coined acronym); over-rejection costs a P3 attempt and is the
safe failure direction per hard rule 2, so this was a deliberate choice,
confirmed by asking, not an oversight.

**A real implementation bug was found and fixed via live grounding
against the real model, not by this session's own synthetic tests.**
The first version of P3's rewrite application (`_with_bullet_text`)
updated only a bullet's `.text` on an accepted rewrite, never merging
`keywords_added` into `.keywords`. A live run against the real bank
(required_keywords=["CMB"], a real term present in `role_utd_researcher`'s
`b_utd_02.what` field but untagged anywhere) showed a real, unmocked
model producing a correctly-guarded, accepted rewrite with
`keywords_added: ["CMB"]` — yet `coverage` stayed 0.0 after acceptance,
because R001's coverage math reads `bullet.keywords`, not `bullet.text`,
and the keyword was never actually added to the working candidate. Fixed
by renaming `_with_bullet_text` to `_with_bullet_rewrite`, now merging
`keywords_added` (stem-deduplicated) into the transient candidate
bullet's `.keywords` alongside the text change; the canonical `full_bank`
passed to `apply_p3` is never touched by this, only the working candidate
used for this specific job's render/score. Re-ran the same live case
after the fix: coverage 0.0 -> 1.0, R001 dropped out of `hard_failures`.
A regression test
(`test_apply_p3_accepted_rewrite_merges_keywords_added_into_the_working_bank`)
was added after the fact, confirmed failing against the pre-fix code and
passing after; flagged here because the bug was caught by real-model
grounding, not by this session's own initial test-writing, worth
remembering as a reason real-data checks earn their keep even after
"tests green."

**Two real live-model runs (real Ollama, not mocked) confirm the whole
P3 mechanism end to end.** (1) `required_keywords` from a real job
(Robinhood "Machine Learning Engineer", job_id 318, whose deficit D3
already confirmed P0-P2 cannot close): the real model, asked to
incorporate "SQL"/"XGBoost", declined to fabricate either and returned a
rewrite with `keywords_added: []`, a plain reorganization of the parent
bullet's own `what` field text; accepted (nothing to reject), but
correctly did not move `coverage` at all, since it added nothing new.
(2) `required_keywords=["CMB"]` (the fix-verifying case above): the real
model correctly surfaced an already-present, genuinely-describable term
as a new keyword tag, verified traceable to the parent's own `what`
field, closing that specific R001 deficit for real. Together these show
the model itself tends to behave safely under this prompt, and the guard
is what makes that reliable and enforceable rather than merely hoped for.

**D30 addendum: the keywords_added fix above was re-verified live, but
initially only against `run_ladder()`'s in-memory return value, not the
persisted bank state — the user caught this gap explicitly and asked for
it to be closed, not just reasserted.** "Re-verified live after the fix"
originally meant: same required_keywords=["CMB"] case, same real model,
confirmed `coverage` 0.0 -> 1.0 in the `PatchResult` returned by a single
`run_ladder()` call. That is real, but it only exercises the transient
working candidate `apply_p3` builds for that one call; it says nothing
about whether `apply_variants_to_bank()`'s output, once actually
persisted via `dump_bank()` and reloaded via `load_bank()`, still carries
the improvement, or whether a second, independent `run_ladder()` call
against that reloaded bank correctly finds and reuses the variant. Ran
the full chain live, for real, on the exact same reproduction case, not
a fresh similar one: (1) real `run_ladder()` call, real Ollama, accepted
rewrite, `coverage` 0.0 -> 1.0 in the return value; (2)
`apply_variants_to_bank()` on the canonical `full_bank` — confirmed the
canonical bullet's own `text`/`keywords` stay unchanged, only a new
`BulletVariant` is appended; (3) `dump_bank()` to a real file on disk
(scratch path, never the real `resume/bank/aankit.yaml`); (4)
`load_bank()` reload, confirmed pydantic-equal to the pre-dump bank; (5)
a **second, independent** `run_ladder()` call using the reloaded
(from-disk) bank as `full_bank` — confirmed it found and reused the
persisted variant (`reused_existing_variant=True`, zero new LLM calls
this time) and `coverage` was 1.0 again, for this separate run; (6)
`used_count` incremented 1 -> 2 on this second, independent use. All six
steps passed on the first real attempt. A permanent regression test,
`test_accepted_p3_rewrite_survives_persist_reload_and_is_reused_with_
coverage_intact` (`tests/test_patch.py`), was added afterward so this
composed chain, not just each step's own separate unit test, stays
covered by the automated suite; it exercises `apply_p3()` directly
rather than the full render/PDF pipeline, for speed, but the sequence of
operations (accept, writeback, persist, reload, reuse, re-verify
coverage) is identical to what the live run exercised.

**D30 second addendum (2026-08-05): the "re-verified live" claims above
were prose only, no captured evidence in this repo. The user asked
directly whether the persisted bank state had actually been checked and
whether a repro had been shown, not just re-asserted; it had not, in
this session's context. Re-ran the whole chain live, for real, with
every intermediate value printed and shown, and that run (not the prose
above) is now the citable evidence.**

Correcting a conflation risk first: **the CMB case is not job_id 318's
own deficit.** Job 318's (Robinhood "Machine Learning Engineer") real
required_keywords, per D3's own live extraction, are terms like
`SQL`/`XGBoost` from its actual JD, the case where the model correctly
declined to fabricate (see the "Two real live-model runs" paragraph
above). `required_keywords=["CMB"]` targets a genuinely different,
unrelated bullet, `role_utd_researcher`'s `b_utd_02`, chosen by
`_select_p3_target` because it has the fewest keywords (2) and shortest
text (118 chars) of any bullet in the real bank, not because of any
connection to job 318. The two cases were run together for convenience
in earlier sessions and should not be cited as the same deficit.

Ran a standalone script (scratch, not part of the automated suite) against
the real `resume/bank/aankit.yaml` (loaded read-only) and real
`identity.toml` (loaded read-only), real Ollama via `OLLAMA_BASE_URL`
(`qwen3.5:9b-q4_K_M`), `required_keywords=["CMB"]`:

1. `measure.coverage(bank, ["CMB"]) == 0.0` before anything runs.
   `_select_p3_target(bank)` selects `role_utd_researcher`/`b_utd_02`,
   `keywords=['data processing', 'large-scale datasets']`, no existing
   variants.
2. Live call returned (raw, schema-parsed): `text="Processed and managed
   1,600 high-resolution CMB simulated maps totaling 24GB across
   multiple train, validation, and test splits to produce a clean,
   reproducible dataset for model training."`, `keywords_added=["CMB"]`,
   `accepted=True`.
3. `validate_rewrite()` re-run explicitly against that output:
   `violations == []`. Every capitalized/numeric token in the rewrite
   (1,600, CMB, 24GB, train/validation/test) traces to the bullet's own
   `what`/`how`/`result`.
4. `apply_variants_to_bank()`: canonical bullet's `.text` and `.keywords`
   confirmed byte-identical to before (`['data processing',
   'large-scale datasets']`); a new `BulletVariant` appended
   (`keywords_added=["CMB"]`, `used_count=1`). **
   `measure.coverage(canonical_with_variant, ["CMB"])` stays `0.0`** —
   this is the precise mechanism, not a bug: `coverage()` reads
   `bullet.keywords`, and a variant is never merged into the canonical
   bullet's own `.keywords`. The improvement lives only on the variant
   and on whatever working candidate a `apply_p3()`/`run_ladder()` call
   actually builds from it, never on the canonical bank directly.
5. `dump_bank()` to a scratch path (never the real `aankit.yaml`),
   `load_bank()` reload, confirmed pydantic-equal to the pre-dump bank.
   A **second, independent** `apply_p3()` call against the reloaded
   (from-disk) bank found and reused the persisted variant
   (`reused_existing_variant=True`, zero new LLM calls this time); the
   working candidate it returned scored `measure.coverage(..., ["CMB"])
   == 1.0`.

Net: `0.0 -> 1.0`, confirmed live, on the working candidate, exactly as
claimed, with the canonical bank's own bullet fields verified untouched
at every step. One thing this particular run did **not** re-check live:
the `used_count` 1->2 increment on a *second* `apply_variants_to_bank()`
call — that increment path remains covered only by the existing
`FakeClient`-based regression test
(`test_accepted_p3_rewrite_survives_persist_reload_and_is_reused_with_
coverage_intact`), not by today's live run. Flagged here rather than
silently folded into "all six steps re-verified," per the same standard
this addendum is itself applying.

---

**D31. E1 (profile registry + `profiles brief`) ships with the top
corpus keywords and current-measurements sections falling back to real
existing code when their real data source is empty, and "profile
config" turned out to be `render.py`'s own stated dependency, not a
tangent.**

Two things anchored E1's scope rather than requiring a guess. First,
`resume/render.py`'s `RenderProfile` dataclass docstring already said
outright: *"Stand-in for E1's not-yet-built profile registry... where
that data ultimately comes from is E1's decision, not render.py's."*
Second, `rules.score_resume()`'s own docstring: *"the caller decides
what 'the current base resume' means, this function just scores it."*
Together these settled what would otherwise have been two separate
open questions (does E1 need to build a profile registry, and what does
"current base resume" mean before any base resume exists) into things
the codebase had already flagged as E1's job specifically, not invented
fresh.

**Profile registry** (`config/profiles.yaml` +
`src/jobengine/profiles/config.py`): one `ProfileConfig` entry per
`bank.KNOWN_PROFILES` value (`display_name`, `section_order`,
`include_summary`, `summary_text`), `to_render_profile()` adapting it to
`render.py`'s `RenderProfile`. All 3 profiles ship with the same flat
`section_order` (`work_history, projects, education, publications`) and
`include_summary: false`, matching what every existing `RenderProfile`
call site (`patch.py`'s `run_ladder()`, `scripts/render_sample.py`,
`scripts/render_pdf_sample.py`) already constructs inline today, not a
new content decision. Spec 09's harder, genuinely per-title judgment
calls (moving education to the bottom, adding a summary section) are
deliberately not decided here: nothing available grounds asserting any
of the 3 profiles needs the exception, and the one summary trigger
otherwise relevant to this user (visa/sponsorship) is already covered by
the contact block's work-authorization line per spec 09 itself.
Confirmed by asking (this session's plan review) rather than guessed;
revisit per-profile at E2 time, when a human is looking at a real
generated resume against a real target title.

**`keyword_corpus` empty-corpus fallback** (`profiles/brief.py`'s
`_top_corpus_keywords()`): falls back to `bank.keyword_counts()` (an
already-existing function, already used by `measure.coverage()`/
`missing_keywords()`) restricted to `measure.select_for_profile(bank,
profile)`'s output, `Counter.most_common(limit)`. The brief output
labels which source produced the list explicitly, so a future E2 session
never mistakes bank-frequency for real market-corpus data. Corrected in
conversation before implementation: the user's initial framing attributed
this gap to C4 (relevance pre-filter) and cited "the same stand-in D1
used for R002" as precedent; neither holds up. `keyword_corpus` is empty
because no daily orchestrator has ever called
`pipeline.extract.analyze_job()` (C3's own output) against real jobs, a
gap already flagged under C3 in PROGRESS.md's Known Issues, unrelated to
C4. And D1 built no bank-frequency stand-in for R002 specifically — R002
has no fallback at all (D28), real PDF geometry only. Checked before
citing either claim as justification for the design, not assumed.

**`gap_ledger` empty-ledger fallback**: renders an explicit "P4 is not
built and no orchestrator has run the patch ladder against real jobs
yet" line rather than a silently blank section. Structurally distinct
from the corpus case, not the same caveat twice: `gap_ledger` cannot
have real rows yet regardless of C3/C4, since nothing writes to it until
P4 exists (deliberately not built, see D4/PROGRESS.md) and something
calls `run_ladder()` against real jobs.

**"Current base resume's rubric measurements" with no `base_resumes`
row yet**: confirmed by asking (AskUserQuestion during this session's
plan review) to render+score `measure.select_for_profile(bank, profile)`
on the fly, exactly the unpatched-candidate shape D1's own grounding
scored, explicitly labeled in the brief output as the on-the-fly
candidate, not a real generated base resume. Scored against the brief's
own top-keywords list (corpus or bank-frequency fallback) as
`required_keywords`: there is no job-specific keyword list at profile
granularity, so the market's own top keywords are the only defensible
thing to measure coverage/front-load against here, a forced choice
rather than an arbitrary one, and it ties the brief's own two sections
together meaningfully (a real live run against `ai_ml_engineer`,
2026-08-05, scored `coverage: 1.0` for exactly this reason: with the
bank-frequency fallback active, the required keywords are by
construction already present in the candidate that carries them).

**Live-verified, not just unit-tested**, per this project's standing
grounding norm: `uv run python -m jobengine.profiles brief --profile
{ai_ml_engineer,software_engineer,data_scientist}` against the real
`data/jobengine.db` (read-only, confirmed unchanged before/after:
`keyword_corpus`/`gap_ledger` still 0 rows, `jobs` still 3882,
`companies` still 15) and real `resume/bank/aankit.yaml` all three
produced real, non-empty markdown: real rubric numbers in the
measurements section (`ai_ml_engineer`: `score 63.27`, `hard_failures:
['R002']`, `front_load 0.5`, `pages 3`) and honest degradation text for
both empty tables, not a crash or a blank brief.

**Not built this session, by explicit scope**: `patch.py`'s
`run_ladder()` and the two render scripts still construct
`RenderProfile` inline rather than loading `config/profiles.yaml`
through the new registry; migrating them wasn't asked for. No CLI
(`__main__.py`) unit test was written either, matching this codebase's
existing convention: no other module's CLI (`bank.py`,
`rubric/__main__.py`) has one, every `main()`/`_cmd_*` here is only ever
exercised by a live manual run, matched rather than introducing a new,
unprecedented pattern for this one module alone.

---

**D32. `ai_ml_engineer`'s base resume ships with R002 as a known,
documented soft-fail (front_load 0.50, needs 0.75), not silently
accepted and not blocked on.**

The first real edit ever made to the hand-authored `resume/bank/
aankit.yaml` (three bullets on `role_bantrly`: `b_bantrly_02`,
`b_bantrly_03`, `b_bantrly_04`, tightened for length while preserving
every fact and every already-tagged keyword) is now live: `bank
validate` reports 0 errors/0 warnings, and `uv run python -m
jobengine.profiles brief --profile ai_ml_engineer` against the real,
edited bank confirms `score 63.40` (up from 63.27), `hard_failures:
['R002']` only (`R003`/`R013` already passed before this edit and still
do), `coverage: 1.0`, `front_load: 0.50`, `pages: 3`.

**The gap was investigated exhaustively before concluding it should
ship as-is, not assumed unfixable.** Live-tested, real-scored (D1's
actual `rules.score_resume()`, not an estimate), against the real bank:
(1) the automatic `run_ladder()` P0-P2 tiers, which left `front_load`
completely unchanged (0.50 -> 0.50) — traced to two separate causes:
`apply_p0`'s role-swap only fires when the later role's aggregate
keyword score beats the earlier one's (`role_bantrly`: 16 vs.
`role_utd_researcher`: 3, so it correctly declines by its own
optimization goal), and `apply_p2` grabs the *first* role matching a
not-yet-front-loaded keyword stem in bank order, hits the non-promotable
`role_utd_researcher` first, and stops there by design, never reaching
the genuinely-promotable project roles. (2) Three manual structural
overrides (promoting `role_utd_researcher` ahead of `role_bantrly`,
legal under R009's date-overlap tolerance; promoting the `projects`
section ahead of `work_history`; both combined) — all three real-scored
*worse* than baseline (0.20 each), because `front_load` is a fixed-space
allocation over a fixed top-half-of-page-1 budget, not a rank order:
every reorder only redistributes which keywords occupy that space, none
create more of it, on a 3-page candidate with more required-keyword
content than fits in half a page. (3) Two content-cut candidates
(dropping `role_ju` entirely: a genuine no-op, 0.50 -> 0.50, since that
role's content was already rendering past page 1 regardless of
position; trimming `role_bantrly` to summary+2 bullets: a real gain to
0.60, but at the cost of `embeddings`, previously passing). (4) A
genuinely fact-preserving line-count trim of `role_bantrly`'s three
non-top-10-keyword bullets (the edit now shipped) recovered only ~18pt
of the ~75pt `cosmology` needed (`y=471.0 -> 452.9`) and the ~21pt still
separating `machine learning` even after that same 18pt gain
(`y=434.7 -> 416.6`), confirmed via the real renderer, not estimated
from character counts. A synthetic, explicitly-not-real-content probe
(prefix-truncating those same three bullets to incomplete sentences)
did cross 0.70, proving the geometry math was sound, but also proving
the honest gap: closing it for real requires cutting actual content,
not just tightening it.

**Every tested path to 0.75 costs more than it's worth, and none was
applied.** The two structural promotions net-lose keywords (0.20 vs.
0.50 baseline). The role-bantrly-to-3-bullets cut nets +1 keyword but
sacrifices `embeddings`. Only the shipped tightening is a clean,
zero-cost win (+small score bump, +2 lines of headroom, zero keywords
lost) — it just isn't, on its own, enough to cross the threshold. No
further cut was applied without being asked; that's a real content
decision (what to drop), not a mechanical one, and belongs to a human
call, not an automated one, same as D3/D4's own repeated confirmations
before touching selection or content.

**This mirrors C3's D27 ship-decision directly, not a new precedent.**
Per hard rule 11, the rubric is deterministic and directional pressure
toward a better resume, not a pass/fail gate a resume must clear before
it can be used: `R001`'s coverage (1.0) is the rule spec 09's own DoD
cites as the real bar ("coverage above 0.80"), comfortably cleared.
`R002`'s specific 0.75 front-load threshold is a proxy for "does a
skimming recruiter see the right keywords fast," not a hard requirement
this resume is unusable without. The score/hard-failure state travels
with every job this resume gets attached to via the review queue (per
spec 09 and Phase F's design), so this soft-fail is visible at the
point someone chooses to send it, not buried. Revisit only if real
application outcomes (once F1's review queue and outcome tracking exist)
show R002 specifically correlating with worse response rates for this
profile, the same evidence bar D27 itself set, not a preemptive
guess.

---

**D33. R002 (front-loading) demoted from a hard failure to a scored-only
component. R001 and R006 reviewed against the same reasoning and
deliberately left as hard failures.**

rules.py's check_r002 is removed from score_resume()'s hard_failures list.
front_load remains exactly as weighted in score.py (25 of 100 points) and
in measurements output; no signal is lost, only the binary gate on top of
an already-continuous measurement.

**Evidence, not symmetry, is why only R002 moves.** Two independent,
exhaustive investigations, on two different profiles, each tried every
legitimate lever (P0-P2 automatic ladder, manual structural promotion,
fact-preserving content trims) and found the same structural ceiling:
front_load is a fixed-space allocation over a fixed top-half-of-page-1
budget, not a rank order, so reorders redistribute which keywords occupy
that space rather than creating more of it. ai_ml_engineer: D32, 0.50
ceiling. software_engineer: this session, 0.40 ceiling, R003/R013 cleared
via a legitimate retag but front_load unmoved. In both cases every tested
path past the ceiling either nets worse (structural promotions) or costs
real content (cutting a passing keyword to buy another).

**Why R002 specifically, and not by pattern-matching on rule shape.**
Reviewed all 13 hard rules for the same "continuous measurement forced
into a threshold" shape R002 has. R001 (coverage) shares it exactly, spec
08 gives it its own continuous scored twin same as R002, and P4's own
spec text ("skip the job entirely if a hard rule other than R001 still
fails") already treats R001 as different-in-kind from the rest of the
hard-failure list. R006 (line count) is architecturally R002's closest
sibling: same pdfplumber-derived geometry, same soft-convention-as-cutoff
shape. Neither is touched here. Both lack what R002 now has: a real,
exhaustive, two-case investigation showing a genuine ceiling with no
legitimate fix, not just a plausible argument by analogy. R001 in
particular carries D27's existing precedent toward strictness
("under-extraction is a safe failure direction") and is the system's only
gate against a resume that doesn't cover the job's keywords at all;
demoting it preemptively would remove real protection on pattern-matching
alone. R003 was also reviewed and rejected as a candidate: it's a bounded
count with no continuous twin in score.py, and its bounds encode a
genuine structural convention (a 1-bullet role looks incomplete, a
12-bullet role looks unedited), not a proxy measurement squeezed into
pass/fail.

Revisit R001 or R006 only if a future case does the same exhaustive-
investigation work this one did for R002 and finds the same kind of real,
unfixable ceiling, not by extending this decision's reasoning alone.

---

**D34. E2's coverage=1.0 across all three profiles is measured against
bank-frequency fallback keywords, not real market demand, and needs
re-validation once corpus data exists.**

All three profiles (ai_ml_engineer, software_engineer, data_scientist)
reached `passed: True, coverage: 1.0` this session via `profiles brief`'s
`_top_corpus_keywords()`. That function's first choice is real
`keyword_corpus` rows (C3's actual extraction output against real JDs);
today it falls back to the bank's own keyword frequency for every
profile, because `keyword_corpus` has zero rows for any profile (no
daily pipeline orchestrator has ever called
`pipeline.extract.analyze_job()` against a real job, a gap already
flagged under C3 and E1 in PROGRESS.md's Known Issues, unchanged by
anything done this session).

**This makes coverage=1.0 an easier bar than it looks, structurally, not
just by chance.** Bank-frequency fallback builds its "required keywords"
list from the same bank the candidate resume is selected from, so a
resume scored this way is being measured against its own vocabulary, not
the market's. Coverage against real corpus keywords, drawn from actual
job postings this profile competes against, is a materially different
and harder bar: a keyword the bank never mentions can't appear in the
bank-frequency top list at all, but it can absolutely appear in a real
JD's top-10.

**Legitimate first pass, not a result to distrust, but not the real
number either.** Every rubric investigation this session (R002's
demotion, the `role_utd_researcher`/`role_bantrly_lessongen` retag and
drop decisions) was grounded in real rendering and real PDF geometry;
none of that is in question. What's specifically unvalidated is only the
keyword list coverage is measured against. E2's spec 09 DoD text
("coverage above 0.80") does not specify against which keyword source,
so this isn't a DoD violation, but it is a gap worth tracking honestly
rather than letting "coverage: 1.0" read as a stronger claim than it is.

Re-validate once C3's extraction orchestrator has run `analyze_job()`
against a real batch of live jobs per profile and `keyword_corpus` has
real rows (the same precondition D31/E1 already flagged as blocking the
brief's "real" mode). Re-run each profile's `profiles brief` at that
point; if coverage drops meaningfully below 0.80 against real corpus
keywords, that's new information this session's numbers could not have
surfaced, not a regression.

---

**D35. F1 (review queue) ships with no dedicated spec file, a lazy
per-job trigger instead of a batch orchestrator, and review state on
`job_resume_variants` rather than `applications` after a real filter
conflict was found and fixed during implementation.**

No `specs/10-*.md` exists for F1: TODO.md's own Rules section deferred
writing Phase F specs until Phase D ran on real data, which it now has,
but nobody had written one when this session started. This plan
(written in Claude Code's plan mode, approved before implementation)
functions as that document; `docs/architecture.md`'s existing stage list
(review as stage 8, after re-score+lint, before apply) was the only
prior design intent and is consistent with what shipped.

**Scope, confirmed by asking, not assumed:** F1 triggers C3 extraction
and the D3/D4 patch ladder itself, lazily, the first time a reviewer
opens a specific (job, profile) pair (`queue/orchestrate.py`'s
`ensure_reviewed()`). No batch/cron orchestrator was built. This was a
real three-way fork (lazy-trigger vs. UI-only assuming a future batch
job vs. building a real batch orchestrator now) resolved via
AskUserQuestion before any code was written, since building the "real"
scheduled version properly would need C4 (relevance pre-filter, not
built) for stage 2.5's ranking cut first.

**A real bug was found and fixed before it ever shipped, not after.**
The initial implementation plan (drafted by a planning sub-agent)
proposed tracking review state (`pending_review`/`approved`/`rejected`)
as rows in the `applications` table. Checked against the actual
`is_already_applied()` implementation
(`src/jobengine/pipeline/filter.py:163`, B3's own shipped filter)
before accepting that design: it treats **any** row in `applications`
for a `job_id` as "already applied," regardless of `status`. Creating an
`applications` row the moment a job entered the queue would have
silently and permanently marked every reviewed-but-not-yet-applied job,
and every rejected one, as "already applied" to any future B3 filter
pass. Fixed before implementation: review state moved onto
`job_resume_variants` itself (`review_status`/`reviewed_at`, new
columns), and `applications` rows are now created **only** on approval,
leaving `is_already_applied()` untouched and correct. A regression test
(`test_creating_a_pending_review_variant_does_not_mark_job_already_applied`,
`tests/test_db.py`) exists specifically so this can't regress silently.

**A second real gap was found by the tests written to prove the fix,
not by inspection alone.** `job_resume_variants`' only prior uniqueness
constraint, `UNIQUE(base_resume_id, selection_hash)` (no `job_id`),
would have rejected a second job's insert outright if its patch ladder
converged on an identical bullet selection to an already-inserted job's
row, contradicting spec 08's own "two jobs... share one rendered file"
intent. The fix (a new `UNIQUE(job_id, profile)` index, matching every
other per-(job,profile) table in the schema, plus dropping the old
table-level constraint entirely so hash-collision across jobs is
possible again) required a genuine SQLite table rebuild for any db that
predates this change, not just an additive `CREATE INDEX`: `migrate.py`
gained real detect-old-shape-and-rebuild logic
(`_rebuild_job_resume_variants_if_needed()`), the first migration this
project has needed beyond idempotent `CREATE ... IF NOT EXISTS`
statements. Verified via a dedicated test file
(`tests/test_db_migrate.py`) that reconstructs the exact pre-migration
table shape via raw SQL and confirms rows survive the rebuild,
`review_status`/`reviewed_at` are added, the old constraint no longer
blocks a shared hash across two jobs, and the new per-(job,profile)
uniqueness still holds. Applied to the real `data/jobengine.db` only
after explicit confirmation (hard rule 13); `job_resume_variants` had 0
real rows at migration time, so the rebuild copied nothing.

**A third real bug, found only by running the real app, not by any
test:** FastAPI runs sync route handlers and sync `Depends()` callables
in a threadpool by default, even for `async def` routes, so a single
shared `sqlite3.Connection` built once at startup gets used from a
different OS thread on every request. `sqlite3.Connection` objects
reject cross-thread use by default (`ProgrammingError`). Fixed by adding
an explicit `check_same_thread` parameter to
`jobengine.db.migrate.connect()` (default `True`, preserving every
other single-threaded caller's existing safety net), with only
`jobengine.web.app` passing `check_same_thread=False`. Documented as
safe for this app's actual single-operator, one-browser usage, not as a
general concurrency guarantee.

**Verified end to end against the real running app and the real db, not
just the automated suite**, using this session's own real worked
example (job_id 3871, Airbnb "Software Engineer, Biztech Client and
Identity", already confirmed to survive B3 for `software_engineer`):
started `uv run uvicorn jobengine.web.app:app` against the real
`data/jobengine.db`, hit `/jobs/3871/software_engineer` live. First
visit: ~22s (matches C1's documented Ollama cold-start latency), real
`analyze_job()` and real `run_ladder()` fired for real, on-screen
numbers matched the plan's own pre-computed worked example exactly
(score 18.98, coverage 0.14, `hard_failures: ['R001']`, all four patch
tiers attempted). Second visit: 0.01s, byte-identical HTML, zero new
model calls, confirming the lazy-trigger idempotency. `POST .../reject`
returned 303, flipped `review_status` to `rejected`, created no
`applications` row (confirming the filter-conflict fix holds for real,
not just in a test), and the job dropped off `GET /`. This is also the
first-ever real `job_analysis`, `keyword_corpus`, and
`job_resume_variants`/`rubric_results` rows this project has ever
written to `data/jobengine.db` outside a scratch copy, closing several
gaps PROGRESS.md's Known Issues had flagged since C3/E1
("no daily orchestrator has ever called `analyze_job()` against real
jobs").

Full suite 370/370 (up from 328), `ruff check`/`format --check` clean.

---

**D36. C4 (relevance pre-filter) ships built, real-production-verified,
and closed against spec 06's own DoD -- but spec 07's Task 1 numeric
eval genuinely fails, alongside a real qualitative pass, and both are
recorded honestly rather than picking the flattering one.**

Planned in Claude Code plan mode per the user's request, grounded before
any code against real data: a live prototype hung 13+ minutes on the
first attempt (root-caused later, see below), a scaled-down real probe
(8 real fixture jobs) gave an honest small-n directional signal (rho
~0.45, explicitly caveated as not the real measurement), and the plan
itself was reviewed against the actual schema (`relevance_scores`
already existed from A1; `config/filters.yaml`'s `daily_cap` already
loaded with zero consumers) before writing a line of implementation.

Built `src/jobengine/pipeline/relevance.py` (`RelevanceSchema`,
`build_profile_card()`/`render_profile_card()`, `score_relevance()`,
`score_job()`, `select_top_n()`/`apply_relevance_cutoff()`, the
`score`/`calibrate` CLI), `db/models.py`'s `RelevanceScore` + 5 helpers,
`config/relevance.yaml` (new: `disqualifier_blocklist`,
`freshness_window_days`, both `null`/deferred per the same D23 reasoning
as `daily_cap`), and `eval/tasks/relevance.py` (Task 1, hand-rolled
Spearman rho, no scipy dependency) wired into the existing eval harness
alongside Task 2. Tests-first throughout per hard rule 7: 50 new tests
(`test_relevance.py` 31, `test_eval_relevance.py` 13, plus `test_db.py`/
`test_filter.py` additions), full suite 432/432, ruff clean.

**Three real bugs found and fixed during this session, each caught by
verification rather than assumed away:**

1. **The original live-prototype hang, root-caused via a controlled
   escalation test, not left as an unresolved risk.** The first prototype
   used a loosely-typed ad hoc schema (`seniority_match: str`, unbounded
   `relevance: int`); re-run with the real shipped `RelevanceSchema`
   (`Literal["under","match","over"]`, `Field(ge=0,le=100)`) at
   escalating sizes up to spec 06's full 6k-char/30-keyword shape
   completed in 5-16s every time, no hang. Conclusion: the looser
   ad hoc grammar was the likely cause, not a systemic Ollama/hardware
   issue. Added an explicit `asyncio.wait_for(..., timeout=config.local.
   timeout_s)` around `score_relevance()`'s call anyway, as defense in
   depth for an unattended ~900-call batch, not because the root cause
   stayed uncertain.

2. **`score_job()` gated only on `matches_profiles()` (title match), not
   the full B3 chain, found via real-number quantification before the
   expensive production run, not discovered mid-run.** A direct count
   against the real db showed 1049 jobs surviving title-match alone vs.
   854 surviving the full `passes_all_filters()` chain -- an unbounded
   run would have wasted ~195 real LLM calls on jobs already disqualified
   by location/seniority/employment-type. Fixed by gating `score_job()`
   on `passes_all_filters()` first (job-level checks), then
   `matches_profiles()` only for the per-profile fan-out. A dedicated
   regression test (`test_score_job_skips_llm_when_title_matches_but_
   other_b3_checks_fail`) added; `_seed_job()`'s test default location
   also had to change from unset (silently `None`, failing every
   B3-location check) to a real US city, since every prior `score_job()`
   test had been implicitly relying on skipping that check entirely.

3. **Relocation-requiring US jobs were scoring low/getting flagged as
   "disqualified" by the model, found via the user's own direct review
   of real scoring output, not caught by any test.** The profile card's
   `location_rules` text only said "on-site outside the US is a
   disqualifier," leaving the model free to independently read a
   same-country relocation requirement (e.g. "must relocate to SF Bay
   Area") as a negative -- despite `identity.toml`'s real, already-true
   `preferences.willing_to_relocate = true`. Fixed by reading that field
   (read-only, hard rule 1) and, when true, explicitly telling the model
   relocating anywhere in the US is acceptable and not a disqualifier.
   Verified by rescoring the same jobs before/after: 7 of 8
   relocation-flagged jobs improved substantially (one 0 -> 85), one
   stayed low for an independently legitimate reason (a genuine skill
   mismatch the model's own `one_line` still names). Explicitly
   distinguished from a related but separate, larger, NOT-built feature
   request (the rendered resume's own contact/location line dynamically
   showing "Relocating to X" per job) -- confirmed with the user this is
   out of scope for C4, saved as its own memory
   (`feature-resume-header-relocation`) for a future session.

**Real production run, not just eval numbers.** After the location fix
was validated on a 100-job bounded sample (39 real scores, sensible
disqualifiers/reasoning, confirmed zero real-db writes on scratch-copy
dry runs beforehand per hard rule 13), ran the full real backlog
unbounded: **921 `relevance_scores` rows across 854 distinct real jobs**,
1h46m wall clock, zero hangs, a real `runs` row recorded
(`stage=relevance`). `software_engineer` avg score 64.0 (n=775),
`data_scientist` 80.5 (n=82), `ai_ml_engineer` 77.5 (n=64). First-ever
real relevance-scoring production data this project has produced.

**Task 1's real numeric eval fails; `calibrate`'s real qualitative check
passes at 100% -- both recorded, neither hidden to make the other look
better.** `uv run python -m jobengine.eval run` against the full 50-job/
150-point fixture: rho 0.23-0.35 per profile (need >= 0.70), top-30
overlap 0.63-0.70 (need >= 0.75) -- Task 1 FAILED, worse than the small-n
planning-time probe suggested (rho ~0.45), a real finding, not
optimistic. Separately, the user ran `calibrate --profile
software_engineer` themselves, live, against real production-scored
jobs: 20/20 = 100% agreement with the model's own scores and reasoning,
spot-checked by hand, clearing spec 06's 70% bar cleanly. This is a
genuine, unresolved tension worth stating plainly: the model's
individual judgments hold up under real human review, but don't
rank-correlate well against the older hand-labeled fixture. Possible
explanations not yet investigated: the fixture's original labels (from
C2, an hour of hand-labeling months earlier under different context) may
themselves be noisier or use different implicit criteria than the user's
in-the-moment calibration judgment; or n=50/profile is genuinely too
small for a stable rho given real score variance. Per TODO.md's literal
C4 "Done:" line (spec 07's Task 1 numbers) and spec 06's own DoD (a full
run + `calibrate` >= 70%), the two bars disagree -- both are recorded
here rather than one being quietly treated as the deciding one; see
PROGRESS.md for how C4 is marked in the status table given this.

Full suite 432/432, `ruff check`/`format --check` clean.
