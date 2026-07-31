# Architecture

Revision 2. Supersedes the per-job tailoring design, which contradicted the
methodology it was supposed to implement.

## What this is

A personal pipeline that finds freshly-posted jobs on Greenhouse and Ashby,
scores each one against a deterministic rubric, patches a per-title base
resume only when the rubric says it needs it, and queues the result for
review and application.

**It runs at zero marginal cost.** No paid API calls in the daily loop.

## The thesis

Lee Korelitz's guide makes two claims that drive everything here.

**Speed.** ATS sorts candidates in the order they applied. If you are resume
#139, the recruiter may have filled their interview schedule at #75. So
freshness beats volume and the pipeline optimizes for being early.

**Per title, not per application.** His words: "Applying fast with a resume
customized to the job title will get you more interviews than customizing your
resume for every application and saves you time." Resumes are job-title
specific because different titles have different keyword sets. He says to
build the keyword list from 10 to 15 JDs sharing a title, then build one
resume for that title.

The earlier design generated a resume per job. That is slower, more expensive,
and explicitly contrary to the source. **Three resumes, not thirty a day.**

## Core design rule

**Everything mechanical is mechanical.** Lee's criteria are almost entirely
checkable in code: keyword presence, keyword position on the page, bullet
counts, sentence structure, tense, typography. A rubric evaluates them
exactly and instantly. An LLM is only invoked when the rubric identifies a
specific deficit that selection alone cannot close.

## Cost

| Stage | How | Cost |
|---|---|---|
| Slug registry, fetch, diff | Python + public ATS APIs | free |
| Deterministic filters | Python | free |
| Relevance scoring | Qwen3.5-9B local, constrained | free |
| Keyword extraction | Qwen3.5-9B local, constrained | free |
| Keyword corpus | SQL aggregation | free |
| Base resume generation (3, monthly) | interactive Claude Code session | covered by Pro |
| Rubric scoring | Python, deterministic | free |
| Patch tiers P0-P2 | Python, deterministic selection | free |
| Patch tier P3 (rephrase) | local, ~400 tokens in | free |
| Apply | Playwright, local | free |

Note on Claude Code billing: interactive terminal and IDE sessions draw from
your Pro plan. Do **not** set `ANTHROPIC_API_KEY` in your shell profile,
because Claude Code prioritizes that key and moves the session onto metered
API billing. The status of headless `claude -p` billing has changed more than
once in 2026; check `/status` and the support docs before scripting it.

## Source strategy

Query the ATS APIs directly. Do not scrape job boards.

| Source | Endpoint | Auth | Date field |
|---|---|---|---|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | none | `updated_at`, not first-posted |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true` | none | `publishedAt`, true post date |

The Greenhouse asymmetry is why we store daily snapshots and compute
`first_seen_at` ourselves. It cannot be backfilled, so ingestion ships before
everything else.

## Profiles

Three, each owning a title alias list, an accumulating keyword corpus, a base
resume, a section order, and per-role title overrides.

| Profile | Matches JD titles like |
|---|---|
| `ai_ml_engineer` | AI Engineer, ML Engineer, Applied Scientist, LLM Engineer |
| `software_engineer` | Software Engineer, Backend Engineer, Platform Engineer |
| `data_scientist` | Data Scientist, Analytics Engineer, ML Analyst |

One bullet bank feeds all three.

## Pipeline

```
0.  slug registry       weekly     deterministic
1.  fetch + diff        2x daily   deterministic     -> first_seen_at
2.  filter              2x daily   deterministic     -> 300-500 survivors
2.5 relevance score     daily      local             -> rank, cut to N
3.  extract keywords    daily      local constrained -> corpus + per-job set
4.  route to profile    daily      deterministic     -> which base resume
5.  rubric score        daily      deterministic     -> pass or deficit list
6.  patch (P0-P3)       daily      mostly free       -> job-specific variant
7.  re-score + lint     daily      deterministic     -> gate
8.  review              manual     Telegram + web
9.  apply               by autonomy level
```

### The monthly loop, separate from the daily one

```
M1. corpus review       monthly    you + Claude Code interactive
M2. regenerate 3 base resumes      you + Claude Code interactive
M3. render + rubric baseline       deterministic
```

Base resumes are regenerated when the keyword corpus has drifted enough to
matter, which the dashboard flags. That is roughly monthly, it happens with
you at the terminal, and it is the only place a strong model writes prose.

### The patch ladder

The rubric produces a deficit list. Patches are attempted in order, and the
cheapest one that closes the gap wins.

| Tier | Action | Cost |
|---|---|---|
| P0 | reorder existing bullets by relevance to this JD's keywords | free |
| P1 | swap in a bank bullet not currently on the resume | free |
| P2 | promote a project or role currently below the fold | free |
| P3 | rephrase one existing bullet to naturally carry a missing keyword | ~400 tokens, local |
| P4 | no coverage possible; log to gap ledger and accept | free |

Most deficits close at P0 or P1, because the bank is larger than any single
rendered resume. P3 is capped at two calls per job.

**P3 output is stored back into the bank as a phrasing variant of its parent
bullet.** Over time the bank accumulates the phrasings that worked, and P3
fires less often. The system gets cheaper and more consistent as it runs.

## Resume generation

Three separated concerns.

**Content is data.** `resume/bank/*.yaml` holds every claim, tagged with
keywords and a verification status.

**Selection is deterministic.** Which bullets appear, in what order, is
computed from keyword overlap. No model decides this.

**Rendering is deterministic.** Selected data plus the golden .docx template
through python-docx. The LLM never touches layout.

An LLM writes prose in exactly two places: the monthly base resume generation
(interactive, human present) and the P3 rephrase (one bullet, constrained,
must pass the linter and keep its parent bank ID).

### The gap ledger

When no bank bullet covers a JD keyword and P3 cannot honestly produce one,
the keyword is logged rather than invented. The dashboard ranks uncovered
keywords by how many jobs each would unlock. That is a portfolio backlog
sorted by market value.

`status: speculative` bullets render only in watermarked local previews and
are hard-blocked from outbound files. Promotion requires an artifact URL.

## Storage

SQLite at `data/jobengine.db`, single source of truth. Outcomes are an
append-only event log so the dashboard can measure time-in-stage.

## Deployment

Split at the browser boundary. Compute is containerized and portable. The
apply stage needs a headful browser with a persistent profile and stays on the
host. Local now, cloud later is a deploy rather than a rewrite.

The DGX Spark, when available, is another tier behind the same interface: a
different `base_url` and model name. It is bandwidth-bound rather than
capacity-bound, so it earns its place on the monthly generation loop, not on
the high-volume daily stages the laptop already handles.

## Non-goals

- Per-application resume rewriting. The methodology says not to.
- Mass applying, LinkedIn or Indeed scraping, bulk cold email.
- Fabricated experience. See the gap ledger.
- Any paid API call in the daily loop.
