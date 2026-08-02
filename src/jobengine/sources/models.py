"""Normalized job posting shape shared by the Greenhouse and Ashby clients.

See specs/04-sources.md. Both clients return a list of these; downstream
sync/diff logic (B2) maps this onto the `jobs` table row.
"""

from typing import Literal

from pydantic import BaseModel


class JobPosting(BaseModel):
    source: Literal["greenhouse", "ashby"]
    company_slug: str
    ats_job_id: str
    title: str
    location_raw: str | None = None
    remote: bool | None = None
    department: str | None = None
    url: str | None = None
    apply_url: str | None = None
    compensation_raw: str | None = None
    description_plain: str | None = None
    ats_date: str | None = None
    raw_json: str
