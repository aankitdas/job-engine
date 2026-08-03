"""Greenhouse job board client. See specs/04-sources.md."""

import html
import json
import re
from html.parser import HTMLParser

import httpx

from jobengine.sources._client import REQUEST_SEMAPHORE, make_client, retryable
from jobengine.sources.models import JobPosting

BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"

_WHITESPACE_RE = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    """Collects text content, tracking whether any genuine tag was seen.

    A tag boundary contributes a separating space so stripped tags don't
    glue adjacent words together (e.g. "</p><ul><li>" must not merge the
    text on either side).
    """

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self.found_tag = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        self.found_tag = True
        self._chunks.append(" ")

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        self.found_tag = True
        self._chunks.append(" ")

    def handle_endtag(self, tag: str) -> None:
        self.found_tag = True
        self._chunks.append(" ")

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


def _extract(markup: str) -> tuple[str, bool]:
    parser = _TextExtractor()
    parser.feed(markup)
    parser.close()
    return parser.text(), parser.found_tag


def _strip_html(raw: str) -> str:
    """Greenhouse's `content` field is not consistently escaped the same
    way. Real, currently-observed API data double-escapes its own markup
    (`&lt;h2&gt;About Stripe&lt;/h2&gt;`, no literal tag anywhere), while a
    JD could in principle contain genuine literal tags alongside an
    entity-escaped literal mention of a fake tag that must survive as
    visible text (e.g. "&lt;fast&gt;" inside otherwise real markup).

    These two shapes are ambiguous once collapsed to the same string one
    unescape apart, so resolve it by checking whether the raw feed
    contains any genuine tag structure: if it does, trust that pass as-is,
    since a real parser's own entity handling already leaves any
    still-escaped sequence as plain text within the same pass. If it does
    not, i.e. every tag-like sequence in the raw content is itself still
    entity-escaped, unescape once and re-parse, which reveals and strips
    the real markup instead of leaving it as literal garbage text.

    The found_tag branch assumes a field is never a MIX of literal tags
    and separately-escaped literal text in the same string; confirmed true
    for all 2,691 real Greenhouse jobs in data/jobengine.db as of this
    writing (100% double-escaped, 0% mixed), but that's an observation
    about today's API responses, not a guarantee about future ones. If it
    ever breaks, the failure mode is silent wrong output, not a crash: the
    heuristic picks whichever single pass ran, so a genuinely mixed field
    would just silently choose one branch and mangle the other half. If
    descriptions ever look wrong again after a Greenhouse API change,
    check here first.
    """
    text, found_tag = _extract(raw)
    if not found_tag:
        text, _ = _extract(html.unescape(raw))
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
