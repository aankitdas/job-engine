"""Slop linter: a deterministic gate on generated resume text.

See specs/02-slop-linter.md. Two error-level rule classes (S = AI tells,
H = Headless-Headhunter methodology compliance), one warning class (W), and
one fatal hard block (E999) that no flag or config can suppress.

The lint target is bank-shaped YAML, same shape as resume/bank/aankit.yaml,
per spec 01's own note that bank text flows downstream through this linter.
Unlike bank.py's Bank/Role/Bullet, the models here are deliberately lenient
(missing summary, missing id, etc. all parse) so a structural problem comes
back as a lint Issue (H004, H005, ...) instead of a pydantic ValidationError
with no rule code attached.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel

from jobengine.resume.bank import (
    DEFAULT_BANK_PATH,
    Bank,
    is_past_tense,
    load_bank,
)

_MAX_CHARS = 105 * 3  # 315, same estimate as bank.py rule 7, error here not warning


class LintSummary(BaseModel):
    id: str | None = None
    text: str = ""
    keywords: list[str] = []
    status: str | None = None


class LintBullet(BaseModel):
    id: str | None = None
    text: str = ""
    keywords: list[str] = []
    status: str | None = None


class LintRole(BaseModel):
    id: str | None = None
    summary: LintSummary | None = None
    bullets: list[LintBullet] = []


class LintTarget(BaseModel):
    roles: list[LintRole] = []


@dataclass
class Issue:
    rule: str
    entity_id: str
    message: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.entity_id}: {self.message}"


@dataclass
class Report:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    fatal: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and not self.fatal


# ---------------------------------------------------------------------------
# S001-S006: AI tells
# ---------------------------------------------------------------------------

_DASH_RE = re.compile(r"[—–]|\s--\s|\s-\s")

# Word-boundary, case-insensitive, with light suffix tolerance so inflected
# forms actually used in prose (streamlined, leveraging, ...) are caught,
# not just the bare dictionary form. spearhead(ed) is spec 02's own explicit
# example of this; the rest follow the same pattern rather than being
# literal-only, since literal-only would miss the CV's own violations the
# spec calls out (streamlined, spearheaded).
_BANNED_VOCAB = {
    word: re.compile(rf"\b(?:{pattern})\b", re.IGNORECASE)
    for word, pattern in {
        "leverage": r"leverag(?:e|es|ed|ing)",
        "spearhead": r"spearhead(?:s|ed|ing)?",
        "utilize": r"utiliz(?:e|es|ed|ing)",
        "robust": r"robust(?:ly)?",
        "seamless": r"seamless(?:ly)?",
        "cutting-edge": r"cutting-edge",
        "delve": r"delv(?:e|es|ed|ing)",
        "tapestry": r"tapestr(?:y|ies)",
        "testament": r"testaments?",
        "underscore": r"underscor(?:e|es|ed|ing)",
        "pivotal": r"pivotal(?:ly)?",
        "showcase": r"showcas(?:e|es|ed|ing)",
        "harness": r"harness(?:es|ed|ing)?",
        "elevate": r"elevat(?:e|es|ed|ing)",
        "streamline": r"streamlin(?:e|es|ed|ing)",
        "navigate": r"navigat(?:e|es|ed|ing)",
        "realm": r"realms?",
        "landscape": r"landscapes?",
        "meticulous": r"meticulous(?:ly)?",
        "comprehensive": r"comprehensive(?:ly)?",
        "holistic": r"holistic(?:ally)?",
        "synergy": r"synerg(?:y|ies|istic)",
        "empower": r"empower(?:s|ed|ing|ment)?",
        "unlock": r"unlock(?:s|ed|ing)?",
        "foster": r"foster(?:s|ed|ing)?",
    }.items()
}

_CONTRAST_RE = re.compile(
    r"not just .+?,? but\b|it'?s not about .+?, ?it'?s about|isn'?t just\b",
    re.IGNORECASE,
)

_HEDGE_RE = re.compile(r"\b(?:helped|worked|aimed|sought) to\b", re.IGNORECASE)

_VAGUE_QUANTITY_RE = re.compile(r"\b(?:various|several)\b", re.IGNORECASE)

_FIRST_PERSON_RE = re.compile(r"\b(?:I|my|we|our)\b")

# H006: keywords in this bank are dual-purpose, ATS coverage tags (rule 10 in
# specs/01-bullet-bank.md) and, here, a jargon-leak signal. Most coverage
# keywords are plain domain nouns a summary is meant to say (cosmology,
# automation, optimization, ...), so only this explicit list of actual
# tool/tech-stack proper nouns counts as jargon for H006, exact match
# case-insensitive against the full keyword string. Deliberately a
# maintained list, not a heuristic, per spec 02's "configurable jargon
# list." Update it when a new tool lands in the bank.
_TECH_JARGON_TERMS = {
    "python",
    "fastapi",
    "llm",
    "llm-as-judge",
    "nlp",
    "ocr",
    "alteryx",
    "tableau",
    "hydra",
    "unet",
    "emergenet",
    "groq",
    "rag",
    "ccss",
    "gradio",
    "hugging face spaces",
    "ollama",
    "chroma db",
    "pydantic",
    "docker",
    "github actions",
    "vad",
    "json schema",
}


def _first_content_word(clause: str) -> str:
    """Like bank.py's first-word check, but skips a leading and/or so a
    triad's third clause ("and improving X") isn't missed because the verb
    isn't literally the first word."""
    clause = clause.strip()
    lead = re.match(r"(?:and|or)\s+", clause, re.IGNORECASE)
    if lead:
        clause = clause[lead.end() :]
    match = re.match(r"[^\w]*(\w+)", clause)
    return match.group(1) if match else ""


