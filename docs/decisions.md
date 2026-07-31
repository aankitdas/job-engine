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

**D4. SQLite. The spreadsheet is an export, not a system of record.**

**D5. Resume content is data; rendering is deterministic.**

**D6. The anti-slop rule is a linter, not a prompt instruction.**
Wired as a PostToolUse hook so failures feed back automatically.

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
