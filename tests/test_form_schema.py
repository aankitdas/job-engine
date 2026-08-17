"""Tests for src/jobengine/apply/form_schema.py (G1). Written before
implementation per this project's project-wide tests-first convention.
No spec file exists yet for Phase G (TODO.md's Rule 4 defers writing one
until the prior phase runs on real data); see the G1 plan in
docs/decisions.md for the design this implements.

_DISCORD_QUESTIONS/_DISCORD_DEMOGRAPHIC_QUESTIONS/_DISCORD_LOCATION_QUESTIONS
are the real, live-captured response shape from
GET https://boards-api.greenhouse.io/v1/boards/discord/jobs/8675277002?questions=true
(job_id 3950 in data/jobengine.db), not a synthetic minimal fixture --
classify_autonomy_ceiling()'s whole rule depends on Greenhouse's real
`question_<id>` vs. clean-semantic-name field-naming convention, so the
fixture has to be the real shape to mean anything.
"""

from __future__ import annotations

import httpx
import pytest

from jobengine.apply.form_schema import (
    ApplyConfig,
    FormField,
    FormSchema,
    classify_autonomy_ceiling,
    fetch_greenhouse_form_schema,
    load_apply_config,
)


def _run(coro):
    import asyncio

    return asyncio.run(coro)


_DISCORD_QUESTIONS = [
    {
        "description": None,
        "label": "First Name",
        "required": True,
        "fields": [{"name": "first_name", "type": "input_text", "values": []}],
    },
    {
        "description": None,
        "label": "Last Name",
        "required": True,
        "fields": [{"name": "last_name", "type": "input_text", "values": []}],
    },
    {
        "description": None,
        "label": "Preferred First Name",
        "required": False,
        "fields": [{"name": "preferred_name", "type": "input_text", "values": []}],
    },
    {
        "description": None,
        "label": "Email",
        "required": True,
        "fields": [{"name": "email", "type": "input_text", "values": []}],
    },
    {
        "description": None,
        "label": "Phone",
        "required": True,
        "fields": [{"name": "phone", "type": "input_text", "values": []}],
    },
    {
        "description": None,
        "label": "Resume/CV",
        "required": True,
        "fields": [
            {"name": "resume", "type": "input_file", "values": []},
            {"name": "resume_text", "type": "textarea", "values": []},
        ],
    },
    {
        "description": None,
        "label": "Cover Letter",
        "required": False,
        "fields": [
            {"name": "cover_letter", "type": "input_file", "values": []},
            {"name": "cover_letter_text", "type": "textarea", "values": []},
        ],
    },
    {
        "description": None,
        "label": "Why do you want to work at Discord?",
        "required": True,
        "fields": [{"name": "question_37606073002", "type": "textarea", "values": []}],
    },
    {
        "description": None,
        "label": "Are you legally authorized to work in the United States for our Company?",
        "required": True,
        "fields": [
            {
                "name": "question_37606077002",
                "type": "multi_value_single_select",
                "values": [
                    {"label": "Yes", "value": 1},
                    {"label": "No", "value": 0},
                ],
            }
        ],
    },
    {
        "description": None,
        "label": "Are you currently based in or willing to relocate to the Bay Area for this position? ",
        "required": True,
        "fields": [
            {
                "name": "question_37606079002",
                "type": "multi_value_single_select",
                "values": [
                    {"label": "Yes", "value": 1},
                    {"label": "No", "value": 0},
                ],
            }
        ],
    },
    {
        "description": None,
        "label": "Are you currently located in the US?",
        "required": True,
        "fields": [
            {
                "name": "question_37606078002",
                "type": "multi_value_single_select",
                "values": [
                    {"label": "Yes", "value": 1},
                    {"label": "No", "value": 0},
                ],
            }
        ],
    },
    {
        "description": None,
        "label": "How did you hear about this job?",
        "required": False,
        "fields": [
            {"name": "question_37606076002", "type": "input_text", "values": []}
        ],
    },
    {
        "description": None,
        "label": "LinkedIn Profile",
        "required": False,
        "fields": [
            {"name": "question_37606074002", "type": "input_text", "values": []}
        ],
    },
    {
        "description": None,
        "label": "Website",
        "required": False,
        "fields": [
            {"name": "question_37606075002", "type": "input_text", "values": []}
        ],
    },
]

_DISCORD_DEMOGRAPHIC_QUESTIONS = {
    "header": "Voluntary Self Identification",
    "description": "...",
    "questions": [
        {
            "id": 4033064002,
            "label": "Gender",
            "required": True,
            "type": "multi_value_single_select",
            "answer_options": [
                {
                    "id": 4196776002,
                    "label": "Male",
                    "free_form": False,
                    "decline_to_answer": False,
                },
                {
                    "id": 4196778002,
                    "label": "I don't wish to answer",
                    "free_form": False,
                    "decline_to_answer": True,
                },
            ],
        }
    ],
}

