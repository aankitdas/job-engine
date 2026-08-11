"""CLI: uv run python -m jobengine.eval {run|compare}. See
specs/07-model-eval.md.
"""

import argparse
import asyncio

from jobengine.db.migrate import DEFAULT_DB_PATH, connect
from jobengine.eval import harness
from jobengine.llm.router import load_config
from jobengine.pipeline.filter import load_filter_config
from jobengine.pipeline.relevance import load_relevance_config
from jobengine.resume.bank import DEFAULT_BANK_PATH, load_bank


def _main() -> None:
    parser = argparse.ArgumentParser(prog="jobengine.eval")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--model", required=True)

    subparsers.add_parser("compare")

    args = parser.parse_args()
    conn = connect(DEFAULT_DB_PATH)
    try:
        if args.command == "run":
            llm_config = load_config()
            filter_config = load_filter_config()
            relevance_config = load_relevance_config()
            bank = load_bank(DEFAULT_BANK_PATH)
            asyncio.run(
                harness.run_all(
                    conn,
                    args.model,
                    llm_config,
                    filter_config,
                    relevance_config,
                    bank,
                )
            )
        elif args.command == "compare":
            _compare(conn)
    finally:
        conn.close()


def _compare(conn) -> None:
    rows = conn.execute(
        "SELECT model, task, metric, value, passed, fixture_version, run_at "
        "FROM model_evals ORDER BY run_at DESC"
    ).fetchall()
    if not rows:
        print(
            "No model_evals rows yet. Run "
            "`uv run python -m jobengine.eval run --model <name>` first."
        )
        return
    for row in rows:
        status = "PASS" if row["passed"] else "FAIL"
        version = (row["fixture_version"] or "")[:8]
        print(
            f"{row['run_at']}  {row['model']:20s} {row['task']:20s} "
            f"{row['metric']:22s} {row['value']:.3f}  {status}  "
            f"fixture={version}"
        )


if __name__ == "__main__":
    _main()
