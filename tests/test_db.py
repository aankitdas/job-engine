import sqlite3

import pytest

from jobengine.db.migrate import connect, init
from jobengine.db.models import (
    Application,
    BaseResume,
    Company,
    Job,
    JobResumeVariant,
    Outcome,
    RelevanceScore,
    RubricResultRow,
    find_job_resume_variant_by_hash,
    get_company,
    get_job,
    get_job_by_id,
    get_job_resume_variant,
    get_relevance_score,
    get_rubric_results,
    insert_application,
    insert_base_resume,
    insert_job_resume_variant,
    insert_outcome,
    insert_rubric_results,
    latest_base_resume,
    latest_base_resume_version,
    list_existing_variant_pairs,
    list_pending_review_queue,
    list_relevance_scores_for_cutoff,
    update_relevance_selection,
    update_review_status,
    upsert_company,
    upsert_job,
    upsert_relevance_score,
)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "jobengine.db"
    connection = connect(db_path)
    init(connection)
    yield connection
    connection.close()


@pytest.fixture
def conn_with_company(conn):
    """A connection with the acme/greenhouse company already seeded, for
    tests whose focus is jobs rather than companies. Job tests that also
    want to assert on company immutability upsert their own company row
    instead, so their first upsert call is the one that fixes first_seen_at.
    """
    upsert_company(
        conn,
        Company(
            slug="acme",
            ats="greenhouse",
            name="Acme",
            status="active",
            source="seed",
            first_seen_at="2026-06-01T00:00:00+00:00",
        ),
    )
    return conn


def test_init_is_idempotent(conn):
    init(conn)
    init(conn)


def test_job_upsert_inserts_new_row(conn_with_company):
    conn = conn_with_company
    job = Job(
        ats="greenhouse",
        company_slug="acme",
        ats_job_id="123",
        title="Software Engineer",
        content_hash="hash-a",
        first_seen_at="2026-07-01T00:00:00+00:00",
        last_seen_at="2026-07-01T00:00:00+00:00",
    )
    job_id = upsert_job(conn, job)
    stored = get_job(conn, "greenhouse", "acme", "123")
    assert stored is not None
    assert stored.id == job_id
    assert stored.title == "Software Engineer"
    assert stored.first_seen_at == "2026-07-01T00:00:00+00:00"


def test_second_sync_of_unchanged_job_does_not_move_first_seen_at(conn_with_company):
    """The exact scenario from specs/00-data-model.md's definition of done:
    a second sync of the same job must not clobber first_seen_at, even
    though the syncing code always computes a "now" candidate for it."""
    conn = conn_with_company
    first_sync = Job(
        ats="greenhouse",
        company_slug="acme",
        ats_job_id="123",
        title="Software Engineer",
        content_hash="hash-a",
        first_seen_at="2026-07-01T00:00:00+00:00",
        last_seen_at="2026-07-01T00:00:00+00:00",
    )
    upsert_job(conn, first_sync)

    second_sync = Job(
        ats="greenhouse",
        company_slug="acme",
        ats_job_id="123",
        title="Software Engineer",
        content_hash="hash-a",
        first_seen_at="2026-07-02T00:00:00+00:00",
        last_seen_at="2026-07-02T00:00:00+00:00",
    )
    upsert_job(conn, second_sync)

    stored = get_job(conn, "greenhouse", "acme", "123")
    assert stored.first_seen_at == "2026-07-01T00:00:00+00:00"
    assert stored.last_seen_at == "2026-07-02T00:00:00+00:00"


def test_job_upsert_updates_changed_fields_on_real_edit(conn_with_company):
    conn = conn_with_company
    upsert_job(
        conn,
        Job(
            ats="greenhouse",
            company_slug="acme",
            ats_job_id="123",
            title="Software Engineer",
            content_hash="hash-a",
            first_seen_at="2026-07-01T00:00:00+00:00",
            last_seen_at="2026-07-01T00:00:00+00:00",
        ),
    )
    upsert_job(
        conn,
        Job(
            ats="greenhouse",
            company_slug="acme",
            ats_job_id="123",
            title="Senior Software Engineer",
            content_hash="hash-b",
            first_seen_at="2026-07-02T00:00:00+00:00",
            last_seen_at="2026-07-02T00:00:00+00:00",
        ),
    )
    stored = get_job(conn, "greenhouse", "acme", "123")
    assert stored.title == "Senior Software Engineer"
    assert stored.content_hash == "hash-b"
    assert stored.first_seen_at == "2026-07-01T00:00:00+00:00"


