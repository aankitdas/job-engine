"""One failing fixture per rule in specs/02-slop-linter.md, plus one clean
sample pulled from the real bank (per the spec's own definition of done,
this doubles as a regression check on resume/bank/aankit.yaml itself).

slop_lint.py does not exist yet. Every test here is expected to fail on
collection or on first call until it is implemented.
"""

from jobengine.db.migrate import connect, init
from jobengine.resume.bank import load_bank as load_real_bank
from jobengine.resume.slop_lint import (
    LintBullet,
    LintRole,
    LintSummary,
    LintTarget,
    lint_path,
    lint_target,
)

# ---------------------------------------------------------------------------
# Synthetic fixtures. Each bad fixture only needs to reliably trigger its own
# rule; it does not need to stay clean on every other rule too.
# ---------------------------------------------------------------------------


def _lint_bullet(**overrides) -> LintBullet:
    fields = {
        "id": "b_test_01",
        "text": "Built a modular routing engine that separated "
        "transcription from scoring across 8 assessment modules, "
        "cutting audio API costs and improving accuracy",
        "keywords": ["Python", "FastAPI"],
        "status": "verified",
    }
    fields.update(overrides)
    return LintBullet(**fields)


def _lint_summary(**overrides) -> LintSummary:
    fields = {
        "id": "b_test_sum",
        "text": "Built the systems behind a product by turning input into output",
        "keywords": [],
        "status": "verified",
    }
    fields.update(overrides)
    return LintSummary(**fields)


def _lint_role(**overrides) -> LintRole:
    fields = {
        "id": "role_test",
        "summary": _lint_summary(),
        "bullets": [_lint_bullet(), _lint_bullet(id="b_test_02")],
    }
    fields.update(overrides)
    return LintRole(**fields)


def _target(role: LintRole) -> LintTarget:
    return LintTarget(roles=[role])


# Ground truth id set for the synthetic fixtures above. A superset of
# whatever a given test actually uses is fine, H008 only cares about ids
# that are missing, not extras.
_ALL_TEST_IDS = {"b_test_sum", "b_test_01", "b_test_02"}

_LONG_BULLET_TEXT = (
    "Built a modular routing engine that separated transcription from "
    "scoring across many assessment modules while also handling "
    "authentication authorization logging metrics tracing caching "
    "batching retries and a fairly large amount of additional plumbing "
    "work across the entire distributed system end to end and shipped "
    "it to every classroom in the district ahead of schedule"
)


def test_clean_target_has_no_errors_or_warnings():
    report = lint_target(_target(_lint_role()), bank_ids=_ALL_TEST_IDS)
    assert report.errors == []
    assert report.fatal == []
    # W002 is a documented stub (see test_w002 below), it always fires.
    assert [w.rule for w in report.warnings] == ["W002"]
    assert report.ok


def test_clean_real_bank_bullet_passes_everything():
    """The clean sample is the real role_bantrly role from
    resume/bank/aankit.yaml (including b_bantrly_01), not a hand-written
    string, so this test also regression-checks the real bank content, per
    spec 02's own definition of done. All 5 of the role's real bullets are
    carried over, not just one, so H004's bullet-count check (which has
    nothing to do with prose quality) doesn't fire on a single-bullet role
    that was never a realistic target in the first place."""
    bank = load_real_bank()
    role = next(r for r in bank.roles if r.id == "role_bantrly")
    assert any(b.id == "b_bantrly_01" for b in role.bullets)

    lint_role = LintRole(
        id=role.id,
        summary=LintSummary(
            id=role.summary.id,
            text=role.summary.text,
            keywords=role.summary.keywords,
            status=role.summary.status,
        ),
        bullets=[
            LintBullet(
                id=bullet.id,
                text=bullet.text,
                keywords=bullet.keywords,
                status=bullet.status,
            )
            for bullet in role.bullets
        ],
    )
    bank_ids = set()
    for other_role in bank.roles:
        bank_ids.add(other_role.summary.id)
        bank_ids.update(b.id for b in other_role.bullets)

    report = lint_target(_target(lint_role), bank_ids=bank_ids)
    assert report.errors == []
    assert report.fatal == []
    assert [w.rule for w in report.warnings] == ["W002"]


def test_s001_em_dash_used_as_punctuation():
    role = _lint_role(
        bullets=[
            _lint_bullet(text="Built a routing engine — cutting audio costs"),
            _lint_bullet(id="b_test_02"),
        ]
    )
    report = lint_target(_target(role), bank_ids=_ALL_TEST_IDS)
    assert any(issue.rule == "S001" for issue in report.errors)


def test_s002_banned_vocabulary():
    role = _lint_role(
        bullets=[
            _lint_bullet(
                text="Leveraged a robust, seamless pipeline to streamline reporting"
            ),
            _lint_bullet(id="b_test_02"),
        ]
    )
    report = lint_target(_target(role), bank_ids=_ALL_TEST_IDS)
    assert any(issue.rule == "S002" for issue in report.errors)


