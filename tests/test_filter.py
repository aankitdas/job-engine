"""Tests for src/jobengine/pipeline/filter.py (B3). Written before
implementation per CLAUDE.md hard rule 7. See specs/04-sources.md's "Open
item" section and D23/D23-addendum in docs/decisions.md: filter.py exposes
pure functions with no persisted filter-survivor table, and daily_cap is a
deliberate non-target placeholder, not tuned to any number.
"""

from pathlib import Path

import pytest

from jobengine.db.migrate import connect, init
from jobengine.db.models import Job
from jobengine.pipeline.filter import (
    is_already_applied,
    is_citizenship_or_clearance_required,
    is_excluded_employment_type,
    is_remote,
    load_filter_config,
    matches_profiles,
)

CONFIG_PATH = Path("config/filters.yaml")


@pytest.fixture
def config():
    return load_filter_config(CONFIG_PATH)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "jobengine.db"
    connection = connect(db_path)
    init(connection)
    yield connection
    connection.close()


def _job(**overrides) -> Job:
    defaults = {
        "ats": "greenhouse",
        "company_slug": "acme",
        "ats_job_id": "1",
        "title": "Software Engineer",
        "location_raw": "San Francisco, CA",
        "remote": None,
        "department": "Engineering",
        "raw_json": "{}",
        "first_seen_at": "2026-08-02T00:00:00+00:00",
        "last_seen_at": "2026-08-02T00:00:00+00:00",
    }
    defaults.update(overrides)
    return Job(**defaults)


# --- matches_profiles: 0 / 1 / multiple profile matches ---


def test_matches_profiles_zero_matches(config):
    job = _job(title="Enterprise Account Executive, Mid Market")
    assert matches_profiles(job, config) == []


def test_matches_profiles_single_match(config):
    job = _job(title="Senior Data Scientist, Platform Inference")
    assert matches_profiles(job, config) == ["data_scientist"]


def test_matches_profiles_multiple_matches(config):
    # "Machine Learning Engineer" hits both the ai_ml_engineer alias
    # ("machine learning engineer") and software_engineer's bare "engineer".
    job = _job(title="Machine Learning Engineer")
    result = matches_profiles(job, config)
    assert set(result) == {"ai_ml_engineer", "software_engineer"}


def test_matches_profiles_is_case_insensitive(config):
    job = _job(title="SENIOR SOFTWARE ENGINEER")
    assert "software_engineer" in matches_profiles(job, config)


# --- exclusion_keywords: bare "engineer" mis-routing fix ---


def test_security_engineer_excluded_from_software_engineer_despite_bare_engineer_alias(
    config,
):
    job = _job(title="Security Engineer, Application Security")
    assert "software_engineer" not in matches_profiles(job, config)


def test_forward_deployed_engineer_excluded_from_software_engineer(config):
    job = _job(title="Forward Deployed Engineer - NYC")
    assert "software_engineer" not in matches_profiles(job, config)


def test_forward_deployed_software_engineer_still_matches_via_override(config):
    # Same "forward deployed" exclusion keyword fires, but "software" in the
    # title overrides it: this is a real software engineering role, not a
    # client-facing deployment role.
    job = _job(title="Forward Deployed Software Engineer - SF")
    assert "software_engineer" in matches_profiles(job, config)


# --- remote resolution: column vs location_raw fallback ---


def test_is_remote_uses_column_when_present(config):
    job = _job(location_raw="San Francisco, CA", remote=1)
    assert is_remote(job, config) is True


def test_is_remote_column_false_short_circuits_even_if_location_says_remote(config):
    # Real db finding: 324 jobs have "remote" in location text but remote=0/falsy
    # from the source ATS. The explicit column value wins over the text guess
    # since it came from structured Ashby data, not a heuristic.
    job = _job(location_raw="Remote, US", remote=0)
    assert is_remote(job, config) is False


def test_is_remote_falls_back_to_location_text_when_column_is_null(config):
    # Greenhouse never populates `remote` (all NULL in the real db), so this
    # is the common case for that ATS, not an edge case.
    job = _job(ats="greenhouse", location_raw="Remote - US", remote=None)
    assert is_remote(job, config) is True


def test_is_remote_false_when_column_null_and_no_remote_text(config):
    job = _job(ats="greenhouse", location_raw="San Francisco, CA", remote=None)
    assert is_remote(job, config) is False


def test_is_remote_false_when_column_and_location_both_absent(config):
    job = _job(location_raw=None, remote=None)
    assert is_remote(job, config) is False


# --- employment type exclusion: Greenhouse title heuristic vs Ashby structured field ---


def test_employment_type_greenhouse_excludes_intern_title(config):
    job = _job(ats="greenhouse", title="Software Engineering Intern", raw_json="{}")
    assert is_excluded_employment_type(job, config) is True


