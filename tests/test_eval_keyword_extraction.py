"""Tests for the spec 07 Task 2 (keyword extraction) eval: pooled TP/FP/FN
arithmetic, schema-failure resilience, fixture_version hashing, and
model_evals persistence.
"""

import asyncio
import json
from typing import Any

import pytest

from jobengine.db.migrate import connect, init
from jobengine.eval import report
from jobengine.eval.tasks import keyword_extraction
from jobengine.llm.schemas import (
    ApiConfig,
    FallbackConfig,
    LLMConfig,
    LocalConfig,
    RoutingConfig,
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "jobengine.db"
    connection = connect(db_path)
    init(connection)
    yield connection
    connection.close()


def _llm_config() -> LLMConfig:
    return LLMConfig(
        local=LocalConfig(
            enabled=True,
            base_url="http://fake:11434",
            model="qwen3.5:9b-q4_K_M",
            context=16384,
            timeout_s=120,
        ),
        routing=RoutingConfig(relevance="local", extract="local", rephrase="local"),
        fallback=FallbackConfig(relevance="skip", extract="fail", rephrase="skip"),
        api=ApiConfig(enabled=False),
    )


def _seed_labeled_job(
    conn, job_id: int, description: str, required_keywords: list[str]
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO companies (slug, ats, name, status, source, first_seen_at) "
        "VALUES ('acme', 'greenhouse', 'Acme', 'active', 'seed', '2026-01-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO jobs (id, ats, company_slug, ats_job_id, title, description, "
        "raw_json, first_seen_at, last_seen_at) "
        "VALUES (?, 'greenhouse', 'acme', ?, 'Software Engineer', ?, '{}', "
        "'2026-08-02T00:00:00+00:00', '2026-08-02T00:00:00+00:00')",
        (job_id, str(job_id), description),
    )
    conn.execute(
        "INSERT INTO human_labels (job_id, profile, relevance, keywords, labelled_at) "
        "VALUES (?, 'software_engineer', 90, ?, '2026-08-03T00:00:00+00:00')",
        (job_id, json.dumps(required_keywords)),
    )
    conn.commit()


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)
        self.prompt_eval_count = 1
        self.eval_count = 1


class _SequencedClient:
    """Returns one canned response per call, in call order."""

    def __init__(self, contents: list[str]) -> None:
        self._contents = list(contents)
        self.calls = 0

    async def chat(self, **kwargs: Any):
        content = self._contents[self.calls]
        self.calls += 1
        return _FakeResponse(content)


def _payload(required, preferred=None, tech_stack=None) -> str:
    return json.dumps(
        {
            "required_keywords": required,
            "preferred_keywords": preferred or [],
            "tech_stack": tech_stack or [],
        }
    )


# ---------------------------------------------------------------------------
# Task2Report arithmetic
# ---------------------------------------------------------------------------


def test_pooled_tp_fp_fn_arithmetic_across_labeled_jobs(conn):
    # job 1: labeled {python, kubernetes}; extracted {python, kubernetes, aws}
    #   -> TP=2 (python, kubernetes), FP=1 (aws), FN=0
    _seed_labeled_job(
        conn, 1, "Requirements: Python, Kubernetes", ["Python", "Kubernetes"]
    )
    # job 2: labeled {go, grpc}; extracted {go}
    #   -> TP=1 (go), FP=0, FN=1 (grpc)
    _seed_labeled_job(conn, 2, "Requirements: Go, gRPC", ["Go", "gRPC"])
    # job 3: model returns a schema-invalid payload (missing required fields)
    _seed_labeled_job(conn, 3, "Requirements: Rust", ["Rust"])

    client = _SequencedClient(
        [
            _payload(["python", "Kubernetes", "AWS"]),
            _payload(["Go"]),
            '{"required_keywords": ["Rust"]}',  # missing preferred_keywords/tech_stack
        ]
    )

    result = _run(keyword_extraction.run(conn, _llm_config(), local_client=client))

    assert result.attempted == 3
    assert result.schema_failures == 1
    assert result.tp == 3  # 2 + 1
    assert result.fp == 1  # 1 + 0
    assert result.fn == 1  # 0 + 1
    assert result.precision == pytest.approx(0.75)  # 3 / (3 + 1)
    assert result.recall == pytest.approx(0.75)  # 3 / (3 + 1)
    assert result.schema_validity_rate == pytest.approx(2 / 3)


def test_a_schema_failure_does_not_abort_the_remaining_jobs(conn):
    _seed_labeled_job(conn, 1, "Requirements: Python", ["Python"])
    _seed_labeled_job(conn, 2, "Requirements: Go", ["Go"])

    client = _SequencedClient(
        [
            "not valid json at all",
            _payload(["Go"]),
        ]
    )

    result = _run(keyword_extraction.run(conn, _llm_config(), local_client=client))

    assert client.calls == 2, "the second job must still be attempted"
    assert result.schema_failures == 1
    assert result.tp == 1
    assert result.fp == 0
    assert result.fn == 0