_DISCORD_LOCATION_QUESTIONS = [
    {
        "description": None,
        "label": "Longitude",
        "required": True,
        "fields": [{"name": "longitude", "type": "input_hidden", "values": []}],
    },
    {
        "description": None,
        "label": "Latitude",
        "required": True,
        "fields": [{"name": "latitude", "type": "input_hidden", "values": []}],
    },
    {
        "description": None,
        "label": "Location",
        "required": True,
        "fields": [{"name": "location", "type": "input_text", "values": []}],
    },
]


def _discord_response_json() -> dict:
    return {
        "id": 8675277002,
        "title": "Senior Software Engineer, Enterprise Platform",
        "questions": _DISCORD_QUESTIONS,
        "demographic_questions": _DISCORD_DEMOGRAPHIC_QUESTIONS,
        "location_questions": _DISCORD_LOCATION_QUESTIONS,
    }


# Real, live-captured shapes (jobs 4466 and 410/7995153 in
# data/jobengine.db, both Airbnb) that motivated D39's fix: the original
# free-text-only classify_autonomy_ceiling() missed required
# multi_value_single_select attestations entirely.
_AIRBNB_8129371_QUESTIONS = [
    {
        "label": "First Name",
        "required": True,
        "fields": [{"name": "first_name", "type": "input_text", "values": []}],
    },
    {
        "label": "Last Name",
        "required": True,
        "fields": [{"name": "last_name", "type": "input_text", "values": []}],
    },
    {
        "label": "Email",
        "required": True,
        "fields": [{"name": "email", "type": "input_text", "values": []}],
    },
    {
        "label": "Phone",
        "required": True,
        "fields": [{"name": "phone", "type": "input_text", "values": []}],
    },
    {
        "label": "Resume/CV",
        "required": True,
        "fields": [
            {"name": "resume", "type": "input_file", "values": []},
            {"name": "resume_text", "type": "textarea", "values": []},
        ],
    },
    {
        "label": "How did you hear about this job?",
        "required": True,
        "fields": [
            {
                "name": "question_68585807",
                "type": "multi_value_single_select",
                "values": [{"label": "LinkedIn", "value": 1}],
            }
        ],
    },
    {
        "label": "Are you legally authorized to work in the country where the job is located?",
        "required": True,
        "fields": [
            {
                "name": "question_68585812",
                "type": "multi_value_single_select",
                "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}],
            }
        ],
    },
    {
        "label": "Will you now or in the future require company sponsorship to retain or extend your work authorization in the country where the job is located?",
        "required": True,
        "fields": [
            {
                "name": "question_68585813",
                "type": "multi_value_single_select",
                "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}],
            }
        ],
    },
    {
        "label": "Airbnb Candidate Privacy Policy",
        "required": True,
        "fields": [
            {
                "name": "question_68585814",
                "type": "multi_value_single_select",
                "values": [{"label": "I agree", "value": 1}],
            }
        ],
    },
    {
        "label": "Are you currently subject to any non-compete or non-solicitation agreement that would impact your ability to work at Airbnb or prevent you from accepting a job offer from Airbnb? ",
        "required": True,
        "fields": [
            {
                "name": "question_68585815",
                "type": "multi_value_single_select",
                "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}],
            }
        ],
    },
    {
        "label": "Are you currently or have you ever worked for Airbnb in any capacity? This could include, but is not limited to, a full-time employee, intern, apprentice, or contingent worker.",
        "required": True,
        "fields": [
            {
                "name": "question_68585816",
                "type": "multi_value_single_select",
                "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}],
            }
        ],
    },
    {
        "label": "Candidate AI Usage Attestation:",
        "required": True,
        "fields": [
            {
                "name": "question_68585817",
                "type": "multi_value_single_select",
                "values": [{"label": "I attest", "value": 1}],
            }
        ],
    },
]


def _airbnb_8129371_response_json() -> dict:
    return {
        "id": 8129371,
        "title": "Staff Machine Learning Engineer, Traffic Intelligence",
        "questions": _AIRBNB_8129371_QUESTIONS,
    }


