# Spec 06: Relevance Pre-Filter (Stage 2.5)

## Why this stage exists

Without local inference, the deterministic filters in stage 2 have to be
aggressive enough to cut straight to 20-40 jobs, because everything past that
gate costs money. That forces you to guess thresholds and throw away jobs you
never looked at.

With a free local model you invert it: loosen stage 2 to let 300-500 jobs
through, score every one, and pass only the top N to the paid pipeline. You
see a much wider net for the same spend.

This stage is optional by design. If local inference is unavailable, it is
skipped and the deterministic filters tighten automatically.

## Module
`src/jobengine/pipeline/relevance.py`

## Input
Every job surviving stage 2, with `first_seen_at` inside the freshness window.

## Per job

One local call, schema-constrained, per profile the job's title could plausibly
match. Input is the JD (truncated to 6k tokens) plus a compact profile card:
target titles, top 30 corpus keywords, seniority band, location rules.

Do **not** send the bullet bank. This stage judges the job, not the fit of
specific bullets, and keeping input small is what makes 400 calls a night
viable.

## Output schema

```json
{
  "profile": "ai_ml_engineer",
  "relevance": 0-100,
  "seniority_match": "under" | "match" | "over",
  "keyword_hits": ["..."],
  "disqualifiers": ["requires active security clearance", "10+ years required"],
  "one_line": "why this scored what it scored"
}
```

## Hard disqualifiers

Anything in `disqualifiers` matching the configured blocklist forces a score
of 0 regardless of the model's number. Clearance requirements, years-of-
experience floors above your band, and on-site-only in a city you will not
move to are deterministic facts, not judgment calls. The model surfaces them;
code decides.

## Ranking and cutoff

Sort by relevance, take the top N per the daily cap. Ties break by
`first_seen_at` ascending, because a fresher posting is worth more than a
marginally better match. That tiebreak is the whole thesis of the project
expressed as one line of code.

Everything scored but not selected is retained with its score. Two reasons:
the dashboard can show you what you nearly saw, and if the paid pipeline has
spare budget the next day, yesterday's near-misses are already ranked.

## Calibration

The score is meaningless until validated. Build this check in from the start:

`uv run python -m jobengine.pipeline.relevance calibrate` samples 20 scored
jobs across the range, prints JD title plus score plus the one-line reason,
and asks you to agree or disagree. Store your verdicts. If agreement is below
70%, the prompt is wrong and the stage is doing damage rather than filtering.

Re-run calibration after any prompt change. This is the cheapest quality
control in the system and the easiest to skip.

## Cost

Zero marginal cost, roughly 400 calls a night at 6k input tokens each. On a
laptop 4060 at ~50 tok/s generation with short outputs, expect the run to be
prompt-processing bound. Budget 15 to 30 minutes wall clock. It runs overnight,
so this does not matter, but do not run it synchronously in front of a user.

## Definition of done
A full night's run scores every stage-2 survivor, the top N match what you
would have picked by hand on a spot check, and `calibrate` reports above 70%
agreement.
