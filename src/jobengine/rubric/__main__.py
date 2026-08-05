"""uv run python -m jobengine.rubric {score,explain}. See specs/08-rubric.md's
CLI section. `patch` is not implemented here: that's D3's patch ladder, not
D1's deterministic scorer.

Both commands need a job's required/preferred keywords, sourced from
job_analysis (C3's real output), never from a live LLM call: the rubric
stays deterministic by construction (D8 in docs/decisions.md), so this CLI
refuses to run C3 itself. Run extraction first if job_analysis has no row
for the (job, profile) pair yet.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jobengine.db.migrate import DEFAULT_DB_PATH, connect
from jobengine.db.models import get_job_analysis
from jobengine.resume.bank import DEFAULT_BANK_PATH, load_bank
from jobengine.rubric import measure, rules


def _load_job_keywords(job_id: int, profile: str) -> tuple[list[str], list[str]]:
    conn = connect(DEFAULT_DB_PATH)
    analysis = get_job_analysis(conn, job_id, profile)
    conn.close()
    if analysis is None:
        raise SystemExit(
            f"No job_analysis row for job {job_id}, profile {profile!r}. "
            "Run C3 extraction first (jobengine.pipeline.extract.analyze_job)."
        )
    required = (
        json.loads(analysis.required_keywords) if analysis.required_keywords else []
    )
    preferred = (
        json.loads(analysis.preferred_keywords) if analysis.preferred_keywords else []
    )
    return required, preferred


def _candidate(profile: str):
    bank = load_bank(DEFAULT_BANK_PATH)
    return measure.select_for_profile(bank, profile)


def _cmd_score(args: argparse.Namespace) -> int:
    pdf_path = Path(args.pdf)
    docx_path = pdf_path.with_suffix(".docx")
    if not docx_path.exists():
        raise SystemExit(f"expected a sibling docx at {docx_path}, found none")

    required, preferred = _load_job_keywords(args.job, args.profile)
    result = rules.score_resume(
        bank=_candidate(args.profile),
        profile=args.profile,
        docx_path=docx_path,
        pdf_path=pdf_path,
        required_keywords=required,
        preferred_keywords=preferred,
    )
    print(result.model_dump_json(indent=2))
    return 0 if result.passed else 1


def _cmd_explain(args: argparse.Namespace) -> int:
    pdf_path = Path(args.pdf)
    docx_path = pdf_path.with_suffix(".docx")
    required, preferred = _load_job_keywords(args.job, args.profile)
    bank = _candidate(args.profile)
    all_keywords = (required + preferred)[:10]

    rule = args.rule.upper()
    if rule == "R002":
        height = measure.page1_height(pdf_path)
        half = height / 2
        print(f"page 1 height: {height}, top-half cutoff (y <): {half}")
        for occ in measure.front_load_detail(pdf_path, all_keywords):
            if occ.top is None:
                print(f"  {occ.keyword!r}: not found on page 1")
            else:
                print(
                    f"  {occ.keyword!r}: first occurrence top={occ.top:.1f}  "
                    f"above_half={occ.above_half}"
                )
        ratio = measure.front_load(pdf_path, all_keywords)
        print(f"front_load ratio: {ratio:.2f} (threshold 0.75)")
    elif rule == "R006":
        for role in bank.roles:
            for entity_id, text in measure.iter_entries(role):
                n = measure.line_count_from_pdf(pdf_path, text)
                flag = "OVER 3 LINES" if n > 3 else "ok"
                print(f"  {entity_id}: {n} lines ({flag})")
    else:
        result = rules.score_resume(
            bank=bank,
            profile=args.profile,
            docx_path=docx_path,
            pdf_path=pdf_path,
            required_keywords=required,
            preferred_keywords=preferred,
        )
        matches = [d for d in result.deficits if d.rule == rule]
        if not matches:
            print(f"{rule}: PASS")
        else:
            for d in matches:
                print(f"{rule}: FAIL - {d.detail}")
                if d.missing:
                    print(f"  missing: {d.missing}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="jobengine.rubric")
    subparsers = parser.add_subparsers(dest="command", required=True)

    score_parser = subparsers.add_parser("score")
    score_parser.add_argument("pdf")
    score_parser.add_argument("--profile", required=True)
    score_parser.add_argument("--job", type=int, required=True)

    explain_parser = subparsers.add_parser("explain")
    explain_parser.add_argument("rule")
    explain_parser.add_argument("pdf")
    explain_parser.add_argument("--profile", required=True)
    explain_parser.add_argument("--job", type=int, required=True)

    args = parser.parse_args()
    if args.command == "score":
        sys.exit(_cmd_score(args))
    else:
        sys.exit(_cmd_explain(args))


if __name__ == "__main__":
    main()
