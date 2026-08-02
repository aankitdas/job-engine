# Decision Record

Revision 2.

---

**D1. Query ATS APIs directly instead of scraping aggregators.**
Greenhouse and Ashby publish free unauthenticated JSON. Scraping means
proxies, 429s, and constant breakage for worse data.

**D2. Company slugs are a maintained registry, not a search.**
Neither API supports cross-company search. Curated seed plus bulk harvest,
validated weekly, dead slugs marked rather than retried.

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