def test_s003_contrast_construction():
    role = _lint_role(
        bullets=[
            _lint_bullet(
                text="Built not just a dashboard, but a full analytics platform"
            ),
            _lint_bullet(id="b_test_02"),
        ]
    )
    report = lint_target(_target(role), bank_ids=_ALL_TEST_IDS)
    assert any(issue.rule == "S003" for issue in report.errors)


def test_s004_gerund_triad():
    role = _lint_role(
        bullets=[
            _lint_bullet(
                text="Built a platform, streamlining onboarding, automating "
                "reports, and improving retention"
            ),
            _lint_bullet(id="b_test_02"),
        ]
    )
    report = lint_target(_target(role), bank_ids=_ALL_TEST_IDS)
    assert any(issue.rule == "S004" for issue in report.errors)


def test_s005_hedge_phrase():
    role = _lint_role(
        bullets=[
            _lint_bullet(text="Worked to improve the onboarding flow for new users"),
            _lint_bullet(id="b_test_02"),
        ]
    )
    report = lint_target(_target(role), bank_ids=_ALL_TEST_IDS)
    assert any(issue.rule == "S005" for issue in report.errors)


def test_s006_various_or_several_where_a_number_would_do():
    role = _lint_role(
        bullets=[
            _lint_bullet(text="Integrated several APIs across various services"),
            _lint_bullet(id="b_test_02"),
        ]
    )
    report = lint_target(_target(role), bank_ids=_ALL_TEST_IDS)
    assert any(issue.rule == "S006" for issue in report.errors)


def test_h001_more_than_one_period():
    role = _lint_role(
        bullets=[
            _lint_bullet(text="Built a routing engine. It reduced costs significantly."),
            _lint_bullet(id="b_test_02"),
        ]
    )
    report = lint_target(_target(role), bank_ids=_ALL_TEST_IDS)
    assert any(issue.rule == "H001" for issue in report.errors)


def test_h002_exceeds_three_estimated_lines():
    assert len(_LONG_BULLET_TEXT) > 315
    role = _lint_role(
        bullets=[
            _lint_bullet(text=_LONG_BULLET_TEXT),
            _lint_bullet(id="b_test_02"),
        ]
    )
    report = lint_target(_target(role), bank_ids=_ALL_TEST_IDS)
    assert any(issue.rule == "H002" for issue in report.errors)


def test_h003_not_past_tense():
    role = _lint_role(
        bullets=[
            _lint_bullet(
                text="Building a modular routing engine that separates "
                "transcription from scoring"
            ),
            _lint_bullet(id="b_test_02"),
        ]
    )
    report = lint_target(_target(role), bank_ids=_ALL_TEST_IDS)
    assert any(issue.rule == "H003" for issue in report.errors)


def test_h004_role_has_fewer_than_three_total_bullets():
    role = _lint_role(bullets=[_lint_bullet()])  # 1 bullet + summary = 2
    report = lint_target(_target(role), bank_ids=_ALL_TEST_IDS)
    assert any(issue.rule == "H004" for issue in report.errors)


def test_h005_role_missing_summary_bullet():
    role = _lint_role(summary=None)
    report = lint_target(_target(role), bank_ids=_ALL_TEST_IDS)
    assert any(issue.rule == "H005" for issue in report.errors)


def test_h006_summary_leaks_a_sibling_bullet_keyword():
    role = _lint_role(
        summary=_lint_summary(
            text="Built the FastAPI service that powers real-time scoring"
        ),
        bullets=[
            _lint_bullet(keywords=["FastAPI", "routing"]),
            _lint_bullet(id="b_test_02"),
        ],
    )
    report = lint_target(_target(role), bank_ids=_ALL_TEST_IDS)
    assert any(issue.rule == "H006" for issue in report.errors)


def test_h007_first_person_pronouns():
    role = _lint_role(
        bullets=[
            _lint_bullet(
                text="Built a routing engine that I used to cut my team's API costs"
            ),
            _lint_bullet(id="b_test_02"),
        ]
    )
    report = lint_target(_target(role), bank_ids=_ALL_TEST_IDS)
    assert any(issue.rule == "H007" for issue in report.errors)


def test_h008_bullet_id_not_traceable_to_bank_isolated():
    """Internal-function test: fabricate a bank_ids set directly, no YAML
    involved. See test_h008_bullet_id_not_traceable_via_real_yaml_loader
    below for the end-to-end version through the actual loader."""
    role = _lint_role(
        bullets=[
            _lint_bullet(id="b_ghost_99"),
            _lint_bullet(id="b_test_02"),
        ]
    )
    report = lint_target(_target(role), bank_ids={"b_test_sum", "b_test_02"})
    assert any(
        issue.rule == "H008" and issue.entity_id == "b_ghost_99"
        for issue in report.errors
    )


