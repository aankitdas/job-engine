"""Tests for src/jobengine/pipeline/relevance.py (C4). Written before
implementation per CLAUDE.md hard rule 7. See specs/06-relevance-filter.md
and specs/07-model-eval.md's Task 1.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from jobengine.db.migrate import connect, init
from jobengine.db.models import Job, get_relevance_score, upsert_job
from jobengine.llm.schemas import (
    ApiConfig,
    FallbackConfig,
    LLMConfig,
    LocalConfig,
    RoutingConfig,
)
from jobengine.pipeline.filter import (
    CitizenshipClearanceConfig,
    EmploymentTypeConfig,
    FilterConfig,
    LocationConfig,
    ProfileFilterConfig,
    SeniorityConfig,
)
from jobengine.pipeline.relevance import (
    RankableScore,
    RelevanceConfig,
    RelevanceSchema,
    apply_relevance_cutoff,
    build_profile_card,
    is_hard_disqualified,
    load_relevance_config,
    render_profile_card,
    score_job,
    score_relevance,
    select_top_n,
)
from jobengine.resume.bank import Bank, Bullet, Meta, Role, SummaryBullet


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "jobengine.db"
    connection = connect(db_path)
    init(connection)
    yield connection
    connection.close()


def _seed_company(conn, *, slug="acme", ats="greenhouse"):
    conn.execute(
        "INSERT OR IGNORE INTO companies (slug, ats, name, status, source, first_seen_at) "
        "VALUES (?, ?, ?, 'active', 'seed', '2026-01-01T00:00:00+00:00')",
        (slug, ats, slug.title()),
    )
    conn.commit()


def _seed_job(
    conn,
    *,
    ats_job_id="1",
    title="Software Engineer",
    description="Requirements: Python, FastAPI.",
    first_seen_at="2026-08-07T00:00:00+00:00",
    location_raw="San Francisco, CA",
) -> int:
    _seed_company(conn)
    return upsert_job(
        conn,
        Job(
            ats="greenhouse",
            company_slug="acme",
            ats_job_id=ats_job_id,
            title=title,
            description=description,
            location_raw=location_raw,
            raw_json="{}",
            first_seen_at=first_seen_at,
            last_seen_at=first_seen_at,
        ),
    )


def _filter_config() -> FilterConfig:
    return FilterConfig(
        profiles={
            "software_engineer": ProfileFilterConfig(
                title_aliases=["software engineer", "engineer"]
            ),
            "ai_ml_engineer": ProfileFilterConfig(title_aliases=["ai engineer"]),
        },
        location=LocationConfig(
            remote_synonyms=["remote"], us_major_city_names=["san francisco"]
        ),
        seniority=SeniorityConfig(exclude_title_keywords=["manager", "director"]),
        citizenship_clearance=CitizenshipClearanceConfig(exclude_phrases=[]),
        employment_type=EmploymentTypeConfig(
            exclude_ashby_types=[], exclude_title_keywords=[]
        ),
    )


def _relevance_config(**overrides) -> RelevanceConfig:
    fields = {
        "disqualifier_blocklist": ["security clearance", "citizenship"],
        "freshness_window_days": None,
    }
    fields.update(overrides)
    return RelevanceConfig(**fields)


def _llm_config() -> LLMConfig:
    return LLMConfig(
        local=LocalConfig(
            enabled=True,
            base_url="http://fake:11434",
            model="qwen3.5:9b-q4_K_M",
            context=16384,
            timeout_s=120,
        ),
        routing=RoutingConfig(relevance="local", extract="local", rephrase="local"),
        fallback=FallbackConfig(relevance="skip", extract="fail", rephrase="skip"),
        api=ApiConfig(enabled=False),
    )


def _summary(id_="s1", text="Built systems.") -> SummaryBullet:
    return SummaryBullet(id=id_, text=text, keywords=[], status="verified")


def _bullet(id_, keywords=None, profiles=None) -> Bullet:
    return Bullet(
        id=id_,
        status="verified",
        what="a thing",
        how="carefully",
        result="it worked",
        text="Built a thing that worked well.",
        keywords=keywords or [],
        profiles=profiles or ["software_engineer"],
    )


def _bank() -> Bank:
    role = Role(
        id="r1",
        company="Acme",
        location="Remote",
        start="2022-01",
        end="2023-01",
        kind="full_time",
        title={"default": "Engineer"},
        summary=_summary(),
        bullets=[
            _bullet("b1", keywords=["Python"], profiles=["software_engineer"]),
            _bullet("b2", keywords=["FastAPI"], profiles=["software_engineer"]),
            _bullet("b3", keywords=["LLM"], profiles=["ai_ml_engineer"]),
        ],
    )
    return Bank(meta=Meta(owner="test", updated="2026-01-01"), roles=[role])


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)
        self.prompt_eval_count = 10
        self.eval_count = 5


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self._content = json.dumps(payload)
        self.calls: list[dict[str, Any]] = []

    async def chat(self, **kwargs: Any):
        self.calls.append(kwargs)
        return _FakeResponse(self._content)


_PAYLOAD = {
    "relevance": 80,
    "seniority_match": "match",
    "keyword_hits": ["Python"],
    "disqualifiers": [],
    "one_line": "Strong fit.",
}


# ---------------------------------------------------------------------------
# is_hard_disqualified: pure function
# ---------------------------------------------------------------------------


def test_is_hard_disqualified_matches_single_word_blocklist_phrase():
    assert is_hard_disqualified(["Requires citizenship"], ["citizenship"]) is True


def test_is_hard_disqualified_matches_multi_word_phrase():
    assert (
        is_hard_disqualified(
            ["must hold an active security clearance"], ["security clearance"]
        )
        is True
    )


def test_is_hard_disqualified_case_insensitive():
    assert is_hard_disqualified(["ITAR restricted role"], ["itar"]) is True


def test_is_hard_disqualified_false_when_disqualifiers_empty():
    assert is_hard_disqualified([], ["citizenship"]) is False


def test_is_hard_disqualified_false_when_no_overlap():
    assert is_hard_disqualified(["10+ years required"], ["citizenship"]) is False


# ---------------------------------------------------------------------------
# select_top_n: cutoff logic
# ---------------------------------------------------------------------------


def _rankable(job_id, score, first_seen_at="2026-08-01T00:00:00+00:00"):
    return RankableScore(job_id=job_id, score=score, first_seen_at=first_seen_at)


def test_select_top_n_none_selects_every_row():
    rows = [_rankable(1, 10), _rankable(2, 90)]
    assert select_top_n(rows, None) == {1, 2}


def test_select_top_n_selects_exactly_top_n_by_score():
    rows = [_rankable(1, 10), _rankable(2, 90), _rankable(3, 50)]
    assert select_top_n(rows, 2) == {2, 3}


def test_select_top_n_ties_break_by_first_seen_at_ascending():
    rows = [
        _rankable(1, 50, first_seen_at="2026-08-02T00:00:00+00:00"),
        _rankable(2, 50, first_seen_at="2026-08-01T00:00:00+00:00"),
    ]
    assert select_top_n(rows, 1) == {2}


def test_select_top_n_cap_larger_than_rows_selects_everything():
    rows = [_rankable(1, 10)]
    assert select_top_n(rows, 100) == {1}


def test_select_top_n_zero_cap_selects_nothing():
    rows = [_rankable(1, 10)]
    assert select_top_n(rows, 0) == set()


# ---------------------------------------------------------------------------
# profile card
# ---------------------------------------------------------------------------


def test_build_profile_card_target_titles_from_filter_config(conn):
    card = build_profile_card(conn, _bank(), "software_engineer", _filter_config())
    assert card.target_titles == ["software engineer", "engineer"]


def test_build_profile_card_seniority_band_reflects_exclusions(conn):
    card = build_profile_card(conn, _bank(), "software_engineer", _filter_config())
    assert "manager" in card.seniority_band
    assert "director" in card.seniority_band


def test_build_profile_card_top_keywords_falls_back_to_bank_frequency(conn):
    card = build_profile_card(conn, _bank(), "software_engineer", _filter_config())
    assert "Python" in card.top_keywords
    assert "FastAPI" in card.top_keywords
    assert "LLM" not in card.top_keywords  # ai_ml_engineer-only bullet


def test_build_profile_card_location_rules_say_us_relocation_is_acceptable_when_willing(
    conn, tmp_path
):
    """Real bug found while reviewing a live scoring run: several
    genuinely-relevant jobs (matching profile, US-located, correct
    seniority) scored low or got flagged as "disqualified" purely
    because they required relocation to a specific US city (e.g. "must
    relocate to SF Bay Area"). identity.toml's own
    preferences.willing_to_relocate=true means that should never read as
    a disqualifier; only genuinely non-US on-site roles should."""
    identity_path = tmp_path / "identity.toml"
    identity_path.write_text("[preferences]\nwilling_to_relocate = true\n")
    card = build_profile_card(
        conn,
        _bank(),
        "software_engineer",
        _filter_config(),
        identity_path=identity_path,
    )
    assert "relocat" in card.location_rules.lower()
    assert "not a disqualifier" in card.location_rules.lower()


def test_build_profile_card_location_rules_conservative_when_not_willing_to_relocate(
    conn, tmp_path
):
    identity_path = tmp_path / "identity.toml"
    identity_path.write_text("[preferences]\nwilling_to_relocate = false\n")
    card = build_profile_card(
        conn,
        _bank(),
        "software_engineer",
        _filter_config(),
        identity_path=identity_path,
    )
    assert "not a disqualifier" not in card.location_rules.lower()


def test_build_profile_card_display_name_absent_without_registry(conn):
    card = build_profile_card(conn, _bank(), "software_engineer", _filter_config())
    assert card.display_name is None


def test_build_profile_card_display_name_present_with_registry(conn):
    from jobengine.profiles.config import ProfileConfig

    registry = {
        "software_engineer": ProfileConfig(
            id="software_engineer",
            display_name="Software Engineer",
            section_order=["work_history"],
        )
    }
    card = build_profile_card(
        conn, _bank(), "software_engineer", _filter_config(), profile_registry=registry
    )
    assert card.display_name == "Software Engineer"


def test_render_profile_card_produces_nonempty_text(conn):
    card = build_profile_card(conn, _bank(), "software_engineer", _filter_config())
    text = render_profile_card(card)
    assert "software engineer" in text.lower()
    assert "Python" in text


# ---------------------------------------------------------------------------
# score_relevance: the LLM call
# ---------------------------------------------------------------------------


def test_relevance_module_never_imports_ollama_directly():
    source = Path("src/jobengine/pipeline/relevance.py").read_text()
    assert "import ollama" not in source
    assert "ollama.Client" not in source
    assert "ollama.AsyncClient" not in source


def test_score_relevance_sets_think_false():
    client = _FakeClient(_PAYLOAD)
    _run(
        score_relevance("some JD text", "card text", _llm_config(), local_client=client)
    )
    assert len(client.calls) == 1
    assert client.calls[0]["think"] is False


def test_score_relevance_passes_constrained_schema():
    client = _FakeClient(_PAYLOAD)
    _run(
        score_relevance("some JD text", "card text", _llm_config(), local_client=client)
    )
    assert client.calls[0]["format"] == RelevanceSchema.model_json_schema()


def test_score_relevance_returns_parsed_output():
    client = _FakeClient(_PAYLOAD)
    result = _run(
        score_relevance("some JD text", "card text", _llm_config(), local_client=client)
    )
    assert result.output == _PAYLOAD
    assert result.cost_usd == 0.0


# ---------------------------------------------------------------------------
# score_job: per-job orchestrator
# ---------------------------------------------------------------------------


def test_score_job_skips_llm_when_no_profile_matches(conn):
    job_id = _seed_job(conn, title="Corporate Recruiter")
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    job = Job(**dict(row))
    client = _FakeClient(_PAYLOAD)

    result = _run(
        score_job(
            conn,
            job,
            _filter_config(),
            _relevance_config(),
            _llm_config(),
            _bank(),
            local_client=client,
        )
    )

    assert result == []
    assert client.calls == []


def test_score_job_skips_llm_when_title_matches_but_other_b3_checks_fail(conn):
    """Real gap caught before the first unbounded real run: score_job()
    used to gate only on matches_profiles() (title), not the full B3
    chain -- a job whose title matches but whose location/seniority/
    employment-type/citizenship fails should never reach the LLM,
    exactly like passes_all_filters() enforces everywhere else."""
    job_id = _seed_job(
        conn, title="Software Engineer", first_seen_at="2026-08-07T00:00:00+00:00"
    )
    conn.execute(
        "UPDATE jobs SET location_raw = 'Berlin, Germany' WHERE id = ?", (job_id,)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    job = Job(**dict(row))
    client = _FakeClient(_PAYLOAD)

    result = _run(
        score_job(
            conn,
            job,
            _filter_config(),
            _relevance_config(),
            _llm_config(),
            _bank(),
            local_client=client,
        )
    )

    assert result == []
    assert client.calls == []


def test_score_job_calls_once_per_matched_profile(conn):
    """Real behavioral difference from analyze_job(): one call per
    matched profile, not one call fanned out to many rows."""
    job_id = _seed_job(conn, title="Software Engineer")
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    job = Job(**dict(row))
    client = _FakeClient(_PAYLOAD)

    result = _run(
        score_job(
            conn,
            job,
            _filter_config(),
            _relevance_config(),
            _llm_config(),
            _bank(),
            local_client=client,
        )
    )

    assert len(result) == 1  # only software_engineer alias matches this title
    assert len(client.calls) == 1


def test_score_job_persists_one_relevance_scores_row_per_profile(conn):
    job_id = _seed_job(conn, title="Software Engineer")
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    job = Job(**dict(row))
    client = _FakeClient(_PAYLOAD)

    _run(
        score_job(
            conn,
            job,
            _filter_config(),
            _relevance_config(),
            _llm_config(),
            _bank(),
            local_client=client,
        )
    )

    stored = get_relevance_score(conn, job_id, "software_engineer")
    assert stored is not None
    assert stored.score == 80.0
    assert stored.selected == 0


def test_score_job_disqualifier_forces_score_to_zero(conn):
    job_id = _seed_job(conn, title="Software Engineer")
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    job = Job(**dict(row))
    payload = {**_PAYLOAD, "disqualifiers": ["requires active security clearance"]}
    client = _FakeClient(payload)

    _run(
        score_job(
            conn,
            job,
            _filter_config(),
            _relevance_config(),
            _llm_config(),
            _bank(),
            local_client=client,
        )
    )

    stored = get_relevance_score(conn, job_id, "software_engineer")
    assert stored.score == 0.0


def test_score_job_rerun_upserts_instead_of_duplicating(conn):
    job_id = _seed_job(conn, title="Software Engineer")
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    job = Job(**dict(row))

    _run(
        score_job(
            conn,
            job,
            _filter_config(),
            _relevance_config(),
            _llm_config(),
            _bank(),
            local_client=_FakeClient(_PAYLOAD),
        )
    )
    _run(
        score_job(
            conn,
            job,
            _filter_config(),
            _relevance_config(),
            _llm_config(),
            _bank(),
            local_client=_FakeClient({**_PAYLOAD, "relevance": 20}),
        )
    )

    count = conn.execute(
        "SELECT COUNT(*) AS n FROM relevance_scores WHERE job_id = ?", (job_id,)
    ).fetchone()["n"]
    assert count == 1
    assert get_relevance_score(conn, job_id, "software_engineer").score == 20.0


# ---------------------------------------------------------------------------
# apply_relevance_cutoff
# ---------------------------------------------------------------------------


def test_apply_relevance_cutoff_selects_exactly_top_n(conn):
    job_a = _seed_job(conn, ats_job_id="1")
    job_b = _seed_job(conn, ats_job_id="2")
    job_c = _seed_job(conn, ats_job_id="3")
    from jobengine.db.models import RelevanceScore, upsert_relevance_score

    for job_id, score in [(job_a, 90.0), (job_b, 50.0), (job_c, 10.0)]:
        upsert_relevance_score(
            conn,
            RelevanceScore(
                job_id=job_id,
                profile="software_engineer",
                score=score,
                selected=0,
                scored_at="2026-08-07T00:00:00+00:00",
            ),
        )

    apply_relevance_cutoff(conn, "software_engineer", daily_cap=2)

    assert get_relevance_score(conn, job_a, "software_engineer").selected == 1
    assert get_relevance_score(conn, job_b, "software_engineer").selected == 1
    assert get_relevance_score(conn, job_c, "software_engineer").selected == 0


def test_apply_relevance_cutoff_rerun_demotes_a_job_that_falls_out_of_top_n(conn):
    job_a = _seed_job(conn, ats_job_id="1")
    job_b = _seed_job(conn, ats_job_id="2")
    from jobengine.db.models import RelevanceScore, upsert_relevance_score

    upsert_relevance_score(
        conn,
        RelevanceScore(
            job_id=job_a,
            profile="software_engineer",
            score=90.0,
            selected=0,
            scored_at="2026-08-07T00:00:00+00:00",
        ),
    )
    apply_relevance_cutoff(conn, "software_engineer", daily_cap=1)
    assert get_relevance_score(conn, job_a, "software_engineer").selected == 1

    upsert_relevance_score(
        conn,
        RelevanceScore(
            job_id=job_b,
            profile="software_engineer",
            score=99.0,
            selected=0,
            scored_at="2026-08-07T01:00:00+00:00",
        ),
    )
    apply_relevance_cutoff(conn, "software_engineer", daily_cap=1)

    assert get_relevance_score(conn, job_a, "software_engineer").selected == 0
    assert get_relevance_score(conn, job_b, "software_engineer").selected == 1


# ---------------------------------------------------------------------------
# passes_relevance_floor
# ---------------------------------------------------------------------------


def test_passes_relevance_floor_true_when_unscored(conn):
    """Fail open: a job C4 hasn't scored yet (nightly batch hasn't
    reached it, or relevance is disabled) must still surface, same as
    before C4 existed -- an unscored job is not evidence of a poor fit."""
    from jobengine.pipeline.relevance import passes_relevance_floor

    job_id = _seed_job(conn)

    assert passes_relevance_floor(
        conn, job_id, "software_engineer", _relevance_config(min_relevance_score=20)
    )


def test_passes_relevance_floor_false_below_floor(conn):
    from jobengine.db.models import RelevanceScore, upsert_relevance_score
    from jobengine.pipeline.relevance import passes_relevance_floor

    job_id = _seed_job(conn)
    upsert_relevance_score(
        conn,
        RelevanceScore(
            job_id=job_id,
            profile="software_engineer",
            score=15.0,
            scored_at="2026-08-07T00:00:00+00:00",
        ),
    )

    assert not passes_relevance_floor(
        conn, job_id, "software_engineer", _relevance_config(min_relevance_score=20)
    )


def test_passes_relevance_floor_true_at_or_above_floor(conn):
    from jobengine.db.models import RelevanceScore, upsert_relevance_score
    from jobengine.pipeline.relevance import passes_relevance_floor

    job_id = _seed_job(conn)
    upsert_relevance_score(
        conn,
        RelevanceScore(
            job_id=job_id,
            profile="software_engineer",
            score=20.0,  # exactly at the floor -- inclusive, not exclusive
            scored_at="2026-08-07T00:00:00+00:00",
        ),
    )

    assert passes_relevance_floor(
        conn, job_id, "software_engineer", _relevance_config(min_relevance_score=20)
    )


def test_passes_relevance_floor_true_when_floor_is_zero(conn):
    """min_relevance_score defaults to 0 -- every real score (0-100) is
    >= 0, so the floor is a no-op unless config/relevance.yaml sets it,
    matching disqualifier_blocklist's own opt-in-by-config shape."""
    from jobengine.db.models import RelevanceScore, upsert_relevance_score
    from jobengine.pipeline.relevance import passes_relevance_floor

    job_id = _seed_job(conn)
    upsert_relevance_score(
        conn,
        RelevanceScore(
            job_id=job_id,
            profile="software_engineer",
            score=0.0,
            scored_at="2026-08-07T00:00:00+00:00",
        ),
    )

    assert passes_relevance_floor(
        conn, job_id, "software_engineer", _relevance_config()
    )


