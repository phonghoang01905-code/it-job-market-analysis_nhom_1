import json
from decimal import Decimal

import pytest

from data_ana.models import JobPost
from data_ana.sources import enrich_detail
from data_ana.salary import normalize_salary, public_salary_text, monthly_salary_label, salary_label
from data_ana.utils import parse_salary_vnd


def detail(post, salary, **extra):
    job = {"@type": "JobPosting", "title": post.title, "description": "Python developer", "baseSalary": salary, **extra}
    enrich_detail(post, '<script type="application/ld+json">' + json.dumps(job) + '</script>', {})
    return post


def test_itviec_public_schema_recovers_usd_salary_despite_login_card():
    post = detail(JobPost(source="itviec", title="DevSecOps Expert", salary_text="Sign in to view salary"), {
        "currency": "USD", "value": {"unitText": "MONTH", "minValue": 2500, "maxValue": 3000, "value": "2,500 - 3,000 USD"}})
    assert post.salary_text == "2,500 - 3,000 USD/month"
    assert (post.salary_min, post.salary_max) == (62_500_000, 75_000_000)


def test_topdev_public_schema_keeps_salary_ceiling_as_ceiling():
    post = detail(JobPost(source="topdev", title="Developer", salary_text="Login to view salary"), {
        "currency": "VND", "value": {"unitText": "MONTH", "maxValue": "30000000", "value": "Up to 30.000.000 VND"}})
    assert (post.salary_min, post.salary_max) == (None, 30_000_000)
    assert monthly_salary_label(post.salary_min, post.salary_max) == "Tối đa 30.000.000 ₫/tháng"


@pytest.mark.parametrize("text", ["14 – 16 million VND/month", "25 – 40 triệu"])
def test_explicit_vnd_value_takes_precedence_over_itviec_default_usd_metadata(text):
    post = detail(JobPost(source="itviec", title="Developer"), {"currency": "USD", "value": {"unitText": "MONTH", "value": text}})
    assert post.salary_min in {14_000_000, 25_000_000}
    assert post.salary_max in {16_000_000, 40_000_000}


def test_base_salary_ignores_estimates_and_negotiable_values():
    post = detail(JobPost(source="topdev", title="Developer", salary_text="Login to view salary"), {
        "currency": "VND", "value": {"unitText": "MONTH", "value": "Negotiable"}},
        estimatedSalary={"currency": "VND", "minValue": 60_000_000, "maxValue": 70_000_000})
    assert post.salary_text == "Negotiable"
    assert (post.salary_min, post.salary_max) == (None, None)


@pytest.mark.parametrize("salary", [
    {"value": 100_000_000},
    {"currency": "EUR", "value": {"unitText": "MONTH", "value": 2000}},
    {"currency": "USD", "value": {"unitText": "MONTH", "minValue": 3000, "maxValue": 2000}},
    {"currency": "VND", "value": {"unitText": "MONTH", "value": 0}},
    {"currency": "VND", "value": {"unitText": "MONTH", "value": "NaN"}},
    {"currency": "VND", "value": {"unitText": "MONTH", "value": True}},
])
def test_incomplete_or_invalid_schema_does_not_invent_a_salary(salary):
    assert public_salary_text(salary) == ""


def test_detail_does_not_take_salary_from_recommended_jobs():
    jobs = [
        {"@type": "JobPosting", "title": "Different role", "baseSalary": {"currency": "USD", "value": {"unitText": "MONTH", "value": 5000}}},
        {"@type": "JobPosting", "title": "Actual role", "description": "Actual description"},
    ]
    post = JobPost(source="itviec", title="Actual role", salary_text="Sign in to view salary")
    enrich_detail(post, '<script type="application/ld+json">' + json.dumps(jobs) + '</script>', {})
    assert post.description == "Actual description"
    assert (post.salary_min, post.salary_max) == (None, None)


def test_itviec_schema_title_without_accents_still_identifies_same_job():
    post = JobPost(source="itviec", title="Chuyên gia Vận hành Hạ tầng CNTT")
    detail(post, {"currency": "USD", "value": {"unitText": "MONTH", "minValue": 2500, "maxValue": 3500}}, title="Chuyen gia Van hanh Ha tang CNTT")
    assert (post.salary_min, post.salary_max) == (62_500_000, 87_500_000)


def test_annual_hourly_and_custom_rate_stay_consistent_between_crawler_and_etl():
    text = public_salary_text({"currency": "USD", "value": {"unitText": "YEAR", "value": 12000}})
    assert parse_salary_vnd(text) == (25_000_000, 25_000_000)
    assert normalize_salary(text, Decimal("26000"))["salary_min"] == 26_000_000
    assert parse_salary_vnd("20 USD/hour") == (None, None)


@pytest.mark.parametrize("text", ["1,000.50 - 2,000.75 USD/month", "1.000,50 - 2.000,75 USD/month"])
def test_salary_with_thousands_and_decimal_marks(text):
    assert parse_salary_vnd(text) == (25_012_500, 50_018_750)


@pytest.mark.parametrize("text", ["Sign in to view salary", "Login to view salary", "Đăng nhập để xem lương", "Chưa công khai số tiền (cần đăng nhập trang gốc)", "Negotiable", "Lương cạnh tranh", "", "You'll love it"])
def test_no_amount_uses_consistent_negotiable_display(text):
    assert salary_label(text) == "Thỏa thuận (chưa nêu số tiền)"


def test_display_prefers_available_amount_over_login_placeholder():
    assert salary_label("Sign in to view salary", None, 30_000_000) == "Tối đa 30.000.000 ₫/tháng"
    assert salary_label("", 20_000_000, None) == "Từ 20.000.000 ₫/tháng"
    assert salary_label("2500 - 3000 USD/month", 62_500_000, 75_000_000) == "2500 - 3000 USD/month"
