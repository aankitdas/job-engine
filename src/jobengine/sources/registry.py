"""Company registry: seed, manual add, weekly slug validation.

See specs/04-sources.md. Three population paths (seed, harvest, manual add);
harvest (Common Crawl CDX bulk slug extraction) is not built yet, deferred
out of B1's scope. `validate` is the weekly probe: it never retries a slug
into the next bucket itself (each fetch already retries 5xx/timeouts via
`_client.retryable`), it only classifies the outcome and updates status.
"""

import argparse
import asyncio
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

from jobengine.db.migrate import DEFAULT_DB_PATH, connect
from jobengine.db.models import Company
from jobengine.sources import ashby, greenhouse
from jobengine.sources.models import JobPosting

DEFAULT_SEED_PATH = Path("config/seed_companies.yaml")

Fetcher = Callable[[str], Awaitable[list[JobPosting]]]

_FETCHERS: dict[str, Fetcher] = {
    "greenhouse": greenhouse.fetch_board,
    "ashby": ashby.fetch_board,
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _insert_new_company(conn: sqlite3.Connection, company: Company) -> bool:
    """Insert only if (slug, ats) is absent. Never touches an existing row.

    A second `seed` run over the same file must not reset an already
    `active` company's status back to `unverified`, so this deliberately
    does not use `jobengine.db.models.upsert_company`, whose ON CONFLICT
    clause always overwrites status and source.
    """
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO companies (
            slug, ats, name, status, source, first_seen_at,
            last_ok_at, last_checked_at, consecutive_failures
        ) VALUES (
            :slug, :ats, :name, :status, :source, :first_seen_at,
            :last_ok_at, :last_checked_at, :consecutive_failures
        )
        """,
        company.model_dump(),
    )
    return cursor.rowcount > 0


def seed(conn: sqlite3.Connection, path: Path = DEFAULT_SEED_PATH) -> tuple[int, int]:
    """Load the hand-curated seed file. Returns (newly_inserted, total_entries)."""
    entries = yaml.safe_load(path.read_text()) or []
    inserted = 0
    for entry in entries:
        company = Company(
            slug=entry["slug"],
            ats=entry["ats"],
            name=entry["name"],
            status="unverified",
            source="seed",
            first_seen_at=_now(),
        )
        if _insert_new_company(conn, company):
            inserted += 1
    conn.commit()
    return inserted, len(entries)


def add(conn: sqlite3.Connection, ats: str, slug: str, name: str) -> bool:
    """Manually register a single company. Returns False if already present."""
    company = Company(
        slug=slug,
        ats=ats,
        name=name,
        status="unverified",
        source="manual",
        first_seen_at=_now(),
    )
    inserted = _insert_new_company(conn, company)
    conn.commit()
    return inserted


async def _probe(ats: str, slug: str, fetchers: dict[str, Fetcher]) -> str:
    """Classify one probe into a bucket: active_ok, active_zero, dead, retry."""
    fetch = fetchers[ats]
    try:
        postings = await fetch(slug)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return "dead"
        return "retry"
    except httpx.TimeoutException:
        return "retry"
    return "active_ok" if postings else "active_zero"


async def _validate_async(
    conn: sqlite3.Connection, fetchers: dict[str, Fetcher]
) -> dict[str, int]:
    rows = conn.execute(
        "SELECT slug, ats, status, consecutive_failures FROM companies "
        "WHERE status IN ('unverified', 'active')"
    ).fetchall()
    counts = {"active": 0, "dead": 0}
    now = _now()
    for slug, ats, status, failures in rows:
        bucket = await _probe(ats, slug, fetchers)
        if bucket == "active_ok":
            conn.execute(
                "UPDATE companies SET status = 'active', last_ok_at = ?, "
                "last_checked_at = ?, consecutive_failures = 0 "
                "WHERE slug = ? AND ats = ?",
                (now, now, slug, ats),
            )
            counts["active"] += 1
        elif bucket == "active_zero":
            # 200 with zero jobs: active, but do not reset consecutive_failures.
            conn.execute(
                "UPDATE companies SET status = 'active', last_ok_at = ?, "
                "last_checked_at = ? WHERE slug = ? AND ats = ?",
                (now, now, slug, ats),
            )
            counts["active"] += 1
        elif bucket == "dead":
            new_failures = failures + 1
            new_status = "dead" if new_failures >= 3 else status
            conn.execute(
                "UPDATE companies SET status = ?, last_checked_at = ?, "
                "consecutive_failures = ? WHERE slug = ? AND ats = ?",
                (new_status, now, new_failures, slug, ats),
            )
            if new_status == "dead":
                counts["dead"] += 1
        # "retry": 5xx or timeout after exhausting the client's own retries.
        # Do not increment failures or touch status; probe again next week.
    conn.commit()
    return counts


def validate(
    conn: sqlite3.Connection, fetchers: dict[str, Fetcher] | None = None
) -> dict[str, int]:
    return asyncio.run(_validate_async(conn, fetchers or _FETCHERS))


def _main() -> None:
    parser = argparse.ArgumentParser(prog="jobengine.sources.registry")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("seed")

    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("ats", choices=["greenhouse", "ashby"])
    add_parser.add_argument("slug")
    add_parser.add_argument("name")

    subparsers.add_parser("validate")

    args = parser.parse_args()
    conn = connect(DEFAULT_DB_PATH)
    try:
        if args.command == "seed":
            inserted, total = seed(conn)
            print(f"seeded {inserted} new companies ({total} entries in seed file)")
        elif args.command == "add":
            added = add(conn, args.ats, args.slug, args.name)
            print("added" if added else "already registered")
        elif args.command == "validate":
            counts = validate(conn)
            print(f"active: {counts['active']}  dead: {counts['dead']}")
    finally:
        conn.close()


if __name__ == "__main__":
    _main()