def test_passes_relevance_floor_checks_the_right_profile(conn):
    """A job scored above the floor for one profile but below it (or
    unscored) for another must be judged per-profile, not globally."""
    from jobengine.db.models import RelevanceScore, upsert_relevance_score
    from jobengine.pipeline.relevance import passes_relevance_floor

    job_id = _seed_job(conn)
    upsert_relevance_score(
        conn,
        RelevanceScore(
            job_id=job_id,
            profile="software_engineer",
            score=90.0,
            scored_at="2026-08-07T00:00:00+00:00",
        ),
    )
    upsert_relevance_score(
        conn,
        RelevanceScore(
            job_id=job_id,
            profile="ai_ml_engineer",
            score=5.0,
            scored_at="2026-08-07T00:00:00+00:00",
        ),
    )
    config = _relevance_config(min_relevance_score=20)

    assert passes_relevance_floor(conn, job_id, "software_engineer", config)
    assert not passes_relevance_floor(conn, job_id, "ai_ml_engineer", config)


# ---------------------------------------------------------------------------
# load_relevance_config
# ---------------------------------------------------------------------------


def test_load_relevance_config_reads_real_config_file():
    config = load_relevance_config(Path("config/relevance.yaml"))
    assert "security clearance" in config.disqualifier_blocklist
    assert config.freshness_window_days is None
    assert config.min_relevance_score == 20
