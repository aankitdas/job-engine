"""specs/08-rubric.md's 13 hard rules, R001-R013. Each check_r0XX function is
pure: given already-computed measurements (or, where the measurement is
cheap and bank-only, the candidate Bank directly), it returns a Deficit on
failure or None on pass. score_resume() is the one orchestration point that
calls measure.py, runs every check, and assembles the spec's JSON shape.

The patch ladder (P0-P4) is not built here. See TODO.md: D1 is the
deterministic scorer, D3 is the patch ladder.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber
from pydantic import BaseModel

from jobengine.resume import slop_lint
from jobengine.resume.bank import Bank, is_past_tense
from jobengine.rubric import measure, score


class Deficit(BaseModel):
    rule: str
    detail: str
    missing: list[str] = []


class RubricResult(BaseModel):
    passed: bool
    score: float
    hard_failures: list[str]
    deficits: list[Deficit]
    measurements: dict[str, float | int]


def check_r001(bank: Bank, required_keywords: list[str]) -> Deficit | None:
    cov = measure.coverage(bank, required_keywords)
    if cov >= 0.70:
        return None
    return Deficit(
        rule="R001",
        detail=f"coverage {cov:.2f} < 0.70",
        missing=measure.missing_keywords(bank, required_keywords),
    )


def check_r002(front_load_ratio: float) -> Deficit | None:
    if front_load_ratio >= 0.75:
        return None
    return Deficit(rule="R002", detail=f"front-load {front_load_ratio:.2f} < 0.75")


def check_r003(bank: Bank) -> Deficit | None:
    bad = []
    for role in bank.roles:
        total = 1 + len(role.bullets)  # + summary
        if not (3 <= total <= 8):
            bad.append(f"{role.id}={total}")
    if not bad:
        return None
    return Deficit(rule="R003", detail=f"roles outside 3-8 bullets: {', '.join(bad)}")


def check_r004(bank: Bank) -> Deficit | None:
    """Structurally guaranteed: Role.summary is a single required field, not
    a list, so "exactly one summary" can't be violated by the schema itself.
    Checked anyway for symmetry with the other 12 rules; inert today, same
    category as slop_lint's H008 pre-D4."""
    return None


def check_r005(bank: Bank) -> Deficit | None:
    bad = []
    for role in bank.roles:
        for entity_id, text in measure.iter_entries(role):
            if text.count(".") > 1:
                bad.append(entity_id)
    if not bad:
        return None
    return Deficit(rule="R005", detail=f"more than one period: {', '.join(bad)}")


def check_r006(line_counts: dict[str, int]) -> Deficit | None:
    bad = [bid for bid, n in line_counts.items() if n > 3]
    if not bad:
        return None
    return Deficit(rule="R006", detail=f"renders over 3 lines: {', '.join(bad)}")


def check_r007(bank: Bank) -> Deficit | None:
    bad = []
    for role in bank.roles:
        for entity_id, text in measure.iter_entries(role):
            if not is_past_tense(text):
                bad.append(entity_id)
    if not bad:
        return None
    return Deficit(rule="R007", detail=f"not past tense: {', '.join(bad)}")


def check_r008(bank: Bank) -> Deficit | None:
    bad = []
    for role in bank.roles:
        for entity_id, text in measure.iter_entries(role):
            if measure.has_first_person_pronoun(text):
                bad.append(entity_id)
    if not bad:
        return None
    return Deficit(rule="R008", detail=f"first-person pronoun: {', '.join(bad)}")


def check_r009(bank: Bank) -> Deficit | None:
    if measure.is_reverse_chronological(bank.roles):
        return None
    return Deficit(rule="R009", detail="roles are not in reverse chronological order")


def check_r010(docx_path: Path) -> Deficit | None:
    violations = measure.measure_typography(docx_path)
    if not violations:
        return None
    return Deficit(rule="R010", detail="; ".join(violations[:5]))