def _has_gerund_triad(text: str) -> bool:
    run = 0
    for clause in text.split(","):
        word = _first_content_word(clause).lower()
        if word.endswith("ing"):
            run += 1
            if run >= 3:
                return True
        else:
            run = 0
    return False


def _lint_text(entity_id: str, text: str, report: Report) -> None:
    if _DASH_RE.search(text):
        report.errors.append(
            Issue(
                "S001", entity_id, "em dash, en dash, or ASCII dash used as punctuation"
            )
        )
    for word, pattern in _BANNED_VOCAB.items():
        if pattern.search(text):
            report.errors.append(
                Issue("S002", entity_id, f"banned AI-tell word '{word}'")
            )
    if _CONTRAST_RE.search(text):
        report.errors.append(
            Issue(
                "S003",
                entity_id,
                "contrast construction ('not just X, but Y' or similar)",
            )
        )
    if _has_gerund_triad(text):
        report.errors.append(
            Issue("S004", entity_id, "three or more comma-separated gerund clauses")
        )
    if _HEDGE_RE.search(text):
        report.errors.append(
            Issue("S005", entity_id, "hedge phrase ('helped to', 'worked to', etc.)")
        )
    if _VAGUE_QUANTITY_RE.search(text):
        report.errors.append(
            Issue(
                "S006", entity_id, "'various' or 'several' used where a number would do"
            )
        )
    if text.count(".") > 1:
        report.errors.append(
            Issue("H001", entity_id, "text contains more than one period")
        )
    if len(text) > _MAX_CHARS:
        report.errors.append(
            Issue(
                "H002",
                entity_id,
                f"text is {len(text)} chars, exceeds the 3-line estimate ({_MAX_CHARS} chars)",
            )
        )
    if not is_past_tense(text):
        report.errors.append(
            Issue("H003", entity_id, "text does not appear to open in past tense")
        )
    if _FIRST_PERSON_RE.search(text):
        report.errors.append(
            Issue("H007", entity_id, "first-person pronoun (I, my, we, our)")
        )


def _check_speculative(entity_id: str, preview: bool, report: Report) -> None:
    if preview:
        report.warnings.append(
            Issue("W003", entity_id, "speculative bullet present in a preview render")
        )
    else:
        report.fatal.append(
            Issue(
                "E999",
                entity_id,
                "speculative bullet in a non-preview render, fatal, not suppressible",
            )
        )


def _lint_role(
    role: LintRole, *, bank_ids: set[str], preview: bool, report: Report
) -> None:
    role_id = role.id or "?"
    total = len(role.bullets) + (1 if role.summary is not None else 0)
    if not (3 <= total <= 8):
        report.errors.append(
            Issue(
                "H004", role_id, f"{total} total bullets including summary, must be 3-8"
            )
        )
    if role.summary is None:
        report.errors.append(
            Issue("H005", role_id, "role is missing its summary bullet")
        )

    jargon: set[str] = set()
    if role.summary is not None:
        jargon.update(
            k.lower() for k in role.summary.keywords if k.lower() in _TECH_JARGON_TERMS
        )
    for bullet in role.bullets:
        jargon.update(
            k.lower() for k in bullet.keywords if k.lower() in _TECH_JARGON_TERMS
        )

    if role.summary is not None:
        summary_id = role.summary.id or role_id
        _lint_text(summary_id, role.summary.text, report)
        if role.summary.status == "speculative":
            _check_speculative(summary_id, preview, report)
        summary_lower = role.summary.text.lower()
        for word in jargon:
            if word in summary_lower:
                report.errors.append(
                    Issue("H006", summary_id, f"summary names jargon term '{word}'")
                )
        if role.summary.id is not None and role.summary.id not in bank_ids:
            report.errors.append(
                Issue("H008", role.summary.id, "id not traceable to any bank bullet")
            )

    for bullet in role.bullets:
        bullet_id = bullet.id or role_id
        _lint_text(bullet_id, bullet.text, report)
        if bullet.status == "speculative":
            _check_speculative(bullet_id, preview, report)
        if bullet.id is not None and bullet.id not in bank_ids:
            report.errors.append(
                Issue("H008", bullet.id, "id not traceable to any bank bullet")
            )


