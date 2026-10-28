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


def test_salary_with_vietnamese_accents_thousands_and_open_bounds():
    assert parse_salary_vnd("20 - 35 triệu") == (20_000_000, 35_000_000)
    assert parse_salary_vnd("$1,000 - $2,000") == (25_000_000, 50_000_000)
    assert parse_salary_vnd("Tới 25 triệu") == (None, 25_000_000)
    assert parse_salary_vnd("Từ 20 triệu") == (20_000_000, None)
    assert parse_salary_vnd("Thoả thuận") == (None, None)
    assert parse_salary_vnd("Login to view salary") == (None, None)
    assert infer_work_model("Trực tiếp") == "Onsite"
    assert infer_work_model("Làm việc từ xa") == "Remote"

