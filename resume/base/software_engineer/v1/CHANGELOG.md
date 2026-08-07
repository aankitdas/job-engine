# software_engineer base resume: v1

First version. No v0 to diff against, so this entry records what v1
*is* and the two real content edits behind it, not a diff.

## Selection

`measure.select_for_profile(bank, "software_engineer")`'s output,
rendered in the bank's own natural role/bullet order. No patch ladder
(P0-P2) applied: role and bullet order are exactly as declared in
`resume/bank/aankit.yaml`. See `selection.yaml` for the exact role/
bullet id list.

Roles included: `role_bantrly`, `role_utd_researcher`, `role_sei` (work
history), `role_bantrly_lessongen`, `role_docintel` (projects). Section
order: work_history, projects, education, publications, per
`config/profiles.yaml`'s current default.

## Content edit: `b_utd_02` retagged onto this profile

`role_utd_researcher` started this session tagged to `software_engineer`
via only its untagged summary plus `b_utd_05` (Hydra hyperparameter
sweep automation) — 2 total entries, below R003/R013's 3-8 floor. All 5
bullets on that role were reviewed for content before deciding: `b_utd_02`
(processing and managing 1,600 CMB simulated maps across train/val/test
splits) was the least ML-research-specific of the remaining four and
reads as data-pipeline engineering, not model architecture or academic
publication framing (`b_utd_01`, `b_utd_03` do read that way).
Retagged `[ai_ml_engineer, data_scientist]` -> `[ai_ml_engineer,
data_scientist, software_engineer]`. Brings the role to 3 entries for
this profile, clearing R003/R013 with zero fabricated content.

## Known state: R002 (front-load) is a scored deficit, not a gate

`score 66.87`, `passed: true`, `hard_failures: []`. R002 was demoted
from a hard failure to a scored-only component this session (D33,
docs/decisions.md) after this profile hit the same real structural
ceiling `ai_ml_engineer` hit in D32: `front_load 0.40`, automatic patch
ladder and manual reorder investigation found no fix that doesn't cost
more than it gains. `front_load: 0.40` remains fully visible in
`measurements` and still weighted at 25/100 in the score. `coverage:
1.0`, R003/R013 both pass clean.

## Known caveat: coverage=1.0 is against bank-frequency fallback, not real corpus

`required_keywords` used for this scoring is the bank's own top-30
keyword frequency for this profile, not real `keyword_corpus` data
(zero rows today, no orchestrator has run `analyze_job()` against live
jobs). Coverage against your own bank's vocabulary is a materially
easier bar than coverage against real market demand. See D34,
docs/decisions.md. Re-validate once corpus data exists.
