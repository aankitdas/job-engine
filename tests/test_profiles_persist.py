"""Tests for src/jobengine/profiles/persist.py (E2's first real
persistence path). Written before implementation per hard rule 7.
See specs/09-base-resumes.md's "Output" section for the file format.

CHANGELOG.md is deliberately not written by persist_base_resume(): "what
changed from v{N-1} and why" is narrative judgment from the interactive
session (spec 09's own framing), not something mechanically derivable
from the bank/render/score state the way the other four files are. The
caller writes it separately.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from jobengine.db.migrate import connect, init
from jobengine.resume.bank import Bank, Bullet, Meta, Role, SummaryBullet
from jobengine.resume.render import Identity


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


def _bullet(id_: str, text="Built a thing that worked well.", keywords=None) -> Bullet:
    return Bullet(
        id=id_,
        status="verified",
        what="a thing",
        how="carefully",
        result="it worked",
        text=text,
        keywords=keywords or [],
        profiles=["ai_ml_engineer"],
    )


def _role(id_: str, bullets) -> Role:
    return Role(
        id=id_,
        company="Acme",
        location="Remote",
        start="2022-01",
        end="2023-01",
        kind="full_time",
        title={"default": "Engineer"},
        summary=_summary(f"{id_}_s"),
        bullets=bullets,
    )


def _bank() -> Bank:
    role = _role(
        "r1",
        [
            _bullet("b1", "Built a Python service that scaled well.", ["Python"]),
            _bullet("b2", "Shipped a second thing that also worked well."),
        ],
    )
    return Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=[role])


def _profile_config():
    from jobengine.profiles.config import ProfileConfig

    return ProfileConfig(
        id="ai_ml_engineer",
        display_name="AI/ML Engineer",
        section_order=["work_history"],
        include_summary=False,
        summary_text=None,
    )


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "jobengine.db"
    connection = connect(db_path)
    init(connection)
    yield connection
    connection.close()


def test_persist_base_resume_writes_the_four_expected_files(conn, tmp_path):
    from jobengine.profiles.persist import persist_base_resume

    out_root = tmp_path / "resume_base"
    result = persist_base_resume(
        conn=conn,
        bank=_bank(),
        profile="ai_ml_engineer",
        profile_config=_profile_config(),
        identity=_identity(),
        required_keywords=["Python"],
        out_root=out_root,
    )
    out_dir = out_root / "ai_ml_engineer" / "v1"
    assert result.out_dir == out_dir
    assert (out_dir / "selection.yaml").exists()
    assert (out_dir / "resume.docx").exists()
    assert (out_dir / "resume.pdf").exists()
    assert (out_dir / "rubric.json").exists()
    assert not (out_dir / "CHANGELOG.md").exists()


def test_persist_base_resume_selection_yaml_matches_candidate_bullet_order(
    conn, tmp_path
):
    from jobengine.profiles.persist import persist_base_resume

    result = persist_base_resume(
        conn=conn,
        bank=_bank(),
        profile="ai_ml_engineer",
        profile_config=_profile_config(),
        identity=_identity(),
        required_keywords=["Python"],
        out_root=tmp_path / "resume_base",
    )
    selection = yaml.safe_load((result.out_dir / "selection.yaml").read_text())
    assert selection["profile"] == "ai_ml_engineer"
    assert selection["version"] == 1
    assert selection["section_order"] == ["work_history"]
    assert selection["roles"] == [{"role_id": "r1", "bullet_ids": ["b1", "b2"]}]


def test_persist_base_resume_rubric_json_contains_real_score(conn, tmp_path):
    from jobengine.profiles.persist import persist_base_resume

    result = persist_base_resume(
        conn=conn,
        bank=_bank(),
        profile="ai_ml_engineer",
        profile_config=_profile_config(),
        identity=_identity(),
        required_keywords=["Python"],
        out_root=tmp_path / "resume_base",
    )
    rubric = json.loads((result.out_dir / "rubric.json").read_text())
    assert rubric["profile"] == "ai_ml_engineer"
    assert rubric["version"] == 1
    assert rubric["required_keywords"] == ["Python"]
    assert rubric["result"]["measurements"]["coverage"] == 1.0
    assert rubric["result"] == result.rubric_result.model_dump()


def test_persist_base_resume_inserts_db_row_with_correct_paths(conn, tmp_path):
    from jobengine.profiles.persist import persist_base_resume

    out_root = tmp_path / "resume_base"
    result = persist_base_resume(
        conn=conn,
        bank=_bank(),
        profile="ai_ml_engineer",
        profile_config=_profile_config(),
        identity=_identity(),
        required_keywords=["Python"],
        out_root=out_root,
    )
    row = conn.execute(
        "SELECT * FROM base_resumes WHERE id = ?", (result.id,)
    ).fetchone()
    assert row["profile"] == "ai_ml_engineer"
    assert row["version"] == 1
    assert row["docx_path"] == str(result.out_dir / "resume.docx")
    assert row["pdf_path"] == str(result.out_dir / "resume.pdf")
    assert json.loads(row["section_order"]) == ["work_history"]
    selection = json.loads(row["selection"])
    assert selection["roles"] == [{"role_id": "r1", "bullet_ids": ["b1", "b2"]}]
    assert row["retired_at"] is None


def test_persist_base_resume_increments_version_on_second_call(conn, tmp_path):
    from jobengine.profiles.persist import persist_base_resume

    out_root = tmp_path / "resume_base"
    first = persist_base_resume(
        conn=conn,
        bank=_bank(),
        profile="ai_ml_engineer",
        profile_config=_profile_config(),
        identity=_identity(),
        required_keywords=["Python"],
        out_root=out_root,
    )
    second = persist_base_resume(
        conn=conn,
        bank=_bank(),
        profile="ai_ml_engineer",
        profile_config=_profile_config(),
        identity=_identity(),
        required_keywords=["Python"],
        out_root=out_root,
    )
    assert first.version == 1
    assert second.version == 2
    assert second.out_dir == out_root / "ai_ml_engineer" / "v2"
    assert first.id != second.id
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM base_resumes WHERE profile = 'ai_ml_engineer'"
    ).fetchone()["n"]
    assert count == 2