def test_job_direct_update_of_first_seen_at_raises(conn_with_company):
    conn = conn_with_company
    job_id = upsert_job(
        conn,
        Job(
            ats="greenhouse",
            company_slug="acme",
            ats_job_id="123",
            title="Software Engineer",
            first_seen_at="2026-07-01T00:00:00+00:00",
            last_seen_at="2026-07-01T00:00:00+00:00",
        ),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE jobs SET first_seen_at = ? WHERE id = ?",
            ("2026-08-01T00:00:00+00:00", job_id),
        )


def test_second_sync_of_unchanged_company_does_not_move_first_seen_at(conn):
    upsert_company(
        conn,
        Company(
            slug="acme",
            ats="greenhouse",
            name="Acme",
            status="active",
            source="seed",
            first_seen_at="2026-07-01T00:00:00+00:00",
        ),
    )
    upsert_company(
        conn,
        Company(
            slug="acme",
            ats="greenhouse",
            name="Acme",
            status="active",
            source="seed",
            first_seen_at="2026-07-02T00:00:00+00:00",
            last_checked_at="2026-07-02T00:00:00+00:00",
        ),
    )
    stored = get_company(conn, "acme", "greenhouse")
    assert stored.first_seen_at == "2026-07-01T00:00:00+00:00"
    assert stored.last_checked_at == "2026-07-02T00:00:00+00:00"


def test_company_direct_update_of_first_seen_at_raises(conn):
    upsert_company(
        conn,
        Company(
            slug="acme",
            ats="greenhouse",
            name="Acme",
            status="active",
            source="seed",
            first_seen_at="2026-07-01T00:00:00+00:00",
        ),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE companies SET first_seen_at = ? WHERE slug = ? AND ats = ?",
            ("2026-08-01T00:00:00+00:00", "acme", "greenhouse"),
        )


def test_outcomes_are_append_only(conn_with_company):
    conn = conn_with_company
    job_id = upsert_job(
        conn,
        Job(
            ats="greenhouse",
            company_slug="acme",
            ats_job_id="123",
            title="Software Engineer",
            first_seen_at="2026-07-01T00:00:00+00:00",
            last_seen_at="2026-07-01T00:00:00+00:00",
        ),
    )
    conn.execute(
        "INSERT INTO base_resumes (id, profile, version, selection, section_order, generated_at) "
        "VALUES (1, 'software_engineer', 1, '[]', '[]', '2026-07-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO job_resume_variants "
        "(id, job_id, profile, base_resume_id, selection_hash, created_at) "
        "VALUES (1, ?, 'software_engineer', 1, 'hash', '2026-07-01T00:00:00+00:00')",
        (job_id,),
    )
    conn.execute(
        "INSERT INTO applications (job_id, resume_variant_id, autonomy_level, status) "
        "VALUES (?, 1, 0, 'pending')",
        (job_id,),
    )
    application_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    outcome_id = insert_outcome(
        conn,
        Outcome(
            application_id=application_id,
            status="submitted",
            occurred_at="2026-07-01T00:00:00+00:00",
        ),
    )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE outcomes SET status = 'rejected' WHERE id = ?", (outcome_id,)
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM outcomes WHERE id = ?", (outcome_id,))


def _base_resume(profile="ai_ml_engineer", version=1, **overrides):
    fields = {
        "profile": profile,
        "version": version,
        "selection": "[]",
        "section_order": "[]",
        "docx_path": "resume/base/ai_ml_engineer/v1/resume.docx",
        "pdf_path": "resume/base/ai_ml_engineer/v1/resume.pdf",
        "rubric": "{}",
        "generated_at": "2026-08-06T00:00:00+00:00",
    }
    fields.update(overrides)
    return BaseResume(**fields)


def test_insert_base_resume_inserts_and_returns_id(conn):
    resume_id = insert_base_resume(conn, _base_resume())
    row = conn.execute(
        "SELECT profile, version, docx_path FROM base_resumes WHERE id = ?",
        (resume_id,),
    ).fetchone()
    assert row["profile"] == "ai_ml_engineer"
    assert row["version"] == 1
    assert row["docx_path"] == "resume/base/ai_ml_engineer/v1/resume.docx"