def test_employment_type_greenhouse_excludes_contract_title(config):
    job = _job(
        ats="greenhouse",
        title="(Contract) Senior Data Scientist, Platform Inference",
        raw_json="{}",
    )
    assert is_excluded_employment_type(job, config) is True


def test_employment_type_greenhouse_full_time_title_not_excluded(config):
    job = _job(ats="greenhouse", title="Software Engineer", raw_json="{}")
    assert is_excluded_employment_type(job, config) is False


def test_employment_type_ashby_excludes_via_structured_field_even_with_clean_title(
    config,
):
    # Title alone gives no hint; only Ashby's raw_json.employmentType says
    # this is an internship. Structured field must be checked, not just title text.
    job = _job(
        ats="ashby",
        title="Software Engineer",
        raw_json='{"employmentType": "Intern"}',
    )
    assert is_excluded_employment_type(job, config) is True


def test_employment_type_ashby_full_time_not_excluded(config):
    job = _job(
        ats="ashby",
        title="Software Engineer",
        raw_json='{"employmentType": "FullTime"}',
    )
    assert is_excluded_employment_type(job, config) is False


# --- dedup against applications.job_id ---


def _seed_company(conn, slug="acme") -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO companies (slug, ats, name, status, source, first_seen_at)
        VALUES (?, 'greenhouse', ?, 'active', 'manual', '2026-08-02T00:00:00+00:00')
        """,
        (slug, slug.title()),
    )


def _seed_applied_job(conn) -> int:
    """Insert a job plus the full FK chain (companies, base_resumes,
    job_resume_variants, applications) needed to mark it as already applied to."""
    _seed_company(conn)
    job_id = conn.execute(
        """
        INSERT INTO jobs (
            ats, company_slug, ats_job_id, title, first_seen_at, last_seen_at
        ) VALUES ('greenhouse', 'acme', '1', 'Software Engineer',
                  '2026-08-02T00:00:00+00:00', '2026-08-02T00:00:00+00:00')
        RETURNING id
        """
    ).fetchone()[0]
    base_resume_id = conn.execute(
        """
        INSERT INTO base_resumes (
            profile, version, selection, section_order, generated_at
        ) VALUES ('software_engineer', 1, '{}', '[]', '2026-08-02T00:00:00+00:00')
        RETURNING id
        """
    ).fetchone()[0]
    variant_id = conn.execute(
        """
        INSERT INTO job_resume_variants (
            job_id, profile, base_resume_id, selection_hash, created_at
        ) VALUES (?, 'software_engineer', ?, 'hash1', '2026-08-02T00:00:00+00:00')
        RETURNING id
        """,
        (job_id, base_resume_id),
    ).fetchone()[0]
    conn.execute(
        """
        INSERT INTO applications (
            job_id, resume_variant_id, autonomy_level, status
        ) VALUES (?, ?, 0, 'submitted')
        """,
        (job_id, variant_id),
    )
    conn.commit()
    return job_id


def test_is_already_applied_true_when_applications_row_exists(conn):
    job_id = _seed_applied_job(conn)
    assert is_already_applied(conn, job_id) is True


def test_is_already_applied_false_when_applications_table_is_empty(conn):
    # Real db state today: applications has zero rows. Must not raise or
    # default to True just because the table is empty.
    _seed_company(conn)
    job_id = conn.execute(
        """
        INSERT INTO jobs (
            ats, company_slug, ats_job_id, title, first_seen_at, last_seen_at
        ) VALUES ('greenhouse', 'acme', '2', 'Software Engineer',
                  '2026-08-02T00:00:00+00:00', '2026-08-02T00:00:00+00:00')
        RETURNING id
        """
    ).fetchone()[0]
    conn.commit()
    assert is_already_applied(conn, job_id) is False


def test_is_already_applied_false_for_unknown_job_id(conn):
    assert is_already_applied(conn, 999999) is False


# --- citizenship/clearance hard exclude, all profiles ---


def test_citizenship_clearance_excludes_raytheon_style_clearance_requirement(config):
    description = (
        "You will design and build mission-critical software systems. "
        "Candidates must be able to obtain and maintain a security clearance "
        "as a condition of employment."
    )
    assert is_citizenship_or_clearance_required(description, config) is True


def test_citizenship_clearance_normal_jd_not_excluded(config):
    description = (
        "We are looking for a Software Engineer to join our backend team. "
        "You will build and ship APIs used by millions of users."
    )
    assert is_citizenship_or_clearance_required(description, config) is False


def test_citizenship_clearance_eeoc_sponsorship_boilerplate_is_not_a_false_positive(
    config,
):
    # "sponsorship" appears here in an unrelated EEOC/ERG context, not a visa
    # or citizenship requirement. The check must be specific to
    # citizenship/clearance language, not any use of the word "sponsorship".
    description = (
        "We are an equal opportunity employer and celebrate diversity. "
        "We offer sponsorship of employee resource groups (ERGs) including "
        "Women in Tech and Pride@Company."
    )
    assert is_citizenship_or_clearance_required(description, config) is False
