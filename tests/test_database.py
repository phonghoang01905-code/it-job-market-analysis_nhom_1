"""Run real PostgreSQL tests only when TEST_DATABASE_URL is supplied."""
import os
import uuid
from decimal import Decimal

import psycopg
from psycopg import sql
import pytest

from data_ana import database
from data_ana.etl import normalize_job


@pytest.fixture
def isolated_database(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run real PostgreSQL integration tests")
    schema = "test_data_ana_" + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    connect = lambda _: psycopg.connect(url, options=f"-c search_path={schema}", connect_timeout=10)
    monkeypatch.setattr(database, "connect", connect)
    try:
        yield connect
    finally:
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def sample(**overrides):
    raw = {"source": "itviec", "job_id": "123", "title": "Python Dev", "company": "ACME", "url": "https://example.com/job/123", "salary_text": "$1000 - $2000", "description": "Python Docker", "posted_date": "2026-10-28", "scraped_at": "2026-10-28T07:00:00+07:00"}
    return normalize_job({**raw, **overrides}, Decimal("25000"))


def test_real_database_incremental_by_id_or_url(isolated_database):
    first = database.load_incremental([sample()], "test")
    assert first == {"inserted": 1, "skipped": 0}
    assert database.load_incremental([sample(url="https://example.com/new-slug")], "test") == {"inserted": 0, "skipped": 1}
    assert database.load_incremental([sample(job_id="new-id")], "test") == {"inserted": 0, "skipped": 1}
    assert database.load_incremental([sample(source="topcv")], "test")["inserted"] == 1
    with isolated_database(None) as connection:
        assert connection.execute("SELECT count(*) FROM jobs").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM companies").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM skills").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM job_skills").fetchone()[0] == 4


def test_real_database_rolls_back_all_four_tables(isolated_database):
    with isolated_database(None) as connection:
        database.initialize(connection)
    broken = sample(job_id="bad", url="https://example.com/bad")
    broken["salary_min"] = Decimal("-1")
    with pytest.raises(psycopg.errors.CheckViolation):
        database.load_incremental([sample(), broken], "test")
    with isolated_database(None) as connection:
        for name in ("jobs", "companies", "skills", "job_skills"):
            assert connection.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(name))).fetchone()[0] == 0


def test_language_enrichment_backfills_existing_jobs_without_duplicate(isolated_database):
    first = sample()
    first["programming_languages"] = []
    first["language_evidence"] = {}
    database.load_incremental([first], "test")
    refreshed = sample()
    refreshed["requirements"] = "Python and JavaScript"
    from data_ana.languages import extract_languages
    refreshed["programming_languages"], refreshed["language_evidence"] = extract_languages(requirements=refreshed["requirements"])
    assert database.load_incremental([refreshed], "test") == {"inserted": 0, "skipped": 1}
    with isolated_database(None) as connection:
        row = connection.execute("SELECT programming_languages, requirements, description FROM jobs").fetchone()
        assert row == (["JavaScript", "Python"], "Python and JavaScript", "Python Docker")


def test_profile_backfill_and_missing_legacy_benefits_do_not_erase_data(isolated_database):
    job = sample(requirements="English IELTS 6.5 required. Teamwork.", benefits="13th month bonus. Health insurance.")
    database.load_incremental([job], "test")
    legacy = sample()
    assert database.load_incremental([legacy], "test") == {"inserted": 0, "skipped": 1}
    with isolated_database(None) as c:
        row = c.execute("SELECT benefits, english_status, foreign_languages, supplementary_skills FROM jobs").fetchone()
        assert row == ("13th month bonus. Health insurance.", "required", ["Tiếng Anh"], ["Làm việc nhóm"])


def test_original_spoken_language_tag_survives_database_load(isolated_database):
    job = sample(skills=["Python", "English"])
    assert job["foreign_languages"] == ["Tiếng Anh"]
    assert "English" not in job["skills"]
    database.load_incremental([job], "test")
    with isolated_database(None) as c:
        assert c.execute("SELECT foreign_languages,english_status FROM jobs").fetchone() == (["Tiếng Anh"], "mentioned")
