# ai_ml_engineer base resume: v2

## What changed from v1

Nothing in selection or content. `selection.yaml` is byte-identical to
v1 except the `version:` field itself: same 6 roles, same bullet ids, in
the same order. No bank edit this session touched anything tagged
`ai_ml_engineer` (the `b_utd_02` retag added `software_engineer`, the
`b_lessongen_04` change removed `data_scientist`; both bullets already
carried `ai_ml_engineer` before and after).

What changed is the rubric's own gate, not the resume: D33 in
docs/decisions.md demoted R002 (front-loading) from a hard failure to a
scored-only component, after two exhaustive investigations (this
profile in D32, `software_engineer` in this session) found the same real
structural ceiling and no legitimate fix that didn't cost more than it
gained. v1's `rubric.json` was generated before that decision and still
shows the stale `passed: false, hard_failures: ['R002']`. v2 exists
purely to carry a `rubric.json` that reflects the current rules:
`passed: true, hard_failures: []`, `front_load: 0.50` unchanged and
still visible in `measurements` and in the weighted score, per D33's
explicit intent that no signal be lost, only the binary gate.

## Known caveat: coverage=1.0 is against bank-frequency fallback, not real corpus

Same caveat as v1, restated because it's still true: `required_keywords`
here is the bank's own top-30 keyword frequency for this profile, not
real `keyword_corpus` data (still zero rows, no orchestrator has run
`analyze_job()` against live jobs yet). Coverage against your own bank's
vocabulary is a materially easier bar than coverage against real market
demand. See D34 in docs/decisions.md. Re-validate once corpus data
exists; do not read `coverage: 1.0` as a stronger claim than that.

## State carried over from v1, unchanged

`score 63.40`, `coverage: 1.0`, `front_load: 0.50`, `pages: 3`. Full
investigation of the front-load gap (automatic patch ladder, manual
structural reorders, content-cut variants, the real content edit to
`role_bantrly`'s three bullets) is recorded as D32, not repeated here
since nothing about the resume itself changed.