def test_keyword_normalization_is_case_and_whitespace_insensitive(conn):
    _seed_labeled_job(conn, 1, "Requirements: Python", [" Python ", "AWS"])
    client = _SequencedClient([_payload(["python", "aws"])])

    result = _run(keyword_extraction.run(conn, _llm_config(), local_client=client))

    assert result.tp == 2
    assert result.fp == 0
    assert result.fn == 0


def test_predicted_set_is_the_union_of_required_and_preferred_keywords(conn):
    # A term the model files under preferred_keywords must still count as
    # a match, not a miss: required-vs-preferred is not a scoring boundary.
    _seed_labeled_job(
        conn, 1, "Requirements: Docker, Kubernetes", ["Docker", "Kubernetes"]
    )
    client = _SequencedClient([_payload(required=["Docker"], preferred=["Kubernetes"])])

    result = _run(keyword_extraction.run(conn, _llm_config(), local_client=client))

    assert result.tp == 2
    assert result.fp == 0
    assert result.fn == 0


def test_tech_stack_is_excluded_from_the_predicted_set(conn):
    # tech_stack is scoped to "every tool named anywhere in the posting",
    # broader than the qualifications-section-only ground truth; a term
    # that only appears there must not count as a false positive against
    # a label that never claimed to cover it, nor as a match.
    _seed_labeled_job(conn, 1, "Requirements: Docker", ["Docker"])
    client = _SequencedClient(
        [_payload(required=["Docker"], tech_stack=["Kubernetes"])]
    )

    result = _run(keyword_extraction.run(conn, _llm_config(), local_client=client))

    assert result.tp == 1
    assert result.fp == 0
    assert result.fn == 0


def test_a_job_labeled_on_two_tied_profiles_is_graded_once_not_twice(conn):
    _seed_labeled_job(conn, 1, "Requirements: Python", ["Python"])
    # Second human_labels row for the same job, a relevance tie (D24).
    conn.execute(
        "INSERT INTO human_labels (job_id, profile, relevance, keywords, labelled_at) "
        "VALUES (1, 'ai_ml_engineer', 90, ?, '2026-08-03T00:00:00+00:00')",
        (json.dumps(["Python"]),),
    )
    conn.commit()
    client = _SequencedClient([_payload(["Python"])])

    result = _run(keyword_extraction.run(conn, _llm_config(), local_client=client))

    assert result.attempted == 1
    assert client.calls == 1


def test_no_labeled_keywords_yields_an_empty_but_well_defined_report(conn):
    result = _run(keyword_extraction.run(conn, _llm_config(), local_client=None))

    assert result.attempted == 0
    assert result.precision == 0.0
    assert result.recall == 0.0
    assert result.schema_validity_rate == 0.0


# ---------------------------------------------------------------------------
# report.py: fixture_version, printing, model_evals persistence
# ---------------------------------------------------------------------------


def test_fixture_version_changes_when_fixture_bytes_change(tmp_path):
    path = tmp_path / "human_labels.yaml"
    path.write_text("a: 1\n")
    version_a = report.fixture_version(path)

    path.write_text("a: 2\n")
    version_b = report.fixture_version(path)

    assert version_a != version_b


def test_fixture_version_is_stable_for_identical_bytes(tmp_path):
    path = tmp_path / "human_labels.yaml"
    path.write_text("a: 1\n")
    assert report.fixture_version(path) == report.fixture_version(path)


def test_print_task2_report_shows_real_arithmetic_not_just_pass_fail(capsys):
    task_report = keyword_extraction.Task2Report(
        attempted=4, schema_failures=1, tp=3, fp=1, fn=1
    )
    report.print_task2_report(task_report)
    out = capsys.readouterr().out

    assert "TP=3" in out
    assert "FP=1" in out
    assert "FN=1" in out
    assert "3/4" in out  # both precision and recall denominators
    assert "0.750" in out


def test_write_task2_model_evals_writes_one_row_per_metric(conn):
    task_report = keyword_extraction.Task2Report(
        attempted=4, schema_failures=0, tp=3, fp=1, fn=1
    )

    ids = report.write_task2_model_evals(conn, "qwen3.5:9b-q4_K_M", task_report)

    assert len(ids) == 3
    rows = conn.execute(
        "SELECT metric, value, passed FROM model_evals ORDER BY metric"
    ).fetchall()
    by_metric = {r["metric"]: (r["value"], r["passed"]) for r in rows}
    assert by_metric["precision"][0] == pytest.approx(0.75)
    assert by_metric["precision"][1] == 1  # 0.75 >= 0.70 threshold
    assert by_metric["recall"][0] == pytest.approx(0.75)
    assert by_metric["recall"][1] == 0  # 0.75 < 0.85 threshold
    assert by_metric["schema_validity_rate"][0] == pytest.approx(1.0)
    assert by_metric["schema_validity_rate"][1] == 1
