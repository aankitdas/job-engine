# Spec 07: Local Model Evaluation

Revision 2. Two tasks, not four. Tailoring and critic evaluation are gone
because neither is an LLM job any more.

## Why

"Which local model can do this" should be a number. Both remaining LLM stages
have objectively checkable outputs, so model choice is measurable rather than
argued. The harness transfers unchanged to the DGX Spark.

## Module
`src/jobengine/eval/` with `harness.py`, `tasks/`, `report.py`.

## Fixture set

Built once, at `tests/fixtures/eval/`.

- **50 real JDs** from a live sync, spanning all three profiles and a
  deliberate spread of quality, including some without a clear requirements
  section (Lee's "bad JDs").
- **Your relevance labels**, 0-100 per profile, for all 50.
- **Your hand-extracted required-keyword lists** for 15 of them.

Labelling takes about an hour. It is the highest-value hour in the project,
because it converts every future model question from an argument into a
twenty-minute measurement.

## Task 1: Relevance scoring

Metrics: Spearman rank correlation against your labels, plus top-30 set
overlap. Overlap is the one that matters, since the pipeline only consumes the
top N.

Pass: rho >= 0.70, top-30 overlap >= 0.75.

Below that, try two different prompts before blaming the model.

## Task 2: Keyword extraction

Metrics: precision and recall against your hand-extracted lists.

Pass: recall >= 0.85, precision >= 0.70.

Recall matters more. A missed required keyword silently costs you a match,
while a spurious one gets diluted by corpus occurrence counts.

Also report schema validity rate. With constrained decoding it should be
exactly 1.0; anything less means the grammar is misconfigured, not that the
model is weak.

## Task 3 (optional): P3 rephrase quality

Only worth running if P3 fires often enough to matter. Take 20 bank bullets
and 20 target keywords, request rephrases, and measure:

- slop linter pass rate (gate: >= 0.80)
- R005 to R008 compliance (gate: 1.0)
- claim-introduction violations, meaning any new proper noun, number, or
  technology absent from the parent bullet (gate: 0, hard fail)

A single claim-introduction violation disqualifies a model regardless of
everything else.

## Report

```
uv run python -m jobengine.eval run --model qwen3.5:9b-q4_K_M
uv run python -m jobengine.eval compare
```

Writes to `model_evals` (id, model, task, metric, value, passed,
fixture_version, run_at), keyed on fixture_version so results invalidate when
the fixtures change rather than silently comparing across different tests.

## Candidates, in order

1. `qwen3.5:9b-q4_K_M`
2. `granite4:8b` (Apache 2.0, built for structured and agentic work)
3. `qwen3:8b`
4. `mistral:7b-v0.3` (smallest footprint, most KV headroom)

Stop at the first that passes both required tasks.

## Definition of done
A full run on one model produces a report for both required tasks and writes
rows to `model_evals`.
