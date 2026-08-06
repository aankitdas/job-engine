"""E1's `profiles brief` content generator. See specs/09-base-resumes.md's
"Inputs" section: brief.md is the entire input to E2's interactive
session.

Two of spec 09's five listed sections are deliberately not built here:
"rank change since last generation" and the market "diff summary" both
need a previous generation to diff against, and this is the first-ever
brief (`base_resumes` is empty, E2 hasn't run). Nothing to diff yet, not
silently dropped; add them once a second generation exists.

`keyword_corpus` and `gap_ledger` are both expected to be empty against
the real db today: `keyword_corpus` because no daily orchestrator has
ever called `pipeline.extract.analyze_job()` against real jobs (a gap
already flagged under C3 in PROGRESS.md's Known Issues, nothing to do
with C4/the relevance filter); `gap_ledger` because P4 (accept and log to
gap_ledger) is not built and no orchestrator has run the patch ladder
against real jobs either. Both degrade to an explicit, honest message
rather than a silent empty section or a crash.

"the current base resume's rubric measurements" has no real
`base_resumes` row to read yet either (E2 hasn't run). Confirmed with the
user: render+score `measure.select_for_profile(bank, profile)` on the fly
as the "current" stand-in, the same unpatched-candidate shape D1's own
grounding scored, and the same shape `rules.score_resume()`'s own
docstring anticipates ("the caller decides what 'the current base
resume' means"). Scored against this brief's own top-keywords list
(corpus or bank-frequency fallback): there is no job-specific keyword
list at profile granularity, so the market's own top keywords are the
only defensible "required_keywords" to measure coverage/front-load
against here.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal, NamedTuple

from jobengine.profiles.config import ProfileConfig, to_render_profile
from jobengine.resume.bank import Bank, BulletRef, keyword_counts
from jobengine.resume.pdf import render_pdf
from jobengine.resume.render import Identity, RenderProfile, render
from jobengine.rubric import measure, rules


class TopKeywords(NamedTuple):
    keywords: list[tuple[str, int]]
    source: Literal["corpus", "bank_frequency"]


def _top_corpus_keywords(
    conn: sqlite3.Connection, bank: Bank, profile: str, limit: int = 30
) -> TopKeywords:
    rows = conn.execute(
        "SELECT keyword, occurrences FROM keyword_corpus "
        "WHERE profile = ? ORDER BY occurrences DESC LIMIT ?",
        (profile, limit),
    ).fetchall()
    if rows:
        return TopKeywords(keywords=[(r[0], r[1]) for r in rows], source="corpus")

    candidate = measure.select_for_profile(bank, profile)
    fallback = keyword_counts(candidate).most_common(limit)
    return TopKeywords(keywords=fallback, source="bank_frequency")


def _gap_ledger_top(
    conn: sqlite3.Connection, profile: str, limit: int = 10
) -> list[tuple[str, int]]:
    rows = conn.execute(
        "SELECT keyword, COUNT(*) AS n FROM gap_ledger WHERE profile = ? "
        "GROUP BY keyword ORDER BY n DESC LIMIT ?",
        (profile, limit),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def _current_measurements(
    *,
    bank: Bank,
    profile: str,
    render_profile: RenderProfile,
    identity: Identity,
    out_dir: Path,
    required_keywords: list[str],
) -> rules.RubricResult:
    candidate = measure.select_for_profile(bank, profile)
    doc = render(candidate, identity, render_profile)
    out_dir.mkdir(parents=True, exist_ok=True)
    docx_path = out_dir / f"{profile}_current_candidate.docx"
    doc.save(docx_path)
    pdf_path = render_pdf(docx_path, out_dir)
    return rules.score_resume(
        bank=candidate,
        profile=profile,
        docx_path=docx_path,
        pdf_path=pdf_path,
        required_keywords=required_keywords,
    )


def _unselected_bullets_with_top_keywords(
    bank: Bank, profile: str, top_keywords: list[str]
) -> list[BulletRef]:
    target_stems = {measure.stem(k) for k in top_keywords}
    if not target_stems:
        return []
    refs: list[BulletRef] = []
    for role in bank.roles:
        for bullet in role.bullets:
            if profile in bullet.profiles:
                continue
            bullet_stems = {measure.stem(k) for k in bullet.keywords}
            if bullet_stems & target_stems:
                refs.append(BulletRef(role.id, bullet, is_summary=False))
    return refs


def generate_brief(
    *,
    conn: sqlite3.Connection,
    bank: Bank,
    profile: str,
    profile_config: ProfileConfig,
    identity: Identity,
    out_dir: Path,
) -> str:
    top = _top_corpus_keywords(conn, bank, profile, limit=30)
    gap = _gap_ledger_top(conn, profile, limit=10)
    top_keyword_names = [kw for kw, _ in top.keywords]
    measurements = _current_measurements(
        bank=bank,
        profile=profile,
        render_profile=to_render_profile(profile_config),
        identity=identity,
        out_dir=out_dir,
        required_keywords=top_keyword_names,
    )
    unselected = _unselected_bullets_with_top_keywords(bank, profile, top_keyword_names)

    lines: list[str] = [f"# Brief: {profile_config.display_name} ({profile})", ""]

    lines.append("## Top corpus keywords")
    if top.source == "corpus":
        lines.append(f"(from keyword_corpus, {len(top.keywords)} keywords)")
    else:
        lines.append(
            "(keyword_corpus has no rows for this profile yet -- no daily "
            "pipeline orchestrator has run analyze_job() against real jobs "
            "yet. Falling back to the bank's own keyword frequency for "
            "this profile.)"
        )
    if top.keywords:
        for kw, count in top.keywords:
            lines.append(f"- {kw}: {count}")
    else:
        lines.append("(no keywords found for this profile in either source)")
    lines.append("")

    lines.append("## Current base resume rubric measurements")
    lines.append(
        "(no base_resumes row exists yet for this profile -- this is the "
        "unpatched candidate, select_for_profile(bank, profile) rendered "
        "and scored on the fly, not a real generated base resume. Scored "
        "against this brief's own top keywords above, corpus or "
        "bank-frequency fallback.)"
    )
    lines.append(f"- passed: {measurements.passed}")
    lines.append(f"- score: {measurements.score:.2f}")
    lines.append(f"- hard_failures: {measurements.hard_failures}")
    for name, value in measurements.measurements.items():
        lines.append(f"- {name}: {value}")
    lines.append("")

    lines.append("## Uncovered gap-ledger keywords")
    if gap:
        for kw, count in gap:
            lines.append(f"- {kw}: {count}")
    else:
        lines.append(
            "(gap_ledger has no rows for this profile yet -- P4 is not "
            "built and no orchestrator has run the patch ladder against "
            "real jobs yet.)"
        )
    lines.append("")

    lines.append("## Unselected bank bullets carrying top keywords")
    if unselected:
        for ref in unselected:
            lines.append(f"- {ref.role_id}/{ref.bullet.id}: {ref.bullet.text}")
    else:
        lines.append("(none found)")
    lines.append("")

    return "\n".join(lines)
