# Job Engine

Personal job search pipeline. Fetches jobs from Greenhouse and Ashby public
APIs, scores them against a deterministic rubric, patches a per-title base
resume when needed, and queues results for review and application.

## Commands
- Tests: `uv run pytest`
- Lint: `uv run ruff check src/ && uv run ruff format src/`
- Slop linter: `uv run python -m jobengine.resume.slop_lint <file>`
- Dev server: `uv run uvicorn jobengine.web.app:app --reload`

## Hard rules

1. Never write to `identity.toml`. Read-only to all code and to you.
2. Never invent resume content. Every bullet must trace to `resume/bank/*.yaml`.
   Uncovered JD keywords go to the gap ledger, not into a new bullet.
3. The slop linter is a gate. Fix the content, never the linter.
4. The LLM never touches layout. Content is data; rendering is deterministic.
5. No new dependencies without asking me first.
6. Read the spec before implementing. Ambiguity means ask, not guess.
7. Tests before implementation for anything in `pipeline/`, `resume/`, `rubric/`.

## Style
- Python 3.12, type hints everywhere, pydantic at boundaries.
- No em dashes anywhere, including comments and docstrings.
- Boring explicit code over clever code.

Append these to the existing CLAUDE.md from SETUP.md.

## Session protocol

- **Start of every session: read PROGRESS.md.** It is the source of truth for
  what exists. Do not assume anything from a previous session persists in
  context.
- **End of every session: run `/checkpoint`.**
- Work one TODO.md item at a time. Do not start the next one without asking.

## Additional hard rules

8. All LLM calls go through `jobengine.llm.router`. Never call a provider SDK
   directly.
9. **Never construct an Anthropic provider.** The daily pipeline is zero-cost
   by design. If you believe a stage needs a paid call, stop and ask.
10. Never write `ANTHROPIC_API_KEY` into any file, shell profile, .env, or
    docker-compose. Claude Code prioritizes that variable over subscription
    auth and it will silently move interactive sessions onto metered billing.
11. The rubric is deterministic. If you are tempted to ask a model whether a
    resume is good, you are solving the wrong problem: express it as a rule in
    `specs/08-rubric.md` instead, or ask me.
12. P3 rephrases must not introduce any proper noun, number, or technology
    absent from the parent bullet. Validate this in code, not in the prompt.