# job 410 (ats_job_id 7995153, "Acquisition Manager"): required cover
# letter + required "How did you hear" (proves the mapped label works
# regardless of which real company/job uses it) among other real
# required fields nothing maps -- trimmed to the load-bearing rows.
_AIRBNB_7995153_QUESTIONS = [
    {
        "label": "First Name",
        "required": True,
        "fields": [{"name": "first_name", "type": "input_text", "values": []}],
    },
    {
        "label": "Cover Letter",
        "required": True,
        "fields": [
            {"name": "cover_letter", "type": "input_file", "values": []},
            {"name": "cover_letter_text", "type": "textarea", "values": []},
        ],
    },
    {
        "label": "How did you hear about this job?",
        "required": True,
        "fields": [{"name": "question_67517254", "type": "input_text", "values": []}],
    },
    {
        "label": "Gender",
        "required": True,
        "fields": [
            {
                "name": "question_67517256",
                "type": "multi_value_single_select",
                "values": [{"label": "Male", "value": 1}],
            }
        ],
    },
]


def _airbnb_7995153_response_json() -> dict:
    return {
        "id": 7995153,
        "title": "Acquisition Manager",
        "questions": _AIRBNB_7995153_QUESTIONS,
    }


def _apply_config(**overrides) -> ApplyConfig:
    fields = {
        "mapped_question_labels": [
            "How did you hear about this job?",
            "LinkedIn Profile",
            "Website",
            "Portfolio",
        ]
    }
    fields.update(overrides)
    return ApplyConfig(**fields)


# ---------------------------------------------------------------------------
# fetch_greenhouse_form_schema: real GET, questions=true, mocked transport
# ---------------------------------------------------------------------------


def test_fetch_greenhouse_form_schema_parses_the_real_discord_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "questions=true" in str(request.url)
        assert request.url.path == "/v1/boards/discord/jobs/8675277002"
        return httpx.Response(200, json=_discord_response_json())

    transport = httpx.MockTransport(handler)

    schema = _run(
        fetch_greenhouse_form_schema("discord", "8675277002", transport=transport)
    )

    assert schema.ats == "greenhouse"
    assert schema.job_id == "8675277002"
    # 14 real questions -> more real fields than questions since resume/
    # cover letter each expand to 2 fields (file + text variant).
    field_names = {f.name for f in schema.fields}
    assert "first_name" in field_names
    assert "question_37606073002" in field_names
    assert len(schema.fields) == 16


def test_fetch_greenhouse_form_schema_ignores_demographic_and_location_questions():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_discord_response_json())

    transport = httpx.MockTransport(handler)

    schema = _run(
        fetch_greenhouse_form_schema("discord", "8675277002", transport=transport)
    )

    field_names = {f.name for f in schema.fields}
    assert "longitude" not in field_names
    assert "latitude" not in field_names
    assert "location" not in field_names


def test_fetch_greenhouse_form_schema_retries_on_5xx_like_sources_client():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(502)
        return httpx.Response(200, json=_discord_response_json())

    transport = httpx.MockTransport(handler)

    schema = _run(
        fetch_greenhouse_form_schema("discord", "8675277002", transport=transport)
    )

    assert len(calls) == 3
    assert schema.job_id == "8675277002"


def test_fetch_greenhouse_form_schema_raises_on_404_no_retry():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    with pytest.raises(httpx.HTTPStatusError):
        _run(fetch_greenhouse_form_schema("discord", "8675277002", transport=transport))
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# classify_autonomy_ceiling: pure, deterministic. D39 inverted the
# default after a real 40-job live run found the original free-text-only
# check silently passed required multi_value_single_select attestations
# (see docs/decisions.md D39) -- these tests are built on that real
# evidence, not the pre-fix synthetic cases.
# ---------------------------------------------------------------------------


