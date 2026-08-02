"""Fetch and diff: pull each active company's board and reconcile it against
the jobs table. See specs/04-sources.md, "Sync and diff".

first_seen_at immutability is not re-implemented here: `upsert_job`'s
ON CONFLICT clause already omits first_seen_at from its SET list (A1), so
passing now() unconditionally on every call is safe, on an existing row the
database silently keeps the old value no matter what this module passes.

"Record an edit event" (spec 04) has no backing table in the 16-table
schema; a changed content_hash is logged via `logging` and counted in this
run's `runs.counts` JSON, not written as a new per-job row. Confirmed by
asking.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from jobengine.db.migrate import DEFAULT_DB_PATH, connect
from jobengine.db.models import (
    Job,
    Run,
    close_missing_jobs,
    get_job,
    list_active_companies,
    record_run,
    upsert_job,
)
from jobengine.sources import ashby, greenhouse
from jobengine.sources.models import JobPosting

logger = logging.getLogger(__name__)

Fetcher = Callable[[str], Awaitable[list[JobPosting]]]

_FETCHERS: dict[str, Fetcher] = {
    "greenhouse": greenhouse.fetch_board,
    "ashby": ashby.fetch_board,
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _content_hash(description: str | None) -> str:
    return hashlib.sha256((description or "").encode()).hexdigest()


def _to_job(posting: JobPosting, *, now: str) -> Job:
    return Job(
        ats=posting.source,
        company_slug=posting.company_slug,
        ats_job_id=posting.ats_job_id,
        title=posting.title,
        location_raw=posting.location_raw,
        remote=None if posting.remote is None else int(posting.remote),
        department=posting.department,
        url=posting.url,
        apply_url=posting.apply_url,
        compensation_raw=posting.compensation_raw,
        description=posting.description_plain,
        content_hash=_content_hash(posting.description_plain),
        ats_date=posting.ats_date,
        first_seen_at=now,
        last_seen_at=now,
        closed_at=None,
        raw_json=posting.raw_json,
    )


@dataclass
class CompanyResult:
    ok: bool
    new: int = 0
    updated: int = 0
    edited: int = 0
    closed: int = 0
    error: str | None = None


@dataclass
class RunSummary:
    companies_ok: int = 0
    companies_failed: int = 0
    new: int = 0
    updated: int = 0
    edited: int = 0
    closed: int = 0
    errors: list[str] = field(default_factory=list)


async def _sync_company(
    conn: sqlite3.Connection, ats: str, slug: str, fetchers: dict[str, Fetcher]
) -> CompanyResult:
    try:
        postings = await fetchers[ats](slug)
    except Exception as exc:  # noqa: BLE001 - any client failure skips this company, never the run
        logger.error("sync failed for %s/%s: %s", ats, slug, exc)
        return CompanyResult(ok=False, error=f"{ats}/{slug}: {exc}")

    now = _now()
    result = CompanyResult(ok=True)
    seen_ids: set[str] = set()
    for posting in postings:
        seen_ids.add(posting.ats_job_id)
        existing = get_job(conn, ats, slug, posting.ats_job_id)
        job = _to_job(posting, now=now)
        upsert_job(conn, job)
        if existing is None:
            result.new += 1
        else:
            result.updated += 1
            if existing.content_hash != job.content_hash:
                result.edited += 1
                logger.info("content changed: %s/%s/%s", ats, slug, posting.ats_job_id)

    result.closed = close_missing_jobs(conn, ats, slug, seen_ids, now)
    return result


async def _sync_async(
    conn: sqlite3.Connection, fetchers: dict[str, Fetcher]
) -> RunSummary:
    summary = RunSummary()
    companies = list_active_companies(conn)
    results = await asyncio.gather(
        *(_sync_company(conn, c.ats, c.slug, fetchers) for c in companies)
    )
    for result in results:
        if result.ok:
            summary.companies_ok += 1
            summary.new += result.new
            summary.updated += result.updated
            summary.edited += result.edited
            summary.closed += result.closed
        else:
            summary.companies_failed += 1
            summary.errors.append(result.error or "unknown error")
    return summary


def sync(
    conn: sqlite3.Connection,
    dry_run: bool = False,
    fetchers: dict[str, Fetcher] | None = None,
) -> RunSummary:
    """Fetch every active company's board and reconcile it against jobs.

    Single code path for real and --dry-run: the diff always runs and
    always writes, dry_run only decides commit vs. rollback at the very
    end, so there is exactly one implementation of the diff logic to get
    right, not two.
    """
    started_at = _now()
    summary = asyncio.run(_sync_async(conn, fetchers or _FETCHERS))
    ended_at = _now()
    record_run(
        conn,
        Run(
            stage="sync",
            started_at=started_at,
            ended_at=ended_at,
            counts=json.dumps(
                {
                    "new": summary.new,
                    "updated": summary.updated,
                    "edited": summary.edited,
                    "closed": summary.closed,
                    "companies_ok": summary.companies_ok,
                    "companies_failed": summary.companies_failed,
                }
            ),
            errors=json.dumps(summary.errors) if summary.errors else None,
        ),
    )
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return summary


def _main() -> None:
    parser = argparse.ArgumentParser(prog="jobengine.sources.sync")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    conn = connect(DEFAULT_DB_PATH)
    try:
        summary = sync(conn, dry_run=args.dry_run)
        print(
            f"companies ok={summary.companies_ok} failed={summary.companies_failed} "
            f"| jobs new={summary.new} updated={summary.updated} "
            f"edited={summary.edited} closed={summary.closed}"
        )
        for error in summary.errors:
            print(f"  error: {error}")
    finally:
        conn.close()


if __name__ == "__main__":
    _main()