def test_latest_base_resume_version_returns_0_when_none_exist(conn):
    assert latest_base_resume_version(conn, "ai_ml_engineer") == 0


def test_latest_base_resume_version_returns_max_version_for_profile(conn):
    insert_base_resume(conn, _base_resume(profile="ai_ml_engineer", version=1))
    insert_base_resume(conn, _base_resume(profile="ai_ml_engineer", version=2))
    insert_base_resume(conn, _base_resume(profile="data_scientist", version=1))
    assert latest_base_resume_version(conn, "ai_ml_engineer") == 2
    assert latest_base_resume_version(conn, "data_scientist") == 1
    assert latest_base_resume_version(conn, "software_engineer") == 0


def test_base_resumes_row_satisfies_job_resume_variants_fk(conn_with_company):
    conn = conn_with_company
    resume_id = insert_base_resume(conn, _base_resume())
    job_id = upsert_job(
        conn,
        Job(
            ats="greenhouse",
            company_slug="acme",
            ats_job_id="999",
            title="ML Engineer",
            first_seen_at="2026-08-06T00:00:00+00:00",
            last_seen_at="2026-08-06T00:00:00+00:00",
        ),
    )
    conn.execute(
        "INSERT INTO job_resume_variants "
        "(job_id, profile, base_resume_id, selection_hash, created_at) "
        "VALUES (?, 'ai_ml_engineer', ?, 'hash', '2026-08-06T00:00:00+00:00')",
        (job_id, resume_id),
    )
    row = conn.execute(
        "SELECT base_resume_id FROM job_resume_variants WHERE job_id = ?", (job_id,)
    ).fetchone()
    assert row["base_resume_id"] == resume_id


# ---------------------------------------------------------------------------
# F1: job_resume_variants / rubric_results / applications
# ---------------------------------------------------------------------------


def _job(ats_job_id="1", title="Software Engineer", **overrides):
    fields = {
        "ats": "greenhouse",
        "company_slug": "acme",
        "ats_job_id": ats_job_id,
        "title": title,
        "first_seen_at": "2026-08-07T00:00:00+00:00",
        "last_seen_at": "2026-08-07T00:00:00+00:00",
    }
    fields.update(overrides)
    return Job(**fields)


def _variant(job_id, base_resume_id, selection_hash="hash1", **overrides):
    fields = {
        "job_id": job_id,
        "profile": "software_engineer",
        "base_resume_id": base_resume_id,
        "patch_tiers_applied": '["P0", "P1"]',
        "bullet_ids": '["b_1", "b_2"]',
        "selection_hash": selection_hash,
        "docx_path": "resume/rendered/variants/1/software_engineer/candidate.docx",
        "pdf_path": "resume/rendered/variants/1/software_engineer/candidate.pdf",
        "score": 66.87,
        "coverage": 1.0,
        "front_load": 0.4,
        "passed": True,
        "accepted": None,
        "created_at": "2026-08-07T00:00:00+00:00",
    }
    fields.update(overrides)
    return JobResumeVariant(**fields)


@pytest.fixture
def conn_with_job_and_base_resume(conn_with_company):
    conn = conn_with_company
    job_id = upsert_job(conn, _job())
    resume_id = insert_base_resume(conn, _base_resume(profile="software_engineer"))
    return conn, job_id, resume_id


def test_insert_job_resume_variant_inserts_and_returns_id(
    conn_with_job_and_base_resume,
):
    conn, job_id, resume_id = conn_with_job_and_base_resume
    variant_id = insert_job_resume_variant(conn, _variant(job_id, resume_id))
    row = conn.execute(
        "SELECT job_id, profile, review_status FROM job_resume_variants WHERE id = ?",
        (variant_id,),
    ).fetchone()
    assert row["job_id"] == job_id
    assert row["profile"] == "software_engineer"
    assert row["review_status"] == "pending"


def test_get_job_resume_variant_returns_none_when_absent(
    conn_with_job_and_base_resume,
):
    conn, job_id, _ = conn_with_job_and_base_resume
    assert get_job_resume_variant(conn, job_id, "software_engineer") is None


