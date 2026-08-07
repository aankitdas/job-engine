# Spec 08: Deterministic Rubric and Patch Ladder

This replaces the LLM critic. It is the core of the system.

## Module
`src/jobengine/rubric/` with `rules.py`, `score.py`, `patch.py`,
`measure.py`.

## Input
A rendered resume (docx and its PDF), the profile it was built for, and the
target job's extracted keyword set.

## Output
```json
{
  "passed": true,
  "score": 87,
  "hard_failures": [],
  "deficits": [
    {"rule": "R001", "detail": "coverage 0.62 < 0.70",
     "missing": ["Kubernetes", "Airflow", "A/B testing"]}
  ],
  "measurements": {"coverage": 0.62, "front_load": 0.80, "pages": 2}
}
```

## Hard rules (any failure blocks the resume)

| ID | Rule | How measured |
|---|---|---|
| R001 | Required-keyword coverage >= 0.70 | set intersection, case and stem normalized |
| R002 | >= 0.75 of the profile's top 10 corpus keywords in the top half of page 1 | see Front-loading below |
| R003 | Every role has 3 to 8 bullets including the summary | count from selection |
| R004 | Every role has exactly one summary bullet | bank structure |
| R005 | Every bullet contains at most one period | regex |
| R006 | Every bullet renders in 3 lines or fewer | see Line measurement |
| R007 | Every bullet is past tense | shared heuristic with the bank validator |
| R008 | No first-person pronouns | regex on word boundaries |
| R009 | Roles in reverse chronological order | date sort check |
| R010 | Typography matches the golden spec | docx XML inspection |
| R011 | Single column | no tables or text boxes in the body |
| R012 | Zero speculative bullets | bank status check, cannot be suppressed |
| R013 | Slop linter passes with zero errors | spec 02 |

R010 checks: Arial everywhere, sizes 14 / 12 / 10.5, spacing 1.15 in the
header block and 1.5 in the body, margins 0.5in all sides, exactly one right
tab stop at 7.5in, left alignment not justified.

## Score (0-100, advisory)

Weighted, used for ranking and for the dashboard, never as a gate on its own.

| Component | Weight |
|---|---|
| Keyword coverage (continuous, not the R001 threshold) | 40 |
| Front-loading ratio | 25 |
| Keyword density in the first role | 15 |
| Bullets carrying two or more keywords | 10 |
| Page count penalty above 2 pages | 10 |

Track score against real outcomes in the dashboard. If after 50 applications
the score does not separate responses from silence, the weights are wrong and
you have the data to fix them. That feedback loop is the reason the score
exists at all.

## Front-loading measurement

Lee's target is 75% of your keyword list in the first half of page one. That
requires real geometry, not a guess.

Render to PDF, extract text with per-token bounding boxes (`pdfplumber`), take
page 1, and treat "first half" as `y < page_height / 2` in the same coordinate
space. Match keywords case-insensitively with simple stemming. Report the
ratio of top-10 profile keywords whose first occurrence falls above the line.

Cache the extraction per rendered file hash so repeated scoring is free.

## Line measurement

R006 needs rendered lines, not characters. Two options:

1. Preferred: measure from the PDF. Count distinct baseline y-values within a
   bullet's bounding box. Exact.
2. Fallback when no PDF: estimate at 105 characters per line for Arial 10.5
   on a 7.5in column and warn rather than fail above 315 characters.

Use option 1 in the pipeline. Option 2 exists so the bank validator can run
without a render.

## Patch ladder

Given a deficit list, attempt in order and stop at the first that clears all
hard rules. Every tier re-runs the full rubric afterward.

### P0: reorder (free)
Sort bullets within each role by count of this job's keywords, descending,
subject to R004 keeping the summary first. Sort roles only if two are
concurrent. Never break R009.

### P1: swap (free)
For each missing keyword, find bank bullets carrying it that are not currently
selected. Swap the lowest-scoring selected bullet in that role for the highest
-scoring candidate, subject to R003. Prefer swaps in the first role, since
they help R002 as well as R001.

### P2: promote (free)
If a missing keyword only appears in a project or role currently below the
fold, move that item up within its section, or move the whole section up if
the profile's section order permits. Respects R009 for work history; projects
have no chronological constraint.

### P3: rephrase (local model, ~400 tokens in, ~100 out)
Only when P0 through P2 leave hard failures. Pick the one selected bullet with
the most room (fewest keywords, shortest rendered length) and ask for a
rewrite that naturally incorporates one or two missing keywords.

Constraints on the call:
- Input is the single bullet's what/how/result fields, the target keywords,
  and the rules. Never the whole bank, never the JD text.
- Output is schema-constrained: `{"text": "...", "keywords_added": [...]}`.
- Result must pass the slop linter and R005 through R008 or it is discarded.
- Maximum two P3 calls per job. After that, go to P4.
- **The rewrite must not introduce a claim absent from the parent bullet's
  what/how/result.** Validate by checking that no new proper noun, number, or
  technology appears that is not in the parent or in `identity.toml`. A
  keyword may only be added if the bank bullet's `keywords` list already
  contains it or the keyword names something the parent already describes.

On success, write the result back to the bank as a variant:

```yaml
- id: b_bantrly_01
  text: "..."                 # the canonical phrasing
  variants:
    - text: "..."
      keywords_added: [Kubernetes]
      created_at: "2026-08-03"
      used_count: 4
```

The selector prefers an existing variant over a new P3 call. The bank
accumulates phrasings that worked and P3 fires progressively less often.

### P4: accept and log
Write every still-missing keyword to `gap_ledger` with the job id. Mark the
variant `passed: false, accepted: true` if the deficit is soft, or skip the
job entirely if a hard rule other than R001 still fails.

## Storage

New table `job_resume_variants`: id, job_id, profile, base_resume_id,
patch_tiers_applied (JSON), bullet_ids (JSON ordered), docx_path, pdf_path,
score, coverage, front_load, passed, review_status, reviewed_at, created_at.
Row uniqueness is (job_id, profile), enforced by
`idx_job_resume_variants_job_profile`, not by the hash below.

Deduplicate on (base_resume_id, bullet_ids hash), but only at the file
level: before rendering, the caller (F1's `queue/orchestrate.py`) checks
whether an existing row already has this exact (base_resume_id, hash)
pair and, if so, reuses that row's docx_path/pdf_path instead of
rendering again. Two jobs whose patches produce identical selections
share one rendered file, but each still gets its own row, since job_id
is required on every row.

## CLI
```
uv run python -m jobengine.rubric score <pdf> --profile ai_ml_engineer --job 1234
uv run python -m jobengine.rubric patch --job 1234 --dry-run
uv run python -m jobengine.rubric explain R002 --job 1234
```

`explain` prints the geometric measurement with the actual y-coordinates. You
will need it the first time R002 fails for a reason you do not believe.

## Definition of done
Scoring the current base resume against three real JDs produces plausible
coverage numbers you agree with by hand. The patch ladder closes at least one
real deficit at P1 without any model call. `tests/test_rubric.py` has a
failing fixture per hard rule.
