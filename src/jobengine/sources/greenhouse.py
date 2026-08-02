"""Greenhouse job board client. See specs/04-sources.md."""

import html
import json
import re

import httpx

from jobengine.sources._client import REQUEST_SEMAPHORE, make_client, retryable
from jobengine.sources.models import JobPosting

BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(raw: str) -> str:
    # Tags first, then entities: an escaped "&lt;fast&gt;" must survive as
    # literal text, not get eaten by the tag regex once unescaped.
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


@retryable()
async def _get_board(client: httpx.AsyncClient, slug: str) -> dict:
    async with REQUEST_SEMAPHORE:
        response = await client.get(BOARD_URL.format(token=slug))
    response.raise_for_status()
    return response.json()


def _to_posting(slug: str, job: dict) -> JobPosting:
    department = (
        ", ".join(d["name"] for d in job.get("departments", []) if d.get("name"))
        or None
    )
    absolute_url = job.get("absolute_url")
    return JobPosting(
        source="greenhouse",
        company_slug=slug,
        ats_job_id=str(job["id"]),
        title=job["title"],
        location_raw=(job.get("location") or {}).get("name"),
        remote=None,
        department=department,
        url=absolute_url,
        apply_url=absolute_url,
        compensation_raw=None,
        description_plain=_strip_html(job.get("content") or ""),
        ats_date=job.get("updated_at"),
        raw_json=json.dumps(job),
    )


async def fetch_board(
    slug: str, *, transport: httpx.BaseTransport | None = None
) -> list[JobPosting]:
    async with make_client(transport=transport) as client:
        data = await _get_board(client, slug)
    return [_to_posting(slug, job) for job in data.get("jobs", [])]
