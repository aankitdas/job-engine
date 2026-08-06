# ai_ml_engineer base resume: v1

First version. No v0 to diff against, so this entry records what v1
*is* and the one real content edit behind it, not a diff.

## Selection

`measure.select_for_profile(bank, "ai_ml_engineer")`'s output, rendered
in the bank's own natural role/bullet order. No patch ladder (P0-P2) is
applied to this version: role and bullet order are exactly as declared
in `resume/bank/aankit.yaml`, not reordered for front-loading. See
`selection.yaml` for the exact role/bullet id list.

Roles included: `role_bantrly`, `role_utd_researcher`, `role_unl`,
`role_ju` (work history), `role_bantrly_lessongen`, `role_docintel`
(projects). Section order: work_history, projects, education,
publications, per `config/profiles.yaml`'s current default (not yet
customized per profile, see D31 in docs/decisions.md).

## Content edit

Three bullets on `role_bantrly` (`b_bantrly_02`, `b_bantrly_03`,
`b_bantrly_04`) were tightened for length ahead of this version:
shorter phrasing, every fact and every already-tagged keyword
preserved, no new claims. This is the first-ever edit to the
hand-authored `resume/bank/aankit.yaml`. Full before/after text and the
verification (`validate_rewrite()`, real slop-lint pass, real line
counts) are in D32, docs/decisions.md.

## Known state: R002 ships as a soft-fail

`score 63.40`, `passed: false`, `hard_failures: ['R002']`
(`front_load 0.50`, needs `0.75`). `coverage: 1.0` (spec 09's actual
DoD metric) and R003/R013 pass clean. This was investigated
exhaustively, not left unexamined: the automatic patch ladder, three
manual structural reorders, and two content-cut variants were all
real-scored before concluding the gap isn't cheaply closeable without
either cutting real content or accepting a net loss of other passing
keywords. Full investigation and the ship rationale (mirrors C3's D27
decision: the rubric is directional pressure, not a hard gate, and this
score travels with the resume via the review queue rather than being
hidden) are recorded as D32 in docs/decisions.md.

## Required keywords used for this scoring

Top 30 by the bank's own keyword frequency for this profile (`keywords_
corpus` has no rows yet — no daily orchestrator has populated it against
real jobs; see the Known Issues in PROGRESS.md under C3/E1). See
`rubric.json` for the exact list and full measurement detail.
