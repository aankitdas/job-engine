"""Real measurement functions backing specs/08-rubric.md's hard rules.

Every function here reads something concrete (bank content, a rendered docx,
a rendered PDF's real geometry) and returns a number or a bool. No LLM calls,
no judgment calls: the rubric replaces an LLM critic (D8 in
docs/decisions.md), and that only holds if this module stays deterministic.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path
from typing import NamedTuple

import pdfplumber
from docx import Document as OpenDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from jobengine.resume.bank import Bank, Role, keyword_counts
from jobengine.resume.render import FONT, MARGIN, TAB_POSITION

_VALID_SIZES = {Pt(10.5), Pt(12), Pt(14)}
_VALID_LINE_SPACINGS = (1.15, 1.5)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_PRONOUN_RE = re.compile(r"\b(?:I|me|my|mine|we|us|our|ours)\b", re.IGNORECASE)


def select_for_profile(bank: Bank, profile: str) -> Bank:
    """The minimal, non-invented candidate resume for a profile: keep only
    bullets already tagged for it (bank.py's own bullet.profiles field, no
    new selection/ranking logic, that's D3's job), and drop any role left
    with zero bullets entirely rather than rendering a bare summary line.
    Education and publications are untagged and pass through unchanged."""
    selected_roles = []
    for role in bank.roles:
        filtered_bullets = [b for b in role.bullets if profile in b.profiles]
        if not filtered_bullets:
            continue
        selected_roles.append(role.model_copy(update={"bullets": filtered_bullets}))
    return bank.model_copy(update={"roles": selected_roles})


def stem(keyword: str) -> str:
    """Light suffix-only normalization, matching spec 08's literal "case and
    stem normalized" wording. Not a real stemmer (no Porter/Snowball): the
    goal is consistent normalization of both sides of a comparison, not
    linguistic correctness. Known limitation, not fixed here: this does not
    resolve synonyms/abbreviations (e.g. "LLM" vs "Large Language Models"),
    confirmed against real C3 extraction output during D1 planning. Revisit
    only if that recurs as a practical problem, same pattern as D27."""
    s = keyword.lower().strip()
    if s.endswith("ies"):
        return s[:-3] + "y"
    if s.endswith("es") and not s.endswith("ses"):
        return s[:-2]
    if s.endswith("s") and not s.endswith("ss"):
        return s[:-1]
    return s


def coverage(bank: Bank, required_keywords: list[str]) -> float:
    """R001: set intersection of the candidate resume's own keyword tags
    against required_keywords, stem normalized. Vacuously 1.0 when nothing
    is required."""
    if not required_keywords:
        return 1.0
    bank_stems = {stem(k) for k in keyword_counts(bank)}
    required_stems = {stem(k) for k in required_keywords}
    return len(bank_stems & required_stems) / len(required_stems)


def missing_keywords(bank: Bank, required_keywords: list[str]) -> list[str]:
    """Original-cased required_keywords whose stem has no match in the
    candidate resume's keyword tags, for the deficit's "missing" list."""
    bank_stems = {stem(k) for k in keyword_counts(bank)}
    seen_stems: set[str] = set()
    missing: list[str] = []
    for kw in required_keywords:
        kw_stem = stem(kw)
        if kw_stem in seen_stems:
            continue
        seen_stems.add(kw_stem)
        if kw_stem not in bank_stems:
            missing.append(kw)
    return missing


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class _ParsedPage(NamedTuple):
    height: float
    tokens: list[tuple[str, float]]  # (token, top), reading order


_MAX_CACHE_ENTRIES = 32
_PAGE_CACHE: dict[str, list[_ParsedPage]] = {}


def _parsed_pdf(pdf_path: Path) -> list[_ParsedPage]:
    """Spec 08: "Cache the extraction per rendered file hash so repeated
    scoring is free." Keyed by a sha256 of the PDF's own bytes, not the
    path, so two paths pointing at byte-identical content (e.g. spec 08's
    Storage section dedup, "two jobs whose patches produce identical
    selections share one rendered file") hit the same cache entry. Every
    other function in this module that needs PDF geometry goes through
    this one parse, rather than each opening and re-parsing the file
    independently. Bounded at _MAX_CACHE_ENTRIES with simple oldest-in
    eviction, not a true LRU: this process scores a bounded number of
    distinct resumes per run, not an unbounded long-lived cache, so a
    precise LRU isn't worth the extra code."""
    file_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    cached = _PAGE_CACHE.get(file_hash)
    if cached is not None:
        return cached

    with pdfplumber.open(pdf_path) as pdf:
        pages = []
        for page in pdf.pages:
            words = sorted(
                page.extract_words(), key=lambda w: (round(w["top"], 1), w["x0"])
            )
            flat: list[tuple[str, float]] = []
            for w in words:
                for token in _tokenize(w["text"]):
                    flat.append((token, w["top"]))
            pages.append(_ParsedPage(height=page.height, tokens=flat))

    if len(_PAGE_CACHE) >= _MAX_CACHE_ENTRIES:
        _PAGE_CACHE.pop(next(iter(_PAGE_CACHE)))
    _PAGE_CACHE[file_hash] = pages
    return pages


def page1_height(pdf_path: Path) -> float:
    return _parsed_pdf(pdf_path)[0].height


def page_count(pdf_path: Path) -> int:
    return len(_parsed_pdf(pdf_path))


class KeywordOccurrence(NamedTuple):
    keyword: str
    top: float | None
    above_half: bool


def front_load_detail(pdf_path: Path, keywords: list[str]) -> list[KeywordOccurrence]:
    """Per-keyword detail behind R002's ratio: where (if anywhere) each of
    the top-10 keywords first occurs on page 1, and whether that's above
    the half-page line. `rubric explain R002` prints this directly, per
    spec 08's "explain prints the geometric measurement with the actual
    y-coordinates.\""""
    top10 = keywords[:10]
    if not top10:
        return []

    page1 = _parsed_pdf(pdf_path)[0]
    half = page1.height / 2

    occurrences = []
    for kw in top10:
        kw_tokens = _tokenize(kw)
        if not kw_tokens:
            occurrences.append(KeywordOccurrence(kw, None, False))
            continue
        first_top = _first_occurrence_top(page1.tokens, kw_tokens)
        above = first_top is not None and first_top < half
        occurrences.append(KeywordOccurrence(kw, first_top, above))
    return occurrences


def front_load(pdf_path: Path, keywords: list[str]) -> float:
    """R002: ratio of the top-10 keyword list whose first occurrence on page
    1 falls above y = page_height / 2. A keyword absent from page 1 entirely
    counts as not front-loaded, not as excluded from the denominator: it
    certainly isn't in the top half if it isn't there at all."""
    occurrences = front_load_detail(pdf_path, keywords)
    if not occurrences:
        return 1.0
    hits_above = sum(1 for o in occurrences if o.above_half)
    return hits_above / len(occurrences)


def _first_occurrence_top(
    flat: list[tuple[str, float]], tokens: list[str]
) -> float | None:
    n = len(tokens)
    for i in range(len(flat) - n + 1):
        if [flat[i + j][0] for j in range(n)] == tokens:
            return flat[i][1]
    return None


def line_count_from_pdf(pdf_path: Path, bullet_text: str) -> int:
    """R006, option 1: distinct baseline y-values within a bullet's real
    rendered span, located by matching its token sequence in reading order.
    Raises if the text can't be found, rather than silently returning 0,
    since a missing match means the caller passed the wrong PDF or text."""
    target_tokens = _tokenize(bullet_text)
    if not target_tokens:
        return 0

    for page in _parsed_pdf(pdf_path):
        flat = page.tokens
        window = min(6, len(target_tokens))
        for i in range(len(flat) - window + 1):
            if [flat[i + j][0] for j in range(window)] == target_tokens[:window]:
                span = flat[i : i + len(target_tokens)]
                if len(span) < len(target_tokens):
                    continue
                tops = {round(top, 1) for _, top in span}
                return len(tops)

    raise ValueError(f"bullet text not found in {pdf_path}: {bullet_text[:60]!r}")


def measure_typography(docx_path: Path) -> list[str]:
    """R010: font, sizes, margins, tab-stop position, and justify-alignment
    are checked universally across every paragraph/run. Line spacing is
    checked against the valid pair (1.15 header / 1.5 body) rather than
    positionally validated per section; a real, deliberate scope reduction,
    not an oversight: this rule's job in the rubric is catching drift in an
    already-rendered document (a bad manual edit, a future P3 rewrite), and
    render.py's own golden test already pins the exact per-role spacing at
    construction time."""
    doc = OpenDocument(str(docx_path))
    violations: list[str] = []

    section = doc.sections[0]
    for attr in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        if getattr(section, attr) != MARGIN:
            violations.append(f"{attr} != 0.5in")

    tab_positions: set[int] = set()
    for paragraph in doc.paragraphs:
        if paragraph.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY:
            violations.append(f"paragraph {paragraph.text[:30]!r} is justified")

        line_spacing = paragraph.paragraph_format.line_spacing
        if paragraph.text.strip() and line_spacing not in _VALID_LINE_SPACINGS:
            violations.append(
                f"paragraph {paragraph.text[:30]!r} line_spacing {line_spacing} "
                f"not in {_VALID_LINE_SPACINGS}"
            )

        for tab_stop in paragraph.paragraph_format.tab_stops:
            tab_positions.add(tab_stop.position)

        for run in paragraph.runs:
            if not run.text.strip():
                continue
            if run.font.name != FONT:
                violations.append(
                    f"run {run.text[:30]!r} font {run.font.name} != {FONT}"
                )
            if run.font.size not in _VALID_SIZES:
                violations.append(
                    f"run {run.text[:30]!r} size {run.font.size} not in 10.5/12/14"
                )

    if tab_positions - {TAB_POSITION}:
        violations.append(f"tab stop(s) not at 7.5in: {tab_positions - {TAB_POSITION}}")

    return violations


def is_single_column(docx_path: Path) -> bool:
    """R011: no tables or text boxes in the body. Reads the raw document.xml
    directly rather than via python-docx's object model, since python-docx
    has no high-level "does this document contain a table" query."""
    with zipfile.ZipFile(docx_path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    return (
        "<w:tbl>" not in xml
        and "<w:pict>" not in xml
        and "mc:AlternateContent" not in xml
    )


def iter_entries(role: Role) -> list[tuple[str, str]]:
    """(entity_id, text) for a role's summary and every bullet, the unit
    R005/R007/R008/R012 all check per-entry."""
    entries = [(role.summary.id, role.summary.text)]
    entries.extend((b.id, b.text) for b in role.bullets)
    return entries


def has_first_person_pronoun(text: str) -> bool:
    return _PRONOUN_RE.search(text) is not None


_ONGOING_SENTINEL = "9999-12"  # lexically sorts after any real YYYY-MM date


def role_end_or_ongoing(role: Role) -> str:
    """The role's end date, or a sentinel that sorts after any real
    YYYY-MM date, for date-range comparisons that treat an ongoing role
    (end=None) as extending to the present. Public so patch.py's P0 can
    use the exact same "ongoing" convention R009 itself uses."""
    return role.end or _ONGOING_SENTINEL


def roles_date_overlap(a: Role, b: Role) -> bool:
    """True if a and b's [start, end] ranges genuinely overlap. Used by
    P0 to decide which adjacent role pairs it's allowed to swap without
    ever breaking R009 (see is_reverse_chronological's own docstring)."""
    a_end = role_end_or_ongoing(a)
    b_end = role_end_or_ongoing(b)
    return not (a_end < b.start or b_end < a.start)


def is_reverse_chronological(roles: list[Role]) -> bool:
    """R009: non-project roles only, projects have no chronological
    constraint per the patch ladder's P2 section. A role with no start date
    (shouldn't happen for a non-project role per the bank schema, but not
    assumed) is skipped rather than crashing the comparison.

    A violation is a role appearing before an earlier, non-overlapping
    role, not merely a different start date: two roles with genuinely
    overlapping date ranges (real example: role_sei 2021-10 to 2023-08
    overlaps role_unl 2021-05 to 2023-06) may appear in either order
    without failing R009, matching the natural meaning of "concurrent" in
    resume-writing and what P0's patch-ladder tier is allowed to reorder
    without ever breaking this rule. Confirmed by asking, since the
    original stricter (start-date-monotonic) check would have made P0's
    own "sort roles only if two are concurrent" permission inert on every
    pair in the real bank."""
    ordered = [r for r in roles if r.kind != "project" and r.start is not None]
    for i in range(len(ordered) - 1):
        if role_end_or_ongoing(ordered[i]) < ordered[i + 1].start:
            return False
    return True


def speculative_entry_ids(bank: Bank) -> list[str]:
    """R012: ids of every summary/bullet with status == "speculative"."""
    bad: list[str] = []
    for role in bank.roles:
        if role.summary.status == "speculative":
            bad.append(role.summary.id)
        bad.extend(b.id for b in role.bullets if b.status == "speculative")
    return bad
