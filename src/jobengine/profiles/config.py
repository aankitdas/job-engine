"""E1's profile registry. See specs/09-base-resumes.md's "Profile section
order" and resume/render.py's RenderProfile docstring: this module is the
"E1's decision" the docstring defers to.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from jobengine.resume.bank import KNOWN_PROFILES
from jobengine.resume.render import RenderProfile

DEFAULT_PROFILES_PATH = Path("config/profiles.yaml")

# render.py's render() only ever looks up a section by these names
# (its section_renderers dict); validating against this set here gives a
# clear config-load error instead of a KeyError deep inside render().
_VALID_SECTIONS = {"education", "work_history", "projects", "publications"}


class ProfileConfig(BaseModel):
    id: str
    display_name: str
    section_order: list[str]
    include_summary: bool = False
    summary_text: str | None = None


def load_profile_config(path: Path = DEFAULT_PROFILES_PATH) -> dict[str, ProfileConfig]:
    raw = yaml.safe_load(path.read_text())
    entries = raw.get("profiles", {})

    unknown = set(entries) - KNOWN_PROFILES
    if unknown:
        raise ValueError(f"{path}: profile(s) not in KNOWN_PROFILES: {sorted(unknown)}")
    missing = KNOWN_PROFILES - set(entries)
    if missing:
        raise ValueError(f"{path}: missing entry for profile(s): {sorted(missing)}")

    registry: dict[str, ProfileConfig] = {}
    for profile_id, fields in entries.items():
        section_order = fields["section_order"]
        bad_sections = set(section_order) - _VALID_SECTIONS
        if bad_sections:
            raise ValueError(
                f"{path}: {profile_id}.section_order has unknown section(s) "
                f"{sorted(bad_sections)}, valid: {sorted(_VALID_SECTIONS)}"
            )
        if len(section_order) != len(set(section_order)):
            raise ValueError(
                f"{path}: {profile_id}.section_order has a duplicate section: "
                f"{section_order}"
            )
        registry[profile_id] = ProfileConfig(id=profile_id, **fields)

    return registry


def to_render_profile(cfg: ProfileConfig) -> RenderProfile:
    return RenderProfile(
        section_order=cfg.section_order,
        include_summary=cfg.include_summary,
        summary_text=cfg.summary_text,
    )
