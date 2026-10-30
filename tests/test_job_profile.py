from decimal import Decimal
import json

from data_ana.job_profile import extract_profile
from data_ana.models import JobPost
from data_ana.sources import enrich_detail
from data_ana.crawl import write_csv, merge_posts
from data_ana.etl import normalize_job


def test_english_training_benefit_is_not_a_language_requirement():
    profile = extract_profile(description="International English speaking environment. Free English classes.", benefits="Free English classes. Annual health check and insurance.")
    assert profile["english_status"] == "unknown"
    assert profile["foreign_languages"] == []
    assert "Đào tạo ngoại ngữ" in profile["benefit_tags"]
    assert "Bảo hiểm" in profile["benefit_tags"]


def test_soft_skills_language_level_and_benefits_have_distinct_evidence():
    p = extract_profile(requirements="Good communication skills and teamwork. English IELTS 6.5 is required. Japanese is a plus.", benefits="13th month bonus. Paid annual leave. Laptop provided.")
    assert p["supplementary_skills"] == ["Giao tiếp", "Làm việc nhóm"]
    assert p["foreign_languages"] == ["Tiếng Anh", "Tiếng Nhật"]
    assert p["english_status"] == "required"
    assert "6.5" in p["english_requirement"]
    assert p["benefit_tags"] == ["Nghỉ phép", "Thiết bị làm việc", "Thưởng"]
    assert p["profile_evidence"]["foreign_languages"]["Tiếng Nhật"]["status"] == "preferred"


def test_negative_and_preferred_english_are_not_reported_as_mandatory():
    assert extract_profile(requirements="Không yêu cầu tiếng Anh.")["english_status"] == "not_required"
    assert extract_profile(requirements="English proficiency is a plus.")["english_status"] == "preferred"
    assert extract_profile(requirements="No English required.")["english_status"] == "not_required"
    assert extract_profile(description="English IELTS 6.5 is required.", skills=["English"])["english_status"] == "required"
    assert extract_profile(requirements="No prior experience required, fluent English.")["english_status"] != "not_required"


def test_generic_domain_or_benefit_text_is_not_an_applicant_skill():
    p = extract_profile(description="We build insurance and communication software. Company team building.")
    assert p["supplementary_skills"] == []
    assert p["benefits"] == "" and p["benefit_tags"] == []
    assert extract_profile(requirements="Excellent analytical skills.")["supplementary_skills"] == ["Tư duy phân tích"]
    assert "Excel" not in extract_profile(requirements="Excellent analytical skills.")["supplementary_skills"]


def test_detail_extraction_and_raw_etl_roundtrip(tmp_path):
    post = JobPost(source="topcv", title="Developer", url="https://example.com/1")
    ld = {"@type": "JobPosting", "description": "Build Python apps", "jobBenefits": "<ul><li>Thưởng tháng 13</li><li>Bảo hiểm sức khỏe</li></ul>"}
    html = '<script type="application/ld+json">' + json.dumps(ld) + '</script><section class="premium-job-description__box"><h2>Yêu cầu ứng viên</h2><p>Ưu tiên tiếng Anh TOEIC 700. Kỹ năng giao tiếp tốt.</p></section>'
    assert enrich_detail(post, html, {})
    assert post.benefits.splitlines() == ["Thưởng tháng 13", "Bảo hiểm sức khỏe"]
    assert post.english_status == "preferred"
    assert "700" in post.english_requirement
    path = tmp_path / "raw.csv"
    write_csv([post], path)
    loaded = merge_posts([], path)[0]
    assert loaded.profile_evidence == post.profile_evidence
    assert loaded.benefits == post.benefits
    cleaned = normalize_job(loaded.to_row(), Decimal("25000"))
    assert cleaned["benefit_tags"] == post.benefit_tags
    assert cleaned["english_status"] == "preferred"


def test_dashboard_preserves_english_evidence_from_processed_csv(tmp_path):
    import pandas as pd
    from data_ana.dashboard import load_jobs
    post = JobPost(source="itviec", title="Developer", skills=["Python", "English"], url="https://example.com/1")
    cleaned = normalize_job(post.to_row(), Decimal("25000"))
    # ETL intentionally excludes spoken languages from technical skills.
    assert "English" not in cleaned["skills"]
    row = {**post.to_row(), "skills": ";".join(cleaned["skills"]), "profile_evidence": json.dumps(cleaned["profile_evidence"])}
    path = tmp_path / "processed.csv"
    pd.DataFrame([row]).to_csv(path,index=False)
    result = load_jobs(path)
    assert result.iloc[0]["foreign_languages"] == "Tiếng Anh"
    assert result.iloc[0]["english_status"] == "mentioned"
