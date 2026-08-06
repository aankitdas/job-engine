import pytest
from pydantic import ValidationError

from jobengine.db.migrate import connect, init
from jobengine.resume.bank import (
    DEFAULT_BANK_PATH,
    Bank,
    Bullet,
    BulletVariant,
    Education,
    Meta,
    Role,
    SummaryBullet,
    coverage_gaps,
    dump_bank,
    load_bank,
    validate_bank,
)


def _valid_bullet(**overrides) -> Bullet:
    fields = {
        "id": "b_test_01",
        "status": "verified",
        "what": "a modular routing engine",
        "how": "separated transcription from scoring across 8 modules",
        "result": "cut audio API costs",
        "text": "Built a modular routing engine that separated transcription "
        "from scoring across 8 modules, cutting audio API costs",
        "keywords": ["routing engine", "audio API"],
        "evidence": "internal",
        "profiles": ["ai_ml_engineer"],
    }
    fields.update(overrides)
    return Bullet(**fields)


def _valid_summary(**overrides) -> SummaryBullet:
    fields = {
        "id": "b_test_sum",
        "text": "Built the systems behind a product by turning input into output",
        "keywords": ["systems"],
        "status": "verified",
    }
    fields.update(overrides)
    return SummaryBullet(**fields)


def _valid_role(**overrides) -> Role:
    fields = {
        "id": "role_test",
        "company": "TestCo",
        "location": "Texas",
        "start": "2026-01",
        "end": None,
        "kind": "full_time",
        "title": {"default": "AI Engineer"},
        "summary": _valid_summary(),
        "bullets": [
            _valid_bullet(),
            _valid_bullet(id="b_test_02"),
        ],
    }
    fields.update(overrides)
    return Role(**fields)


def _bank_with_role(role: Role) -> Bank:
    return Bank(meta=Meta(owner="Test", updated="2026-01-01"), roles=[role])


def test_project_role_needs_no_company_location_or_start():
    """Per Lee's rule, projects skip dates and location entirely, unlike
    full_time/internship/research roles."""
    role = _valid_role(
        kind="project", company=None, location=None, start=None, end=None
    )
    report = validate_bank(_bank_with_role(role))
    assert report.ok


def test_clean_bank_has_no_errors_or_warnings():
    report = validate_bank(_bank_with_role(_valid_role()))
    assert report.errors == []
    assert report.warnings == []
    assert report.ok


def test_rule1_duplicate_ids_across_entities():
    role = _valid_role(
        summary=_valid_summary(id="b_test_01")  # collides with bullet id
    )
    report = validate_bank(_bank_with_role(role))
    assert any(issue.rule == "R1" for issue in report.errors)


def test_rule2_verified_requires_evidence():
    role = _valid_role(
        bullets=[
            _valid_bullet(evidence=None),
            _valid_bullet(id="b_test_02"),
        ]
    )
    report = validate_bank(_bank_with_role(role))
    assert any(issue.rule == "R2" for issue in report.errors)


def test_rule3_speculative_is_a_warning_not_an_error():
    role = _valid_role(
        bullets=[
            _valid_bullet(status="speculative", evidence=None),
            _valid_bullet(id="b_test_02"),
        ]
    )
    report = validate_bank(_bank_with_role(role))
    assert any(issue.rule == "R3" for issue in report.warnings)
    assert not any(issue.rule == "R3" for issue in report.errors)


def test_rule4_what_how_result_must_be_non_empty():
    role = _valid_role(
        bullets=[
            _valid_bullet(how=""),
            _valid_bullet(id="b_test_02"),
        ]
    )
    report = validate_bank(_bank_with_role(role))
    assert any(issue.rule == "R4" for issue in report.errors)


def test_rule5_at_most_one_period():
    role = _valid_role(
        bullets=[
            _valid_bullet(text="Built a thing. Then shipped it."),
            _valid_bullet(id="b_test_02"),
        ]
    )
    report = validate_bank(_bank_with_role(role))
    assert any(issue.rule == "R5" for issue in report.errors)


def test_rule6_text_must_open_in_past_tense():
    role = _valid_role(
        bullets=[
            _valid_bullet(text="Building a routing engine for audio API scoring"),
            _valid_bullet(id="b_test_02"),
        ]
    )
    report = validate_bank(_bank_with_role(role))
    assert any(issue.rule == "R6" for issue in report.errors)


def test_rule7_long_text_is_a_warning_not_an_error():
    long_text = "Built " + "a very long resume bullet clause " * 12 + "here"
    role = _valid_role(
        bullets=[
            _valid_bullet(text=long_text, keywords=[]),
            _valid_bullet(id="b_test_02"),
        ]
    )
    report = validate_bank(_bank_with_role(role))
    assert any(issue.rule == "R7" for issue in report.warnings)
    assert not any(issue.rule == "R7" for issue in report.errors)


def test_rule8_summary_is_a_single_required_field_not_a_list():
    # Structural, not a validate_bank check: a role with no summary key
    # cannot be parsed into a Role at all, since summary is a required
    # single field rather than a list.
    fields = {
        "id": "role_test",
        "company": "TestCo",
        "location": "Texas",
        "start": "2026-01",
        "kind": "full_time",
        "title": {"default": "AI Engineer"},
        "bullets": [_valid_bullet()],
    }
    with pytest.raises(ValidationError):
        Role(**fields)


def test_rule9_role_needs_between_3_and_8_total_bullets():
    role = _valid_role(bullets=[_valid_bullet()])  # 1 bullet + summary = 2
    report = validate_bank(_bank_with_role(role))
    assert any(issue.rule == "R9" for issue in report.errors)