def test_get_job_resume_variant_round_trips(conn_with_job_and_base_resume):
    conn, job_id, resume_id = conn_with_job_and_base_resume
    insert_job_resume_variant(conn, _variant(job_id, resume_id))
    variant = get_job_resume_variant(conn, job_id, "software_engineer")
    assert variant is not None
    assert variant.job_id == job_id
    assert variant.score == 66.87
    assert variant.review_status == "pending"


def test_job_resume_variant_unique_job_profile_index_rejects_duplicate(
    conn_with_job_and_base_resume,
):
    """The whole point of the F1 migration (docs/decisions.md): a second
    variant for the same (job_id, profile) must be rejected, not silently
    accepted as a second row."""
    conn, job_id, resume_id = conn_with_job_and_base_resume
    insert_job_resume_variant(conn, _variant(job_id, resume_id, selection_hash="a"))
    with pytest.raises(sqlite3.IntegrityError):
        insert_job_resume_variant(
            conn, _variant(job_id, resume_id, selection_hash="b")
        )


def test_different_jobs_can_share_a_selection_hash(conn_with_job_and_base_resume):
    """Confirms the fix: the OLD UNIQUE(base_resume_id, selection_hash)
    constraint alone would have rejected this; two different jobs with
    an identical patch selection must both succeed, as two distinct
    rows, per spec 08's file-reuse dedup intent."""
    conn, job_id, resume_id = conn_with_job_and_base_resume
    other_job_id = upsert_job(conn, _job(ats_job_id="2", title="Other Role"))
    insert_job_resume_variant(
        conn, _variant(job_id, resume_id, selection_hash="shared")
    )
    other_variant_id = insert_job_resume_variant(
        conn, _variant(other_job_id, resume_id, selection_hash="shared")
    )
    assert get_job_resume_variant(conn, other_job_id, "software_engineer") is not None
    assert other_variant_id is not None


def test_find_job_resume_variant_by_hash_returns_none_when_absent(
    conn_with_job_and_base_resume,
):
    conn, _, resume_id = conn_with_job_and_base_resume
    assert find_job_resume_variant_by_hash(conn, resume_id, "nope") is None


def test_find_job_resume_variant_by_hash_finds_existing_match(
    conn_with_job_and_base_resume,
):
    conn, job_id, resume_id = conn_with_job_and_base_resume
    insert_job_resume_variant(
        conn, _variant(job_id, resume_id, selection_hash="findme")
    )
    found = find_job_resume_variant_by_hash(conn, resume_id, "findme")
    assert found is not None
    assert found.job_id == job_id


def test_update_review_status_sets_status_and_reviewed_at(
    conn_with_job_and_base_resume,
):
    conn, job_id, resume_id = conn_with_job_and_base_resume
    variant_id = insert_job_resume_variant(conn, _variant(job_id, resume_id))
    update_review_status(conn, variant_id, "rejected", "2026-08-07T01:00:00+00:00")
    variant = get_job_resume_variant(conn, job_id, "software_engineer")
    assert variant.review_status == "rejected"
    assert variant.reviewed_at == "2026-08-07T01:00:00+00:00"


def test_insert_and_get_rubric_results_round_trip(conn_with_job_and_base_resume):
    conn, job_id, resume_id = conn_with_job_and_base_resume
    variant_id = insert_job_resume_variant(conn, _variant(job_id, resume_id))
    results = [
        RubricResultRow(
            job_resume_variant_id=variant_id,
            rule_id="R001",
            passed=False,
            measurement=0.14,
            detail="coverage 0.14 < 0.70",
            evaluated_at="2026-08-07T00:00:00+00:00",
        ),
        RubricResultRow(
            job_resume_variant_id=variant_id,
            rule_id="R003",
            passed=True,
            measurement=None,
            detail=None,
            evaluated_at="2026-08-07T00:00:00+00:00",
        ),
    ]
    insert_rubric_results(conn, results)
    fetched = get_rubric_results(conn, variant_id)
    assert {r.rule_id for r in fetched} == {"R001", "R003"}
    r001 = next(r for r in fetched if r.rule_id == "R001")
    assert r001.passed is False
    assert r001.measurement == 0.14


def test_get_job_by_id_returns_none_when_absent(conn):
    assert get_job_by_id(conn, 999999) is None


def test_get_job_by_id_round_trips(conn_with_company):
    conn = conn_with_company
    job_id = upsert_job(conn, _job())
    job = get_job_by_id(conn, job_id)
    assert job is not None
    assert job.id == job_id
    assert job.title == "Software Engineer"


