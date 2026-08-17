"""G1: form schema fetch + deterministic autonomy-ceiling classification.
No browser, no filling, no submitting -- that's G2 onward. See D16 in
docs/decisions.md ("autonomy level is decided deterministically from the
form schema, which both APIs expose before a browser opens") and the G1
plan (docs/decisions.md; Phase G has no dedicated spec file yet, same
situation F1 was in before D35).

Greenhouse only. A real, live GET against
boards-api.greenhouse.io/v1/boards/{slug}/jobs/{id}?questions=true
(verified against job_id 3950, Discord, this session) returns a clean,
public, unauthenticated form schema. Ashby has no equivalent: a direct
GET against a per-job posting-api endpoint returns 401, and the public
apply page is a client-rendered SPA whose only embedded state is
Datadog/org config, not form fields. Ashby jobs get no computed ceiling
until a real endpoint surfaces or G2's browser automation can read the
rendered DOM directly.

classify_autonomy_ceiling() never returns 3: D16 calls level 3 "earned,"
and G4 (the phase that will define what earns it) doesn't exist yet.
Inventing that rule here would be guessing, not reading it off a schema.

classify_autonomy_ceiling()'s default direction was inverted after a
real 40-job live run (top Greenhouse jobs, score>=20, open) found the
original free-text-only check missed non-free-text required fields
entirely -- 21/40 jobs classified as ceiling 2, but 20 of those had
required `multi_value_single_select` attestations (privacy policy
consent, non-compete, AI-usage attestation) the system has no way to
answer, silently passed through because they aren't free text. The rule
now requires *every* required field to be recognized (standard or
explicitly mapped), not just free-text ones to be absent -- see D39 in
docs/decisions.md for the full real-data writeup.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml
from pydantic import BaseModel, Field

from jobengine.sources._client import REQUEST_SEMAPHORE, make_client, retryable

DEFAULT_APPLY_CONFIG_PATH = Path("config/apply.yaml")

BOARD_JOB_URL = (
    "https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs/{ats_job_id}"
    "?questions=true"
)

# Fields with these clean, semantic names are Greenhouse's own standard
# identity/resume fields, never a custom question -- real, observed
# convention (job 3950): every non-standard field is instead named
# "question_<numeric_id>". Deliberately excludes cover_letter/
# cover_letter_text: a required cover letter needs genuinely generated
# prose, the same fabrication-risk category as a custom free-text essay
# (D18), so it must never silently pass as "standard" the way resume
# does (resume stays standard because this pipeline already
# deterministically produces that exact file, D3/D4 -- cover letter has
# no equivalent deterministic source anywhere in this codebase).
_STANDARD_FIELD_NAMES = {
    "first_name",
    "last_name",
    "preferred_name",
    "email",
    "phone",
    "resume",
    "resume_text",
}


class FormField(BaseModel):
    name: str
    label: str
    field_type: str
    required: bool
    values: list[str] = []


class FormSchema(BaseModel):
    job_id: str
    ats: str
    fields: list[FormField]
    fetched_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ApplyConfig(BaseModel):
    mapped_question_labels: list[str] = []


class AutonomyClassification(BaseModel):
    ceiling: int
    unmapped_required_fields: list[FormField]


def load_apply_config(path: Path = DEFAULT_APPLY_CONFIG_PATH) -> ApplyConfig:
    with open(path) as f:
        return ApplyConfig(**yaml.safe_load(f))


@retryable()
async def _get_job(
    client: httpx.AsyncClient, company_slug: str, ats_job_id: str
) -> dict:
    async with REQUEST_SEMAPHORE:
        response = await client.get(
            BOARD_JOB_URL.format(company_slug=company_slug, ats_job_id=ats_job_id)
        )
    response.raise_for_status()
    return response.json()


def _to_fields(questions: list[dict]) -> list[FormField]:
    fields = []
    for question in questions:
        for field in question.get("fields", []):
            fields.append(
                FormField(
                    name=field["name"],
                    label=question["label"],
                    field_type=field["type"],
                    required=question["required"],
                    values=[v["label"] for v in field.get("values", [])],
                )
            )
    return fields


async def fetch_greenhouse_form_schema(
    company_slug: str,
    ats_job_id: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> FormSchema:
    """Only the top-level `questions` array feeds the schema.
    `demographic_questions` (voluntary EEO self-identification, always
    carries a "decline to answer" option -- a compliance concern, not an
    autonomy signal) and `location_questions` (hidden lat/long/location
    autofill, type input_hidden, never human-facing) are deliberately
    excluded. Not every company uses that separation consistently, though:
    real job 4466 (Airbnb) puts its own EEO questions (Gender, Race,
    Veteran Status) directly in `questions`, not `demographic_questions`.
    All observed `required=False` there, so classify_autonomy_ceiling()'s
    fallback already handles it correctly (an unrecognized field caps the
    ceiling regardless of source) if a company ever marks one required --
    no special-casing needed here."""
    async with make_client(transport=transport) as client:
        data = await _get_job(client, company_slug, ats_job_id)
    return FormSchema(
        job_id=str(ats_job_id),
        ats="greenhouse",
        fields=_to_fields(data.get("questions", [])),
    )


def classify_autonomy_ceiling(
    schema: FormSchema, config: ApplyConfig
) -> AutonomyClassification:
    """Ceiling 2 (eligible for G3's auto-fill-then-pause-before-submit,
    once G3 exists) requires EVERY required field on the form to be
    recognized: a Greenhouse standard identity field
    (_STANDARD_FIELD_NAMES) or a label in
    config.mapped_question_labels. Any other required field caps the
    job at ceiling 1 (eligible for G2's assisted dry-run fill, never
    auto-submit -- answering an unrecognized required field needs real
    human judgment, D18). Never 3, see module docstring.

    Deliberately NOT "cap only on required free text": a real 40-job
    live run found required multi_value_single_select attestations
    (privacy policy consent, non-compete, AI-usage attestation -- see
    job 4466 in D39) that a free-text-only check silently missed, since
    they're selects, not free text. The system has no more ability to
    answer those than a free-text essay; recognized-or-not is the real
    signal, not field type.

    Required fields are grouped by label before classifying: Greenhouse
    represents "provide ONE of these" (Resume/CV: file upload OR pasted
    text) as multiple fields sharing one question's label and required
    flag, not independent requirements (real, confirmed: job 4466 shows
    resume and resume_text both required=True under one Resume/CV
    question). A label-group is satisfied if ANY field in it is
    recognized; only a group where NO alternative is recognized
    contributes to unmapped_required_fields, as one representative field
    per group rather than one per alternative."""
    mapped_labels = {label.strip().lower() for label in config.mapped_question_labels}

    def _is_recognized(field: FormField) -> bool:
        return (
            field.name in _STANDARD_FIELD_NAMES
            or field.label.strip().lower() in mapped_labels
        )

    groups: dict[str, list[FormField]] = {}
    for field in schema.fields:
        if field.required:
            groups.setdefault(field.label, []).append(field)

    unmapped = [
        fields[0] for fields in groups.values() if not any(map(_is_recognized, fields))
    ]

    return AutonomyClassification(
        ceiling=1 if unmapped else 2, unmapped_required_fields=unmapped
    )


def _main() -> None:
    import argparse
    import asyncio

    from jobengine.db.migrate import DEFAULT_DB_PATH, connect

    parser = argparse.ArgumentParser(prog="jobengine.apply.form_schema")
    parser.add_argument("job_id", type=int)
    args = parser.parse_args()

    conn = connect(DEFAULT_DB_PATH)
    try:
        row = conn.execute(
            "SELECT ats, company_slug, ats_job_id, title FROM jobs WHERE id = ?",
            (args.job_id,),
        ).fetchone()
        if row is None:
            raise SystemExit(f"no job with id {args.job_id}")
        if row["ats"] != "greenhouse":
            raise SystemExit(
                f"job {args.job_id} is ats={row['ats']!r}; G1 only supports "
                "greenhouse today (see module docstring)"
            )

        schema = asyncio.run(
            fetch_greenhouse_form_schema(row["company_slug"], row["ats_job_id"])
        )
        config = load_apply_config()
        classification = classify_autonomy_ceiling(schema, config)

        print(f"job {args.job_id}: {row['title']!r}")
        for field in schema.fields:
            print(
                f"  {field.name:28} type={field.field_type:28} "
                f"required={field.required!s:5} label={field.label}"
            )
        print(f"autonomy ceiling: {classification.ceiling}")
        if classification.unmapped_required_fields:
            print("unmapped required fields (a human must fill these):")
            for field in classification.unmapped_required_fields:
                print(f"  {field.name:28} label={field.label}")
    finally:
        conn.close()


if __name__ == "__main__":
    _main()
