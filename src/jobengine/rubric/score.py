"""The weighted 0-100 score from specs/08-rubric.md's Score table. Advisory
only, never a gate on its own (that's what R001-R013's hard_failures are
for); this is what ranks jobs and feeds the dashboard.

Two of the five components have no formula in the spec text and were
confirmed by asking rather than guessed: density is distinct target-keyword
hits over the first role's own word count (a true density, not a coverage
ratio), and the multi-keyword-bullet fraction is computed across the whole
candidate resume, not just the first role.
"""

from __future__ import annotations

from pathlib import Path

from jobengine.resume.bank import Bank, Role
from jobengine.rubric import measure

_COVERAGE_WEIGHT = 40
_FRONT_LOAD_WEIGHT = 25
_DENSITY_WEIGHT = 15
_MULTI_KEYWORD_WEIGHT = 10
_PAGE_PENALTY_WEIGHT = 10


def _coverage_component(bank: Bank, required_keywords: list[str]) -> float:
    return measure.coverage(bank, required_keywords)


def _front_load_component(pdf_path: Path, keywords: list[str]) -> float:
    return measure.front_load(pdf_path, keywords[:10])


def _density_component(first_role: Role | None, keywords: list[str]) -> float:
    """Distinct target keywords (stem normalized) found anywhere in the
    first role's own text (summary + bullets), divided by that role's total
    word count. A short, keyword-dense first role scores higher than a
    long, diluted one; a resume with no roles at all has density 0."""
    if first_role is None or not keywords:
        return 0.0
    texts = [text for _, text in measure.iter_entries(first_role)]
    word_count = sum(len(text.split()) for text in texts)
    if word_count == 0:
        return 0.0
    combined = " ".join(texts).lower()
    target_stems = {measure.stem(k) for k in keywords}
    text_stems = {measure.stem(w) for w in combined.split()}
    hits = len(target_stems & text_stems)
    return hits / word_count


def _multi_keyword_component(bank: Bank, keywords: list[str]) -> float:
    """Fraction of the whole candidate resume's bullets that carry >= 2 of
    the target keywords among their own declared keyword tags. Bullets
    only, not the per-role summary: R003's "3 to 8 bullets including the
    summary" spells out that qualifier explicitly when it wants the summary
    counted, so "bullets" alone elsewhere is read as real bullets only."""
    target_stems = {measure.stem(k) for k in keywords}
    total = 0
    multi = 0
    for role in bank.roles:
        for bullet in role.bullets:
            total += 1
            entry_stems = {measure.stem(k) for k in bullet.keywords}
            if len(entry_stems & target_stems) >= 2:
                multi += 1
    if total == 0:
        return 0.0
    return multi / total


def _page_penalty_component(page_count: int) -> float:
    """1.0 = full penalty (worst), 0.0 = no penalty. Linear beyond 2 pages,
    capped at 1.0 so a 5-page resume doesn't score below 0 overall; spec
    gives no cap or slope, this is the simplest defensible choice."""
    if page_count <= 2:
        return 0.0
    return min(1.0, (page_count - 2) / 2)


def compute_score(
    *,
    bank: Bank,
    required_keywords: list[str],
    preferred_keywords: list[str],
    pdf_path: Path,
    page_count: int,
) -> float:
    all_keywords = required_keywords + preferred_keywords
    first_role = bank.roles[0] if bank.roles else None

    coverage = _coverage_component(bank, required_keywords)
    front_load = _front_load_component(pdf_path, all_keywords)
    density = _density_component(first_role, all_keywords)
    multi_keyword = _multi_keyword_component(bank, all_keywords)
    page_penalty = _page_penalty_component(page_count)

    # page_penalty is 0 (no penalty) to 1 (max penalty); the component's
    # weighted contribution is its inverse, "goodness", so all 5 weights
    # (40+25+15+10+10) sum to a true 100 when every component is perfect.
    return (
        coverage * _COVERAGE_WEIGHT
        + front_load * _FRONT_LOAD_WEIGHT
        + min(density, 1.0) * _DENSITY_WEIGHT
        + multi_keyword * _MULTI_KEYWORD_WEIGHT
        + (1 - page_penalty) * _PAGE_PENALTY_WEIGHT
    )
