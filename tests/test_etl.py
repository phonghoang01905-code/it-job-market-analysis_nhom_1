import json
from decimal import Decimal

import pytest

from data_ana.etl import extract_normalized_skills, normalize_salary, run_etl


@pytest.mark.parametrize("text,expected", [
    ("20 - 35 triệu", (20_000_000, 35_000_000)),
    ("$1,000 - $2,000", (25_000_000, 50_000_000)),
    ("1.500 USD", (37_500_000, 37_500_000)),
    ("Tới 25 triệu", (None, 25_000_000)),
    ("Từ 20tr", (20_000_000, None)),
    ("15,5 - 20 triệu", (15_500_000, 20_000_000)),
    ("Login to view salary", (None, None)),
    ("Thoả thuận", (None, None)),
    ("$20/hour", (None, None)),
    ("12000 USD/year", (25_000_000, 25_000_000)),
])
def test_salary_normalization(text, expected):
    result = normalize_salary(text, Decimal("25000"))
    assert (result["salary_min"], result["salary_max"]) == expected


def test_custom_exchange_rate_and_original_salary_retained():
    salary = normalize_salary("$1000 - $2000", Decimal("26000"))
    assert salary["salary_min"] == 26_000_000
    assert salary["salary_min_original"] == 1000
    assert salary["salary_currency"] == "USD"
    assert salary["usd_vnd_rate"] == 26000


def test_skill_aliases_boundaries_and_truncated_tags():
    skills = extract_normalized_skills("ReactJS Engineer", "Build Node.js, C++, C# and PostgreSQL. Go to the office.", ["React", "1 năm kinh nghiệm...", "English", "k..."])
    assert skills == ["C#", "C++", "NodeJS", "PostgreSQL", "React"]
    assert extract_normalized_skills("Engineer", "go to work", []) == []


def test_etl_old_json_format_deduplicates_and_reports_invalid_rows(tmp_path):
    original = {"source": "topcv", "title": " Dev  ", "company": " ACME ", "url": "https://example.com/job/1?tracking=a", "skills": "Python;python", "salary_text": "20 triệu", "description": "<p>Docker</p>", "posted_date": "1 tuần trước", "scraped_at": "2026-10-28T00:00:00+00:00"}
    path = tmp_path / "raw.json"
    path.write_text(json.dumps({"jobs": [original, {**original, "url": "https://example.com/job/1?tracking=b"}, {"source": "topcv", "title": "No ID"}]}), encoding="utf-8")
    report = run_etl(path, tmp_path / "clean")
    assert (report["clean_rows"], report["duplicates"], report["rejected"]) == (1, 1, 1)
    data = json.loads((tmp_path / "clean/jobs.json").read_text(encoding="utf-8"))["jobs"][0]
    assert data["title"] == "Dev" and data["company"] == "ACME"
    assert data["url"] == "https://example.com/job/1"
    assert data["skills"] == ["Docker", "Python"]
    assert data["posted_date"] is None and data["posted_date_text"] == "1 tuần trước"


@pytest.mark.parametrize("rate", ["0", "-1", "NaN", "Infinity"])
def test_etl_rejects_invalid_rate(tmp_path, rate):
    with pytest.raises(ValueError):
        run_etl(tmp_path / "unused.csv", tmp_path / "out", usd_vnd_rate=rate)