def test_classify_autonomy_ceiling_caps_at_1_for_real_discord_shape():
    """Job 3950's required "Why do you want to work at Discord?" alone
    is enough to cap this at 1, same result pre- and post-D39. Since the
    fix also stops treating the 3 held-out eligibility questions as
    recognized, they now show up in unmapped_required_fields too --
    this job was never going to reach ceiling 2 either way, but the
    unmapped list is real and worth asserting on directly."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_discord_response_json())

    schema = _run(
        fetch_greenhouse_form_schema(
            "discord", "8675277002", transport=httpx.MockTransport(handler)
        )
    )

    result = classify_autonomy_ceiling(schema, _apply_config())

    assert result.ceiling == 1
    unmapped_labels = {f.label for f in result.unmapped_required_fields}
    assert "Why do you want to work at Discord?" in unmapped_labels
    assert (
        "Are you legally authorized to work in the United States for our Company?"
        in unmapped_labels
    )


def test_classify_autonomy_ceiling_job_2650_shape_genuinely_earns_2():
    """Real, live-verified shape (Anthropic job 2650): required fields
    are exactly first_name/last_name/email, all standard. The one real
    job of the 40-job run that genuinely earns ceiling 2 under the new
    rule, not just under the old permissive one."""
    schema = FormSchema(
        job_id="5370690008",
        ats="greenhouse",
        fields=[
            FormField(
                name="first_name",
                label="First Name",
                field_type="input_text",
                required=True,
            ),
            FormField(
                name="last_name",
                label="Last Name",
                field_type="input_text",
                required=True,
            ),
            FormField(
                name="email", label="Email", field_type="input_text", required=True
            ),
            FormField(
                name="phone", label="Phone", field_type="input_text", required=False
            ),
            FormField(
                name="resume",
                label="Resume/CV",
                field_type="input_file",
                required=False,
            ),
        ],
    )

    result = classify_autonomy_ceiling(schema, _apply_config())

    assert result.ceiling == 2
    assert result.unmapped_required_fields == []


def test_classify_autonomy_ceiling_job_4466_shape_now_caps_at_1_not_2():
    """The real bug D39 fixes: under the old free-text-only rule this
    real Airbnb shape (job 4466) classified as 2, since every one of its
    non-standard required fields is multi_value_single_select, not free
    text. "How did you hear" is in mapped_question_labels so it's
    correctly absent from unmapped_required_fields; the 6 real
    attestation/eligibility questions are not."""
    schema = _run(
        fetch_greenhouse_form_schema(
            "airbnb",
            "8129371",
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json=_airbnb_8129371_response_json())
            ),
        )
    )

    result = classify_autonomy_ceiling(schema, _apply_config())

    assert result.ceiling == 1
    unmapped_labels = {f.label for f in result.unmapped_required_fields}
    assert "How did you hear about this job?" not in unmapped_labels
    assert "Airbnb Candidate Privacy Policy" in unmapped_labels
    assert "Candidate AI Usage Attestation:" in unmapped_labels
    assert len(unmapped_labels) == 6


def test_classify_autonomy_ceiling_or_group_satisfied_by_either_alternative():
    """The real bug: Greenhouse's Resume/CV question puts resume (file)
    and resume_text (textarea) under one required question -- confirmed
    live on job 4466, both required=True. A flat per-field check would
    wrongly flag the non-standard alternative even when the other one
    fully satisfies the question. Uses a synthetic non-standard OR-group
    (today's real standard fields don't distinguish flat-vs-grouped
    logic, since both alternatives are already recognized either way)."""
    schema = FormSchema(
        job_id="1",
        ats="greenhouse",
        fields=[
            FormField(
                name="question_1",
                label="Writing Sample",
                field_type="input_file",
                required=True,
            ),
            FormField(
                name="question_2",
                label="Writing Sample",
                field_type="textarea",
                required=True,
            ),
        ],
    )
    config = _apply_config(mapped_question_labels=["Writing Sample"])

    result = classify_autonomy_ceiling(schema, config)

    assert result.ceiling == 2
    assert result.unmapped_required_fields == []


def test_classify_autonomy_ceiling_required_cover_letter_caps_at_1():
    """D39's second bug: cover_letter/cover_letter_text used to be in
    _STANDARD_FIELD_NAMES, so a required cover letter silently passed.
    Real shape: job 410 (Airbnb, ats_job_id 7995153) requires one."""
    schema = _run(
        fetch_greenhouse_form_schema(
            "airbnb",
            "7995153",
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json=_airbnb_7995153_response_json())
            ),
        )
    )

    result = classify_autonomy_ceiling(schema, _apply_config())

    assert result.ceiling == 1
    unmapped_labels = {f.label for f in result.unmapped_required_fields}
    assert "Cover Letter" in unmapped_labels
    # The real reason this config entry is load-bearing (see config/apply.yaml):
    # a required "How did you hear" must NOT show up here even though
    # the job caps at 1 anyway for other reasons.
    assert "How did you hear about this job?" not in unmapped_labels


def test_classify_autonomy_ceiling_mapped_label_does_not_cap_even_if_required():
    schema = FormSchema(
        job_id="1",
        ats="greenhouse",
        fields=[
            FormField(
                name="first_name",
                label="First Name",
                field_type="input_text",
                required=True,
            ),
            FormField(
                name="question_9",
                label="LinkedIn Profile",
                field_type="input_text",
                required=True,
            ),
        ],
    )

    result = classify_autonomy_ceiling(schema, _apply_config())

    assert result.ceiling == 2
    assert result.unmapped_required_fields == []


def test_classify_autonomy_ceiling_never_returns_3():
    """Level 3 is 'earned' (D16), not read off a schema -- G4 hasn't
    defined what earns it yet, so this function must never produce it."""
    schema = FormSchema(job_id="1", ats="greenhouse", fields=[])
    assert classify_autonomy_ceiling(schema, _apply_config()).ceiling in (1, 2)


# ---------------------------------------------------------------------------
# load_apply_config
# ---------------------------------------------------------------------------


def test_load_apply_config_reads_the_real_repo_config():
    config = load_apply_config()
    assert "LinkedIn Profile" in config.mapped_question_labels