def test_rule10_is_enforced_by_coverage_not_validate():
    """Rule 10 ("every keyword appears in at least one bullet, or it is
    dead weight") is not a per-bullet text-match check: the spec's own
    role_bantrly example tags its summary with FastAPI/Python while
    deliberately not naming them in the plain-English sentence. So
    validate() does not flag this, and coverage_gaps() is where dead
    weight actually surfaces, against keyword_corpus."""
    role = _valid_role(
        bullets=[
            _valid_bullet(
                text="Built a routing engine for scoring student audio",
                keywords=["FastAPI"],
            ),
            _valid_bullet(id="b_test_02"),
        ]
    )
    report = validate_bank(_bank_with_role(role))
    assert not any(issue.rule == "R10" for issue in report.errors)


def test_coverage_gaps_flags_corpus_keywords_with_no_backing_bullet(tmp_path):
    conn = connect(tmp_path / "jobengine.db")
    init(conn)
    conn.execute(
        "INSERT INTO keyword_corpus (profile, keyword, occurrences, "
        "first_seen_at, last_seen_at) VALUES "
        "('ai_ml_engineer', 'routing engine', 5, 'now', 'now'), "
        "('ai_ml_engineer', 'Kubernetes', 3, 'now', 'now')"
    )
    conn.commit()

    role = _valid_role()  # its bullets carry keyword "routing engine"
    bank = _bank_with_role(role)

    gaps = coverage_gaps(bank, conn, "ai_ml_engineer")
    conn.close()

    gap_keywords = {keyword for keyword, _ in gaps}
    assert "Kubernetes" in gap_keywords
    assert "routing engine" not in gap_keywords


def test_unknown_profile_on_bullet_is_flagged():
    role = _valid_role(
        bullets=[
            _valid_bullet(profiles=["quantum_wizard"]),
            _valid_bullet(id="b_test_02"),
        ]
    )
    report = validate_bank(_bank_with_role(role))
    assert any(issue.rule == "profiles" for issue in report.errors)


def test_education_requires_degree_profiles_is_just_loaded():
    edu = Education(
        id="edu_test",
        degree="MS",
        field="Computer Engineering",
        institution="UT Dallas",
        status="May 2025",
        requires_degree_profiles=["ai_ml_engineer"],
    )
    bank = Bank(meta=Meta(owner="Test", updated="2026-01-01"), education=[edu])
    report = validate_bank(bank)
    assert report.ok


def test_unknown_profile_in_requires_degree_profiles_is_flagged():
    edu = Education(
        id="edu_test",
        degree="MS",
        field="Computer Engineering",
        institution="UT Dallas",
        status="May 2025",
        requires_degree_profiles=["quantum_wizard"],
    )
    bank = Bank(meta=Meta(owner="Test", updated="2026-01-01"), education=[edu])
    report = validate_bank(bank)
    assert any(issue.rule == "profiles" for issue in report.errors)


# ---------------------------------------------------------------------------
# D4: BulletVariant, Bullet.variants, dump_bank round-trip
# ---------------------------------------------------------------------------


def test_bullet_defaults_to_no_variants():
    bullet = _valid_bullet()
    assert bullet.variants == []


def test_bullet_accepts_a_variant():
    variant = BulletVariant(
        text="Rewritten phrasing that adds a keyword.",
        keywords_added=["Kubernetes"],
        created_at="2026-08-05",
        used_count=1,
    )
    bullet = _valid_bullet(variants=[variant])
    assert bullet.variants[0].text == "Rewritten phrasing that adds a keyword."
    assert bullet.variants[0].keywords_added == ["Kubernetes"]
    assert bullet.variants[0].used_count == 1


def test_variant_used_count_defaults_to_zero():
    variant = BulletVariant(text="...", created_at="2026-08-05")
    assert variant.used_count == 0
    assert variant.keywords_added == []


def test_dump_bank_round_trips_a_small_bank(tmp_path):
    role = _valid_role()
    bank = _bank_with_role(role)
    out_path = tmp_path / "bank.yaml"

    dump_bank(bank, out_path)
    reloaded = load_bank(out_path)

    assert reloaded == bank


def test_dump_bank_round_trips_a_bullet_with_a_variant(tmp_path):
    variant = BulletVariant(
        text="Rewritten phrasing.",
        keywords_added=["Kubernetes"],
        created_at="2026-08-05",
        used_count=2,
    )
    role = _valid_role(bullets=[_valid_bullet(variants=[variant])])
    bank = _bank_with_role(role)
    out_path = tmp_path / "bank.yaml"

    dump_bank(bank, out_path)
    reloaded = load_bank(out_path)

    assert reloaded == bank
    assert reloaded.roles[0].bullets[0].variants[0].used_count == 2


def test_dump_bank_round_trips_the_real_bank_with_no_data_loss(tmp_path):
    """Not a formatting-fidelity guarantee (a generic YAML dumper will not
    byte-for-byte match a hand-authored file's exact style), only a data
    one: every field pydantic-equal after load -> dump -> reload. Wiring
    this against the real resume/bank/aankit.yaml automatically is a
    separate, deliberate action, confirmed by asking not to build yet
    (see D30 in docs/decisions.md); this test only proves the mechanism
    is safe to use later, via a tmp_path copy, never writing to the real
    file."""
    original = load_bank(DEFAULT_BANK_PATH)
    out_path = tmp_path / "aankit_copy.yaml"

    dump_bank(original, out_path)
    reloaded = load_bank(out_path)

    assert reloaded == original
