# data_scientist base resume: v1

First version. No v0 to diff against, so this entry records what v1
*is* and the content decision behind it, not a diff.

## Selection

`measure.select_for_profile(bank, "data_scientist")`'s output, rendered
in the bank's own natural role/bullet order. No patch ladder (P0-P2)
applied. See `selection.yaml` for the exact role/bullet id list.

Roles included: `role_bantrly`, `role_utd_researcher`, `role_sei`,
`role_unl`, `role_ju` (work history), `role_docintel` (projects). 6
roles, not 7: `role_bantrly_lessongen` is absent entirely (see below).
Section order: work_history, projects, education, publications, per
`config/profiles.yaml`'s current default.

## Content decision: `role_bantrly_lessongen` dropped from this profile

Started this session tagged to `data_scientist` via only its untagged
summary plus `b_lessongen_04` (CCSS skill taxonomy, coverage tracking) —
2 total entries, below R003/R013's 3-8 floor. All 5 bullets on that role
were reviewed for content before deciding: the other four
(guardrail/content-safety logic, defensive JSON validation, a Gradio UI
deployment) all read as system/application engineering, not analysis or
measurement work, so none was a genuine second `data_scientist` entry.
Rather than force a second, misleading tag onto content that doesn't fit,
`b_lessongen_04`'s `data_scientist` tag was removed instead:
`[ai_ml_engineer, data_scientist]` -> `[ai_ml_engineer]`. With zero
tagged bullets left for this profile, `select_for_profile()` drops the
role entirely (confirmed live: it does not appear with a bare summary
line, per its own docstring). Verified the role is absent from the
candidate before generating this version.

Side effect, not the goal: dropping the role also dropped page count
from 3 to 2, which moved the score beyond what the R003/R013 fix alone
would explain (score.py's page-count penalty applies above 2 pages).

## Known state: R002 (front-load) is a scored deficit, not a gate

`score 66.96`, `passed: true`, `hard_failures: []`. R002 (front-load)
was already demoted to a scored-only component this session (D33,
docs/decisions.md) before this profile was ever scored, so it never
appeared as a hard failure here. `front_load: 0.40` is visible in
`measurements` and weighted at 25/100 in the score regardless.
`coverage: 1.0`, R003/R013 both pass clean across all 6 remaining roles.

## Known caveat: coverage=1.0 is against bank-frequency fallback, not real corpus

`required_keywords` used for this scoring is the bank's own top-30
keyword frequency for this profile, not real `keyword_corpus` data
(zero rows today, no orchestrator has run `analyze_job()` against live
jobs). Coverage against your own bank's vocabulary is a materially
easier bar than coverage against real market demand. See D34,
docs/decisions.md. Re-validate once corpus data exists.
