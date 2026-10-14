from data_ana.utils import extract_skills, infer_level, infer_work_model, parse_salary_vnd


def test_parse_salary_vnd_for_million_range() -> None:
    assert parse_salary_vnd("20 - 35 trieu") == (20_000_000, 35_000_000)


def test_parse_salary_vnd_for_usd_range() -> None:
    assert parse_salary_vnd("$1000 - $2000") == (25_000_000, 50_000_000)


def test_parse_salary_negotiable() -> None:
    assert parse_salary_vnd("Thoa thuan") == (None, None)


def test_extract_skills() -> None:
    assert extract_skills("Senior Python Developer with AWS and Docker") == ["aws", "docker", "python"]


def test_infer_level_and_work_model() -> None:
    assert infer_level("Senior Backend Engineer") == "Senior"
    assert infer_work_model("Hybrid working model") == "Hybrid"

