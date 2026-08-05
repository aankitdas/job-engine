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