def test_latest_base_resume_returns_none_when_absent(conn):
    assert latest_base_resume(conn, "software_engineer") is None


def test_latest_base_resume_returns_highest_version_row(conn):
    insert_base_resume(conn, _base_resume(profile="software_engineer", version=1))
    v2_id = insert_base_resume(
        conn, _base_resume(profile="software_engineer", version=2)
    )
    latest = latest_base_resume(conn, "software_engineer")
    assert latest is not None
    assert latest.id == v2_id
    assert latest.version == 2


def test_insert_application_inserts_and_returns_id(conn_with_job_and_base_resume):
    conn, job_id, resume_id = conn_with_job_and_base_resume
    variant_id = insert_job_resume_variant(conn, _variant(job_id, resume_id))
    application_id = insert_application(
        conn,
        Application(
            job_id=job_id,
            resume_variant_id=variant_id,
            autonomy_level=0,
            status="queued",
        ),
    )
    row = conn.execute(
        "SELECT status, autonomy_level FROM applications WHERE id = ?",
        (application_id,),
    ).fetchone()
    assert row["status"] == "queued"
    assert row["autonomy_level"] == 0


def test_creating_a_pending_review_variant_does_not_mark_job_already_applied(
    conn_with_job_and_base_resume,
):
    """Regression test for the bug caught during F1 planning: is_already_applied()
    (src/jobengine/pipeline/filter.py) checks the applications table for
    ANY row, so a job_resume_variant alone -- with no applications row --
    must never cause that filter to misfire. Only an approved job (which
    gets a real applications row) should."""
    from jobengine.pipeline.filter import is_already_applied

    conn, job_id, resume_id = conn_with_job_and_base_resume
    insert_job_resume_variant(conn, _variant(job_id, resume_id))
    assert is_already_applied(conn, job_id) is False


def test_list_pending_review_queue_returns_only_pending_entries(
    conn_with_job_and_base_resume,
):
    conn, job_id, resume_id = conn_with_job_and_base_resume
    other_job_id = upsert_job(conn, _job(ats_job_id="2", title="Other Role"))
    pending_id = insert_job_resume_variant(
        conn, _variant(job_id, resume_id, selection_hash="pending")
    )
    reviewed_id = insert_job_resume_variant(
        conn, _variant(other_job_id, resume_id, selection_hash="reviewed")
    )
    update_review_status(conn, reviewed_id, "rejected", "2026-08-07T01:00:00+00:00")

    entries = list_pending_review_queue(conn)
    entry_ids = {e.variant_id for e in entries}
    assert pending_id in entry_ids
    assert reviewed_id not in entry_ids


def test_list_existing_variant_pairs_includes_pending_and_reviewed(
    conn_with_job_and_base_resume,
):
    conn, job_id, resume_id = conn_with_job_and_base_resume
    other_job_id = upsert_job(conn, _job(ats_job_id="2", title="Other Role"))
    insert_job_resume_variant(
        conn, _variant(job_id, resume_id, selection_hash="a")
    )
    reviewed_id = insert_job_resume_variant(
        conn, _variant(other_job_id, resume_id, selection_hash="b")
    )
    update_review_status(conn, reviewed_id, "rejected", "2026-08-07T01:00:00+00:00")

    pairs = list_existing_variant_pairs(conn)
    assert (job_id, "software_engineer") in pairs
    assert (other_job_id, "software_engineer") in pairs


def test_list_existing_variant_pairs_empty_when_no_variants(conn):
    assert list_existing_variant_pairs(conn) == set()


# ---------------------------------------------------------------------------
# C4: relevance_scores
# ---------------------------------------------------------------------------


def _relevance_score(job_id, profile="ai_ml_engineer", **overrides):
    fields = {
        "job_id": job_id,
        "profile": profile,
        "score": 75.0,
        "seniority_match": "match",
        "keyword_hits": '["Python", "LLM"]',
        "disqualifiers": "[]",
        "one_line": "Strong fit.",
        "selected": 0,
        "model": "qwen3.5:9b-q4_K_M",
        "scored_at": "2026-08-07T00:00:00+00:00",
    }
    fields.update(overrides)
    return RelevanceScore(**fields)


