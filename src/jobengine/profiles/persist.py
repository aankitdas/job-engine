"""E2's persistence path: writes a base_resumes version to disk and to
the db, per specs/09-base-resumes.md's "Output" section.

CHANGELOG.md ("what changed from v{N-1} and why") is deliberately not
written here: it's narrative judgment from the interactive E2 session,
the same kind of reasoning this project always writes by hand into
docs/decisions.md, not something mechanically derivable from the bank/
render/score state the way selection.yaml/resume.docx/resume.pdf/
rubric.json are. The caller writes it separately, after this function
returns the version number and output directory it needs.

The candidate persisted here is exactly measure.select_for_profile()'s
output in the bank's own natural role/bullet order: no patch ladder
(P0-P2) is applied. Whatever ordering should ship is a selection
decision made before calling this function (by editing the bank, or by
passing an already-reordered `bank`), not something this function
decides on its own.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from jobengine.db.models import (
    BaseResume,
    insert_base_resume,
    latest_base_resume_version,
)
from jobengine.profiles.config import ProfileConfig, to_render_profile
from jobengine.resume.bank import Bank
from jobengine.resume.pdf import render_pdf
from jobengine.resume.render import Identity, render
from jobengine.rubric import measure, rules


@dataclass
class PersistResult:
    id: int
    version: int
    out_dir: Path
    rubric_result: rules.RubricResult


def persist_base_resume(
    *,
    conn: sqlite3.Connection,
    bank: Bank,
    profile: str,
    profile_config: ProfileConfig,
    identity: Identity,
    required_keywords: list[str],
    preferred_keywords: list[str] | None = None,
    out_root: Path = Path("resume/base"),
) -> PersistResult:
    version = latest_base_resume_version(conn, profile) + 1
    out_dir = out_root / profile / f"v{version}"
    out_dir.mkdir(parents=True, exist_ok=True)

    candidate = measure.select_for_profile(bank, profile)
    render_profile = to_render_profile(profile_config)
    doc = render(candidate, identity, render_profile)
    docx_path = out_dir / "resume.docx"
    doc.save(docx_path)
    pdf_path = render_pdf(docx_path, out_dir)

    rubric_result = rules.score_resume(
        bank=candidate,
        profile=profile,
        docx_path=docx_path,
        pdf_path=pdf_path,
        required_keywords=required_keywords,
        preferred_keywords=preferred_keywords,
    )

    selection = {
        "profile": profile,
        "version": version,
        "section_order": profile_config.section_order,
        "roles": [
            {"role_id": role.id, "bullet_ids": [b.id for b in role.bullets]}
            for role in candidate.roles
        ],
    }
    (out_dir / "selection.yaml").write_text(yaml.safe_dump(selection, sort_keys=False))

    generated_at = datetime.now(UTC).isoformat()
    rubric_payload = {
        "profile": profile,
        "version": version,
        "generated_at": generated_at,
        "required_keywords": required_keywords,
        "preferred_keywords": preferred_keywords or [],
        "result": rubric_result.model_dump(),
    }
    (out_dir / "rubric.json").write_text(json.dumps(rubric_payload, indent=2))

    resume_id = insert_base_resume(
        conn,
        BaseResume(
            profile=profile,
            version=version,
            selection=json.dumps(
                {
                    "roles": [
                        {"role_id": role.id, "bullet_ids": [b.id for b in role.bullets]}
                        for role in candidate.roles
                    ]
                }
            ),
            section_order=json.dumps(profile_config.section_order),
            docx_path=str(docx_path),
            pdf_path=str(pdf_path),
            rubric=json.dumps(rubric_payload),
            generated_at=generated_at,
        ),
    )

    return PersistResult(
        id=resume_id, version=version, out_dir=out_dir, rubric_result=rubric_result
    )
