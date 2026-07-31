# Spec 09: Base Resume Generation (Monthly, Interactive)

## Why this is not a pipeline stage

This is the one place a strong model writes prose, and it happens with you at
the terminal in an interactive Claude Code session, which your Pro plan
covers. Making it automated would move it onto metered billing for no benefit,
since it runs roughly monthly and benefits from your judgment.

Per Lee: build the keyword list from 10 to 15 JDs sharing a job title, then
build one resume for that title.

## Trigger

The dashboard flags a profile as stale when any is true:

- 15 or more new JDs analyzed for that profile since the last generation
- the top 10 corpus keywords have changed by 3 or more positions
- median rubric coverage across the last 30 jobs for that profile fell below
  0.75
- 60 days elapsed

Staleness is a suggestion, not a schedule. Regenerating a resume that is
performing well is a good way to make it worse.

## Inputs

```
uv run python -m jobengine.profiles brief --profile ai_ml_engineer > brief.md
```

`brief.md` contains:
- the top 30 corpus keywords with occurrence counts and rank change since last
  generation
- the current base resume's rubric measurements
- the 10 most common uncovered keywords from the gap ledger
- bank bullets carrying the top keywords that are not currently selected
- a diff summary: what changed in the market for this title

That file is the entire input. It is a few hundred lines, it is generated for
free, and it is what makes the interactive session short.

## The session

```
claude
> Read specs/09-base-resumes.md, brief.md, resume/bank/aankit.yaml, and
> docs/headless-headhunter/. Regenerate the ai_ml_engineer base resume.
> Plan first. Show me the selection and the reasoning before writing anything.
```

Rules for the session, which belong in `CLAUDE.md`:

1. Selection first, prose second. Show which bullets, in what order, and why,
   before rewriting a single word.
2. Prefer existing bank text. Rewrite only where the rubric shows a deficit.
3. Any new phrasing is written back to the bank, not just into the output.
4. Never write a bullet that is not traceable to a bank entry.
5. Run the rubric before declaring done.

## Output

```
resume/base/{profile}/v{N}/
  selection.yaml       ordered bullet ids + section order
  resume.docx
  resume.pdf
  rubric.json          the measurements at generation time
  CHANGELOG.md         what changed from v{N-1} and why
```

Versioned, never overwritten. The dashboard compares response rates across
base resume versions, which is the only way to learn whether a regeneration
helped or hurt. Keep at least the previous two versions live.

## Profile section order

Per Lee, education moves to the bottom when the target title does not require
a degree or the degree would make you look overqualified. Configured per
profile, not inferred.

The optional summary section has exactly three triggers in his guide: changing
industries, relocating, or visa and sponsorship. The work-authorization line in
the contact block already covers the third case for this user. Do not add a
summary section unless a trigger genuinely applies.

## Definition of done
Three base resumes exist, each passing the full rubric against its own profile
corpus with coverage above 0.80, and each rendering identically to the golden
template on all R010 typography checks.
