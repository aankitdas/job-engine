"""Ashby job board client. See specs/04-sources.md.

Skips any posting where `isListed` is false; unlisted postings are not meant
to be surfaced publicly.
"""

import json

import httpx

from jobengine.sources._client import REQUEST_SEMAPHORE, make_client, retryable
from jobengine.sources.models import JobPosting

BOARD_URL = (
    "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
)


@retryable()
async def _get_board(client: httpx.AsyncClient, slug: str) -> dict:
    async with REQUEST_SEMAPHORE:
        response = await client.get(BOARD_URL.format(slug=slug))
    response.raise_for_status()
    return response.json()


def _to_posting(slug: str, job: dict) -> JobPosting:
    compensation = job.get("compensation")
    return JobPosting(
        source="ashby",
        company_slug=slug,
        ats_job_id=str(job["id"]),
        title=job["title"],
        location_raw=job.get("location"),
        remote=job.get("isRemote"),
        department=job.get("department") or job.get("team"),
        url=job.get("jobUrl"),
        apply_url=job.get("applyUrl"),
        compensation_raw=json.dumps(compensation) if compensation else None,
        description_plain=job.get("descriptionPlain"),
        ats_date=job.get("publishedAt"),
        raw_json=json.dumps(job),
    )


async def fetch_board(
    slug: str, *, transport: httpx.BaseTransport | None = None
) -> list[JobPosting]:
    async with make_client(transport=transport) as client:
        data = await _get_board(client, slug)
    return [
        _to_posting(slug, job)
        for job in data.get("jobs", [])
        if job.get("isListed", True)
    ]