def check_r011(docx_path: Path) -> Deficit | None:
    if measure.is_single_column(docx_path):
        return None
    return Deficit(rule="R011", detail="document contains a table or text box")


def check_r012(bank: Bank) -> Deficit | None:
    bad = measure.speculative_entry_ids(bank)
    if not bad:
        return None
    return Deficit(rule="R012", detail=f"speculative bullets: {', '.join(bad)}")


def _bank_to_lint_target(bank: Bank) -> slop_lint.LintTarget:
    roles = []
    for role in bank.roles:
        roles.append(
            slop_lint.LintRole(
                id=role.id,
                summary=slop_lint.LintSummary(
                    id=role.summary.id,
                    text=role.summary.text,
                    keywords=role.summary.keywords,
                    status=role.summary.status,
                ),
                bullets=[
                    slop_lint.LintBullet(
                        id=b.id, text=b.text, keywords=b.keywords, status=b.status
                    )
                    for b in role.bullets
                ],
            )
        )
    return slop_lint.LintTarget(roles=roles)


def _bank_entry_ids(bank: Bank) -> set[str]:
    ids: set[str] = set()
    for role in bank.roles:
        ids.add(role.summary.id)
        ids.update(b.id for b in role.bullets)
    return ids


def check_r013(bank: Bank) -> Deficit | None:
    """No job/profile/db context available here, so W001 (keyword coverage)
    and W002 (front-loading) are skipped by construction, matching
    lint_target's own signature (profile/conn both optional). Both are
    warnings, not errors, so they can never affect R013's "zero errors"
    pass/fail anyway."""
    target = _bank_to_lint_target(bank)
    report = slop_lint.lint_target(target, bank_ids=_bank_entry_ids(bank))
    if report.ok:
        return None
    issues = report.errors + report.fatal
    return Deficit(rule="R013", detail="; ".join(str(issue) for issue in issues[:5]))


def score_resume(
    *,
    bank: Bank,
    profile: str,
    docx_path: Path,
    pdf_path: Path,
    required_keywords: list[str],
    preferred_keywords: list[str] | None = None,
) -> RubricResult:
    """The one orchestration point: runs measure.py, all 13 checks, and
    score.py against a candidate resume already produced by
    measure.select_for_profile(). bank here is the candidate (post-filter),
    not the full bank; the caller decides what "the current base resume"
    means, this function just scores it."""
    preferred_keywords = preferred_keywords or []
    all_keywords = required_keywords + preferred_keywords

    entries: list[tuple[str, str]] = []
    for role in bank.roles:
        entries.extend(measure.iter_entries(role))
    line_counts = {
        entity_id: measure.line_count_from_pdf(pdf_path, text)
        for entity_id, text in entries
    }
    front_load_ratio = measure.front_load(pdf_path, all_keywords[:10])
    cov = measure.coverage(bank, required_keywords)

    deficits = [
        d
        for d in (
            check_r001(bank, required_keywords),
            check_r002(front_load_ratio),
            check_r003(bank),
            check_r004(bank),
            check_r005(bank),
            check_r006(line_counts),
            check_r007(bank),
            check_r008(bank),
            check_r009(bank),
            check_r010(docx_path),
            check_r011(docx_path),
            check_r012(bank),
            check_r013(bank),
        )
        if d is not None
    ]
    hard_failures = [d.rule for d in deficits]

    page_count = _pdf_page_count(pdf_path)
    weighted_score = score.compute_score(
        bank=bank,
        required_keywords=required_keywords,
        preferred_keywords=preferred_keywords,
        pdf_path=pdf_path,
        page_count=page_count,
    )

    return RubricResult(
        passed=not hard_failures,
        score=weighted_score,
        hard_failures=hard_failures,
        deficits=deficits,
        measurements={
            "coverage": cov,
            "front_load": front_load_ratio,
            "pages": page_count,
        },
    )


def _pdf_page_count(pdf_path: Path) -> int:
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)