def test_h008_bullet_id_not_traceable_via_real_yaml_loader(tmp_path):
    """End-to-end: a real ground-truth bank YAML on disk, loaded through
    bank.load_bank, and a real lint-target YAML on disk, loaded through
    slop_lint's own loader, with one bullet id genuinely absent from the
    ground truth. Exercises the actual file-reading path, not just the
    in-memory function."""
    bank_path = tmp_path / "mini_bank.yaml"
    bank_path.write_text(
        """
meta:
  owner: "Test"
  updated: "2026-01-01"
roles:
  - id: role_mini
    kind: project
    title:
      default: "Test Role"
    summary:
      id: b_mini_sum
      text: "Built a small test system for verifying traceability"
      keywords: []
      status: verified
    bullets:
      - id: b_mini_01
        status: verified
        what: "a thing"
        how: "a way"
        result: "a result"
        text: "Built a thing using a way that produced a result"
        keywords: []
        evidence: "internal"
        profiles: [ai_ml_engineer]
"""
    )

    target_path = tmp_path / "dangling_id.yaml"
    target_path.write_text(
        """
roles:
  - id: role_target
    summary:
      id: b_mini_sum
      text: "Built a small test system for verifying traceability"
      keywords: []
      status: verified
    bullets:
      - id: b_ghost_99
        text: "Built a feature that was never added to the bank"
        keywords: []
        status: verified
"""
    )

    report = lint_path(target_path, bank_path=bank_path)
    assert any(
        issue.rule == "H008" and issue.entity_id == "b_ghost_99"
        for issue in report.errors
    )
    # The summary id is real, it must not be flagged.
    assert not any(
        issue.rule == "H008" and issue.entity_id == "b_mini_sum"
        for issue in report.errors
    )


def test_w001_keyword_coverage_below_threshold_is_flagged(tmp_path):
    conn = connect(tmp_path / "jobengine.db")
    init(conn)
    conn.execute(
        "INSERT INTO keyword_corpus (profile, keyword, occurrences, "
        "first_seen_at, last_seen_at) VALUES "
        "('ai_ml_engineer', 'Python', 5, 'now', 'now'), "
        "('ai_ml_engineer', 'FastAPI', 4, 'now', 'now'), "
        "('ai_ml_engineer', 'Kubernetes', 3, 'now', 'now'), "
        "('ai_ml_engineer', 'Docker', 2, 'now', 'now')"
    )
    conn.commit()

    role = _lint_role(
        summary=_lint_summary(keywords=["Python"]),
        bullets=[
            _lint_bullet(keywords=[]),
            _lint_bullet(id="b_test_02", keywords=[]),
        ],
    )
    report = lint_target(
        _target(role),
        bank_ids=_ALL_TEST_IDS,
        profile="ai_ml_engineer",
        conn=conn,
    )
    conn.close()
    assert any(issue.rule == "W001" for issue in report.warnings)


def test_w001_keyword_coverage_at_threshold_is_not_flagged(tmp_path):
    conn = connect(tmp_path / "jobengine.db")
    init(conn)
    conn.execute(
        "INSERT INTO keyword_corpus (profile, keyword, occurrences, "
        "first_seen_at, last_seen_at) VALUES "
        "('ai_ml_engineer', 'Python', 5, 'now', 'now'), "
        "('ai_ml_engineer', 'FastAPI', 4, 'now', 'now'), "
        "('ai_ml_engineer', 'Kubernetes', 3, 'now', 'now'), "
        "('ai_ml_engineer', 'Docker', 2, 'now', 'now')"
    )
    conn.commit()

    role = _lint_role(
        summary=_lint_summary(keywords=["Python"]),
        bullets=[
            _lint_bullet(keywords=["FastAPI"]),
            _lint_bullet(id="b_test_02", keywords=["Kubernetes"]),
        ],
    )
    report = lint_target(
        _target(role),
        bank_ids=_ALL_TEST_IDS,
        profile="ai_ml_engineer",
        conn=conn,
    )
    conn.close()
    assert not any(issue.rule == "W001" for issue in report.warnings)


def test_w002_front_loading_is_a_documented_stub():
    """No PDF geometry exists until D2. W002 always reports 'not yet
    measurable' rather than faking a front-load computation."""
    report = lint_target(_target(_lint_role()), bank_ids=_ALL_TEST_IDS)
    w002 = [issue for issue in report.warnings if issue.rule == "W002"]
    assert len(w002) == 1
    assert "not yet measurable" in w002[0].message.lower()


def test_w003_speculative_bullet_in_preview_render_is_a_warning():
    role = _lint_role(
        bullets=[
            _lint_bullet(status="speculative"),
            _lint_bullet(id="b_test_02"),
        ]
    )
    report = lint_target(_target(role), bank_ids=_ALL_TEST_IDS, preview=True)
    assert any(issue.rule == "W003" for issue in report.warnings)
    assert report.fatal == []
    assert report.ok


def test_e999_speculative_bullet_outside_preview_is_fatal_and_unsuppressable():
    role = _lint_role(
        bullets=[
            _lint_bullet(status="speculative"),
            _lint_bullet(id="b_test_02"),
        ]
    )
    report = lint_target(_target(role), bank_ids=_ALL_TEST_IDS, preview=False)
    assert any(issue.rule == "E999" for issue in report.fatal)
    assert not report.ok
