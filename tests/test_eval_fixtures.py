"""Tests for src/jobengine/eval/fixtures.py (C2 scaffolding). Written before
implementation per CLAUDE.md hard rule 7's spirit. See specs/07-model-eval.md
and specs/00-data-model.md's human_labels table.

Uses small hand-written YAML fixtures written to tmp_path, not the real
50-job tests/fixtures/eval/human_labels.yaml, so these tests exercise the
loader's behavior directly rather than depending on how much of the real
file happens to be labelled at any given time.
"""

import json

import pytest
import yaml

from jobengine.db.migrate import connect, init
from jobengine.eval.fixtures import load_human_labels


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "jobengine.db"
    connection = connect(db_path)
    init(connection)
    yield connection
    connection.close()


def _write_labels(tmp_path, entries):
    path = tmp_path / "human_labels.yaml"
    with open(path, "w") as f:
        yaml.dump(entries, f)
    return path


def _seed_jobs(conn, job_ids, company_slug="acme"):
    """human_labels.job_id FKs to jobs.id, which FKs to companies. Seed
    both so these tests can insert human_labels rows for arbitrary ids
    without depending on the real jobengine.db.
    """
    conn.execute(
        "INSERT OR IGNORE INTO companies (slug, ats, name, status, source, first_seen_at) "
        "VALUES (?, 'greenhouse', ?, 'active', 'manual', '2026-08-03T00:00:00+00:00')",
        (company_slug, company_slug.title()),
    )
    for job_id in job_ids:
        conn.execute(
            "INSERT INTO jobs (id, ats, company_slug, ats_job_id, title, first_seen_at, last_seen_at) "
            "VALUES (?, 'greenhouse', ?, ?, 'placeholder', '2026-08-03T00:00:00+00:00', "
            "'2026-08-03T00:00:00+00:00')",
            (job_id, company_slug, str(job_id)),
        )
    conn.commit()


def _human_label_rows(conn):
    return {
        (row["job_id"], row["profile"]): dict(row)
        for row in conn.execute("SELECT * FROM human_labels").fetchall()
    }


def _entry(**overrides):
    defaults = {
        "job_id": 1,
        "title": "Software Engineer",
        "company": "acme",
        "description": "Build things.",
        "relevance": {
            "ai_ml_engineer": None,
            "software_engineer": None,
            "data_scientist": None,
        },
        "required_keywords": None,
    }
    defaults.update(overrides)
    return defaults


def test_load_human_labels_writes_row_for_a_filled_in_profile(conn, tmp_path):
    _seed_jobs(conn, [101])
    entry = _entry(
        job_id=101,
        relevance={
            "ai_ml_engineer": None,
            "software_engineer": 85,
            "data_scientist": 0,
        },
    )
    path = _write_labels(tmp_path, [entry])

    written = load_human_labels(conn, path)

    rows = _human_label_rows(conn)
    assert written == 2
    assert (101, "software_engineer") in rows
    assert rows[(101, "software_engineer")]["relevance"] == 85
    assert (101, "data_scientist") in rows
    assert rows[(101, "data_scientist")]["relevance"] == 0
    assert (101, "ai_ml_engineer") not in rows


def test_load_human_labels_skips_job_with_all_relevance_still_null(conn, tmp_path):
    _seed_jobs(conn, [202])
    entry = _entry(job_id=202)  # default: all three relevance null
    path = _write_labels(tmp_path, [entry])

    written = load_human_labels(conn, path)

    assert written == 0
    assert _human_label_rows(conn) == {}


def test_load_human_labels_null_required_keywords_does_not_break(conn, tmp_path):
    _seed_jobs(conn, [303])
    entry = _entry(
        job_id=303,
        relevance={
            "ai_ml_engineer": 60,
            "software_engineer": None,
            "data_scientist": None,
        },
        required_keywords=None,
    )
    path = _write_labels(tmp_path, [entry])

    load_human_labels(conn, path)

    rows = _human_label_rows(conn)
    assert rows[(303, "ai_ml_engineer")]["keywords"] is None


def test_load_human_labels_attaches_keywords_only_to_the_max_relevance_profile(
    conn, tmp_path
):
    _seed_jobs(conn, [404])
    entry = _entry(
        job_id=404,
        relevance={
            "ai_ml_engineer": 90,
            "software_engineer": 20,
            "data_scientist": None,
        },
        required_keywords=["Python", "PyTorch"],
    )
    path = _write_labels(tmp_path, [entry])

    load_human_labels(conn, path)

    rows = _human_label_rows(conn)
    assert json.loads(rows[(404, "ai_ml_engineer")]["keywords"]) == [
        "Python",
        "PyTorch",
    ]
    assert rows[(404, "software_engineer")]["keywords"] is None
    assert (404, "data_scientist") not in rows


def test_load_human_labels_is_idempotent_and_reflects_updated_values_on_rerun(
    conn, tmp_path
):
    _seed_jobs(conn, [505])
    path = _write_labels(
        tmp_path,
        [
            _entry(
                job_id=505,
                relevance={
                    "ai_ml_engineer": 40,
                    "software_engineer": None,
                    "data_scientist": None,
                },
            )
        ],
    )
    load_human_labels(conn, path)
    assert _human_label_rows(conn)[(505, "ai_ml_engineer")]["relevance"] == 40

    # Simulate the user revising a label in a later sitting and re-running.
    path = _write_labels(
        tmp_path,
        [
            _entry(
                job_id=505,
                relevance={
                    "ai_ml_engineer": 55,
                    "software_engineer": None,
                    "data_scientist": None,
                },
            )
        ],
    )
    load_human_labels(conn, path)

    rows = _human_label_rows(conn)
    assert len(rows) == 1  # updated in place, not duplicated
    assert rows[(505, "ai_ml_engineer")]["relevance"] == 55


def test_load_human_labels_mixed_batch_only_counts_labelled_profiles(conn, tmp_path):
    _seed_jobs(conn, [1, 2, 3])
    entries = [
        _entry(
            job_id=1,
            relevance={
                "ai_ml_engineer": 70,
                "software_engineer": 10,
                "data_scientist": None,
            },
        ),
        _entry(job_id=2),  # all null, skipped
        _entry(
            job_id=3,
            relevance={
                "ai_ml_engineer": None,
                "software_engineer": None,
                "data_scientist": 30,
            },
        ),
    ]
    path = _write_labels(tmp_path, entries)

    written = load_human_labels(conn, path)

    assert written == 3
    rows = _human_label_rows(conn)
    assert len(rows) == 3
    assert (2, "ai_ml_engineer") not in rows
