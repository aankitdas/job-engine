"""Tests for src/jobengine/profiles/brief.py (E1). Written before
implementation per CLAUDE.md hard rule 7. See specs/09-base-resumes.md's
"Inputs" section for brief.md's required content.

Two of the five listed brief.md sections, "rank change since last
generation" and the market "diff summary," need a previous generation to
diff against; this is the first-ever brief (base_resumes is empty), so
there is nothing to diff. Out of scope here, not silently dropped: see
this module's own docstring once written.

No CLI (`__main__.py`) unit test: no other CLI in this codebase
(bank.py, rubric/__main__.py) has one either, every existing `main()`/
`_cmd_*` is only ever exercised by a live manual run. Matched here rather
than introducing a new, unprecedented pattern; the live run is covered
separately, not by the automated suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jobengine.db.migrate import connect, init
from jobengine.resume.bank import Bank, Bullet, Meta, Role, SummaryBullet
from jobengine.resume.render import Identity

_NOW = "2026-08-05T00:00:00Z"


def _identity(**overrides) -> Identity:
    fields = {
        "full_name": "Jordan Rivera",
        "email": "jordan@example.com",
        "phone": "+1-555-123-4567",
        "city": "Austin",
        "state": "TX",
        "linkedin": "https://linkedin.com/in/jordanrivera",
        "github": "https://github.com/jordanrivera",
        "portfolio": "https://jordanrivera.dev",
        "scholar": "https://scholar.google.com/citations?user=abc123",
        "work_authorization_statement": "US citizen, no sponsorship required",
    }
    fields.update(overrides)
    return Identity(**fields)


def _summary(id_: str = "s1", text: str = "Built systems.") -> SummaryBullet:
    return SummaryBullet(id=id_, text=text, keywords=[], status="verified")


def _bullet(
    id_: str,
    text: str = "Built a thing that worked well.",
    keywords=None,
    profiles=None,
) -> Bullet:
    return Bullet(
        id=id_,
        status="verified",
        what="a thing",
        how="carefully",
        result="it worked",
        text=text,
        keywords=keywords or [],
        profiles=profiles or ["ai_ml_engineer"],
    )


def _role(id_: str, *, bullets=None, summary=None) -> Role:
    return Role(
        id=id_,
        company="Acme",
        location="Remote",
        start="2022-01",
        end="2023-01",
        kind="full_time",
        title={"default": "Engineer"},
        summary=summary or _summary(f"{id_}_s"),
        bullets=bullets if bullets is not None else [],
    )


def _bank(roles) -> Bank:
    return Bank(meta=Meta(owner="t", updated="2026-01-01"), roles=roles)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "jobengine.db"
    connection = connect(db_path)
    init(connection)
    yield connection
    connection.close()


def _insert_corpus_row(conn, profile, keyword, occurrences):
    conn.execute(
        "INSERT INTO keyword_corpus "
        "(profile, keyword, occurrences, first_seen_at, last_seen_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (profile, keyword, occurrences, _NOW, _NOW),
    )
    conn.commit()


def _insert_gap_ledger_row(conn, profile, keyword, job_id):
    conn.execute(
        "INSERT OR IGNORE INTO companies "
        "(slug, ats, name, status, source, first_seen_at) "
        "VALUES ('acme', 'greenhouse', 'Acme', 'active', 'seed', ?)",
        (_NOW,),
    )
    conn.execute(
        "INSERT OR IGNORE INTO jobs "
        "(id, ats, company_slug, ats_job_id, title, location_raw, "
        "url, apply_url, first_seen_at, last_seen_at) "
        "VALUES (?, 'greenhouse', 'acme', ?, 'Engineer', 'Remote', "
        "'http://x', 'http://x', ?, ?)",
        (job_id, str(job_id), _NOW, _NOW),
    )
    conn.execute(
        "INSERT INTO gap_ledger (profile, keyword, job_id, first_logged_at) "
        "VALUES (?, ?, ?, ?)",
        (profile, keyword, job_id, _NOW),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# _top_corpus_keywords
# ---------------------------------------------------------------------------


def test_top_corpus_keywords_reads_real_rows_ordered_by_occurrences(conn):
    from jobengine.profiles.brief import _top_corpus_keywords

    _insert_corpus_row(conn, "ai_ml_engineer", "PyTorch", 10)
    _insert_corpus_row(conn, "ai_ml_engineer", "XGBoost", 25)
    _insert_corpus_row(conn, "data_scientist", "SQL", 99)  # other profile

    bank = _bank([])
    result = _top_corpus_keywords(conn, bank, "ai_ml_engineer", limit=30)
    assert result.source == "corpus"
    assert result.keywords == [("XGBoost", 25), ("PyTorch", 10)]


def test_top_corpus_keywords_respects_limit(conn):
    from jobengine.profiles.brief import _top_corpus_keywords

    for i in range(5):
        _insert_corpus_row(conn, "ai_ml_engineer", f"kw{i}", i)

    bank = _bank([])
    result = _top_corpus_keywords(conn, bank, "ai_ml_engineer", limit=2)
    assert len(result.keywords) == 2
    assert result.keywords[0][0] == "kw4"


def test_top_corpus_keywords_falls_back_to_bank_frequency_when_corpus_is_empty(conn):
    from jobengine.profiles.brief import _top_corpus_keywords

    bank = _bank(
        [
            _role(
                "r1",
                bullets=[
                    _bullet("b1", keywords=["Python", "SQL"]),
                    _bullet("b2", keywords=["Python"]),
                    _bullet(
                        "b3",
                        keywords=["Python", "Kubernetes"],
                        profiles=["data_scientist"],  # wrong profile, excluded
                    ),
                ],
            )
        ]
    )
    result = _top_corpus_keywords(conn, bank, "ai_ml_engineer", limit=30)
    assert result.source == "bank_frequency"
    assert result.keywords[0] == ("Python", 2)
    assert ("SQL", 1) in result.keywords
    assert not any(k == "Kubernetes" for k, _ in result.keywords)


# ---------------------------------------------------------------------------
# _gap_ledger_top
# ---------------------------------------------------------------------------


def test_gap_ledger_top_groups_and_counts_by_keyword(conn):
    from jobengine.profiles.brief import _gap_ledger_top

    _insert_gap_ledger_row(conn, "ai_ml_engineer", "CMB", 1)
    _insert_gap_ledger_row(conn, "ai_ml_engineer", "CMB", 2)
    _insert_gap_ledger_row(conn, "ai_ml_engineer", "Rust", 3)
    _insert_gap_ledger_row(conn, "data_scientist", "SQL", 4)  # other profile

    result = _gap_ledger_top(conn, "ai_ml_engineer", limit=10)
    assert result == [("CMB", 2), ("Rust", 1)]


def test_gap_ledger_top_returns_empty_list_when_no_rows(conn):
    from jobengine.profiles.brief import _gap_ledger_top

    assert _gap_ledger_top(conn, "ai_ml_engineer", limit=10) == []


# ---------------------------------------------------------------------------
# _current_measurements (real render -> real soffice -> real score, same
# pattern as test_rubric.py's own real_sample_pdf-based integration test)
# ---------------------------------------------------------------------------


def test_current_measurements_renders_and_scores_a_real_candidate(tmp_path):
    from jobengine.profiles.brief import _current_measurements
    from jobengine.profiles.config import ProfileConfig, to_render_profile

    role = _role(
        "r1",
        bullets=[
            _bullet("b1", text="Built a Python service that scaled well.", keywords=["Python"]),
        ],
    )
    bank = _bank([role])
    cfg = ProfileConfig(
        id="ai_ml_engineer",
        display_name="AI/ML Engineer",
        section_order=["work_history"],
        include_summary=False,
        summary_text=None,
    )
    result = _current_measurements(
        bank=bank,
        profile="ai_ml_engineer",
        render_profile=to_render_profile(cfg),
        identity=_identity(),
        out_dir=tmp_path,
        required_keywords=["Python"],
    )
    assert result.measurements
    assert 0.0 <= result.score <= 100.0


# ---------------------------------------------------------------------------
# _unselected_bullets_with_top_keywords
# ---------------------------------------------------------------------------


def test_unselected_bullets_returns_bullets_not_tagged_but_sharing_a_keyword_stem():
    from jobengine.profiles.brief import _unselected_bullets_with_top_keywords

    role = _role(
        "r1",
        bullets=[
            _bullet("b_selected", keywords=["Python"], profiles=["ai_ml_engineer"]),
            _bullet(
                "b_unselected_match",
                keywords=["Pythons"],  # same stem as "Python"
                profiles=["data_scientist"],
            ),
            _bullet(
                "b_unselected_no_match",
                keywords=["Rust"],
                profiles=["data_scientist"],
            ),
        ],
    )
    bank = _bank([role])
    refs = _unselected_bullets_with_top_keywords(bank, "ai_ml_engineer", ["Python"])
    ids = {ref.bullet.id for ref in refs}
    assert ids == {"b_unselected_match"}


def test_unselected_bullets_returns_empty_when_nothing_qualifies():
    from jobengine.profiles.brief import _unselected_bullets_with_top_keywords

    role = _role(
        "r1", bullets=[_bullet("b1", keywords=["Python"], profiles=["ai_ml_engineer"])]
    )
    bank = _bank([role])
    refs = _unselected_bullets_with_top_keywords(bank, "ai_ml_engineer", ["Python"])
    assert refs == []


# ---------------------------------------------------------------------------
# generate_brief: full integration
# ---------------------------------------------------------------------------


def _profile_config():
    from jobengine.profiles.config import ProfileConfig

    return ProfileConfig(
        id="ai_ml_engineer",
        display_name="AI/ML Engineer",
        section_order=["work_history"],
        include_summary=False,
        summary_text=None,
    )


def test_generate_brief_with_populated_corpus_and_gap_ledger(conn, tmp_path):
    from jobengine.profiles.brief import generate_brief

    _insert_corpus_row(conn, "ai_ml_engineer", "PyTorch", 10)
    _insert_gap_ledger_row(conn, "ai_ml_engineer", "CMB", 1)

    role = _role(
        "r1",
        bullets=[
            _bullet("b1", text="Trained models with PyTorch daily.", keywords=["PyTorch"]),
            _bullet(
                "b_unselected",
                text="Ran SQL queries against a warehouse.",
                keywords=["PyTorch"],
                profiles=["data_scientist"],
            ),
        ],
    )
    bank = _bank([role])

    brief = generate_brief(
        conn=conn,
        bank=bank,
        profile="ai_ml_engineer",
        profile_config=_profile_config(),
        identity=_identity(),
        out_dir=tmp_path,
    )
    assert "# Brief: AI/ML Engineer (ai_ml_engineer)" in brief
    assert "## Top corpus keywords" in brief
    assert "PyTorch: 10" in brief
    assert "## Current base resume rubric measurements" in brief
    assert "## Uncovered gap-ledger keywords" in brief
    assert "CMB: 1" in brief
    assert "## Unselected bank bullets carrying top keywords" in brief
    assert "b_unselected" in brief


def test_generate_brief_degrades_gracefully_with_empty_corpus_and_gap_ledger(
    conn, tmp_path
):
    from jobengine.profiles.brief import generate_brief

    role = _role(
        "r1",
        bullets=[_bullet("b1", text="Built a Python service.", keywords=["Python"])],
    )
    bank = _bank([role])

    brief = generate_brief(
        conn=conn,
        bank=bank,
        profile="ai_ml_engineer",
        profile_config=_profile_config(),
        identity=_identity(),
        out_dir=tmp_path,
    )
    assert "keyword_corpus has no rows" in brief
    assert "Python" in brief  # bank-frequency fallback still surfaced a keyword
    assert "gap_ledger has no rows" in brief
    assert "## Current base resume rubric measurements" in brief
