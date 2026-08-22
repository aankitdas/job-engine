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

**D37. C4 ships closed: Task 1's rho bar (>= 0.70) still fails on all
three profiles after a real multi-fix investigation, but top30_overlap
-- the metric that actually maps to what F1's new relevance floor gate
consumes -- passes on 2 of 3 and is near-passing on the third. Shipped
per the same D27/D36 precedent: real measured numbers on record, not a
manufactured passing gate, with the more decision-relevant metric
called out explicitly rather than letting the failing headline number
stand unchallenged.**

D36 left Task 1 failing (rho 0.23-0.35) with an unresolved tension
against `calibrate`'s 100% agreement, and flagged it as needing
investigation, not a resting point. This session dug into *why*,
verified each hypothesis against real data rather than asserting one,
and fixed three real, distinct bugs along the way:

1. **Determinism (this session's single biggest finding).**
   `LocalProvider.call()` never set `temperature` or `seed` -- Ollama's
   defaults produced real, large score variance on identical calls (job
   2809 swung 0 -> 72 -> 0 across three otherwise-identical relevance
   calls). Fixed by adding `temperature=0.2` (spec 05's stated intent
   for extraction/scoring, never actually wired through) and a fixed
   `seed=42` to `LocalProvider`'s shared `options` dict, affecting all
   three LLM stages (relevance, C3 extraction, D4 rephrase), confirmed
   via the full suite (nothing depended on nondeterminism) and verified
   directly: the same 5 previously-volatile jobs, re-run 3x each after
   the fix, came back with `spread=0` on score, `seniority_match`,
   `disqualifiers`, and `one_line`, word for word, every time. Every
   Task 1 rho measured before this fix (D36's 0.23-0.35 included) was
   partly measuring sampling noise, not just model judgment -- that
   question is now closed, not just patched around.

2. **Fixture ground truth.** Investigating 5 flagged high-human/
   low-model jobs (per-JD, quoted-sentence review, same discipline as
   D26's fixture cleanup) found 4 genuine `human_labels.yaml` labels
   that were too generous, not model bugs: `job_id` 2246 (Stripe Staff
   SWE, API Platform) is a real people-management role under an
   IC-sounding title ("You will lead a team of engineers... 5+ years in
   a strategic technical leadership role") corrected `software_engineer`
   90 -> 10; `job_id` 2732 (Scale AI Infra Eng) and 3267 (OpenAI Codex
   Deployment Eng) are genuine domain mismatches (systems/infra and
   customer-facing consulting, not ML engineering) corrected
   `ai_ml_engineer` 90 -> 15 each; `job_id` 3283 (OpenAI Camera SWE) is
   embedded firmware with zero ML content, corrected `ai_ml_engineer`
   70 -> 10. Each correction cites its source JD sentence inline in the
   fixture, same convention as D26's `required_keywords` corrections.
   The 2246 case also surfaced a real, separate gap worth noting: B3's
   seniority filter is title-only (`is_above_target_seniority`), so a
   people-management role under an IC title sails through B3 and only
   C4's body-text read caught it -- flagged, not yet acted on.

3. **Disqualifiers-field chain-of-thought leakage, recurring at scale
   after an earlier narrower fix.** A real spot-check while validating
   F1's new relevance floor (below) found 6 jobs scored `relevance=0`
   while their own `one_line` called them a strong or excellent match
   (e.g. job 2636: `one_line` "Excellent match: Role targets US-based
   software engineers with Python skills..." alongside a raw
   `disqualifiers` field containing ~600 words of unresolved internal
   debate -- "So likely still a match... But wait... Therefore no
   disqualifier... Thus empty list."). `is_hard_disqualified()` never
   forced these to 0 (none matched the blocklist); the model's own
   `relevance` number simply contradicted its own stated conclusion.
   Table-wide, 23 of the (at the time) 50 zero-scored rows had this
   same verbose leaked-reasoning pattern in `disqualifiers`. This is
   the same failure category as job 3283's earlier, narrower fix
   (self-correction leaking into `disqualifiers`), recurring because
   that fix named specific banned phrases ("re-evaluating", "I will
   remove this") rather than the general pattern. Refixed by
   generalizing `_RELEVANCE_PROMPT`'s instruction: disqualifiers must
   be short phrases (~10 words), reasoning must happen silently and
   never appear in the field at all, and -- the new, load-bearing
   clause -- a disqualifier the model decides does *not* apply must
   never lower the relevance score either. Verified on real re-scores,
   not assumed: the 6 flagged jobs all resolved (5 moved from 0 to
   75-85, matching their positive `one_line`; the 6th, job 1211, was
   re-examined and found to have been a false positive in the original
   spot-check -- a genuine PhD-level ML research role, correctly scored
   low both before and after). The fuller 23-job population: 22 of 23
   now produce short, clean disqualifiers with no score/`one_line`
   contradiction; 1 (job 3127) improved substantially (3+ paragraphs to
   one over-long phrase) but didn't fully hit the ~10-word target,
   noted as a minor residual, not blocking.

**F1's queue gate now consumes C4's score for real.** Before this
session, `relevance_scores.selected` was 1 for all 921 real rows
(`daily_cap` stays deliberately `null` per D23, so `select_top_n`
selects everything) -- C4's score sat in the table doing nothing
downstream; a job like 2246 would have surfaced in F1's queue looking
like any other candidate. Added an independent `min_relevance_score`
floor (`config/relevance.yaml`, currently 20 -- a conservative starting
point from real score distributions, not a calibrated number) and
`passes_relevance_floor()`, wired into `web/app.py`'s `_new_pairs()`
alongside `passes_all_filters()`. Fails open on an unscored (job,
profile): C4's nightly batch and F1's lazy per-request trigger run on
independent schedules, so an unscored job is not evidence of a poor
fit. Measured against the real live db before shipping: of 934
(job, profile) pairs that would previously have surfaced as
"not yet reviewed," 84 are now excluded (79 `software_engineer`, 3
`data_scientist`, 2 `ai_ml_engineer`); spot-checking the lowest-scored
ones is what surfaced bug 3 above.

**Full 50-job/150-point Task 1 re-run, real, after all three fixes,
against the corrected fixture:**

| profile | rho (>= 0.70) | top30_overlap (>= 0.75) |
|---|---|---|
| ai_ml_engineer | 0.557 (FAIL) | 0.767 (PASS) |
| software_engineer | 0.449 (FAIL) | 0.767 (PASS) |
| data_scientist | 0.470 (FAIL) | 0.733 (FAIL, near) |

Real, substantial improvement over D36's pre-fix numbers (rho
0.485/0.303/0.297; top30_overlap all below 0.70) -- software_engineer
rho +0.15, data_scientist +0.17, ai_ml_engineer +0.07 -- but rho still
fails its formal bar on every profile. **Why rho specifically
underperforms relative to top30_overlap, same reasoning already
surfaced mid-investigation:** the human-labeled fixture is heavily
bimodal (roughly three-quarters of labels sit at 0-10, another 10-14%
at 71-100, almost nothing in between). Spearman rho is sensitive to
fine-grained rank ordering across the *whole* list, including within
that empty middle where small, noisy score differences get rank-ordered
as if they were meaningful; top30_overlap only asks whether the same
jobs land in the top slice on both sides, which is far more robust to a
label distribution with almost no real middle ground to rank correctly
in the first place. This structurally penalizes rho beyond what
extraction quality alone would predict, without excusing it.

**Decision: ship C4, keep the relevance floor gate active in F1, same
D27/D36 precedent -- real measured numbers on record, not a passing
gate.** Task 1's literal TODO.md bar (rho >= 0.70) is not met and is
recorded as failing, not glossed over. But top30_overlap is the more
decision-relevant metric here: F1's actual gate is a score floor over
individually-scored jobs (`passes_relevance_floor`), not a consumer of
rank correlation across the full list the way a hypothetical future
`daily_cap`-based top-N cut would be -- and top30_overlap passes on 2 of
3 profiles and is 0.017 from passing on the third. Combined with three
real, root-caused, verified fixes this session (determinism, fixture
correctness, disqualifiers-leak) and a real production validation of
the gate itself (84/934 exclusions, spot-checked, the worst false
positives already caught and fixed), this is judged sufficient to ship
now rather than hold for a rho number that spec 07 itself frames as
hard to clear on a first prompt/model ("try two different prompts
before blaming the model" -- already done once this session, on a
narrower defect than a full model swap). 6 real rows written to
`model_evals` (`spearman_rho_<profile>`, `top30_overlap_<profile>`,
`fixture_version` = the corrected fixture's real hash). Full suite
441/441, `ruff check`/`format --check` clean.

---

**D38. F1's review queue had no batch orchestrator (D35's deliberate
scope cut) and, separately, its relevance floor (D37) was failing open
on every job B2 ever synced, since nothing scheduled C4 to actually
score them.** A live investigation this session (queried against the
real `data/jobengine.db`, not estimated) confirmed
`passes_relevance_floor()` fails open by design on an unscored
`(job, profile)` -- correct behavior for what it was built for, but it
meant the floor gate had never actually filtered anything for any job
synced since C4's last manual scoring run, silently. Real counts at
investigation time: 520 open jobs in F1's own 7-day queue window with
zero `relevance_scores` row, 84 of those surviving B3's full filter
chain (`passes_all_filters()`), 93 real (job, profile) pairs C4 would
need to score (9 jobs match 2 profiles), 84 real C3 extraction calls
(one per surviving job, extraction is job-level not profile-level).
D35's own text names exactly this precondition -- "building the real
scheduled version properly would need C4... first" -- which is now
done (D36/D37), so this was the right time, not a new decision to defer
again.

**Scope, confirmed by asking:** one new module,
`src/jobengine/pipeline/batch.py` (`run_daily_batch()`), run once daily
on its own Task Scheduler entry (`scripts/relevance_batch.sh`), not
chained onto `sync.sh`'s every-3h cadence -- matches
`docs/architecture.md`'s own pipeline table, which puts stages 2.5
(relevance) and 3 (extraction) at `daily`, one tier down from fetch/
filter's `2x daily`. Runs C4 (`score_job()`) for every job in
`list_unscored_open_jobs()`'s incremental candidate set (new
`db/models.py` accessor: open, within `WINDOW_DAYS`, zero
`relevance_scores` row for any profile), then runs C3 (`analyze_job()`)
only for jobs where at least one scored profile clears
`min_relevance_score` -- not every B3 survivor unconditionally, which
was the literal scope first proposed. Deliberately does not call
`queue/orchestrate.py`'s `ensure_reviewed()` or the patch ladder
(D3/D4): rendering a candidate resume stays F1's lazy per-click
trigger, unchanged, per that module's own docstring.

**A real bug in the existing tooling was found and designed around, not
inherited.** `pipeline/relevance.py`'s `score` CLI (`_cmd_score`) has no
"already scored" check -- `freshness_window_days` is deliberately `null`
(D23), so every invocation rescans and re-scores the *entire* open
`jobs` table. Scheduling that CLI directly would have re-called the LLM
for the whole open backlog (3,070+ jobs and growing) on every single
run, forever -- the opposite of "only newly-synced jobs each run."
`list_unscored_open_jobs()`'s `NOT EXISTS (relevance_scores)` clause is
the fix; the CLI itself is left unchanged, still useful as a deliberate
manual/one-off tool (e.g. a full re-score after a prompt change), just
no longer what the scheduler calls. The same incremental principle was
extended to extraction: a new `has_job_analysis()` accessor skips
`analyze_job()` for a job already analyzed by any path (including F1's
own lazy trigger reaching it first via a direct URL visit), so the two
stages can never regress into rescanning their full backlogs either.

**Cost/coverage tradeoff, recorded rather than silently accepted:**
gating C3 on C4's floor (instead of running it for every B3 survivor)
means `keyword_corpus` -- the accumulating per-profile keyword table
M1's monthly base-resume regeneration reads to detect corpus drift --
never sees keywords from a below-floor job's JD, even though that JD
was real, fetched, and B3-eligible. This is a deliberate cost
optimization (avoids real, wasted LLM calls on jobs nothing in F1 will
ever surface to a reviewer, since `passes_relevance_floor()` already
hides them from the queue list), not a correctness bug, but it does
mean `keyword_corpus`'s coverage is now bounded by C4's floor, not by
B3's filters alone -- a real, if minor, second-order effect of D37's
floor gate that hadn't been traced through to the corpus before this
session. Revisit only if a future monthly corpus review (M1) shows
real drift or gaps traceable to this narrowing; not pre-emptively
widened without that evidence, same D27-style precedent.

**Grounded with a real, live-queried backlog estimate, not a guess.**
At C1's measured steady-state latency (600-935ms/call after the known
one-time ~15s Ollama cold start), the first catch-up run against the
520/84/93/84 numbers above was estimated at under 3 minutes wall-clock
total; ongoing incremental cost was estimated from real recent unattended
sync firings (`runs` id 17-19: `new` counts of 2, 88, 4 per 3h cycle) at
a small handful of calls per cycle once caught up, confirmed by
`list_unscored_open_jobs()`'s incremental design rather than re-measured
against a real scheduled firing (none exists yet at the time of this
entry -- Task Scheduler registration is a manual step outside this
session's own file changes, same as B2's original `sync.sh` rollout).

12 new tests (`tests/test_batch.py`), written before implementation per
hard rule 7: the incremental candidate query (already-scored/closed/
outside-window jobs all excluded), the floor-gating of C3 (a
below-floor job gets no `job_analysis` row), extraction's job-level-not-
profile-level call count (one call serving two matched profiles), an
explicit already-scored-job-is-not-rescored regression test (the core
incremental guarantee this whole module exists to provide), an
already-analyzed-job-is-not-reextracted counterpart, a `runs`-row
assertion, and a regression test pinning `web/app.py`'s
`_LIST_WINDOW_DAYS` to the same `WINDOW_DAYS` constant `batch.py` now
owns, so the two can't silently drift apart again. Full suite 458/458
(up from 441), `ruff check`/`format --check` clean.

---

**D39. G1 (form schema fetch + autonomy gating) ships Greenhouse-only,
with a classification rule inverted after a real 40-job live run found
the first cut too permissive, and a real finding that falsifies D16's
literal claim rather than just narrowing it.**

**The Ashby gap, real and falsifying, not a scope footnote.** D16 says
"both APIs expose a schema pre-browser." Verified live against a real
job (3902, Notion): a direct GET against the one plausible per-job
Ashby posting-api endpoint returned `401 Unauthorized`; the public apply
page (`jobs.ashbyhq.com/notion/{id}/application`) is a client-rendered
SPA whose only embedded state (`window.__appData`) is Datadog/org
config, not a field schema. Greenhouse, by contrast, has a clean, public,
unauthenticated endpoint (`GET .../jobs/{id}?questions=true`) confirmed
live and used as-is. Real, live-verified impact at this checkpoint: 393
of 951 distinct scored jobs (41.3%; 362/861, 42.0% open-only) are
`ats='ashby'` — none of them can be classified, and stay implicitly on
the fully manual path. Recorded as a falsification, not a mere gap: the
architecture's own D16 claim was checked against real API behavior and
found wrong for one of the two ATSs, same standard this project has
applied to its own prior claims (D36's contaminated numbers, D27's
literal-DoD misses). G1 ships anyway, scoped to Greenhouse, same
D27-style precedent (ship the real, verified subset; don't hold for the
harder remaining piece).

**The classification rule, inverted after real data, not shipped on
first-pass synthetic confidence.** The first cut of
`classify_autonomy_ceiling()` capped a job's autonomy ceiling at 1 only
if a required *free-text* field existed beyond Greenhouse's standard
identity fields, confirmed by `AskUserQuestion` before implementation
and verified against one real job (3950, Discord) before shipping. The
user then ran a real 40-job live run (top Greenhouse jobs, score>=20,
open) and found this too permissive: 21/40 jobs classified at ceiling 2,
but 20 of those 21 had required `multi_value_single_select` fields the
system has no way to answer — Airbnb's "Candidate AI Usage Attestation,"
"Airbnb Candidate Privacy Policy," non-compete/relocation/eligibility
acknowledgments — invisible to a free-text-only check since they're
selects, not text. Only job 2650 (Anthropic: required fields exactly
`first_name`/`last_name`/`email`, all standard) genuinely had zero
unmapped required fields. **Fix, confirmed by asking:** ceiling 2 now
requires *every* required field on the form to be recognized — a
Greenhouse standard identity field or a label in `config/apply.yaml`'s
`mapped_question_labels` (renamed from `safe_optional_question_labels`,
whose old comment claiming "today's data doesn't need this list" was
itself disproved live: Airbnb job 7995153, "Acquisition Manager," has
"How did you hear about this job?" as `input_text`, `required=True`).
Any other required field caps the job at 1. `classify_autonomy_ceiling()`
now returns `AutonomyClassification` (ceiling + the unmapped required
fields), not a bare int — the list is the decision-relevant signal G2
will need to know what a human must fill, the same way `top30_overlap`
mattered more than raw rho in D37.

**Eligibility-question labels deliberately held out of the mapped list,
confirmed by asking a second time.** "Are you legally authorized to
work...", "Will you require sponsorship...", relocation, and "currently
located in the US" recur across real forms (Discord 3950, Airbnb
4466/7995153) and are philosophically identity.toml-answerable per D16.
Not added to `mapped_question_labels` anyway: G1 is fetch-and-classify
only, with no identity.toml lookup logic; adding the label without that
logic would silently promote a job's ceiling on a question nothing in
this codebase actually answers. Verified this doesn't change either
grounding job's real outcome (2650 has none of these fields present;
4466 caps at 1 regardless, via the privacy-policy/non-compete/AI-
attestation fields alone) — the choice only matters for a hypothetical
future job whose sole non-standard required fields are these eligibility
questions with no other attestations. Revisit once a future session (G2
territory) builds the real identity.toml mapping.

**Two more real field-modeling bugs, found in the same investigation.**
(1) Greenhouse represents "provide ONE of these" (Resume/CV: file
upload OR pasted text) as multiple `fields` entries sharing one
question's `label` and single `required` flag — confirmed live on job
4466, `resume` and `resume_text` both `required=True`. A flat per-field
check would, for any OR-group where one alternative is non-standard,
wrongly cap a job whose *other* alternative was actually sufficient.
Fixed by grouping required fields by `label` before classifying: a
group is satisfied if *any* field in it is recognized, contributing to
`unmapped_required_fields` only if *no* alternative is — one
representative field per group, not one per alternative. This grouping
is free, structurally-correct information already present in
Greenhouse's real JSON (fields nested under one question object), not a
heuristic. (2) `cover_letter`/`cover_letter_text` were in
`_STANDARD_FIELD_NAMES`, so a required cover letter silently passed as
safe. Wrong: a required cover letter needs genuinely generated prose,
the same fabrication-risk category as a custom free-text essay (D18) --
it must never pass the way résumé does (résumé stays standard because
this pipeline already deterministically produces that exact file, D3/D4;
cover letter has no equivalent deterministic source anywhere in this
codebase). Latent in the 40-job sample (0/40 required one) but real,
confirmed on job 7995153, which does. Fixed by removing both names from
`_STANDARD_FIELD_NAMES`; no special-casing needed, the general
recognized-or-not fallback now handles it correctly.

**All three grounding jobs re-verified live post-fix via the real CLI**
(`python -m jobengine.apply.form_schema {2650,4466,410}`), matching the
plan exactly before any code was called done: 2650 -> ceiling 2, empty
unmapped list; 4466 -> ceiling 1, the 6 real unmapped Airbnb attestation/
eligibility labels, "How did you hear" correctly absent; 410 (7995153)
-> ceiling 1, "Cover Letter" now correctly present in the unmapped list,
"How did you hear" still correctly absent. 12 tests in
`tests/test_form_schema.py` (3 new, 9 rewritten for the new
`AutonomyClassification` return shape), all built on real captured
Greenhouse response shapes (Discord, both Airbnb jobs), not synthetic
minimal fixtures -- the whole rule depends on Greenhouse's real
`question_<id>`-vs-clean-name field-naming convention, so a synthetic
fixture wouldn't actually exercise it. Full suite 471/471 (up from 458),
`ruff check`/`format --check` clean. Nothing from this work is committed
to git; this entry and the corresponding `/checkpoint` land before any
commit, per explicit request.

---

**D40. B3's seniority filter now excludes Staff/Senior Staff/Principal/
Distinguished bands, a real 22.4% narrowing of the survivor funnel the
pipeline had no other way to see.**

C4 (relevance scoring) judges title and skill match, not seniority band
-- nothing in the pipeline modeled "is this role above the candidate's
actual level" until this change. `is_above_target_seniority()`
previously excluded only manager/director/head of/vp/vice president/
chief; `config/filters.yaml`'s own comment even documented, as a known
fact, that Staff/Senior/Lead titles passed through untouched. The result
was invisible until a real 40-job spot-check of the top-scored live
Greenhouse jobs (all scoring 95-100) turned out to be almost entirely
Staff/Senior Staff/Principal-tier roles, above a current graduate
student's target band -- C4 scored them highly because the title and
skills genuinely matched a target profile, with no signal anywhere in
the pipeline for "but this level is wrong."

**Grounded in the real db before proposing anything, same discipline
B3's original title-alias list used (D23).** Scoped to the 861 jobs that
were both open and already C4-scored at investigation time (the same
population the 40-job spot-check was drawn from, not a hypothetical
one): 181 titles contain "staff" as a genuine senior-IC title, reviewed
individually, line by line, not sampled -- every one is a real
`Staff Software Engineer, ...` / `Senior Staff Machine Learning
Engineer, ...` / `Staff+ Software Engineer, ...` shape, zero false
positives found outside "Member of Technical Staff." 11 contain
"principal," 1 is "Distinguished Engineer," both unambiguous. Combined,
deduplicated, MTS excepted: **193 of 861 (22.4%)** newly excluded.
Non-engineering "Staff" titles that exist elsewhere in the db (`Staff
Product Manager`, `Staff UX Researcher`, `Staff Brand Designer`) never
appear in this population at all -- they don't match any profile's
`title_aliases`, so they were never reachable by this filter either way.

**The one real ambiguity, handled explicitly per the user's own framing,
not pattern-matched:** Anthropic/OpenAI use "Member of Technical Staff"
as a flat, band-agnostic title spanning entry-level through senior --
the word "staff" inside it does not carry the same signal it does in
"Staff Software Engineer." `SeniorityConfig` gained
`exclude_override_keywords` (`"member of technical staff"`), same
exclude/override shape `ProfileFilterConfig.exclusion_override_keywords`
already uses for `software_engineer`'s "forward deployed" exception, not
a new pattern. But the override reasoning is specific to the *bare*
title -- "Senior Member of Technical Staff" and "Lead Member of
Technical Staff" are real titles where the qualifier carries exactly the
band information the bare form lacks, so the override reasoning does
not extend to them. A broad substring override would have silently
exempted these too, with **0 blast radius today but a real, confirmed
divergence waiting**: 4 `Senior Member of Technical Staff, ...` and 1
`Lead Member of Technical Staff, ...` titles already exist in the open
jobs table, just not yet scored -- the same class of quiet
future-wrongness as the `coverage: 1.0` bank-frequency-fallback caveat
(D34), caught before it shipped rather than after a future `daily_batch`
run (D38) scored them and someone had to notice the gap. Fixed with a
third list, `exclude_override_exceptions`, reusing the identical
`phrase_matches()` substring/word-boundary mechanism already used
everywhere else in this file -- deliberately not a prefix-anchored match
or any other new matching primitive, confirmed by asking: "whichever
reuses the matching shape already in filters.yaml rather than
introducing a new mode for one case." `is_above_target_seniority()`
became a three-tier check (exclude -> override -> exception to the
override) instead of the previous flat any-match.

**What survives, live-verified against the real db with the actual
shipped function, not a simulation:** 637 of 838 open+scored jobs (the
838 denominator reflects real jobs closing between planning and
implementation, not a bug) pass every B3 filter including this one. Top
20 by relevance score: 10 distinct companies (Pinterest 4, Figma 3, Brex
3, Discord/Ramp/DoorDash 2 each, Stripe/OpenAI/Airbnb/Robinhood 1 each),
titles overwhelmingly plain `Software Engineer` / `Senior Software
Engineer` / `Data Scientist` -- the filter produced the intended shape,
not a thin or single-company-dominated list, checked now rather than
discovered at apply time per explicit request.

**Interaction with two known-deferred items, recorded so a future
session doesn't misread a thin queue as a bug:** B3-followup's
`daily_cap` calibration (D23) is still deferred and was never tuned
against any real survivor count -- this filter narrows the population
that calibration would eventually be tuned against by another ~22%, on
top of B3's original filters, so a future B3-followup session needs to
account for this cut specifically, not just re-derive against B3's
original numbers. Separately, the 15-company registry (specs/04-sources.md,
still short of the 150-300 target) is **not** currently the binding
constraint -- the top-20 simulation above spans 10 distinct companies
with real headroom -- but a future session that finds the queue thin
should check company-registry size and `daily_cap` before assuming this
seniority change over-cut; today's evidence says it didn't.

7 new tests in `tests/test_filter.py`, run against the real
`config/filters.yaml` (the `config` fixture loads the production file
directly, not a synthetic mock), including the one existing test this
change deliberately reverses
(`test_seniority_does_not_exclude_staff_ai_engineer` -> removed, staff
is now excluded by design). Full suite 477/477 (up from 471), `ruff
check`/`format --check` clean.

---

**D41. A real, full-chain end-to-end walkthrough (extract -> review ->
approve -> resume file -> apply URL -> real form schema + autonomy
ceiling) on one real job, before G2, surfaced a third real gap neither
of the two already-known ones predicted: nothing anywhere blocks
approving a resume variant that failed the rubric.**

No new code. Every function called already existed and was already
tested (`orchestrate.ensure_reviewed`/`approve`, the same ones
`web/app.py`'s routes call; `apply.form_schema`'s existing CLI). The
point was to chain them for real, on one real job, and see where a
human still has to step in before any browser automation exists.

**The job: 3950 (Discord, "Senior Software Engineer, Enterprise
Platform," `software_engineer`).** Picked by live query, not in
advance: Greenhouse, open, passes every B3 filter including D40's new
seniority check, clears the relevance floor at 95.0 -- among the
highest-scored jobs in the real queue. Had a real `job_analysis` row
already (from `daily_batch`, 2026-08-13) but no `job_resume_variants`
row and no `applications` row, so the patch-ladder/render/approve steps
genuinely executed live during this run rather than replaying one.

**Real result: the patch ladder produced a variant that FAILS the
rubric (`passed=False`, score 16.64, coverage 0.10, R001 FAIL), despite
C4 having scored this exact job 95/100 relevance.** Real cause, not a
bug: `job_analysis.required_keywords` for this JD (Go, Python,
TypeScript, Terraform, CI/CD, SSO, SCIM, OAuth, OIDC, RBAC -- an
enterprise identity/IaC platform role, `jd_quality` already flagged
`'bad'` by C3) has almost no overlap with the current
`software_engineer` bank content, and P1 (swap) has been a structural
no-op against this bank since D29 -- there's no held-back bullet
carrying these keywords for P0-P2 to promote, and P3 (rephrase) can't
honestly manufacture SSO/SCIM/Terraform experience that was never
described in the bank (D18's fabrication guard doing exactly its job).
C4's relevance score measures title/seniority/skill-area fit, not
"does the bank have enough real material to cover this JD's specific
keyword list" -- these are different questions, and this run is the
first time a real job has surfaced daylight between them this wide (95
relevance, 16.64 rubric score).

**`orchestrate.approve()` was called anyway, deliberately, to see what
actually happens -- and nothing stopped it.** Real `applications` row
id 1 (the first one this project has ever written outside a test),
`autonomy_level=0`, `status='queued'`, for a variant that failed its
own rubric. Neither `orchestrate.approve()` nor `web/app.py`'s
`POST /jobs/{job_id}/{profile}/approve` route checks `variant.passed`
before creating the row. F1's review queue UI does show the score/
coverage/hard-failures on the detail page before a human clicks
Approve (so a human paying attention would catch this), but nothing in
the code path enforces it -- an inattentive click, or any future
automated-approval path, would queue a genuinely poor-fit resume with
no gate at all. Not fixed here (out of this run's scope, and "should a
failing variant even be approvable" is a product judgment call, not an
obvious bug fix); flagged for whoever designs F1's next iteration or an
approval gate.

**Real, working-as-designed dedup, not a bug, but worth recording since
it looked surprising at first:** the returned variant's `docx_path`/
`pdf_path` point at job 3871's rendered files
(`resume/rendered/variants/3871/software_engineer/candidate_P0_P1_P2_P3.docx`),
not a new `3950/` directory. Confirmed via direct query:
`job_resume_variants` ids 1 (job 3871) and 2 (job 3950) share the exact
same `selection_hash` -- the patch ladder independently converged on
the identical bank-bullet selection for both jobs (unsurprising given
P1's structural no-op status, D29), so F1's own dedup design
(`find_job_resume_variant_by_hash`, D35) correctly reused the existing
file rather than re-rendering an identical one. Both variants score
similarly low (18.98 and 16.64) and both fail the rubric -- not a
coincidence specific to this pair, likely the same bank-coverage
ceiling showing up twice.

**The two gaps the user already knew about, now with real numbers
attached instead of descriptions:**

1. Job 3950's real, live-fetched (re-run at execution time, not just
   planning time) form schema: **autonomy ceiling 1**, 4 unmapped
   required fields -- "Why do you want to work at Discord?" (a genuine
   free-text essay no code here can honestly answer, D18) plus 3
   eligibility questions (legally authorized to work / willing to
   relocate to the Bay Area / currently located in the US), all three
   answerable in principle from `identity.toml`'s real
   `authorized_to_work_us = true` / `willing_to_relocate = true` fields
   but deliberately unmapped per D39's own scope cut. The real
   `applications` row this run created says `autonomy_level=0`; the
   real computed ceiling for the identical job says `1`. Both numbers
   exist, in the same db, for the same job, right now, with no code
   path connecting them -- `approve()` never reads
   `classify_autonomy_ceiling()`'s output at all.
2. Live-queried the population this actually matters to, not just
   D39's old 41.3%-of-all-scored-jobs figure (which includes jobs
   nobody would ever approve): of the **573 real distinct jobs that
   currently pass every B3 filter and clear the relevance floor** (the
   actual approvable-queue population), **293 (51.1%) are `ats='ashby'`**
   and would get no computed autonomy ceiling at all if picked instead
   of 3950 -- worse than the all-scored-jobs figure suggested, not
   better.

**Net finding for whoever designs G2 next:** the browser-automation
question ("can Playwright fill this form") is not actually the nearest
blocker. Three things sit in front of it, none requiring a browser: (a)
roughly half the real approvable queue has no computed ceiling at all
(Ashby); (b) even a Greenhouse job at the best ceiling this system
computes today (1) still needs a human to write real prose and answer
eligibility questions by hand; (c) nothing currently stops a rubric-
failing variant from reaching `applications` in the first place, so
"which applications are even worth automating" isn't a solved question
yet either. G2 (Playwright dry-run) is still the right next Phase G
step per TODO.md's own ordering, but designing it without accounting
for (a)-(c) would automate filling forms for jobs that, on today's real
data, are disproportionately either uncoverable (Ashby) or poor rubric
fits.

Full suite re-run after this walkthrough (no source changed): 477/477,
`ruff check`/`format --check` clean.

---

**D42. `orchestrate.approve()` now gates on rubric pass/soft-fail/hard-
fail state, closing the exact real gap D41 found (job 3950 queued
cleanly despite a real R001 hard failure). R001-only failure is a soft,
human-overridable deficit; any other hard rule is never overridable --
both the split and the reuse of the already-existing `accepted` column
come directly from spec 08's own, never-built P4 language, not invented
here.**

`specs/08-rubric.md`'s P4 section (never built) already draws this
exact line: *"Mark the variant `passed: false, accepted: true` if the
deficit is soft, or skip the job entirely if a hard rule other than
R001 still fails."* D33 independently arrived at the same split from
the opposite direction when demoting R002 (front-load) but deliberately
leaving R001 alone: R001 "is the system's only gate against a resume
that doesn't cover the job's keywords at all," carrying D27's
precedent toward strictness. This decision reuses both -- the soft/hard
split and the `job_resume_variants.accepted` column that already
existed in the schema, unused, since F1 shipped.

**Real evidence, gathered read-only before deciding how strict the gate
should be, confirms the split is load-bearing, not just spec-
literalism.** Of the 623 (job, profile) pairs currently passing every
B3 filter and the relevance floor, 67 already have real extraction done
(`job_analysis`). Of those 67, **66 (98.5%) already fail R001 coverage
before any patching at all** (`measure.coverage()` against
`measure.select_for_profile()`'s pre-patch candidate, per profile).
This is not a loose proxy: per D29, P1 (swap) is a structural no-op
against the current bank for every profile, and P0/P2 only reorder or
promote existing content -- neither can change which keywords a
candidate carries. Only P3 can move coverage, and it's capped at 2
calls/job with a fabrication guard already proven (D30, job 318) to
decline inventing experience rather than close a gap dishonestly. Both
real variants that exist (3871, 3950) hard-fail on exactly `['R001']`,
nothing else. Separately, all 11 other gated hard rules were checked
directly against `select_for_profile()`'s output for all 3 profiles:
zero failures, for any profile -- expected, not coincidental, since the
base bank already passed clean per E2, P0/P2 don't touch content that
would regress R003/R005/R007/R008/R009/R012/R013, and `apply_p3()`
already discards any rewrite that would regress R005/R006/R007/R008
(D4). In practice, on this pipeline's real output, `hard_failures` is
essentially always either `[]` or exactly `['R001']`. A uniform hard
block would therefore reject ~98% of the real queue outright -- this is
a bank-coverage problem (P4/gap-ledger territory, still unbuilt), not a
rare edge case, so the fix had to be override-shaped, not block-shaped,
for the queue to stay useful at all.

**`has_unrecoverable_rubric_failure(hard_failures: list[str]) -> bool`**
(`src/jobengine/rubric/rules.py`) is the one new pure function: True if
`hard_failures` contains any rule other than R001. Tests first
(`tests/test_rubric.py`, 5 new cases) per hard rule 7.

**The gate lives in `orchestrate.approve()` itself, not just the web
layer, because only `orchestrate.approve()` is reachable from a future
automated path (G3/G4).** Enforcing only at the FastAPI route would
silently stop protecting anything the moment G3/G4 exists -- the same
class of bug D35 already found and fixed once (review state almost went
on `applications` instead of `job_resume_variants` for the identical
future-path reason). Two new exceptions, same pattern as the existing
`NoBaseResumeError`/`JobNotFoundError`: `HardRubricFailureError`
(raised regardless of any override -- there is no override path for a
non-R001 hard rule) and `UnacknowledgedSoftFailureError` (raised only
when `override_soft_failure` is not passed). `approve()` gains a
keyword-only `override_soft_failure: bool = False` param; passing it
True on a genuinely soft (R001-only) failure proceeds and marks the
variant `accepted=True` via `update_review_status()`'s new optional
`accepted` param (`SET accepted = COALESCE(?, accepted)`, so `reject()`'s
existing 4-positional-arg calls are unaffected -- no schema change, no
migration, `accepted` already existed on `job_resume_variants`). Tests
first (`tests/test_queue_orchestrate.py`, 4 new tests covering all
three states, including the specific case that override does **not**
bypass a hard failure).

**The web layer is where "surface prominently, don't silently refuse"
actually lives, per explicit direction: a hard block should not be a
silent refusal, and a soft failure should be visible with real numbers,
not just rejected.** `queue_detail()` (GET) now computes the same
classification from the already-fetched `rubric_results` the moment the
page loads, not only after a failed approve attempt, and passes
`hard_block`/`needs_override` into the template. `queue_detail.html`'s
previously-unconditional Approve button is now three mutually exclusive
states: a passing variant gets today's plain Approve form unchanged; a
soft failure gets the existing fail banner (already showing the real
coverage number and missing keywords) plus a visually distinct amber
"Approve anyway" form (`override_soft_failure=true` hidden field); a
hard failure gets an explanatory banner and **no approve form at all**
-- Reject stays available in every state. The POST route gains a form
field and catches both new exceptions as 409, a backstop for a stale
page or a future caller that skips the check, not the primary UX
mechanism. Tests first (`tests/test_web_app.py`): **the existing
`test_approve_flips_review_status_and_creates_application` test was
itself exercising the exact bug being fixed** (`_EXTRACT_PAYLOAD`'s
`["Go", "Kubernetes"]` has no real bank coverage, so its seeded variant
is a real R001-only failure, and the test asserted a bare POST approve
succeeded) -- split into a without-override-returns-409 test and a
with-override-succeeds-and-sets-accepted test, plus two new tests for
the detail page's button states in both the soft and hard cases.

**Autonomy ceiling deliberately NOT consumed here, kept separable --
same precedent D37 already set with `passes_relevance_floor()` as an
independent gate from B3's filters.** Three reasons: the rubric gate
and the autonomy ceiling answer different questions (resume quality vs.
how much of *submission* can be automated); every variant reaching
`approve()` has rubric data, but the ceiling is Greenhouse-only (D39) --
forcing `approve()` to consume it means deciding right now what happens
for the ~51% of the real approvable queue that's Ashby (D41), a real,
separate design question; and D37's own precedent already established
that composable independent gates, not one merged gate, is the right
shape when the questions and fail-open semantics differ.
`applications.autonomy_level=0` stays hardcoded, still flagged (D41,
PROGRESS.md Known Issues) as a distinct follow-up.

**Verified against the real db, not just the automated suite:** called
`orchestrate.approve()` directly on job 3950's real variant (id 2,
`passed=False`, still `review_status='approved'` from D41's pre-fix
approval, `accepted` still `None`) with no override -- confirmed it now
raises `UnacknowledgedSoftFailureError`, concrete proof the exact real
gap D41 found is closed. Confirmed no side effect from this check
(`applications` count unchanged at 1, the variant's own
`review_status`/`accepted` unchanged) since the gate raises before any
write. Full suite 491/491 (up from 477, +14 tests), `ruff check`/
`format --check` clean.

---

**D43. P4 (accept and log) built, scoped to exactly what spec 08 says:
`ensure_reviewed()` now logs every still-missing required keyword to
`gap_ledger` after `run_ladder()` exhausts. It never touches
`accepted`/`review_status` -- that's a deliberate divergence from spec
08's literal text, not a silent reinterpretation, and the reasoning is
D42's own gate, not guessed fresh.**

**The real numbers, gathered read-only before any code, changed what
this needed to be.** Of 623 real (job, profile) pairs currently passing
every B3 filter + the relevance floor, 67 already have real extraction
done. Pre-patch missing keywords for those 67
(`measure.missing_keywords()` against `select_for_profile()`'s
candidate; per D29, P0/P1/P2 can't remove any of these, only P3 can, and
it's capped/guarded), aggregated by distinct job count:

| profile | keyword | distinct jobs |
|---|---|---|
| software_engineer | go | 16 |
| software_engineer | java | 12 |
| software_engineer | rust | 12 |
| software_engineer | typescript | 11 |
| data_scientist | sql | 8 |
| software_engineer | c++ | 7 |
| software_engineer | react | 6 |
| software_engineer | sql | 5 |
| software_engineer | distributed systems | 5 |
| software_engineer | aws | 3 |

(140 distinct (profile, keyword) gaps total across the 67 pairs.) **The
top gaps are not obscure long-tail infra terms -- they're mainstream
languages `software_engineer`'s bank apparently has zero tagged coverage
for at all.** A single read-only script already made this legible from
n=67, using one existing pure function
(`measure.missing_keywords()`) called nowhere new yet. This is exactly
the finding that shaped the implementation: P4's actual job isn't
discovery (that machinery already exists and is nearly free), it's
durability -- turning an ad hoc snapshot into a persistent, growing
signal across the full future population for M1's monthly review,
without building anything heavier than one insert.

**Decision 1: reuse D42's exact soft/hard classification for what
"soft deficit" means, but do not let P4 auto-write `accepted`.** Spec
08's P4 text ("mark the variant `accepted: true` if the deficit is
soft... skip if a hard rule other than R001 still fails") is the same
sentence D42's `has_unrecoverable_rubric_failure()` already codifies --
not a coincidence, not a second judgment call, and a second parallel
classification function would have been a real duplication this
codebase doesn't have anywhere else. But P4 fires automatically inside
`ensure_reviewed()`, before any human has looked at the resume -- it's
a side effect of the ladder giving up, not a review decision. Auto-
writing `accepted=True` the instant that happens would quietly pre-
empt D42's entire point (a human must take a distinct, deliberate
second action to approve a known-failing resume): `accepted` would
become a synonym for "R001-only failure," set before review even
starts, and D42's "Approve anyway" button would be approving something
the system had already marked accepted on its own. **P4 only writes to
`gap_ledger`. It never touches `review_status` or `accepted`** -- those
stay exclusively human-driven through D42's existing
`approve(..., override_soft_failure=True)` path. Spec 08's "skip the
job entirely if a hard rule other than R001 still fails" is already
satisfied by D42's `HardRubricFailureError` (such a variant can never
be approved); F1's own shipped design (D35) always creates and shows a
variant regardless of pass/fail specifically so a human can see why
it's blocked, so P4 doesn't need to hide anything either.

Separately: gap-ledger logging itself is unconditional on whether R001
as a whole passes, not gated by the soft/hard split at all.
`measure.missing_keywords()` can return non-empty even when R001
*passes* (8/10 required keywords covered is 0.80 coverage, R001 passes,
but 2 keywords are still genuinely missing) -- spec 08 says "write
every still-missing keyword," not "only when R001 fails." `ensure_
reviewed()` calls `measure.missing_keywords()` directly against the
ladder's final candidate bank, independent of `result.passed`, so this
can't silently under-log.

**Decision 2: P4 fires in `orchestrate.ensure_reviewed()`, not inside
`run_ladder()`.** `run_ladder()` (`rubric/patch.py`) has no `conn`
parameter and no `job_id` -- deliberately pure per its own module
docstring ("No persistence to job_resume_variants... here"), reused
directly by `test_patch.py`'s real-bank integration tests with no db in
sight. Adding a gap_ledger write inside it would force every caller,
including those tests, to thread through a db connection and a job_id
just to run a patch ladder, for no benefit P4 actually needs.
`ensure_reviewed()` already does the parallel thing today (calls
`run_ladder()`, then persists `job_resume_variant` and, conditionally,
`rubric_results`, all in one `conn`-having, `job_id`-having place,
before one `commit()`); P4 is one more insert at that same site, same
transaction. `pipeline/batch.py` deliberately never calls
`run_ladder()`/`ensure_reviewed()` at all (D38's own explicit scope
cut), so "reachable from the batch path" wasn't the discriminator here
the way it was for D42's `approve()` gate -- the discriminator is
purity: `run_ladder()` is the reusable core, `ensure_reviewed()` is the
one real orchestration point with db context, and P4 is orchestration,
not patch logic.

**Decision 3: `gap_ledger` accumulates one row per real (job, profile,
keyword) occurrence, no dedup, no new constraint, no migration.** The
schema as it already existed (`job_id NOT NULL`, no unique index) only
supports this shape -- deduping to one row per (profile, keyword) would
require dropping or restructuring `job_id`, the exact column the useful
query depends on: `SELECT profile, keyword, COUNT(DISTINCT job_id) ...
GROUP BY profile, keyword ORDER BY COUNT(DISTINCT job_id) DESC`. That
query is impossible to reconstruct after the fact from a deduped table
without a redundant counter column the schema doesn't have, so
accumulating is not just simpler, it's the only shape that answers the
question this table exists to answer. No new write-time guard needed
either: `ensure_reviewed()` is already idempotent per (job_id, profile)
(returns the existing variant on a second call, never re-runs
`run_ladder()`), so P4 fires at most once per (job, profile)
automatically. `first_logged_at`'s name reads like it expected a
per-(profile, keyword) dedup that was never built -- flagged as a real,
harmless naming/intent mismatch, not fixed here (renaming a column
nothing had ever written to was free before this session but is a real
migration now that real rows exist).

**Implementation:** `GapLedgerRow` (`db/models.py`, mirrors
`RubricResultRow`'s shape) + `insert_gap_ledger_entries()` (executemany,
same pattern as `insert_rubric_results`); `ensure_reviewed()` gains one
new block, right after the existing `insert_rubric_results()` call and
before `ctx.conn.commit()`, computing `measure.missing_keywords(result.
bank, required)` and inserting one `GapLedgerRow` per still-missing
keyword when non-empty. No schema change. Tests first (hard rule 7): 2
in `test_db.py` (round-trip, no dedup), 4 in `test_queue_orchestrate.py`
(logs both keywords for a real known-uncoverable pair reusing this
file's existing `_EXTRACT_PAYLOAD` fixture; logs nothing when nothing is
missing; a second `ensure_reviewed()` call logs nothing further,
idempotency free from the existing early-return; `accepted`/
`review_status` stay untouched even on a real soft failure). Full suite
496/496 (up from 491), `ruff check`/`format --check` clean on every file
touched.

**Verified against a real, production-shaped scratch copy of the real
db (never the real path itself, per hard rule 13), not just the
automated suite:** ran `ensure_reviewed()` against a scratch copy for a
real, previously-untriggered job (2181, Stripe "Software Engineer"),
real bank/filter/profile config, a fake LLM client supplying
`required_keywords=["Go", "Rust"]` (chosen directly from this decision's
own real gap-frequency table above). Real result: variant `passed=False,
coverage=0.0`, and `gap_ledger` gained exactly 2 real rows,
`(software_engineer, "Go", 2181)` and `(software_engineer, "Rust",
2181)` -- confirming the wiring works against the actual production
schema and bank content, not only a freshly-`init()`'d test db. Scratch
copy deleted after verification; the real `data/jobengine.db` was never
opened for write.

---

**D44. `approve()` now redirects back to `/jobs/{job_id}/{profile}`
instead of `/`, and that page grows a fourth state (approved: apply URL
+ manual-submission notice, both action forms hidden) so an approved job
stays reachable with what's actually needed to apply next, instead of
vanishing from every list the moment it's approved.**

**The problem was real, not hypothetical.** `list_pending_review_queue()`
only returns `review_status='pending'`; `list_existing_variant_pairs()`
excludes any pair with a variant, any status, from "not yet reviewed."
An approved job was therefore unreachable from `GET /` in either
section the instant it was approved, and the old redirect to `/` sent
the reviewer straight to that dead end -- with no path back to
`job.apply_url` or the rendered `.docx`, both of which already existed,
just on the page they'd been redirected away from.

**Decision: reuse the existing detail page, not a new confirmation
route.** Every piece of context the confirmation needs was already in
scope on `GET /jobs/{job_id}/{profile}` -- `job` (carries `apply_url`,
a field that already existed on the `Job` model and was simply never
rendered), `docx_url` (already computed, already rendered
unconditionally), and `variant.review_status` (already on the object
passed to the template, just never branched on -- the template
previously showed Approve/Reject regardless of status, so reloading an
already-approved job's page still offered to approve it again). A
dedicated route would have duplicated that exact fetching for no
benefit, and reusing the same URL is what actually satisfies "stays
reachable": nothing new to bookmark, the link that got you here keeps
working. Net change: `approve()`'s redirect target
(`web/app.py`), plus one new `{% if variant.review_status == 'approved'
%}` branch in `queue_detail.html` that shows the apply link (only when
`job.apply_url` is set, same guarded pattern the `pdf_url`/`docx_url`
blocks already use) and wraps the existing Reject/Approve/"Approve
anyway" forms so a settled approval stops offering either action again.
`reject()`'s own redirect to `/` is untouched -- D35's "a rejected job
drops off the list" is a deliberate, different, correct behavior this
change didn't touch.

**Found while implementing, not fixed, flagged for visibility:**
`orchestrate.approve()`/`insert_application()` have no guard against
being invoked twice for the same variant -- nothing enforces
`UNIQUE(resume_variant_id)` on `applications`, and neither function
checks for an existing row first. Today's UI can no longer trigger this
for a human (the button disappears once approved), but a future
automated path (G3/G4) calling `approve()` more than once would create
duplicate `applications` rows silently. Not fixed here, since this
change's own UI fix already closes the one path that could hit it
today; worth a real guard (`INSERT OR IGNORE` plus a unique index, or an
explicit idempotency check in `approve()`) before anything automated
calls it.

**Decision: G1's autonomy ceiling and `unmapped_required_fields` stay
out of this change, kept separate, for four concrete reasons rather
than "different feature":** (1) `fetch_greenhouse_form_schema()` is a
live, unauthenticated GET against Greenhouse -- real latency, real
failure modes, on a page where everything else is local and fast (D35
measured a second detail-page visit at 0.01s, zero new calls; a live
external fetch would end that property on every future visit, not just
once). (2) It's async; every existing async call in this codebase
routes through `orchestrate.py`'s own `asyncio.run()` wrapping --
`web/app.py` has no direct async-to-sync bridge today. (3) Ashby has no
answer at all (D39); ~51% of the real approvable queue is Ashby (D41),
so the template would need a real "ceiling unknown" branch, a second
new UI state this change has no other reason to grow. (4)
`classify_autonomy_ceiling()` needs `ApplyConfig`
(`load_apply_config()`), which `QueueContext` doesn't carry today --
small, but new plumbing, not reuse. The live-fetch-at-render-time shape
itself is correct, not a wrong guess -- D42 (decision 3) already
declined to persist the ceiling anywhere, so a live fetch is the only
shape available without a separate schema/design pass. Recommended,
not built: a real follow-up scoped specifically to the approved-state
view (the one moment the ceiling is actually decision-relevant),
Greenhouse-only per D39, with an explicit "not available for Ashby"
branch rather than a silent gap.

**Tests first (hard rule 7), `tests/test_web_app.py`:** `_seed_job()`
gained an optional `apply_url` kwarg (default `None`, every existing
call site unaffected). 3 new tests, not 4 -- the plan called for a
separate redirect-target test on the plain-pass path and the
override-soft-failure path, but implementation surfaced that both
success cases share one `return RedirectResponse(...)` line in
`approve()`, so a second near-identical test would have covered nothing
new; consolidated to one redirect-target test (via the override path,
this file's only failing-fixture convention) plus the confirmation-
content test and a pending-state regression guard (the new block must
NOT leak before approval). Full suite 499/499 (up from 496), `ruff
check`/`format --check` clean.

**Verified against a real, production-shaped scratch copy of the real
db (never the real path, hard rule 13), through the actual FastAPI app
via `TestClient`, not just the automated suite:** real job 2181
(Stripe, real `apply_url`), fake LLM client, full GET -> POST approve
(with override) -> GET cycle. Confirmed live: pre-approval page still
shows the Approve form; post-approval page shows the real Stripe apply
URL, the "manual" copy, the working `.docx` download link, and neither
action form; a second reload is byte-identical (idempotent, no new
`applications` row). **Incidental real finding, not caused by this
change:** the scratch copy (freshly copied from the real db moments
before) already carried 3 real `applications` rows and 10 real
`job_resume_variants`, not the 1/2 this session's own D43 checkpoint
last recorded -- real usage of the actual running app happened for real
against `data/jobengine.db` between sessions (jobs 4109 and 4041, in
addition to 3950), confirmed by reading the real db directly,
read-only, after the scratch check. Recorded in this checkpoint's
"what exists" numbers, not left stale.

---

**D45. All 10 stale `job_resume_variants` rows (rendered before a real
`identity.toml` correction) invalidated and re-rendered for real,
against the real `data/jobengine.db`, after a read-only-first plan and
your explicit confirmation per hard rule 13 -- 7 deleted and left for
`ensure_reviewed()` to rebuild lazily, 3 re-rendered in place because
they're referenced by real `applications` rows.**

**The problem was a real, visible, wrong claim on every rendered page,
not a cosmetic diff.** `identity.toml`'s `work_authorization.statement`
changed from a version implying no sponsorship would ever be needed to
the accurate "On F1 OPT STEM" (F-1 OPT STEM eventually needs H-1B).
`render.py`'s `_add_status_line()` prints this verbatim in every
resume's header. Confirmed directly against the real file for variant 1
(job 3871) before touching anything: the actual PDF read `On F1 OPT
STEM, Eligible to work in the US without sponsorship | TX` against the
corrected `identity.toml`'s bare `"On F1 OPT STEM"`. All 10 real rows
predated the fix.

**Decision 1: delete-and-defer for the 7 non-approved rows, not a
staleness-hash column, at least for now.** This is the first time in
the project's real history `identity.toml` has changed at all -- a hash
column would be built to solve a problem observed once. The two future
triggers named (`identity.toml`, the bank) aren't actually the same
shape of risk: identity changes are rare, manual, made by the one
person who'd immediately know to trigger a refresh; bank content
changes are more frequent *and* riskier to leave silently stale (they
can change real keyword coverage, not just a header line), so a real
mechanism worth building should cover both under one coherent hash --
a bigger design question (hash the whole bank file? only the selected
bullets?) than a data-fix should absorb on the side. Flagged as a real,
deliberately-deferred follow-up, not silently dropped -- revisit if
manual fixes like this one become recurring toil, not preemptively.

**Decision 2: the 3 approved rows (jobs 3950/4109/4041, referenced by
real `applications` rows 1/2/3) are re-rendered in place, not deleted,
confirmed by asking rather than assumed.** Two independent reasons this
had to be a real question, not a default: (a) SQLite's `PRAGMA
foreign_keys = ON` (set in every `connect()` call) makes deleting them
literally impossible while `applications` references them -- confirmed
empirically against a scratch copy before proposing anything, not
asserted: `DELETE FROM job_resume_variants WHERE id = 2` raised
`FOREIGN KEY constraint failed` immediately; (b) even if it were
technically possible, these are real approval decisions, and "delete
and let it rebuild" would silently orphan the `applications` rows that
record them. Asked directly whether the 3 should be refreshed in place
or left frozen as a historical record of what was actually reviewed;
answer was refresh in place, since none of the 3 have `submitted_at`
set (`NULL` on all three -- nothing marked submitted through this
system), so correcting known-wrong content beats preserving it.

**Mechanism, and a real gotcha caught by reading actual file paths, not
assumed:** re-rendering called `patch.run_ladder()` directly (the same
function `ensure_reviewed()` already calls) with each row's real,
already-extracted `job_analysis.required_keywords`/
`preferred_keywords`, then `UPDATE`d the existing row's `docx_path`,
`pdf_path`, `score`, `coverage`, `front_load`, `passed`,
`patch_tiers_applied`, `bullet_ids`, `selection_hash` in place by `id`
-- never delete+insert, so `applications.resume_variant_id` never
needed to change. F1's dedup (D35) meant rows 1, 2, 4, 5, 8, 9 all
shared one physical file (job 3871's) before this ran, and two of the
three approved rows (2, 8) were among them -- deleting that file
outright (a first-draft instinct) would have broken the surviving
approved rows even though their *db rows* were never touched. Avoided
entirely by calling `run_ladder()` directly rather than going through
`ensure_reviewed()`'s dedup-lookup path: each of the 3 rendered to its
own fresh, independent file under `resume/rendered/variants/{job_id}/
{profile}/`, so no shared file was ever at risk. No rendered files were
deleted at all this session -- the old, now fully-orphaned files under
`variants/3902/` and `variants/4152/` are left on disk, same
already-known, harmless clutter class D44 already flagged for this
directory (`_VARIANTS_OUT_ROOT` not scoped per-run).

**Run for real against the real db, with the real local model, not a
stand-in.** Ollama was reachable this session via the configured
`OLLAMA_BASE_URL` (confirmed live, `qwen3.5:9b-q4_K_M` present) -- no
fake client, no shortcut; all three re-renders genuinely re-attempted
P3 against the real model, same as the original renders. All three
came back with `selection_hash` byte-identical to their pre-fix value,
confirming what D29 already implied but this run verified rather than
assumed: `identity.toml` content has zero influence on P0-P3's
keyword-driven selection logic, only on the rendered header. Score,
coverage, `passed`, and `patch_tiers_applied` are also unchanged for
all three -- the only thing that changed is the header line and the
file bytes.

**Verified before and after, not just planned:** captured full
before-state for rows 2/8/10 before running anything; after commit,
`job_resume_variants` count is 3, `rubric_results` count is 3,
`applications` count is unchanged at 3, `PRAGMA foreign_key_check`
returns clean (`[]`), and all three new PDFs' first-page text reads
`On F1 OPT STEM | TX`, confirmed by direct `pdfplumber` extraction, not
assumed from the code path alone. A full backup of the real db was
taken to the scratchpad directory before any write, as an extra safety
net beyond the transaction itself (same precedent as the D22/D23
addendum backfill). `gap_ledger` (19 rows) and `jobs` were unaffected,
as expected -- `gap_ledger` keys on `job_id` directly, not
`job_resume_variant_id`, and nothing about coverage/keyword math
depends on `identity.toml`.

**Adjacent, same root cause, explicitly out of scope this session:**
the 4 `base_resumes` rows were rendered the same way and are equally
stale, but have no `applications`/FK entanglement and spec 09's own
versioning already expects a new version rather than an overwrite
(`persist_base_resume()`, E2). Flagged, not touched -- revisit
separately if/when regenerating them is wanted.

---

**D46. Two independent pieces this session: a real routing
investigation that found no bug, and a human-readable rubric-rule
explanation feature on the review page, sourced from
`specs/08-rubric.md`'s own text.**

**The routing investigation, read-only, before any config was
proposed.** The job id given (3904) turned out to be a different, real
job entirely (Notion, "Software Engineer, Collections Infra") --
searching for the actual described job (Stripe, "Machine Learning
Engineer", required PyTorch/TensorFlow/XGBoost/Spark) found it as job
4630. **B3's title routing is not the bug.** Live-verified, not
inferred: `matches_profiles()` on job 4630's real title returns
`['ai_ml_engineer', 'software_engineer']`, both, confirmed directly
against the shipped function. Corroborating evidence already sitting in
the db: `pipeline/extract.py`'s `analyze_job()` fans a single extraction
call out to *every* matched profile in one pass (`profiles =
matches_profiles(job, filter_config)`, then one `job_analysis` row per
profile in `profiles`) -- `job_analysis` already had real rows for both
`ai_ml_engineer` and `software_engineer` on job 4630 with identical
extracted keywords, which could only happen if B3 had matched both.

**What actually happened: only the `software_engineer` pairing was ever
clicked into review** (`job_resume_variants` id 14, coverage 0.00). The
`ai_ml_engineer` pairing -- the one that could draw on real PyTorch
work in the bank -- was never triggered, and re-verified live at
investigation time to still be sitting, right now, in `GET /`'s "Not
yet reviewed" section: `passes_all_filters()` true,
`passes_relevance_floor()` true for both profiles (job 4630 has zero
`relevance_scores` rows at all -- C4 never ran on it, and the floor
fails open on an unscored pair, D37), and `(4630, 'ai_ml_engineer')`
confirmed absent from `list_existing_variant_pairs()`. **No config
change proposed or made** -- there was nothing wrong with
`config/filters.yaml` to fix.

**A real, adjacent gap surfaced but explicitly left out of scope:**
`queue_list.html`'s "Not yet reviewed" table lists every `(job,
profile)` pair as a flat, generically-labeled row with no grouping or
visual signal that a given job has more than one candidate profile
route -- easy to act on one and never notice the other sitting a row or
two away in a list of hundreds. A UX-legibility issue, not a routing
defect; flagged for a future session, not built here since it wasn't
what was asked.

**The rubric-rule-explanation feature.** `queue_detail.html`'s "Hard
failures" list rendered bare `rule_id`/`detail` pairs (`R001: coverage
0.00 < 0.70`), meaningful in `specs/08-rubric.md`'s table, opaque on
the page. Added `RuleInfo`/`RULE_INFO` (`rubric/rules.py`, the module
that already owns rule semantics -- `check_r001`-`check_r013`, D42's
`has_unrecoverable_rubric_failure()`), one dict, text quoted directly
from spec 08's own table (and, for R010, the detail paragraph directly
below it), not paraphrased into something new. Considered parsing
`specs/08-rubric.md` live so the "one source" would be the file itself;
rejected -- nothing else in this codebase treats a spec file as runtime
data, and a 13-row, rarely-changing table doesn't earn a markdown
parser over a hand-transcribed constant with a comment pointing back at
spec 08 as the thing to keep it in sync with (same shape as
`_LIST_WINDOW_DAYS` importing `pipeline/batch.py`'s `WINDOW_DAYS`
rather than a second copy, D38). `queue_detail()`
(`web/app.py`) passes `RULE_INFO` into the template context (a plain
module import, no per-request computation); the template shows the
friendly name and one-line explanation alongside the existing terse
`detail` text, which stays -- "coverage 0.00 < 0.70" is real measured
signal, not replaced, just framed. Falls back to the bare `rule_id` for
any rule with no entry, rather than rendering blank or erroring.

**R012 and R013 are deliberately not in `RULE_INFO` yet.** Spec 08's
own text for both is too terse to build a real explanation from without
inventing content spec 08 doesn't provide: R012 ("zero speculative
bullets") is never explained anywhere in spec 08 (that context lives in
spec 01/03's bank-status/watermarking material); R013 ("slop linter
passes with zero errors") just points at spec 02's 17 separate rules
without summarizing any of them. Per explicit instruction, flagged
rather than guessed or silently pulled from a second document (spec
02) the user didn't name as a source. Real tension recorded for R013
specifically: it wraps spec 02's rules, so the *complete* answer for
"why did R013 fail" ultimately lives outside spec 08 either way --
whether R013's own `RULE_INFO` entry should be a generic pointer at
spec 02 (no invented content) or real per-rule text is the user's call,
not decided here. `RULE_INFO` currently has 11 of 13 entries; the
template's fallback means R012/R013 failures still render correctly
today, just without the added explanation, not broken.

Tests first (hard rule 7): `test_rubric.py` gained 4 (exact 11-key set,
every entry non-empty, spot-checks on R001's "0.70" and R010's
"Arial"); `test_web_app.py` gained 1, reusing the file's existing
`_EXTRACT_PAYLOAD` fixture (already a real R001-only failure) to assert
"Keyword coverage" renders alongside "R001". Full suite 504/504 (up
from 499), `ruff check`/`format --check` clean. Manually verified
against a real, production-shaped scratch copy (never the real db) on
the exact job this session's own routing investigation centered on:
job 4630's real, pre-existing R001 failure now renders "Keyword
coverage (R001): coverage 0.00 < 0.70" with the spec-08-sourced
explanation beneath it.

---

**D47. All 8 `job_resume_variants` rows re-checked against a real bank
retag (missing technology tags added -- PyTorch, SQL, others), 4
deleted for real, 4 re-rendered in place, after a read-only-first plan
and explicit confirmation per hard rule 13. Same shape as D45, but this
retag moves real rubric math (`coverage()` reads `bullet.keywords`
directly), so the before/after was computed and shown before anything
ran, not assumed identical the way D45's identity-only fix was.**

**Real before/after, computed read-only against the retagged bank
before any write, answered the actual question asked ("did the retag
fix the 0.00s or is something else also wrong") with a real, mixed
result, not a clean yes.** Of 8 real variants: 2 genuinely fixed off a
stale value (job 4109's software_engineer variant 0.25->0.50; job
2009's ai_ml_engineer variant, deleted this session, 0.0->0.50
pre-patch), 2 more improved but not closed, and **4 unchanged, for two
different real reasons:**

1. **Real, unrelated content gaps (variants for jobs 3950, 3904,
   3917).** Go/Terraform/SSO/SCIM/OAuth/OIDC/RBAC, JavaScript, and R
   were never in scope for an "add missing ML tool tags" retag -- the
   bank has no real work history in them. Tagging them without real
   content would be exactly the fabrication hard rule 2 exists to
   prevent; these need real new bank content (or stay logged in
   `gap_ledger`, already happening per D43) to ever close, not a tag.
2. **Two real, structural findings surfaced by the numbers themselves,
   not assumed -- both checked directly against the actual retagged
   bank before proposing anything:**
   - Job 3917 (`data_scientist`, needs SQL) stayed at 0.333 even though
     `SQL` is now tagged on `b_bantrly_01` -- because that bullet's
     `profiles` list is `['ai_ml_engineer', 'software_engineer']`, not
     `data_scientist`. `select_for_profile()` filters by profile
     membership before coverage is ever computed, so no amount of
     retagging elsewhere fixes this; only adding `data_scientist` to
     that bullet's own `profiles` list would, and whether that's
     correct (does that bullet's SQL usage genuinely belong on a
     data-scientist-framed resume?) is a real content judgment call,
     surfaced for a future session rather than decided here.
   - Job 4630 (`software_engineer`, needs PyTorch/TensorFlow/XGBoost/
     Spark) stayed at 0.000, and re-rendering it could not have changed
     that: `PyTorch` is correctly `ai_ml_engineer`-only in the bank
     (`b_utd_03`), not a retag gap. This is the same job D46's routing
     investigation already found: it genuinely matches both profiles,
     only `software_engineer` was ever reviewed, and ML-framework
     content structurally cannot appear on a `software_engineer`-tagged
     candidate by design. The real fix is reviewing `(4630,
     ai_ml_engineer)`, still sitting live in the queue -- not a data
     migration. Included in this session's delete set anyway (it was
     just as stale as the others), flagged so the unchanged 0.000 isn't
     mistaken for the retag or the re-render not working.

**Mechanics identical to D45, different, larger row set** (the real db
grew from 3 to 8 `job_resume_variants` rows between sessions from real
usage): 4 approved rows (ids 2, 8, 10, 13; jobs 3950/4109/4041/4306),
referenced by 4 real `applications` rows, re-rendered in place via
`patch.run_ladder()` called directly (same mechanism as D45, bypasses
`ensure_reviewed()`'s dedup lookup) and `UPDATE`d by id, `applications`
untouched; 4 pending rows (ids 11, 12, 14, 15; jobs 3904/3917/4630/2009)
deleted outright (`rubric_results` children first), nothing referenced
them. Checked the file-dedup gotcha D45 hit again before doing
anything -- this time clean, no approved row shared a physical file
with a row being deleted (variant 13 shared with variant 2, both
survived; variant 14 shared with variant 11, both deleted together),
so no special handling was needed, just confirmed rather than assumed.

**Run for real, with the real local model:** all 4 re-renders genuinely
re-attempted P3. Real result, matching the pre-patch prediction shown
in the plan exactly (coverage 0.10/0.50/0.50/0.333 for the four,
respectively) -- P3 closed nothing further this time, unlike the
prediction's own caveat that it might. **Unlike D45, `selection_hash`
changed for all 4** (expected and stated in the plan up front: P0's
reorder sorts bullets by keyword score, which the retag changed, so
even an unchanged bullet *set* can produce a different *order* and
therefore a different hash -- D45's hash staying identical was
specific to an identity-only change with zero keyword impact, not a
general property of re-renders). Verified after commit: `job_resume_
variants`/`rubric_results` count 4, `applications` still 4 and all FKs
resolve, `PRAGMA foreign_key_check` clean. Full backup of the real db
taken to scratchpad before any write, same as D45.

**Noted, not acted on:** `gap_ledger` gained no new rows from this
session's 4 re-renders, because P4 lives in `ensure_reviewed()` (D43),
not `run_ladder()`, and this operation deliberately calls `run_ladder()`
directly. The four jobs' original still-missing keywords (including
ones now resolved by the retag, e.g. job 4109's `SQL`) are already in
`gap_ledger` from when each was first reviewed, pre-retag --
`gap_ledger` has no "resolved" concept and isn't meant to (D43: an
append-only historical log, not a live worklist), so those rows stay
as an accurate record of what was missing at the time, not a bug or a
gap this session needs to close.

**A real regression the full-suite re-run caught, not assumed clean:**
2 of 504 tests failed after the retag --
`test_ensure_reviewed_logs_uncovered_keywords_to_gap_ledger` and
`test_ensure_reviewed_second_call_does_not_log_gap_ledger_again`
(`test_queue_orchestrate.py`). Root cause: both hard-code `_EXTRACT_
PAYLOAD = {"required_keywords": ["Go", "Kubernetes"], ...}` as a
controlled example of a fully-uncovered real gap against the *real*
bank (`load_bank()`, not a synthetic fixture) -- and the retag added a
genuine `Kubernetes` tag to `b_bantrly_01`, so the fixture went from
fully-uncovered to half-covered, breaking both tests' exact-2-keyword
assertions. Not a bug in D47's data operation or in the retag itself --
a real, correct side effect of the bank getting more accurate, caught
exactly the way the test suite is supposed to catch it. Fixed by
swapping the fixture to `["Go", "Rust"]`, re-confirmed still fully
uncovered against the retagged bank via `measure.missing_keywords()`
before using it, not reused blindly -- these are also D43's own #1 and
#2 real gap-frequency keywords (16 and 12 distinct jobs), if anything a
more representative real-world example than the original choice. Same
fixture is shared verbatim in `test_web_app.py` (no test there actually
failed, since none assert an exact keyword count, but the same stale
`["Go", "Kubernetes"]` value and a comment describing it as fully
uncovered were both there too) -- updated for consistency and
accuracy, not left silently out of sync with its sibling file. Full
suite re-confirmed green after the fix: 504/504, `ruff check`/`format
--check` clean on both touched test files.

**D48. `GET /` gains a third section, "Approved," sourced from
`applications` and deliberately unscoped by `_LIST_WINDOW_DAYS`,
closing the dead end D44 left open: an approved job had no list view
of its own, the only way to see what you'd applied to was a direct SQL
query against `data/jobengine.db`.**

Three decisions, all made explicit and confirmed before any code was
written, per the user's own instruction not to assume:

1. **Source of truth: `applications`, not `job_resume_variants.
   review_status = 'approved'`.** The two are 1:1 in practice today --
   `insert_application()`'s own docstring says a row is only ever
   created on review approval, `queue/orchestrate.py`'s `approve()` is
   the only call site -- but they are not the same concept.
   `pipeline/filter.py`'s `is_already_applied()` already keys off
   `applications`, not `review_status`, for exactly this "have I
   applied" question, and that is the existing precedent this decision
   follows rather than introducing a second, divergence-prone notion of
   "approved." `applications` also carries fields `job_resume_variants`
   doesn't (`status`, `submitted_at`, `autonomy_level`) that this
   section or a future one will want. Known caveat, already flagged as
   D44's own open item: `approve()` has no guard against firing twice
   for one variant, so `applications` could in theory hold more rows
   than approved variants once something automated (G3/G4) calls
   `approve()` more than once. Not a problem for this section --
   querying `applications` directly and rendering one row per
   application is the correct behavior regardless of whether that guard
   ever lands, not a workaround for its absence.
2. **No `_LIST_WINDOW_DAYS` scoping.** The other two `GET /` sections
   use the 7-day window to bound a scan over the whole `jobs` table for
   things not yet acted on. This section is the opposite: a small,
   bounded set of things already acted on, looked up directly via
   `applications` rows, never by scanning `jobs`. Filtering it by
   `first_seen_at` would silently drop an approved-but-unsubmitted job
   off the list after a week -- exactly the disappearing-job problem
   this section exists to fix, not a variant of it. `list_applications()`
   therefore takes no date argument at all, confirmed by a real test
   seeding a job with `first_seen_at` in 2020.
3. **`applications.status` renders as plain text, no filter or badge.**
   Every real row is `'queued'` today (confirmed via a live, read-only
   query against `data/jobengine.db`: 8/8 real applications rows), and
   nothing in the codebase writes any other value -- `approve()`
   hardcodes `status="queued"`. A filter or badge over a column with
   exactly one observed value is speculative UI for outcome tracking
   (the H-series) that doesn't exist yet, not a reasonable minimal
   feature.

**Implementation:** `db/models.py` gains `ApplicationEntry` (a
presentation-shaped model, mirroring `QueueEntry`'s own precedent) and
`list_applications()` -- `applications JOIN jobs JOIN job_resume_
variants`, `ORDER BY a.id DESC`, no `WHERE`. `web/app.py`'s
`queue_list()` calls it and precomputes a `{application_id:
docx_url}` dict via the existing `_resume_static_url()` (Jinja can't
call a Python module-level function directly, so this has to happen in
the route, not the template -- same reason `pdf_url`/`docx_url` are
already precomputed for `queue_detail()`). `queue_list.html` gains the
third table: title, company, profile, an `<a href>` apply link (or
`-` when `job.apply_url` is null, same convention `queue_detail.html`
already uses), a `.docx` download link, status text, and a link back to
the existing `/jobs/{job_id}/{profile}` detail page. The `.docx` link
was added after the user's review of the first draft of this plan,
which covered only the apply URL: the section's stated purpose is
"approved, still need to submit," and the résumé file is the other half
of what that requires -- without it, every row would still need a
click-through to the detail page just to get the file, defeating the
point of a list view.

7 new tests, tests-first per hard rule 7: `test_db.py` gains
`test_list_applications_empty_when_none`,
`test_list_applications_returns_joined_row` (asserts every field
`ApplicationEntry` exposes, including `docx_path`), and
`test_list_applications_not_scoped_to_a_recent_window` (a job seeded
with `first_seen_at="2020-01-01..."` still appears -- the regression
guard for decision 2). `test_web_app.py` gains
`test_list_page_shows_approved_entry_with_apply_and_resume_links`,
`test_list_page_omits_approved_entry_from_the_other_two_sections`
(re-confirms the existing D44 behavior still holds under the new
section, not just that the new section itself works),
`test_list_page_approved_entry_survives_outside_the_list_window`, and
`test_list_page_shows_no_approved_jobs_message_when_none`. Two of these
tests initially failed for an unrelated reason during writing: their
job titles ("Uniquely Titled Role", "Old Approved Role") didn't contain
"engineer", so `matches_profiles()` returned no match, `analyze_job()`
skipped the LLM call entirely, and `ensure_reviewed()`'s first line
(`analysis.required_keywords`) hit `AttributeError` on the resulting
`None` -- a real gap in `ensure_reviewed()`'s handling of a job that
matches no profile, surfaced by test authoring, not by design; fixed
by renaming the test fixtures' titles to contain "Engineer" rather than
patching `ensure_reviewed()`, since triggering a genuinely unmatched
profile was never this test's intent. Not filed as a new known issue
since every real call site already gates on `matches_profiles()`
returning a real profile before calling `ensure_reviewed()` (`_new_pairs()`
in `web/app.py`) -- this was a test-fixture-only path, not a reachable
production one.

No schema change (both tables and their join already existed), no new
dependencies, read-only against the real `data/jobengine.db` throughout
(only used for the live read-only counts quoted above, per hard rule
13). Verified against the real db: 8 real `applications` rows exist as
of this checkpoint, confirming the section has a real population to
render, not a hypothetical one. Full suite: 511 collected, 506 passing
-- the other 5 (`test_batch.py`) are a pre-existing failure on `main`,
confirmed via `git stash` before writing this up, unrelated to any file
this session touched. `ruff check`/`format --check` clean on every file
this session touched.

**D49. F1-followup: "Score and review" blocking on the full patch ladder
(LLM call, docx render, LibreOffice PDF conversion) inside a FastAPI
request, and the real "UNIQUE constraint failed: job_resume_variants.
job_id, profile" crash that request shape produces under a double
request. Closed via a claim-based mutex (`variant_claims`, new table)
plus extending `pipeline/batch.py` to prefetch every candidate pair's
ladder ahead of a human's click.**

Diagnosed first, before any design: `ensure_reviewed()`
(`queue/orchestrate.py`) was check-then-insert with the entire ladder in
between, and `web/app.py` builds exactly one `sqlite3.Connection` per
process (`check_same_thread=False`, `app.py`'s own documented reason:
FastAPI runs sync routes in a threadpool). Two concurrent requests for
the same `(job_id, profile)` -- a double-click, a reload mid-render, two
tabs -- both saw `existing is None`, both ran the ladder a second time
for nothing (including writing to the *same* output docx/pdf paths, a
silent corruption risk worse than the DB error), then raced the insert;
the loser hit the exact reported UNIQUE constraint failure, unhandled,
surfacing as a 500.

Two shapes were put to the user, with a recommendation and reasons, not
a default:

1. **(a) Background workers inside the web app** -- rejected. The dev
   workflow runs this app as `uv run uvicorn --reload`, which kills
   in-flight background work and any in-memory status on every reload
   during active development -- directly undermining "ready when I get
   to them," the exact case being fixed. It also duplicates scheduling
   logic (`pipeline/batch.py` already knows "which jobs are new, which
   pairs clear the floor") and introduces a second concurrent writer to
   the same connection needing its own locking story, on top of, not
   instead of, the request-thread race above.
2. **(b) Extend `pipeline/batch.py`'s existing incremental orchestrator,
   web app reads only** -- chosen. `batch.py` already exists for exactly
   this purpose (D38: "run on a schedule instead of never as a batch"),
   is already live on Task Scheduler, and is already incremental by
   construction. Adding a third stage (render the ladder for
   floor-clearing pairs) is the established pattern, not a new one. The
   local model call (P3) is Ollama, zero-cost per hard rule 9, so
   running it for every floor-clearing pair rather than only the ones
   clicked is not a paid-API concern -- flagged instead as a wall-clock
   cost (below).

Shape (b) means per-pair status (queued/processing/ready) has to live in
the db, not web-process memory, since the render can now happen in a
different process than the page load showing it. Three states:
`ready` (a `job_resume_variants` row exists, unchanged), `queued` (the
same candidate check `web/app.py`'s old `_new_pairs()` computed, now
`pipeline/batch.py`'s `list_candidate_pairs()` -- moved there and
reused by both the list page and the new render stage, one definition
of "candidate," matching `WINDOW_DAYS`' own single-source-of-truth
precedent, D38), and `processing` (an active `variant_claims` row).

**The race fix and the status mechanism are the same table.**
`variant_claims (job_id, profile, claimed_by, claimed_at)`,
`PRIMARY KEY (job_id, profile)`: `ensure_reviewed()` claims a pair
(`db/models.py`'s `claim_variant()`) before running the ladder --  the
`PRIMARY KEY` is the mutex itself, whichever caller's `INSERT` lands
first wins, a second caller gets `AlreadyProcessingError` immediately,
before doing any of the expensive work, never a second ladder run or a
second insert attempt. Re-checks for an existing variant a second time
immediately after winning the claim (closes a real, separate gap: the
caller that held the claim before you may have finished, inserted the
row, and released the claim in between your first check and winning the
claim yourself -- without this re-check you'd still run the whole ladder
for nothing and hit the same UNIQUE constraint on the insert below). The
claim is always released in a `finally`, success or failure, so an
exception mid-ladder never leaves a pair permanently claimed.

**Orphaned claims, addressed explicitly, not left to `finally` always
firing (the user's own framing, asked before any code):** a
`claimed_at`-based staleness threshold, `STALE_CLAIM_SECONDS = 600`
(`queue/orchestrate.py`), not a startup sweep. `claim_variant()`'s
fallback path (`INSERT` fails because something already holds the
pair) only succeeds if that existing claim's `claimed_at` is older than
the caller's own `stale_cutoff`; the `UPDATE ... WHERE claimed_at < ?`
form makes the reclaim itself atomic under SQLite's serialized writer
(a second concurrent reclaim attempt's `WHERE` no longer matches once
the first has bumped `claimed_at`). This self-heals on the very next
attempt at that pair -- no separate sweep process, no dependency on
which side crashed or whether `finally` ran. 600s was chosen against
every real measurement available, not a round-number guess: the local
model's real full-prompt latency is ~5.1s/call (D38, the closest real
analog to P3's rephrase call), a real PDF conversion measured live this
session at ~0.8s (`resume/pdf.py`'s `render_pdf()` timed 3x against a
real base resume docx, not estimated), and `pdf.py`'s own subprocess
call is hard-capped at 60s regardless. 600s is wide headroom above any
realistic ladder run (including a cold Ollama start, ~15-22s per
C1/D35) while still self-healing well within one scheduled batch window,
not hours later.

**Cost of the new, uncapped render stage, projected against real
numbers, not assumed, before scheduling anything unattended (same bar
D38 set for itself):** a real, read-only query against
`data/jobengine.db` (via `web/app.py`'s own `_new_pairs()` logic,
before it moved) found 41 real candidate pairs in the current backlog
(33 `software_engineer`, 6 `data_scientist`, 2 `ai_ml_engineer`), out of
478 open jobs in the 7-day window; since that backlog accumulated across
the full window, ~41/7 ~= 6 new candidate pairs/day is the projected
steady-state inflow. Per-pair cost: extraction is already done for
these jobs by batch's own earlier stage (job_analysis exists before the
render stage runs, so `ensure_reviewed()`'s own extraction check is a
no-op), so the added cost per pair is P0-P2 (deterministic, no model
call) plus up to 2 P3 rephrase calls (real evidence this is the common
case, not the exception: D42 found 66 of 67 real pairs fail R001 pre-
patch, 98.5%) at ~5.1s each, plus one PDF conversion at ~0.8s -- roughly
11s/pair realistic case. Projected: **first run after this ships, ~7-8
minutes added (clearing the 41-pair backlog) on top of whatever
relevance/extraction costs that run already pays; steady-state, ~1-2
minutes/day added** on top of D38's own ~3 min/day figure. Confirmed
uncapped is still the right call (matches `daily_cap: null`'s existing
philosophy, D23, and this runs unattended overnight where wall-clock
time doesn't block the user) via `AskUserQuestion`, alongside two other
confirmed calls: the on-demand detail route returns a 202 wait/retry
page rather than blocking the request thread when it hits a claimed
pair (simpler, never ties up a thread for the ladder's duration), and
`claimed_by` ('web' vs 'batch') stays a debug-only column, not surfaced
in the UI (matches D48's own "no speculative UI" precedent).

**Implementation:** `db/schema.sql` gains `variant_claims`
(`_SCHEMA_VERSION` bumped to `"0003_variant_claims"` in `migrate.py`,
purely additive -- `init()`'s `executescript` picks it up via
`CREATE TABLE IF NOT EXISTS`, no rebuild needed, unlike the
`job_resume_variants` migration F1 needed). `db/models.py` gains
`claim_variant()`/`release_claim()`/`list_claims()` (the claim
mechanics, each commits immediately -- unlike this module's usual
caller-commits convention -- because the claim only works as a
cross-process mutex if a claim made on one connection is visible to a
different connection's next attempt right away) and
`list_recent_open_jobs()` (the cutoff query moved out of `web/app.py`'s
old `_recent_open_jobs()`, now `datetime('now', ?)`-based to match
`list_unscored_open_jobs()`'s own existing style instead of Python-side
arithmetic). `queue/orchestrate.py`'s `ensure_reviewed()` gains a
`claimed_by: str = "web"` keyword-only param and the claim/re-check/
release logic described above; new `AlreadyProcessingError`.
`pipeline/batch.py` gains `list_candidate_pairs()` (the moved
`_new_pairs()` logic, shared) and a fourth stage in `run_daily_batch()`
that calls `ensure_reviewed(..., claimed_by="batch")` for every
candidate pair, skipping (not failing the run) on `NoBaseResumeError` or
`AlreadyProcessingError`; `BatchResult` gains `variants_rendered`.
`web/app.py`'s `queue_list()` splits candidates into `queued_pairs`/
`processing_pairs` via `list_claims()`; `queue_detail()` catches
`AlreadyProcessingError` and returns a new `processing.html` template at
202 instead of running the ladder. `queue_list.html` gains a Status
column (Queued/Processing) in the "not yet reviewed" table.

23 new tests, tests-first per hard rule 7: `test_db.py` +8 (claim/
reclaim/release round trips, `list_recent_open_jobs()`'s window
inclusion/exclusion/closed-job cases), `test_queue_orchestrate.py` +5
(`AlreadyProcessingError` raised with zero new ladder calls when a
fresh claim is held, a stale claim is reclaimed and the ladder
completes, the claim is released after both success and a simulated
mid-ladder exception, `claimed_by` defaults to `"web"`),
`test_batch.py` +5 (`list_candidate_pairs()` includes a floor-clearing
pair / excludes one below the floor, the render stage renders a
variant / skips a pair with no `base_resumes` row / skips a pair
already claimed), `test_web_app.py` +3 (the list page's real "Queued"/
"Processing" text, the detail route's 202 with zero new ladder calls
when claimed). Migration verified against a scratch db (never the real
one, per hard rule 13): idempotent across two `migrate()` calls,
`variant_claims` present afterward. Full suite: 532 collected, 527
passing -- the same 5 pre-existing `test_batch.py` failures already
documented (a stale relative-date fixture, unrelated), confirmed
unchanged by this session's work. `ruff check`/`format --check` clean
on every file this session touched.

**Not yet done, flagged rather than silently assumed:** the real
`data/jobengine.db` is still on schema version `0002` as of this
checkpoint -- `migrate()` was run only against scratch copies this
session, per hard rule 13, never against the real path. The code as
shipped will raise (no `variant_claims` table) if run against the real
db before `uv run python -m jobengine.db migrate` is run there with
explicit confirmation. See PROGRESS.md's Known Issues.
