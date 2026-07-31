# Spec 01: Bullet Bank

## Goal
A YAML schema plus loader and validator holding every claim that may ever
appear on a generated resume. This is the trust boundary of the whole system.

## Module
`src/jobengine/resume/bank.py`. Data at `resume/bank/aankit.yaml`.

## Schema

```yaml
meta:
  owner: "Aankit Das"
  updated: "2026-07-31"

education:
  - id: edu_utd
    degree: "MS"
    field: "Computer Engineering"
    institution: "University of Texas at Dallas"
    gpa: "3.8/4.0"
    status: "May 2025"        # year if within 3 yrs, else "Status - Graduated"
    requires_degree_profiles: [ai_ml_engineer, data_scientist]

certificates: []

roles:
  - id: role_bantrly
    company: "Bantrly"
    location: "Texas"
    start: "2026-03"
    end: null                  # null renders "to Present"
    kind: full_time            # full_time | internship | research | project
    title:
      default: "AI Engineer"
      ai_ml_engineer: "AI Engineer"
      software_engineer: "Software Engineer, AI Platform"
      data_scientist: "Machine Learning Engineer"
    summary:                   # Lee's mandatory first bullet, plain English
      - id: b_bantrly_sum
        text: "Built the speech and language systems behind a K-12 learning
               app by turning student audio into text and scoring it against
               teaching rubrics"
        keywords: [Python, FastAPI, speech-to-text, LLM]
        status: verified
    bullets:
      - id: b_bantrly_01
        status: verified       # verified | speculative
        what: "modular speech-to-text routing engine"
        how: "separated transcription from LLM scoring across 8 assessment modules"
        result: "cut audio API costs and improved scoring rubric accuracy"
        text: "Built a modular speech-to-text routing engine in Python and
               FastAPI that separated transcription from LLM scoring across 8
               K-12 assessment modules, cutting audio API costs and improving
               rubric accuracy"
        keywords: [Python, FastAPI, LLM, speech-to-text, API design]
        evidence: "internal"   # or a URL; required when status is verified
        profiles: [ai_ml_engineer, software_engineer]

publications:
  - id: pub_ieee_lang
    text: "..."
    authors_bold: "Das, A."
    venue: "IEEE Access"
    url: "..."
```

## Rules the validator enforces

1. Every `bullets[].id` is globally unique.
2. `status: verified` requires a non-empty `evidence`.
3. `status: speculative` requires `evidence: null` and is flagged in output.
4. `what`, `how`, and `result` are all present and non-empty. Lee's format is
   What + How + Result/Reason; a bullet missing one is incomplete.
5. `text` contains at most one period (Lee's rule).
6. `text` is past tense. Heuristic check: first word ends in `ed` or is in an
   irregular-verb allowlist (Built, Led, Wrote, Ran, Drove, Made, Set, Cut,
   Grew, Shipped, Won, Chose, Sent, Held, Kept, Found, Taught, Brought).
7. `text` estimated at most 3 rendered lines at Arial 10.5 on a 7.5in column.
   Approximate at 105 characters per line; warn above 315 characters.
8. Every role has exactly one `summary` entry.
9. Every role has between 3 and 8 total bullets including the summary.
10. Every keyword appears in at least one bullet, or it is dead weight.

## Seeding from the CV

The bank is built once, by hand, from `Aankit_CV.pdf`. Two known issues in the
source that must be resolved during seeding:

- The CV uses em dashes heavily. Every one must go, rewritten not just
  replaced, or the linter will reject the bullet downstream.
- Data conflicts to resolve: BTech date (Sept 2020 in the docx vs Dec 2020 in
  the CV), citation count (130+ vs 140+), and the typo "October 202".
- Job titles differ between the CV and the docx ("AI Engineer" vs "Jr AI
  Scientist", "Machine Learning Researcher" vs "Machine Learning Engineer").
  These become deliberate per-profile `title` overrides, not drift.

## CLI
```
uv run python -m jobengine.resume.bank validate
uv run python -m jobengine.resume.bank stats --by-keyword
uv run python -m jobengine.resume.bank coverage --profile ai_ml_engineer
```

`coverage` cross-references the bank against `keyword_corpus` and prints which
corpus keywords have no backing bullet. That is the gap ledger's static twin
and it is the most useful command in the repo.

## Definition of done
`validate` returns zero errors on the real bank and prints a per-profile
bullet count. `tests/test_bank.py` covers each of the ten rules with a failing
fixture.
