# Spec 02: Slop Linter

## Goal
A deterministic gate on generated resume text. Two rule classes: AI-tell
detection and Headless-Headhunter compliance. Exit non-zero on any error.

## Module
`src/jobengine/resume/slop_lint.py`, runnable as
`python -m jobengine.resume.slop_lint <path-or---changed>`.

## Rule class 1: AI tells (ERROR)

- `S001` em dash or en dash used as punctuation. Any of U+2014, U+2013,
  or the ASCII patterns ` -- `, ` - ` between clauses.
- `S002` banned vocabulary, case-insensitive, word-boundary matched:
  leverage, spearhead(ed), utilize, robust, seamless, cutting-edge, delve,
  tapestry, testament, underscore, pivotal, showcase, harness, elevate,
  streamline, navigate (figurative), realm, landscape (figurative),
  meticulous, comprehensive, holistic, synergy, empower, unlock, foster.
- `S003` contrast constructions: `not just X, but Y`, `it's not about X,
  it's about Y`, `X isn't just Y`.
- `S004` gerund triads: three or more comma-separated clauses each opening
  with a present participle.
- `S005` hedges: "helped to", "worked to", "aimed to", "sought to".
- `S006` the word "various" or "several" where a number would do.

Note S002 includes "spearheaded" and "streamline", both currently in the CV.
That is intentional; those bullets get rewritten during seeding.

## Rule class 2: Methodology compliance (ERROR)

- `H001` more than one period in a bullet.
- `H002` bullet exceeds 3 estimated rendered lines (>315 chars).
- `H003` bullet is not past tense (same heuristic as the bank validator).
- `H004` role has fewer than 3 or more than 8 bullets.
- `H005` role is missing its summary bullet.
- `H006` summary bullet contains jargon: flags any token in a configurable
  jargon list not also present in a plain-English allowlist.
- `H007` first-person pronouns (I, my, we, our).
- `H008` any bullet not traceable to a bank ID.

## Rule class 3: Warnings (non-blocking)

- `W001` keyword coverage below 0.75 for the target profile.
- `W002` fewer than 75% of the profile's top keywords appear in the first
  half of page one (Lee's front-loading target).
- `W003` a `speculative` bullet is present in a preview render.

## Hard block

`speculative` bullets in a non-preview render are `E999`, which is fatal and
cannot be suppressed by config, CLI flag, or environment variable.

## Output

Human-readable by default; `--json` for programmatic use. Exit codes: 0 clean,
1 warnings only with `--strict`, 2 errors present.

## Integration
Wired as the Claude Code `PostToolUse` hook on `Edit|Write`, so failures feed
back into the session automatically.

## Definition of done
`tests/test_slop_lint.py` has one failing fixture per rule and one clean
sample that passes all of them. The clean sample is a real bullet from the
bank, so the test doubles as a regression check on the bank itself.
