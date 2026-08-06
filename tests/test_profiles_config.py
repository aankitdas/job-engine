"""Tests for src/jobengine/profiles/config.py (E1). Written before
implementation per CLAUDE.md hard rule 7. See specs/09-base-resumes.md's
"Profile section order" and render.py's own RenderProfile docstring
("Stand-in for E1's not-yet-built profile registry").
"""

from pathlib import Path

import pytest
import yaml

from jobengine.resume.bank import KNOWN_PROFILES
from jobengine.resume.render import RenderProfile


def _write_yaml(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "profiles.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def _valid_profiles_data() -> dict:
    return {
        "profiles": {
            "ai_ml_engineer": {
                "display_name": "AI/ML Engineer",
                "section_order": ["work_history", "projects", "education"],
                "include_summary": False,
                "summary_text": None,
            },
            "software_engineer": {
                "display_name": "Software Engineer",
                "section_order": ["work_history", "projects", "education"],
                "include_summary": False,
                "summary_text": None,
            },
            "data_scientist": {
                "display_name": "Data Scientist",
                "section_order": ["work_history", "projects", "education"],
                "include_summary": False,
                "summary_text": None,
            },
        }
    }


def test_load_profile_config_against_the_real_config_file_covers_every_known_profile():
    from jobengine.profiles.config import DEFAULT_PROFILES_PATH, load_profile_config

    registry = load_profile_config(DEFAULT_PROFILES_PATH)
    assert set(registry) == KNOWN_PROFILES
    for profile_id, cfg in registry.items():
        assert cfg.id == profile_id
        assert cfg.display_name
        assert cfg.section_order


def test_load_profile_config_returns_profile_config_objects(tmp_path):
    from jobengine.profiles.config import load_profile_config

    path = _write_yaml(tmp_path, _valid_profiles_data())
    registry = load_profile_config(path)
    cfg = registry["ai_ml_engineer"]
    assert cfg.id == "ai_ml_engineer"
    assert cfg.display_name == "AI/ML Engineer"
    assert cfg.section_order == ["work_history", "projects", "education"]
    assert cfg.include_summary is False
    assert cfg.summary_text is None


def test_load_profile_config_raises_when_a_known_profile_is_missing(tmp_path):
    from jobengine.profiles.config import load_profile_config

    data = _valid_profiles_data()
    del data["profiles"]["data_scientist"]
    path = _write_yaml(tmp_path, data)
    with pytest.raises(ValueError, match="data_scientist"):
        load_profile_config(path)


def test_load_profile_config_raises_on_an_unknown_profile_key(tmp_path):
    from jobengine.profiles.config import load_profile_config

    data = _valid_profiles_data()
    data["profiles"]["not_a_real_profile"] = data["profiles"]["data_scientist"]
    path = _write_yaml(tmp_path, data)
    with pytest.raises(ValueError, match="not_a_real_profile"):
        load_profile_config(path)


def test_load_profile_config_raises_on_an_unknown_section_name(tmp_path):
    from jobengine.profiles.config import load_profile_config

    data = _valid_profiles_data()
    data["profiles"]["ai_ml_engineer"]["section_order"] = ["hobbies"]
    path = _write_yaml(tmp_path, data)
    with pytest.raises(ValueError, match="hobbies"):
        load_profile_config(path)


def test_load_profile_config_raises_on_a_duplicate_section_name(tmp_path):
    from jobengine.profiles.config import load_profile_config

    data = _valid_profiles_data()
    data["profiles"]["ai_ml_engineer"]["section_order"] = [
        "work_history",
        "work_history",
    ]
    path = _write_yaml(tmp_path, data)
    with pytest.raises(ValueError, match="duplicate"):
        load_profile_config(path)


def test_to_render_profile_adapts_a_profile_config():
    from jobengine.profiles.config import ProfileConfig, to_render_profile

    cfg = ProfileConfig(
        id="ai_ml_engineer",
        display_name="AI/ML Engineer",
        section_order=["work_history", "education"],
        include_summary=False,
        summary_text=None,
    )
    render_profile = to_render_profile(cfg)
    assert isinstance(render_profile, RenderProfile)
    assert render_profile.section_order == ["work_history", "education"]
    assert render_profile.include_summary is False
    assert render_profile.summary_text is None


def test_to_render_profile_carries_summary_fields_when_present():
    from jobengine.profiles.config import ProfileConfig, to_render_profile

    cfg = ProfileConfig(
        id="ai_ml_engineer",
        display_name="AI/ML Engineer",
        section_order=["work_history"],
        include_summary=True,
        summary_text="Some triggered summary.",
    )
    render_profile = to_render_profile(cfg)
    assert render_profile.include_summary is True
    assert render_profile.summary_text == "Some triggered summary."
