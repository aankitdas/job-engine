"""Tests for jobengine.rubric.patch. See specs/08-rubric.md's Patch ladder
section.

D3 covers P0-P2 (deterministic, zero model calls). D4 adds P3 (rephrase,
local model) and its writeback; P4 (accept and log to gap_ledger) remains
out of scope, see patch.py's own module docstring for why.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from jobengine.llm.schemas import (
    ApiConfig,
    FallbackConfig,
    LLMConfig,
    LocalConfig,
    RoutingConfig,
)
from jobengine.resume.bank import (
    Bank,
    Bullet,
    BulletVariant,
    Meta,
    Role,
    SummaryBullet,
    dump_bank,
    load_bank,
)
from jobengine.resume.render import Identity, load_identity
from jobengine.rubric import measure, patch, rules

_IDENTITY_PATH = Path("identity.toml")


def _identity(**overrides) -> Identity:
    fields = {
        "full_name": "Jordan Rivera",
        "email": "jordan@example.com",
        "phone": "+1-555-123-4567",
        "city": "Austin",
        "state": "TX",
        "linkedin": "https://linkedin.com/in/jordanrivera",
        "github": "https://github.com/jordanrivera",
        "portfolio": "https://jordanrivera.dev",
        "scholar": "https://scholar.google.com/citations?user=abc123",
        "work_authorization_statement": "US citizen, no sponsorship required",
    }
    fields.update(overrides)
    return Identity(**fields)


def _summary(id_: str = "s1", text: str = "Built systems.") -> SummaryBullet:
    return SummaryBullet(id=id_, text=text, keywords=[], status="verified")


def _bullet(
    id_: str,
    text: str = "Built a thing that worked well.",
    keywords=None,
    profiles=None,
    status: str = "verified",
) -> Bullet:
    return Bullet(
        id=id_,
        status=status,
        what="a thing",
        how="carefully",
        result="it worked",
        text=text,
        keywords=keywords or [],
        profiles=profiles or ["ai_ml_engineer"],
    )


def _role(
    id_: str,
    *,
    kind: str = "full_time",
    start: str | None = "2022-01",
    end: str | None = "2023-01",
    bullets=None,
    summary=None,
) -> Role:
    return Role(
        id=id_,
        company="Acme" if kind != "project" else None,
        location="Remote" if kind != "project" else None,
        start=start,
        end=end,
        kind=kind,
        title={"default": "Engineer"},
        summary=summary or _summary(f"{id_}_s"),
        bullets=bullets if bullets is not None else [],
    )


def _bank(roles: list[Role]) -> Bank:
    return Bank(meta=Meta(owner="test", updated="2026-01-01"), roles=roles)


# ---------------------------------------------------------------------------
# P0: reorder
# ---------------------------------------------------------------------------


def test_p0_reorders_bullets_within_a_role_by_descending_keyword_score():
    role = _role(
        "r1",
        bullets=[
            _bullet("b_low", keywords=[]),
            _bullet("b_high", keywords=["Kubernetes", "Airflow"]),
            _bullet("b_mid", keywords=["Kubernetes"]),
        ],
    )
    bank = _bank([role])
    result = patch.apply_p0(bank, required_keywords=["Kubernetes", "Airflow"])
    ids = [b.id for b in result.roles[0].bullets]
    assert ids == ["b_high", "b_mid", "b_low"]


def test_p0_never_reorders_summary_relative_to_bullets():
    summary = _summary("s1", text="Original summary.")
    role = _role(
        "r1", summary=summary, bullets=[_bullet("b1", keywords=["Kubernetes"])]
    )
    bank = _bank([role])
    result = patch.apply_p0(bank, required_keywords=["Kubernetes"])
    assert result.roles[0].summary.id == "s1"
    assert result.roles[0].summary.text == "Original summary."


def test_p0_swaps_overlapping_roles_when_the_later_positioned_one_scores_higher():
    # role_sei/role_unl-style real overlap: different start dates, ranges
    # genuinely overlap. role_b scores higher and starts later positioned;
    # swapping to put it first is legal since R009 tolerates overlap.
    role_a = _role(
        "r_a", start="2021-10", end="2023-08", bullets=[_bullet("a1", keywords=[])]
    )
    role_b = _role(
        "r_b",
        start="2021-05",
        end="2023-06",
        bullets=[_bullet("b1", keywords=["Kubernetes"])],
    )
    bank = _bank([role_a, role_b])
    result = patch.apply_p0(bank, required_keywords=["Kubernetes"])
    assert [r.id for r in result.roles] == ["r_b", "r_a"]


def test_p0_never_swaps_non_overlapping_roles_even_if_earlier_one_scores_higher():
    role_new = _role(
        "r_new", start="2022-01", end="2023-01", bullets=[_bullet("new1", keywords=[])]
    )
    role_old = _role(
        "r_old",
        start="2018-01",
        end="2019-01",
        bullets=[_bullet("old1", keywords=["Kubernetes"])],
    )
    bank = _bank([role_new, role_old])  # already correct R009 order
    result = patch.apply_p0(bank, required_keywords=["Kubernetes"])
    # role_old scores higher but does not overlap role_new: R009 forbids
    # promoting it ahead regardless of keyword score.
    assert [r.id for r in result.roles] == ["r_new", "r_old"]
    assert measure.is_reverse_chronological(result.roles)


def test_p0_never_reorders_project_roles_regardless_of_keyword_score():
    project_a = _role(
        "p_a",
        kind="project",
        start=None,
        end=None,
        bullets=[_bullet("pa1", keywords=[])],
    )
    project_b = _role(
        "p_b",
        kind="project",
        start=None,
        end=None,
        bullets=[_bullet("pb1", keywords=["Kubernetes"])],
    )
    bank = _bank([project_a, project_b])
    result = patch.apply_p0(bank, required_keywords=["Kubernetes"])
    assert [r.id for r in result.roles] == ["p_a", "p_b"]


# ---------------------------------------------------------------------------
# P1: swap
# ---------------------------------------------------------------------------


def test_p1_swaps_lowest_scoring_selected_bullet_for_best_unselected_candidate():
    role = _role(
        "r1",
        bullets=[
            _bullet("selected_low", keywords=[], profiles=["ai_ml_engineer"]),
            _bullet("selected_high", keywords=["Docker"], profiles=["ai_ml_engineer"]),
        ],
    )
    candidate = _bank([role])

    full_role = _role(
        "r1",
        bullets=[
            _bullet("selected_low", keywords=[], profiles=["ai_ml_engineer"]),
            _bullet("selected_high", keywords=["Docker"], profiles=["ai_ml_engineer"]),
            _bullet(
                "candidate_kubernetes",
                keywords=["Kubernetes"],
                profiles=["ai_ml_engineer"],
            ),
        ],
    )
    full_bank = _bank([full_role])

    result = patch.apply_p1(
        candidate,
        full_bank,
        profile="ai_ml_engineer",
        required_keywords=["Kubernetes", "Docker"],
    )
    ids = {b.id for b in result.roles[0].bullets}
    assert ids == {"candidate_kubernetes", "selected_high"}
    assert len(result.roles[0].bullets) == 2  # R003 count preserved


def test_p1_ignores_candidates_from_other_profiles():
    role = _role(
        "r1", bullets=[_bullet("selected", keywords=[], profiles=["ai_ml_engineer"])]
    )
    candidate = _bank([role])

    full_role = _role(
        "r1",
        bullets=[
            _bullet("selected", keywords=[], profiles=["ai_ml_engineer"]),
            _bullet(
                "wrong_profile", keywords=["Kubernetes"], profiles=["software_engineer"]
            ),
        ],
    )
    full_bank = _bank([full_role])

    result = patch.apply_p1(
        candidate, full_bank, profile="ai_ml_engineer", required_keywords=["Kubernetes"]
    )
    assert [b.id for b in result.roles[0].bullets] == ["selected"]


def test_p1_prefers_swapping_in_the_first_role():
    role1 = _role("r1", bullets=[_bullet("r1_low", keywords=[])])
    role2 = _role(
        "r2", start="2019-01", end="2020-01", bullets=[_bullet("r2_low", keywords=[])]
    )
    candidate = _bank([role1, role2])

    full_role1 = _role(
        "r1",
        bullets=[
            _bullet("r1_low", keywords=[]),
            _bullet("r1_candidate", keywords=["Kubernetes"]),
        ],
    )
    full_role2 = _role(
        "r2",
        start="2019-01",
        end="2020-01",
        bullets=[
            _bullet("r2_low", keywords=[]),
            _bullet("r2_candidate", keywords=["Kubernetes"]),
        ],
    )
    full_bank = _bank([full_role1, full_role2])

    result = patch.apply_p1(
        candidate, full_bank, profile="ai_ml_engineer", required_keywords=["Kubernetes"]
    )
    assert "r1_candidate" in {b.id for b in result.roles[0].bullets}
    assert [b.id for b in result.roles[1].bullets] == ["r2_low"]


# ---------------------------------------------------------------------------
# P2: promote
# ---------------------------------------------------------------------------


def test_p2_promotes_section_containing_the_only_source_of_a_missing_keyword():
    work_role = _role("r_work", bullets=[_bullet("w1", keywords=[])])
    project_role = _role(
        "r_proj",
        kind="project",
        start=None,
        end=None,
        bullets=[_bullet("p1", keywords=["Kubernetes"])],
    )
    candidate = _bank([work_role, project_role])
    section_order = ["work_history", "projects", "education"]

    _, new_section_order = patch.apply_p2(
        candidate, section_order, required_keywords=["Kubernetes"]
    )
    assert new_section_order[0] == "projects"


def test_p2_promotes_project_role_within_its_section():
    project_low = _role(
        "p_low",
        kind="project",
        start=None,
        end=None,
        bullets=[_bullet("pl1", keywords=[])],
    )
    project_high = _role(
        "p_high",
        kind="project",
        start=None,
        end=None,
        bullets=[_bullet("ph1", keywords=["Kubernetes"])],
    )
    candidate = _bank([project_low, project_high])
    section_order = ["projects"]

    new_bank, _ = patch.apply_p2(
        candidate, section_order, required_keywords=["Kubernetes"]
    )
    project_roles = [r for r in new_bank.roles if r.kind == "project"]
    assert project_roles[0].id == "p_high"


def test_p2_does_not_reorder_work_history_roles_within_section():
    # Work-history role promotion within-section is out of P2's scope
    # (would need R009-aware logic); only section-level promotion and
    # project-role within-section promotion are implemented.
    role_old = _role(
        "r_old", start="2018-01", end="2019-01", bullets=[_bullet("o1", keywords=[])]
    )
    role_new = _role(
        "r_new",
        start="2022-01",
        end="2023-01",
        bullets=[_bullet("n1", keywords=["Kubernetes"])],
    )
    candidate = _bank([role_old, role_new])
    section_order = ["work_history"]

    new_bank, _ = patch.apply_p2(
        candidate, section_order, required_keywords=["Kubernetes"]
    )
    assert [r.id for r in new_bank.roles] == ["r_old", "r_new"]


# ---------------------------------------------------------------------------
# run_ladder: real bank, real render, real PDF, real re-scoring
# ---------------------------------------------------------------------------


@pytest.fixture
def real_identity():
    return load_identity(_IDENTITY_PATH)


def test_run_ladder_closes_a_real_deficit_with_zero_model_calls(
    tmp_path, real_identity
):
    full_bank = load_bank()
    section_order = ["work_history", "projects", "education", "publications"]

    # A required keyword the bank genuinely has coverage for somewhere,
    # but not necessarily front-loaded or selected by the naive
    # select_for_profile() baseline alone: forces at least one tier to do
    # real work, not trivially pass at P0 with no changes needed.
    required_keywords = ["Python", "LLM", "RAG", "FastAPI", "embeddings"]

    result = patch.run_ladder(
        full_bank=full_bank,
        profile="ai_ml_engineer",
        identity=real_identity,
        section_order=section_order,
        out_dir=tmp_path,
        required_keywords=required_keywords,
        preferred_keywords=[],
    )

    assert result.tiers_applied  # at least one tier was attempted
    assert result.docx_path.exists()
    assert result.pdf_path.exists()
    assert isinstance(result.rubric_result, rules.RubricResult)


def test_run_ladder_creates_out_dir_if_missing(tmp_path, real_identity):
    full_bank = load_bank()
    section_order = ["work_history", "projects", "education", "publications"]
    out_dir = tmp_path / "does_not_exist_yet" / "nested"

    result = patch.run_ladder(
        full_bank=full_bank,
        profile="ai_ml_engineer",
        identity=real_identity,
        section_order=section_order,
        out_dir=out_dir,
        required_keywords=["Python"],
        preferred_keywords=[],
    )
    assert out_dir.is_dir()
    assert result.docx_path.exists()


def test_run_ladder_stops_at_first_tier_that_passes(tmp_path, real_identity):
    full_bank = load_bank()
    section_order = ["work_history", "projects", "education", "publications"]

    # A trivial, already-covered keyword: P0 alone (reordering only,
    # zero selection change) should already pass, so no P1/P2 needed.
    result = patch.run_ladder(
        full_bank=full_bank,
        profile="ai_ml_engineer",
        identity=real_identity,
        section_order=section_order,
        out_dir=tmp_path,
        required_keywords=["Python"],
        preferred_keywords=[],
    )
    if result.passed:
        assert result.tiers_applied == ["P0"]


def test_run_ladder_falls_through_to_p3_on_a_real_job_p0_p2_cannot_close(
    tmp_path, real_identity
):
    """Real required_keywords from a real, live-extracted job (Robinhood
    "Machine Learning Engineer", job_id 318 in the live db), confirmed
    during D3's grounding to NOT close via P0-P2 alone: the bank's
    ai_ml_engineer content has zero coverage for XGBoost/PyTorch/
    TensorFlow/Spark/Kafka/Kubernetes/SQL (a real, current content gap,
    not a synthetic edge case, per D29 in docs/decisions.md). This is
    the realistic common path per the user's own framing, not a rare
    corner: most real jobs' deficits genuinely cannot be closed, so the
    airtight guard rejecting a fabricated addition here, on a real
    unclosable gap, is the scenario that actually matters. LLM output is
    mocked (matching every other test in this suite, e.g. C1/C3's
    precedent) for repeatability; the real live-Ollama run proving this
    end to end is reported separately, not part of the automated suite."""
    full_bank = load_bank()
    section_order = ["work_history", "projects", "education", "publications"]
    required_keywords = [
        "Machine Learning",
        "Python",
        "SQL",
        "XGBoost",
        "Pytorch",
        "Tensorflow",
        "Spark",
        "Kafka",
        "Kubernetes",
    ]

    without_p3 = patch.run_ladder(
        full_bank=full_bank,
        profile="ai_ml_engineer",
        identity=real_identity,
        section_order=section_order,
        out_dir=tmp_path / "no_p3",
        required_keywords=required_keywords,
        preferred_keywords=[],
    )
    assert not without_p3.passed
    assert "R001" in without_p3.rubric_result.hard_failures

    # A plausible but fabricated model response: "SQL" is the first
    # actually-missing keyword (Machine Learning/Python are already
    # covered), and nothing in the real bank's ai_ml_engineer content
    # describes SQL work anywhere. A well-behaved model might still try,
    # since it was asked to.
    client = _FakeClient(
        {
            "text": "Built a routing engine that queried a SQL database "
            "for transcript metadata and scoring history.",
            "keywords_added": ["SQL"],
        }
    )
    with_p3 = patch.run_ladder(
        full_bank=full_bank,
        profile="ai_ml_engineer",
        identity=real_identity,
        section_order=section_order,
        out_dir=tmp_path / "with_p3",
        required_keywords=required_keywords,
        preferred_keywords=[],
        llm_config=_llm_config(),
        local_client=client,
    )

    assert "P3" in with_p3.tiers_applied
    assert len(with_p3.p3_attempts) >= 1
    assert all(not a.accepted for a in with_p3.p3_attempts)
    assert any("SQL" in (a.reason or "") for a in with_p3.p3_attempts)
    # Never silently written back: the canonical bank content is
    # unaffected by a discarded attempt.
    assert patch.apply_variants_to_bank(full_bank, with_p3.p3_attempts) == full_bank
    # The ladder honestly still reports the real failure, not a false pass.
    assert not with_p3.passed
    assert "R001" in with_p3.rubric_result.hard_failures


# ---------------------------------------------------------------------------
# D4: validate_rewrite, the airtight traceability guard (CLAUDE.md hard
# rule 12). This is the one place an LLM writes resume prose with no human
# review before D4's own re-scoring, so every case here matters, not just
# the happy path.
# ---------------------------------------------------------------------------


def _source_bullet(**overrides) -> Bullet:
    fields = {
        "id": "b_test_01",
        "status": "verified",
        "what": "a modular routing engine",
        "how": "separated transcription from scoring across 8 modules using Python",
        "result": "cut audio API costs by 30 percent",
        "text": "Built a modular routing engine that separated transcription "
        "from scoring across 8 modules using Python, cutting audio API costs",
        "keywords": ["routing engine", "audio API", "Python"],
        "evidence": "internal",
        "profiles": ["ai_ml_engineer"],
    }
    fields.update(overrides)
    return Bullet(**fields)


def test_validate_rewrite_allows_pure_rephrasing_of_existing_claims():
    bullet = _source_bullet()
    new_text = (
        "Built a routing engine in Python that separated transcription from "
        "scoring, cutting audio API costs."
    )
    violations = patch.validate_rewrite(bullet, new_text, [], _identity())
    assert violations == []


def test_validate_rewrite_rejects_a_novel_proper_noun():
    bullet = _source_bullet()
    new_text = "Built a routing engine deployed on Kubernetes across 8 modules."
    violations = patch.validate_rewrite(bullet, new_text, [], _identity())
    assert violations != []
    assert any("Kubernetes" in v for v in violations)


def test_validate_rewrite_rejects_a_novel_number():
    bullet = _source_bullet()
    new_text = "Built a routing engine that served 50 requests per second."
    violations = patch.validate_rewrite(bullet, new_text, [], _identity())
    assert violations != []


def test_validate_rewrite_allows_a_number_already_in_the_parent():
    bullet = _source_bullet()  # "result" already mentions "30 percent"
    new_text = "Built a routing engine that cut audio API costs by 30 percent."
    violations = patch.validate_rewrite(bullet, new_text, [], _identity())
    assert violations == []


def test_validate_rewrite_allows_a_proper_noun_already_in_the_parent():
    bullet = _source_bullet()  # "how" already mentions Python
    new_text = "Built a Python routing engine that separated transcription."
    violations = patch.validate_rewrite(bullet, new_text, [], _identity())
    assert violations == []


def test_validate_rewrite_allows_identity_toml_content():
    identity = _identity(city="Austin")
    bullet = _source_bullet()
    new_text = "Built a routing engine while based in Austin, cutting costs."
    violations = patch.validate_rewrite(bullet, new_text, [], identity)
    assert violations == []


def test_validate_rewrite_does_not_flag_the_sentence_initial_word():
    # The bullet's own opening verb is always capitalized by position, not
    # because it's a new proper-noun claim; index 0 must never be flagged.
    bullet = _source_bullet()
    new_text = "Streamlined the routing engine that separated transcription."
    violations = patch.validate_rewrite(bullet, new_text, [], _identity())
    assert not any("Streamlined" in v for v in violations)


def test_validate_rewrite_is_case_insensitive_against_the_parent():
    bullet = _source_bullet()  # "how" mentions "Python" (capitalized)
    new_text = "Built a python-based routing engine for transcription."
    violations = patch.validate_rewrite(bullet, new_text, [], _identity())
    assert violations == []


def test_validate_rewrite_allows_keyword_already_tagged_on_the_bullet():
    bullet = _source_bullet(keywords=["Python", "routing engine"])
    new_text = "Built a Python routing engine for transcription and scoring."
    violations = patch.validate_rewrite(bullet, new_text, ["Python"], _identity())
    assert violations == []


def test_validate_rewrite_allows_keyword_described_but_not_tagged():
    # "audio API" appears in the parent's own text/keywords already, so
    # adding it as a keyword just tags what was already there.
    bullet = _source_bullet(keywords=["routing engine"])  # audio API untagged
    new_text = "Built a routing engine that cut audio API costs."
    violations = patch.validate_rewrite(bullet, new_text, ["audio API"], _identity())
    assert violations == []


def test_validate_rewrite_rejects_keyword_neither_tagged_nor_described():
    bullet = _source_bullet(keywords=["routing engine"])
    new_text = "Built a routing engine that separated transcription from scoring."
    violations = patch.validate_rewrite(bullet, new_text, ["Kubernetes"], _identity())
    assert any("Kubernetes" in v for v in violations)


def test_validate_rewrite_rejects_fabricated_keyword_even_if_text_is_clean():
    # The rewritten TEXT itself introduces no new token, but the model
    # claims to have added a keyword the parent never supports: this must
    # still be rejected, since accepting it would silently misrepresent
    # what the bullet covers (a false ATS-matching claim, not a prose one).
    bullet = _source_bullet(keywords=["routing engine"])
    new_text = "Built a routing engine that separated transcription from scoring."
    violations = patch.validate_rewrite(bullet, new_text, ["TensorFlow"], _identity())
    assert violations != []


def test_validate_rewrite_rejects_multiple_violations_independently():
    bullet = _source_bullet(keywords=["routing engine"])
    new_text = "Built a Kubernetes routing engine that served 99 requests."
    violations = patch.validate_rewrite(bullet, new_text, ["TensorFlow"], _identity())
    joined = " ".join(violations)
    assert "Kubernetes" in joined
    assert "99" in joined
    assert "TensorFlow" in joined


# ---------------------------------------------------------------------------
# D4: call_rephrase (mocked LLM client), _select_p3_target,
# _best_existing_variant, _passes_prose_gates, apply_p3, apply_variants_to_bank
# ---------------------------------------------------------------------------


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
        self.calls: list[dict] = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._content)


def test_call_rephrase_sets_think_false_and_uses_rephrase_stage():
    bullet = _source_bullet()
    client = _FakeClient({"text": "Built a thing.", "keywords_added": []})
    result = asyncio.run(
        patch.call_rephrase(bullet, ["Kubernetes"], _llm_config(), local_client=client)
    )
    assert len(client.calls) == 1
    assert client.calls[0]["think"] is False
    assert result.output["text"] == "Built a thing."


def test_call_rephrase_input_is_only_what_how_result_and_keywords():
    bullet = _source_bullet()
    client = _FakeClient({"text": "Built a thing.", "keywords_added": []})
    asyncio.run(
        patch.call_rephrase(bullet, ["Kubernetes"], _llm_config(), local_client=client)
    )
    prompt = client.calls[0]["messages"][0]["content"]
    assert bullet.what in prompt
    assert bullet.how in prompt
    assert bullet.result in prompt
    assert "Kubernetes" in prompt
    # never the bullet's own canonical text or id, and never a JD.
    assert bullet.text not in prompt
    assert bullet.id not in prompt


def test_select_p3_target_picks_fewest_keywords_then_shortest_text():
    role = Role(
        id="r1",
        company="Acme",
        location="Remote",
        start="2022-01",
        end="2023-01",
        kind="full_time",
        title={"default": "Engineer"},
        summary=_summary("r1_s"),
        bullets=[
            _source_bullet(id="b_many_kw", keywords=["a", "b", "c"], text="short"),
            _source_bullet(id="b_few_kw_long", keywords=["a"], text="x" * 100),
            _source_bullet(id="b_few_kw_short", keywords=["a"], text="short text"),
        ],
    )
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])
    target = patch._select_p3_target(bank)
    assert target is not None
    assert target[1].id == "b_few_kw_short"


def test_select_p3_target_returns_none_for_empty_bank():
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[])
    assert patch._select_p3_target(bank) is None


def test_best_existing_variant_picks_the_one_covering_missing_keywords():
    v1 = BulletVariant(text="v1", keywords_added=["Docker"], created_at="2026-01-01")
    v2 = BulletVariant(
        text="v2", keywords_added=["Kubernetes"], created_at="2026-01-01"
    )
    bullet = _source_bullet(variants=[v1, v2])
    best = patch._best_existing_variant(bullet, ["Kubernetes"])
    assert best is not None
    assert best.text == "v2"


def test_best_existing_variant_returns_none_when_no_variant_covers_it():
    v1 = BulletVariant(text="v1", keywords_added=["Docker"], created_at="2026-01-01")
    bullet = _source_bullet(variants=[v1])
    assert patch._best_existing_variant(bullet, ["Kubernetes"]) is None


def test_passes_prose_gates_rejects_multiple_periods():
    role = _valid_p3_role()
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])
    problems = patch._passes_prose_gates(bank, "Built a thing. Then another.")
    assert any("R005" in p for p in problems)


def test_passes_prose_gates_rejects_first_person_pronoun():
    role = _valid_p3_role()
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])
    problems = patch._passes_prose_gates(bank, "I built a thing that worked.")
    assert any("R008" in p for p in problems)


def test_passes_prose_gates_rejects_present_tense():
    role = _valid_p3_role()
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])
    problems = patch._passes_prose_gates(bank, "Manages a team of five people.")
    assert any("R007" in p for p in problems)


def test_passes_prose_gates_rejects_overlong_text():
    role = _valid_p3_role()
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])
    problems = patch._passes_prose_gates(bank, "Built " + "x" * 400)
    assert any("R006" in p for p in problems)


def test_passes_prose_gates_accepts_clean_text():
    role = _valid_p3_role()
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])
    problems = patch._passes_prose_gates(bank, "Built a clean thing that worked well.")
    assert problems == []


def _valid_p3_role() -> Role:
    return Role(
        id="r1",
        company="Acme",
        location="Remote",
        start="2022-01",
        end="2023-01",
        kind="full_time",
        title={"default": "Engineer"},
        summary=_summary("r1_s"),
        bullets=[
            _source_bullet(id="b1"),
            _source_bullet(
                id="b2", text="Shipped a second bullet that also works well."
            ),
        ],
    )


def test_apply_p3_reuses_existing_variant_with_zero_llm_calls():
    # "Python" is chosen deliberately, not "Kubernetes": it already appears
    # in the parent bullet's "how" field, so this is a legitimate rewrite
    # (surfacing an already-implied skill as an explicit tag), not a
    # fabrication validate_rewrite would (correctly) reject.
    variant = BulletVariant(
        text="Built a Python routing engine for transcription and scoring.",
        keywords_added=["Python"],
        created_at="2026-01-01",
    )
    bullet = _source_bullet(id="b1", variants=[variant])
    role = _valid_p3_role()
    role = role.model_copy(update={"bullets": [bullet, _source_bullet(id="b2")]})
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])

    client = _FakeClient({"text": "should not be called", "keywords_added": []})
    new_bank, attempts = patch.apply_p3(
        bank, bank, ["Python"], _identity(), _llm_config(), local_client=client
    )
    assert len(client.calls) == 0
    assert len(attempts) == 1
    assert attempts[0].accepted is True
    assert attempts[0].reused_existing_variant is True
    assert new_bank.roles[0].bullets[0].text == variant.text


def test_apply_p3_makes_a_new_call_when_no_variant_covers_the_keyword():
    role = _valid_p3_role()
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])
    client = _FakeClient(
        {
            "text": "Built a Python routing engine for transcription and scoring.",
            "keywords_added": ["Python"],
        }
    )
    _, attempts = patch.apply_p3(
        bank, bank, ["Python"], _identity(), _llm_config(), local_client=client
    )
    assert len(client.calls) == 1
    assert len(attempts) == 1
    assert attempts[0].accepted is True
    assert attempts[0].reused_existing_variant is False


def test_apply_p3_accepted_rewrite_merges_keywords_added_into_the_working_bank():
    # An accepted rewrite must actually improve this job's coverage math,
    # not just swap the text: keywords_added has to land on the returned
    # bank's bullet.keywords, or R001 never sees the improvement. b1's
    # default keywords are ["routing engine", "audio API"] (see
    # _source_bullet); "Python" is described in "how" but not tagged.
    role = _valid_p3_role()
    role = role.model_copy(
        update={
            "bullets": [
                _source_bullet(id="b1", keywords=["routing engine", "audio API"]),
                _source_bullet(id="b2"),
            ]
        }
    )
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])
    client = _FakeClient(
        {
            "text": "Built a Python routing engine for transcription and scoring.",
            "keywords_added": ["Python"],
        }
    )
    new_bank, attempts = patch.apply_p3(
        bank, bank, ["Python"], _identity(), _llm_config(), local_client=client
    )
    assert attempts[0].accepted is True
    assert "Python" in new_bank.roles[0].bullets[0].keywords
    assert measure.coverage(new_bank, ["Python"]) == 1.0


def test_apply_p3_discards_a_rewrite_that_fails_the_traceability_guard():
    role = _valid_p3_role()
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])
    client = _FakeClient(
        {
            "text": "Built a routing engine deployed on Kubernetes clusters.",
            "keywords_added": ["Kubernetes"],
        }
    )
    new_bank, attempts = patch.apply_p3(
        bank, bank, ["Kubernetes"], _identity(), _llm_config(), local_client=client
    )
    assert attempts[0].accepted is False
    assert "Kubernetes" in attempts[0].reason
    # unaccepted: canonical bank content is unchanged.
    assert new_bank.roles[0].bullets[0].text == role.bullets[0].text


def test_apply_p3_discards_a_rewrite_that_fails_prose_gates():
    role = _valid_p3_role()
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])
    client = _FakeClient(
        {"text": "I built a thing using Python already.", "keywords_added": []}
    )
    _, attempts = patch.apply_p3(
        bank, bank, ["Python"], _identity(), _llm_config(), local_client=client
    )
    assert attempts[0].accepted is False
    assert "R008" in attempts[0].reason


def test_apply_p3_never_exceeds_max_two_new_llm_calls():
    role = _valid_p3_role()
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])
    # Every candidate gets rejected (fabricated keyword), forcing apply_p3
    # to move to the next-best bullet each time, up to the cap.
    client = _FakeClient(
        {
            "text": "Built a thing deployed on Kubernetes.",
            "keywords_added": ["Kubernetes"],
        }
    )
    _, attempts = patch.apply_p3(
        bank, bank, ["Kubernetes"], _identity(), _llm_config(), local_client=client
    )
    assert len(client.calls) <= 2
    assert all(not a.accepted for a in attempts)


def test_apply_p3_returns_unchanged_bank_with_no_missing_keywords():
    role = _valid_p3_role()
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])
    client = _FakeClient({"text": "should not be called", "keywords_added": []})
    new_bank, attempts = patch.apply_p3(
        bank, bank, [], _identity(), _llm_config(), local_client=client
    )
    assert attempts == []
    assert len(client.calls) == 0
    assert new_bank == bank


def test_apply_p3_returns_unchanged_bank_with_no_llm_config():
    role = _valid_p3_role()
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])
    new_bank, attempts = patch.apply_p3(bank, bank, ["Kubernetes"], _identity(), None)
    assert attempts == []
    assert new_bank == bank


def test_apply_variants_to_bank_creates_a_new_variant_on_first_use():
    role = _valid_p3_role()
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])
    attempts = [
        patch.P3Attempt(
            role_id="r1",
            bullet_id="b1",
            text="Built a Kubernetes routing engine for transcription.",
            keywords_added=["Kubernetes"],
            reused_existing_variant=False,
            accepted=True,
        )
    ]
    new_bank = patch.apply_variants_to_bank(bank, attempts)
    variants = new_bank.roles[0].bullets[0].variants
    assert len(variants) == 1
    assert variants[0].used_count == 1
    assert variants[0].keywords_added == ["Kubernetes"]
    # canonical text is untouched.
    assert new_bank.roles[0].bullets[0].text == role.bullets[0].text


def test_apply_variants_to_bank_increments_used_count_on_reuse():
    variant = BulletVariant(
        text="Built a Kubernetes routing engine for transcription.",
        keywords_added=["Kubernetes"],
        created_at="2026-01-01",
        used_count=3,
    )
    bullet = _source_bullet(id="b1", variants=[variant])
    role = _valid_p3_role().model_copy(
        update={"bullets": [bullet, _source_bullet(id="b2")]}
    )
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])
    attempts = [
        patch.P3Attempt(
            role_id="r1",
            bullet_id="b1",
            text=variant.text,
            keywords_added=["Kubernetes"],
            reused_existing_variant=True,
            accepted=True,
        )
    ]
    new_bank = patch.apply_variants_to_bank(bank, attempts)
    variants = new_bank.roles[0].bullets[0].variants
    assert len(variants) == 1
    assert variants[0].used_count == 4


def test_apply_variants_to_bank_ignores_discarded_attempts():
    role = _valid_p3_role()
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])
    attempts = [
        patch.P3Attempt(
            role_id="r1",
            bullet_id="b1",
            text="discarded text",
            keywords_added=[],
            reused_existing_variant=False,
            accepted=False,
            reason="failed guard",
        )
    ]
    new_bank = patch.apply_variants_to_bank(bank, attempts)
    assert new_bank == bank


def test_accepted_p3_rewrite_survives_persist_reload_and_is_reused_with_coverage_intact(
    tmp_path,
):
    """The full chain, not just its pieces: an accepted P3 rewrite ->
    apply_variants_to_bank -> dump_bank -> load_bank -> a SECOND,
    independent apply_p3 call against the reloaded bank -> reuses the
    variant (zero new LLM calls) -> coverage still reflects the
    improvement. Each step has its own unit test elsewhere; this is the
    one that proves they compose, on the exact same bullet/keyword case
    throughout, not a fresh similar case that happens to also pass.

    Shaped like the real bug's reproduction case (required_keywords=
    ["CMB"] against role_utd_researcher's b_utd_02, see D30 in
    docs/decisions.md): "Python" is genuinely in this bullet's "how" text
    but deliberately NOT in its keywords tag list, so it is a real,
    closeable gap, not an already-covered no-op. Two filler bullets with
    more keywords than the target keep the role within R003's 3-8 range
    (slop_lint's H004, checked inside _passes_prose_gates) while making
    _select_p3_target's "fewest keywords" tie-break land on the intended
    bullet unambiguously."""
    bullet = _source_bullet(id="b1", keywords=["routing engine"])
    filler_1 = _source_bullet(
        id="b2",
        text="Shipped a second bullet that also works well.",
        keywords=["routing engine", "audio API", "extra keyword"],
    )
    filler_2 = _source_bullet(
        id="b3",
        text="Deployed a third bullet that also works well.",
        keywords=["routing engine", "audio API", "another keyword"],
    )
    role = Role(
        id="r1",
        company="Acme",
        location="Remote",
        start="2022-01",
        end="2023-01",
        kind="full_time",
        title={"default": "Engineer"},
        summary=_summary("r1_s"),
        bullets=[bullet, filler_1, filler_2],
    )
    bank = Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])
    assert measure.coverage(bank, ["Python"]) == 0.0  # genuinely missing at the start

    first_call_client = _FakeClient(
        {
            "text": "Built a routing engine in Python that separated transcription "
            "from scoring across 8 modules.",
            "keywords_added": ["Python"],
        }
    )
    working_after_first, attempts = patch.apply_p3(
        bank,
        bank,
        ["Python"],
        _identity(),
        _llm_config(),
        local_client=first_call_client,
    )
    assert len(first_call_client.calls) == 1
    assert attempts[0].accepted is True
    assert attempts[0].role_id == "r1"
    assert attempts[0].bullet_id == "b1"
    assert measure.coverage(working_after_first, ["Python"]) == 1.0

    canonical_with_variant = patch.apply_variants_to_bank(bank, attempts)
    # Canonical tags/text are untouched; only the variant list gained an entry.
    assert canonical_with_variant.roles[0].bullets[0].keywords == ["routing engine"]
    assert measure.coverage(canonical_with_variant, ["Python"]) == 0.0

    persisted_path = tmp_path / "bank_with_variant.yaml"
    dump_bank(canonical_with_variant, persisted_path)
    reloaded = load_bank(persisted_path)
    assert reloaded == canonical_with_variant

    # A second, independent apply_p3 call against the RELOADED bank: must
    # reuse the persisted variant, spending zero new LLM calls.
    second_call_client = _FakeClient(
        {"text": "should not be called", "keywords_added": []}
    )
    working_after_second, attempts2 = patch.apply_p3(
        reloaded,
        reloaded,
        ["Python"],
        _identity(),
        _llm_config(),
        local_client=second_call_client,
    )
    assert len(second_call_client.calls) == 0
    assert attempts2[0].accepted is True
    assert attempts2[0].reused_existing_variant is True
    assert "Python" in working_after_second.roles[0].bullets[0].keywords
    assert measure.coverage(working_after_second, ["Python"]) == 1.0

    final_bank = patch.apply_variants_to_bank(reloaded, attempts2)
    reused_bullet = final_bank.roles[0].bullets[0]
    assert reused_bullet.variants[0].used_count == 2