def test_upsert_relevance_score_inserts_a_row(conn_with_company):
    conn = conn_with_company
    job_id = upsert_job(conn, _job())
    upsert_relevance_score(conn, _relevance_score(job_id))
    row = conn.execute(
        "SELECT score, seniority_match FROM relevance_scores "
        "WHERE job_id = ? AND profile = ?",
        (job_id, "ai_ml_engineer"),
    ).fetchone()
    assert row["score"] == 75.0
    assert row["seniority_match"] == "match"


def test_get_relevance_score_returns_none_when_absent(conn_with_company):
    conn = conn_with_company
    job_id = upsert_job(conn, _job())
    assert get_relevance_score(conn, job_id, "ai_ml_engineer") is None


def test_get_relevance_score_round_trips(conn_with_company):
    conn = conn_with_company
    job_id = upsert_job(conn, _job())
    upsert_relevance_score(conn, _relevance_score(job_id, score=42.0))
    result = get_relevance_score(conn, job_id, "ai_ml_engineer")
    assert result is not None
    assert result.job_id == job_id
    assert result.score == 42.0
    assert result.selected == 0


def test_upsert_relevance_score_rerun_updates_in_place(conn_with_company):
    conn = conn_with_company
    job_id = upsert_job(conn, _job())
    upsert_relevance_score(conn, _relevance_score(job_id, score=10.0))
    upsert_relevance_score(conn, _relevance_score(job_id, score=90.0))
    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM relevance_scores WHERE job_id = ?", (job_id,)
    ).fetchone()
    assert rows["n"] == 1
    result = get_relevance_score(conn, job_id, "ai_ml_engineer")
    assert result.score == 90.0


def test_upsert_relevance_score_different_profiles_are_distinct_rows(
    conn_with_company,
):
    conn = conn_with_company
    job_id = upsert_job(conn, _job())
    upsert_relevance_score(conn, _relevance_score(job_id, "ai_ml_engineer", score=10.0))
    upsert_relevance_score(
        conn, _relevance_score(job_id, "software_engineer", score=80.0)
    )
    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM relevance_scores WHERE job_id = ?", (job_id,)
    ).fetchone()
    assert rows["n"] == 2


def test_list_relevance_scores_for_cutoff_includes_first_seen_at(conn_with_company):
    conn = conn_with_company
    job_id = upsert_job(conn, _job(first_seen_at="2026-08-01T00:00:00+00:00"))
    upsert_relevance_score(conn, _relevance_score(job_id, score=55.0))
    rows = list_relevance_scores_for_cutoff(conn, "ai_ml_engineer")
    assert len(rows) == 1
    assert rows[0].job_id == job_id
    assert rows[0].score == 55.0
    assert rows[0].first_seen_at == "2026-08-01T00:00:00+00:00"


def test_list_relevance_scores_for_cutoff_scoped_to_profile(conn_with_company):
    conn = conn_with_company
    job_id = upsert_job(conn, _job())
    upsert_relevance_score(conn, _relevance_score(job_id, "ai_ml_engineer"))
    upsert_relevance_score(conn, _relevance_score(job_id, "data_scientist"))
    rows = list_relevance_scores_for_cutoff(conn, "ai_ml_engineer")
    assert len(rows) == 1
    assert rows[0].job_id == job_id


def test_update_relevance_selection_sets_selected_and_resets_others(
    conn_with_company,
):
    conn = conn_with_company
    job_a = upsert_job(conn, _job(ats_job_id="1"))
    job_b = upsert_job(conn, _job(ats_job_id="2"))
    upsert_relevance_score(conn, _relevance_score(job_a, selected=1))
    upsert_relevance_score(conn, _relevance_score(job_b, selected=1))

    update_relevance_selection(conn, "ai_ml_engineer", {job_a})

    assert get_relevance_score(conn, job_a, "ai_ml_engineer").selected == 1
    assert get_relevance_score(conn, job_b, "ai_ml_engineer").selected == 0


def test_update_relevance_selection_empty_set_deselects_all(conn_with_company):
    conn = conn_with_company
    job_id = upsert_job(conn, _job())
    upsert_relevance_score(conn, _relevance_score(job_id, selected=1))

    update_relevance_selection(conn, "ai_ml_engineer", set())

    assert get_relevance_score(conn, job_id, "ai_ml_engineer").selected == 0
