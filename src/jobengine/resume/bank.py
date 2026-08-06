"""Bullet bank schema, loader, validator, and CLI.

Every claim that may ever appear on a generated resume lives in
resume/bank/aankit.yaml. This is the trust boundary of the whole system: the
renderer only ever draws from bullets that passed validate(). See
specs/01-bullet-bank.md.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from jobengine.db.migrate import DEFAULT_DB_PATH, connect

DEFAULT_BANK_PATH = Path("resume/bank/aankit.yaml")

# The formal profile registry lands in E1 (specs/09-base-resumes.md). Until
# then this is the single source of truth for which profile names are valid.
KNOWN_PROFILES = {"ai_ml_engineer", "software_engineer", "data_scientist"}

# Rule 6's heuristic allowlist, verbatim from specs/01-bullet-bank.md. Public
# because slop_lint.py's H003 reuses this exact heuristic (specs/02).
IRREGULAR_PAST_TENSE_VERBS = {
    "built",
    "led",
    "wrote",
    "ran",
    "drove",
    "made",
    "set",
    "cut",
    "grew",
    "shipped",
    "won",
    "chose",
    "sent",
    "held",
    "kept",
    "found",
    "taught",
    "brought",
}

# Public because rubric/patch.py's P3 rewrite gate (D4) reuses the same
# char-based line estimate rather than a second hardcoded copy.
CHARS_PER_LINE = 105
MAX_LINES = 3
WARN_CHAR_LIMIT = CHARS_PER_LINE * MAX_LINES  # 315, rule 7

BulletStatus = Literal["verified", "speculative"]
RoleKind = Literal["full_time", "internship", "research", "project"]


class Education(BaseModel):
    id: str
    degree: str
    field: str
    institution: str
    gpa: str | None = None
    status: str
    requires_degree_profiles: list[str] = []


class Certificate(BaseModel):
    id: str
    name: str
    issuer: str | None = None
    year: str | None = None


class SummaryBullet(BaseModel):
    """Lee's mandatory first bullet per role. Lighter than Bullet: no
    what/how/result claim to back, so rules 2 and 4 do not apply to it, and
    it has no profiles list because it is included on every profile's
    rendering of that role."""

    id: str
    text: str
    keywords: list[str] = []
    status: BulletStatus


class BulletVariant(BaseModel):
    """A P3 rephrase (specs/08-rubric.md's patch ladder) that passed
    every gate and was accepted for some job. The canonical `text` above
    never changes; a variant is an alternate phrasing kept alongside it.
    `used_count` increments each time a job's selector picks this
    variant's text over generating a new rewrite."""

    text: str
    keywords_added: list[str] = []
    created_at: str
    used_count: int = 0


class Bullet(BaseModel):
    id: str
    status: BulletStatus
    what: str
    how: str
    result: str
    text: str
    keywords: list[str] = []
    evidence: str | None = None
    profiles: list[str] = []
    variants: list[BulletVariant] = []


class Role(BaseModel):
    """company, location, and start are optional because Lee's rule
    (guide pg. 17-18) is that projects skip dates and location entirely,
    unlike full_time/internship/research roles, where all three are
    always present."""

    id: str
    company: str | None = None
    location: str | None = None
    start: str | None = None
    end: str | None = None
    kind: RoleKind
    title: dict[str, str]
    summary: SummaryBullet
    bullets: list[Bullet] = []


class Publication(BaseModel):
    id: str
    text: str
    authors_bold: str | None = None
    venue: str
    url: str | None = None


class Meta(BaseModel):
    owner: str
    updated: str


class Bank(BaseModel):
    meta: Meta
    education: list[Education] = []
    certificates: list[Certificate] = []
    roles: list[Role] = []
    publications: list[Publication] = []


def load_bank(path: Path = DEFAULT_BANK_PATH) -> Bank:
    raw = yaml.safe_load(path.read_text())
    return Bank.model_validate(raw)


def dump_bank(bank: Bank, path: Path) -> None:
    """Serializes bank to YAML at path. A data-fidelity guarantee only
    (load -> dump -> reload round-trips to a pydantic-equal Bank), not a
    formatting-fidelity one: `sort_keys=False` preserves each model's
    field-declaration order, but a generic dumper will not reproduce a
    hand-authored file's exact original style byte-for-byte. Nothing in
    this codebase calls this against the real resume/bank/aankit.yaml
    yet; confirmed by asking not to build that wiring in D4 (see D30 in
    docs/decisions.md), since aankit.yaml was hand-authored (A2) and a
    surprising reformat would drown a real content change in noise a
    human reviewer would have to wade through."""
    data = bank.model_dump(mode="json", exclude_defaults=False)
    path.write_text(yaml.dump(data, sort_keys=False, allow_unicode=True, width=100))


@dataclass(frozen=True)
class BulletRef:
    """A bullet or summary, together with the role it belongs to. The
    uniform shape lets the validator and the CLI walk every piece of
    resume-eligible text in the bank without caring which kind it is."""

    role_id: str
    bullet: Bullet | SummaryBullet
    is_summary: bool


def iter_bullet_refs(bank: Bank) -> list[BulletRef]:
    refs: list[BulletRef] = []
    for role in bank.roles:
        refs.append(BulletRef(role.id, role.summary, is_summary=True))
        for bullet in role.bullets:
            refs.append(BulletRef(role.id, bullet, is_summary=False))
    return refs


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
    profile_counts: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _first_word(text: str) -> str:
    match = re.match(r"[^\w]*(\w+)", text)
    return match.group(1) if match else ""


def is_past_tense(text: str) -> bool:
    word = _first_word(text)
    if not word:
        return False
    return word.lower().endswith("ed") or word.lower() in IRREGULAR_PAST_TENSE_VERBS


def _all_ids(bank: Bank) -> list[tuple[str, str]]:
    """(entity_id, kind) for every id in the bank, for rule 1's bank-wide
    uniqueness check."""
    ids: list[tuple[str, str]] = []
    for edu in bank.education:
        ids.append((edu.id, "education"))
    for cert in bank.certificates:
        ids.append((cert.id, "certificate"))
    for role in bank.roles:
        ids.append((role.id, "role"))
        ids.append((role.summary.id, "summary"))
        for bullet in role.bullets:
            ids.append((bullet.id, "bullet"))
    for pub in bank.publications:
        ids.append((pub.id, "publication"))
    return ids


def _check_unique_ids(bank: Bank, report: Report) -> None:
    seen: dict[str, str] = {}
    for entity_id, kind in _all_ids(bank):
        if entity_id in seen:
            report.errors.append(
                Issue(
                    "R1",
                    entity_id,
                    f"duplicate id, used by both {seen[entity_id]} and {kind}",
                )
            )
        else:
            seen[entity_id] = kind


def _check_bullet(bullet: Bullet, report: Report) -> None:
    if bullet.status == "verified" and not (bullet.evidence or "").strip():
        report.errors.append(
            Issue("R2", bullet.id, "status is verified but evidence is empty")
        )
    if bullet.status == "speculative":
        if (bullet.evidence or "").strip():
            report.warnings.append(
                Issue(
                    "R3",
                    bullet.id,
                    "status is speculative but evidence is set, expected null",
                )
            )
        else:
            report.warnings.append(
                Issue("R3", bullet.id, "speculative bullet, unverified claim")
            )
    for label, value in (
        ("what", bullet.what),
        ("how", bullet.how),
        ("result", bullet.result),
    ):
        if not value.strip():
            report.errors.append(Issue("R4", bullet.id, f"{label} is empty"))
    for profile in bullet.profiles:
        if profile not in KNOWN_PROFILES:
            report.errors.append(
                Issue("profiles", bullet.id, f"unknown profile '{profile}'")
            )
    if not bullet.profiles:
        report.errors.append(Issue("profiles", bullet.id, "no profiles assigned"))


def _check_text_rules(entity_id: str, text: str, report: Report) -> None:
    if text.count(".") > 1:
        report.errors.append(
            Issue("R5", entity_id, "text contains more than one period")
        )
    if not is_past_tense(text):
        report.errors.append(
            Issue("R6", entity_id, "text does not appear to open in past tense")
        )
    if len(text) > WARN_CHAR_LIMIT:
        report.warnings.append(
            Issue(
                "R7",
                entity_id,
                f"text is {len(text)} chars, estimated over {MAX_LINES} lines",
            )
        )


def _check_role(role: Role, report: Report) -> None:
    total_bullets = len(role.bullets) + 1  # +1 for the mandatory summary
    if not (3 <= total_bullets <= 8):
        report.errors.append(
            Issue(
                "R9",
                role.id,
                f"{total_bullets} total bullets including summary, must be 3-8",
            )
        )
    for key in role.title:
        if key != "default" and key not in KNOWN_PROFILES:
            report.errors.append(
                Issue(
                    "profiles", role.id, f"unknown profile '{key}' in title overrides"
                )
            )
    if "default" not in role.title:
        report.errors.append(Issue("profiles", role.id, "title has no 'default' entry"))


def _count_profiles(bank: Bank, report: Report) -> None:
    counts = dict.fromkeys(KNOWN_PROFILES, 0)
    for role in bank.roles:
        for bullet in role.bullets:
            for profile in bullet.profiles:
                if profile in counts:
                    counts[profile] += 1
    report.profile_counts = counts


def validate_bank(bank: Bank) -> Report:
    """Rules 1-9 from specs/01-bullet-bank.md. Rule 10 (every keyword backed
    by a bullet, or it is dead weight) is not checked here: keywords are
    corpus-matching tags, not a promise that the exact word appears in that
    bullet's own plain-English text (the spec's own role_bantrly example
    tags its summary with FastAPI/Python while deliberately not naming them
    in the sentence, per Lee's rule that summaries must read as
    non-technical). Rule 10 is enforced by coverage_gaps() instead, against
    keyword_corpus, once C3 populates it."""
    report = Report()
    _check_unique_ids(bank, report)
    for edu in bank.education:
        for profile in edu.requires_degree_profiles:
            if profile not in KNOWN_PROFILES:
                report.errors.append(
                    Issue(
                        "profiles",
                        edu.id,
                        f"unknown profile '{profile}' in requires_degree_profiles",
                    )
                )
    for role in bank.roles:
        _check_role(role, report)
        _check_text_rules(role.summary.id, role.summary.text, report)
        for bullet in role.bullets:
            _check_bullet(bullet, report)
            _check_text_rules(bullet.id, bullet.text, report)
    _count_profiles(bank, report)
    return report


def keywords_for_profile(bank: Bank, profile: str) -> set[str]:
    """Keywords available on any role's rendering for this profile: every
    summary's keywords (unconditional, summaries have no profile gate) plus
    keywords from bullets explicitly tagged with this profile."""
    keywords: set[str] = set()
    for role in bank.roles:
        keywords.update(k.lower() for k in role.summary.keywords)
        for bullet in role.bullets:
            if profile in bullet.profiles:
                keywords.update(k.lower() for k in bullet.keywords)
    return keywords


def coverage_gaps(
    bank: Bank, conn: sqlite3.Connection, profile: str
) -> list[tuple[str, int]]:
    """Corpus keywords for this profile with no backing bullet, i.e. rule
    10's dead weight, checked against the real keyword_corpus rather than a
    bullet's own text. The static twin of the gap ledger: run any time,
    costs nothing, no job required."""
    covered = keywords_for_profile(bank, profile)
    rows = conn.execute(
        "SELECT keyword, occurrences FROM keyword_corpus "
        "WHERE profile = ? ORDER BY occurrences DESC",
        (profile,),
    ).fetchall()
    return [
        (row["keyword"], row["occurrences"])
        for row in rows
        if row["keyword"].lower() not in covered
    ]


def keyword_counts(bank: Bank) -> Counter[str]:
    counts: Counter[str] = Counter()
    for ref in iter_bullet_refs(bank):
        counts.update(ref.bullet.keywords)
    return counts


def _cmd_validate(args: argparse.Namespace) -> int:
    bank = load_bank(args.path)
    report = validate_bank(bank)
    for issue in report.errors:
        print(f"ERROR {issue}")
    for issue in report.warnings:
        print(f"WARN  {issue}")
    print()
    for profile, count in sorted(report.profile_counts.items()):
        print(f"{profile:<20} {count} bullets")
    print()
    if report.ok:
        print(f"validate: 0 errors, {len(report.warnings)} warnings")
        return 0
    print(f"validate: {len(report.errors)} errors, {len(report.warnings)} warnings")
    return 1


def _cmd_stats(args: argparse.Namespace) -> int:
    bank = load_bank(args.path)
    if args.by_keyword:
        for keyword, count in keyword_counts(bank).most_common():
            print(f"{keyword:<30} {count}")
    return 0


def _cmd_coverage(args: argparse.Namespace) -> int:
    bank = load_bank(args.path)
    conn = connect(DEFAULT_DB_PATH)
    try:
        gaps = coverage_gaps(bank, conn, args.profile)
    finally:
        conn.close()
    if not gaps:
        print(f"no uncovered keyword_corpus entries for {args.profile}")
        return 0
    for keyword, occurrences in gaps:
        print(f"{keyword:<30} {occurrences}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="jobengine.resume.bank")
    parser.add_argument("--path", type=Path, default=DEFAULT_BANK_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate")

    stats_parser = subparsers.add_parser("stats")
    stats_parser.add_argument("--by-keyword", action="store_true")

    coverage_parser = subparsers.add_parser("coverage")
    coverage_parser.add_argument(
        "--profile", required=True, choices=sorted(KNOWN_PROFILES)
    )

    args = parser.parse_args()
    handlers = {
        "validate": _cmd_validate,
        "stats": _cmd_stats,
        "coverage": _cmd_coverage,
    }
    raise SystemExit(handlers[args.command](args))


if __name__ == "__main__":
    main()
