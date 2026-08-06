"""uv run python -m jobengine.profiles brief --profile <id>. See
specs/09-base-resumes.md's "Inputs" section.

Read-only against data/jobengine.db (hard rule 13) and
resume/bank/aankit.yaml: only ever writes scratch render/PDF output under
resume/rendered/preview/profiles_brief/, never resume/base/ (that's E2's
job) and never the db.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from jobengine.db.migrate import DEFAULT_DB_PATH, connect
from jobengine.profiles.brief import generate_brief
from jobengine.profiles.config import DEFAULT_PROFILES_PATH, load_profile_config
from jobengine.resume.bank import DEFAULT_BANK_PATH, KNOWN_PROFILES, load_bank
from jobengine.resume.render import load_identity

_BRIEF_OUT_DIR = Path("resume/rendered/preview/profiles_brief")


def _cmd_brief(args: argparse.Namespace) -> int:
    registry = load_profile_config(DEFAULT_PROFILES_PATH)
    bank = load_bank(DEFAULT_BANK_PATH)
    identity = load_identity()
    conn = connect(DEFAULT_DB_PATH)
    try:
        brief = generate_brief(
            conn=conn,
            bank=bank,
            profile=args.profile,
            profile_config=registry[args.profile],
            identity=identity,
            out_dir=_BRIEF_OUT_DIR / args.profile,
        )
    finally:
        conn.close()
    print(brief)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="jobengine.profiles")
    subparsers = parser.add_subparsers(dest="command", required=True)

    brief_parser = subparsers.add_parser("brief")
    brief_parser.add_argument(
        "--profile", required=True, choices=sorted(KNOWN_PROFILES)
    )

    args = parser.parse_args()
    sys.exit(_cmd_brief(args))


if __name__ == "__main__":
    main()
