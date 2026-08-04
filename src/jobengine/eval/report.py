"""Report formatting + model_evals persistence for spec 07's eval harness.

fixture_version is a sha256 of the fixture YAML's own bytes, computed at
run time, not a hand-maintained version string: it invalidates results
automatically the moment tests/fixtures/eval/human_labels.yaml changes,
with nothing to remember to bump.
"""

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from jobengine.db.models import ModelEval, insert_model_eval
from jobengine.eval.tasks.keyword_extraction import TASK as TASK2
from jobengine.eval.tasks.keyword_extraction import Task2Report

DEFAULT_FIXTURE_PATH = Path("tests/fixtures/eval/human_labels.yaml")

# specs/07-model-eval.md Task 2 thresholds.
RECALL_THRESHOLD = 0.85
PRECISION_THRESHOLD = 0.70


def fixture_version(path: Path = DEFAULT_FIXTURE_PATH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def task2_passed(report: Task2Report) -> bool:
    return report.precision >= PRECISION_THRESHOLD and report.recall >= RECALL_THRESHOLD


def print_task2_report(report: Task2Report) -> None:
    print(
        f"Task 2: keyword extraction ({report.attempted} labeled jobs, "
        f"{report.schema_failures} schema failures)"
    )
    print(f"  TP={report.tp}  FP={report.fp}  FN={report.fn}")
    print(
        f"  precision = TP/(TP+FP) = {report.tp}/{report.tp + report.fp} "
        f"= {report.precision:.3f}  (pass >= {PRECISION_THRESHOLD})"
    )
    print(
        f"  recall    = TP/(TP+FN) = {report.tp}/{report.tp + report.fn} "
        f"= {report.recall:.3f}  (pass >= {RECALL_THRESHOLD})"
    )
    print(
        f"  schema_validity_rate = "
        f"{report.attempted - report.schema_failures}/{report.attempted} "
        f"= {report.schema_validity_rate:.3f}  (should be exactly 1.0)"
    )
    print(f"  Task 2 {'PASSED' if task2_passed(report) else 'FAILED'}")


def write_task2_model_evals(
    conn: sqlite3.Connection, model: str, report: Task2Report
) -> list[int]:
    run_at = datetime.now(UTC).isoformat()
    version = fixture_version()
    metrics = [
        ("precision", report.precision, report.precision >= PRECISION_THRESHOLD),
        ("recall", report.recall, report.recall >= RECALL_THRESHOLD),
        (
            "schema_validity_rate",
            report.schema_validity_rate,
            report.schema_validity_rate == 1.0,
        ),
    ]
    row_ids = [
        insert_model_eval(
            conn,
            ModelEval(
                model=model,
                task=TASK2,
                metric=metric,
                value=value,
                passed=passed,
                fixture_version=version,
                run_at=run_at,
            ),
        )
        for metric, value, passed in metrics
    ]
    conn.commit()
    return row_ids
