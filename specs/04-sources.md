# Spec 04: ATS Sources and Slug Registry

## Goal
Populate and maintain `companies`, then fetch all open postings from each and
compute `first_seen_at` by diffing against the previous snapshot.

## Module
`src/jobengine/sources/` with `greenhouse.py`, `ashby.py`, `registry.py`,
`sync.py`.

## Clients

Both return a normalized `JobPosting` pydantic model. Shared behaviour:
- `httpx.AsyncClient`, 20s timeout, concurrency cap 10
- `tenacity` retry: 3 attempts, exponential backoff, retry on 5xx and timeouts
  only, never on 404
- descriptive User-Agent identifying this as a personal job search tool
- raw response body stored verbatim on every job

### Greenhouse
`GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`

Returns the whole board in one request, no pagination. `content` is HTML with
HTML entities escaped; decode entities then strip tags to plain text. Fields:
`id`, `title`, `updated_at`, `location.name`, `absolute_url`, `content`,
`departments`, `offices`.

For form schemas later: `GET .../jobs/{id}?questions=true` returns the
per-job application `questions` array. Do not fetch this during normal sync;
only when a job reaches the apply queue.

### Ashby
`GET https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true`

Fields: `title`, `location`, `secondaryLocations`, `department`, `team`,
`isListed`, `isRemote`, `workplaceType`, `descriptionPlain`, `publishedAt`,
`employmentType`, `jobUrl`, `applyUrl`, `compensation`.

Skip any posting where `isListed` is false. Unlisted postings are not meant to
be surfaced publicly.

## Registry

Three population paths:

1. **Seed** (`resume/../config/seed_companies.yaml`): hand-curated, ~150-300
   companies the user would actually work for. Highest signal. Build this
   first; it alone is enough for v1.
2. **Harvest**: bulk slug extraction from Common Crawl CDX index by scanning
   for URLs matching ATS domain patterns
   (`boards.greenhouse.io/*`, `job-boards.greenhouse.io/*`,
   `jobs.ashbyhq.com/*`) and regexing the slug. The open-source
   `Feashliaa/job-board-aggregator` repo does exactly this and yields roughly
   95k identifiers; use its approach or consume its output.
3. **Manual add**: `registry add greenhouse stripe`.

### Validation
Weekly job probes every `unverified` and `active` slug with a single request.
- 200 with jobs: `active`, reset `consecutive_failures`
- 200 with zero jobs: `active`, but do not reset failures
- 404: increment failures; mark `dead` at 3
- 5xx or timeout: do not increment, retry next week

Companies migrate off platforms constantly, so dead slugs are expected and
must not be retried daily.

## Sync and diff

```
for each active company:
    fetch board
    for each posting:
        upsert into jobs on (ats, company_slug, ats_job_id)
        if new row:            set first_seen_at = now
        if existing row:       bump last_seen_at; NEVER touch first_seen_at
                               if content_hash changed, record an edit event
    for jobs in db not in this response and closed_at is null:
        set closed_at = now
```

The `first_seen_at` immutability is the single most important line in this
spec. An upsert that clobbers it silently destroys the freshness signal, and
the damage is invisible until you look at the metrics weeks later. Enforce it
in SQL with a conditional update, not just in Python, and test it explicitly.

## CLI
```
uv run python -m jobengine.sources.registry seed
uv run python -m jobengine.sources.registry validate
uv run python -m jobengine.sources.sync            # fetch + diff
uv run python -m jobengine.sources.sync --dry-run
```

## Scheduling
Every 3 hours, not twice daily as originally planned here. ATS platforms
batch-publish new postings tied to business-hour/weekday HR workflows, not a
fixed clock time, so there is no single "optimal" sync time per company to
aim for. The reliable lever is polling frequency instead: these are free,
unauthenticated APIs with no per-call cost, so shrinking the poll interval
directly shrinks the worst-case "missed a posting for N hours" window with
no real downside. Windows Task Scheduler task `job-engine-sync`: trigger
starts 6am local time, `PT3H` repetition interval, `P1D` duration (fires
every 3 hours, resetting daily).

On WSL2, cron inside the WSL instance only runs while WSL is running, so
scheduling happens on the Windows side: Task Scheduler invokes
`C:\Users\aanki\run-sync.bat`, which shells into WSL to run `cd
~/projects/job-engine && ./scripts/sync.sh`. Point the task directly at the
`.bat` file with no inline arguments, not at `wsl.exe` with an inline `-e
bash -lc "..."` argument string in the task's own Action: the Task
Scheduler GUI's handling of that argument string produced "arguments not
valid" errors during setup, a GUI/argument-parsing quirk, not a problem
with the script. Create the task via `schtasks /create` (CLI) rather than
the GUI for the same reason.

## Definition of done
Two sync runs a day apart produce a non-zero count of rows with
`first_seen_at` on the second day. `tests/test_sync.py` asserts that a second
sync of unchanged data does not modify any `first_seen_at`.