def _check_w001(
    target: LintTarget, profile: str, conn: sqlite3.Connection, report: Report
) -> None:
    covered: set[str] = set()
    for role in target.roles:
        if role.summary is not None:
            covered.update(k.lower() for k in role.summary.keywords if k)
        for bullet in role.bullets:
            covered.update(k.lower() for k in bullet.keywords if k)

    rows = conn.execute(
        "SELECT keyword FROM keyword_corpus WHERE profile = ?", (profile,)
    ).fetchall()
    if not rows:
        return
    matched = sum(1 for row in rows if row["keyword"].lower() in covered)
    ratio = matched / len(rows)
    if ratio < 0.75:
        report.warnings.append(
            Issue(
                "W001",
                "-",
                f"keyword coverage {ratio:.2f} below 0.75 for profile '{profile}'",
            )
        )


def lint_target(
    target: LintTarget,
    *,
    bank_ids: set[str],
    preview: bool = False,
    profile: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> Report:
    report = Report()
    for role in target.roles:
        _lint_role(role, bank_ids=bank_ids, preview=preview, report=report)
    if profile is not None and conn is not None:
        _check_w001(target, profile, conn, report)
    # W002 (front-loading) needs real PDF y-coordinates, which don't exist
    # until D2. Documented no-op rather than a faked measurement.
    report.warnings.append(
        Issue("W002", "-", "front-loading not yet measurable, needs D2 PDF geometry")
    )
    return report


def _bank_bullet_ids(bank: Bank) -> set[str]:
    ids: set[str] = set()
    for role in bank.roles:
        ids.add(role.summary.id)
        for bullet in role.bullets:
            ids.add(bullet.id)
    return ids


def load_lint_target(path: Path) -> LintTarget:
    raw = yaml.safe_load(path.read_text())
    return LintTarget.model_validate(raw)


def lint_path(
    path: Path,
    *,
    bank_path: Path = DEFAULT_BANK_PATH,
    preview: bool = False,
    profile: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> Report:
    target = load_lint_target(path)
    bank_ids = _bank_bullet_ids(load_bank(bank_path))
    return lint_target(
        target, bank_ids=bank_ids, preview=preview, profile=profile, conn=conn
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# Only resume/bank/*.yaml is a lint target today. Extend this once D4 starts
# writing patched/rephrased variant files.
_LINTABLE_PATH_RE = re.compile(r"^resume/bank/.*\.ya?ml$")


def _print_report(report: Report, *, as_json: bool) -> None:
    if as_json:
        payload = {
            "errors": [issue.__dict__ for issue in report.errors],
            "warnings": [issue.__dict__ for issue in report.warnings],
            "fatal": [issue.__dict__ for issue in report.fatal],
        }
        print(json.dumps(payload, indent=2))
        return
    for issue in report.fatal:
        print(f"FATAL {issue}")
    for issue in report.errors:
        print(f"ERROR {issue}")
    for issue in report.warnings:
        print(f"WARN  {issue}")


def _exit_code(report: Report, *, strict: bool) -> int:
    if report.errors or report.fatal:
        return 2
    if report.warnings and strict:
        return 1
    return 0


def _cmd_changed(args: argparse.Namespace) -> int:
    hook_input = json.loads(sys.stdin.read())
    file_path = hook_input.get("tool_input", {}).get("file_path", "")
    if not _LINTABLE_PATH_RE.match(file_path.replace("\\", "/")):
        return 0
    report = lint_path(Path(file_path), preview=args.preview, profile=args.profile)
    _print_report(report, as_json=args.json)
    return _exit_code(report, strict=args.strict)


def _cmd_path(args: argparse.Namespace) -> int:
    report = lint_path(Path(args.path), preview=args.preview, profile=args.profile)
    _print_report(report, as_json=args.json)
    return _exit_code(report, strict=args.strict)


def main() -> None:
    parser = argparse.ArgumentParser(prog="jobengine.resume.slop_lint")
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("path", nargs="?", default=None)
    target_group.add_argument("--changed", action="store_true")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--profile", default=None)
    args = parser.parse_args()

    if args.changed:
        raise SystemExit(_cmd_changed(args))
    raise SystemExit(_cmd_path(args))


if __name__ == "__main__":
    main()
