from datetime import datetime, timezone

import pandas as pd

from data_ana.collect_salary import qualify_posts
from data_ana.models import JobPost


def test_only_convertible_public_and_supported_estimated_jobs_are_published():
    stamp = datetime.now(timezone.utc).isoformat()
    posts = [JobPost(source="topcv", title="Backend Developer Python", company=f"Company {i}", location="Hà Nội", level="Middle",
        skills=["Python", "SQL"], requirements="Minimum 3 years of experience. Python SQL.", url=f"https://example.com/{i}",
        scraped_at=stamp, salary_text=f"{20+i} - {30+i} triệu", salary_min=(20+i)*1_000_000, salary_max=(30+i)*1_000_000) for i in range(3)]
    posts += [JobPost(source="itviec", title="Backend Developer Python", company="Target", location="Hà Nội", level="Middle", skills=["Python", "SQL"],
        requirements="Minimum 3 years of experience. Python SQL.", url="https://example.com/target", scraped_at=stamp),
        JobPost(source="topdev", title="Unknown role", url="https://example.com/missing", scraped_at=stamp),
        JobPost(source="topcv", title="Invalid salary", url="https://example.com/invalid", scraped_at=stamp, salary_min=40_000_000, salary_max=20_000_000)]
    selected, audit = qualify_posts(posts)
    assert [p.url for p in selected] == [p.url for p in posts[:4]]
    assert audit.salary_group.tolist() == ["A", "A", "A", "B", "C", "C"]
    assert pd.isna(posts[3].salary_min)  # The estimate is not written into the original field.
    assert audit.loc[4:, "salary_comparison_midpoint"].isna().all()


def test_empty_collection_does_not_invent_jobs():
    selected, audit = qualify_posts([])
    assert not selected and audit.empty


def test_daily_publish_archives_missing_salary_instead_of_putting_it_back_in_main_file(tmp_path):
    from data_ana.crawl import merge_posts
    from data_ana.salary_selection import update_salary_dataset
    path = tmp_path/"jobs.csv"
    known = JobPost(source="topcv", title="Developer", url="https://example.com/1", salary_text="20 - 30 triệu", salary_min=20_000_000, salary_max=30_000_000)
    unknown = JobPost(source="itviec", title="Developer", url="https://example.com/2")
    selected, _ = update_salary_dataset([known, unknown], path)
    assert len(selected) == 1
    assert len(merge_posts([], path)) == 1
    assert len(merge_posts([], tmp_path/"jobs_archive.csv")) == 2
    update_salary_dataset([unknown], path)
    assert len(merge_posts([], path)) == 1
    assert len(merge_posts([], tmp_path/"jobs_archive.csv")) == 2


def test_hourly_pay_without_working_hours_is_not_published_as_a_monthly_salary():
    stamp = datetime.now(timezone.utc).isoformat()
    values = dict(title="Backend Developer Python", location="Hà Nội", level="Middle", skills=["Python", "SQL"],
                  requirements="Minimum 3 years of experience. Python SQL.", scraped_at=stamp)
    donors = [JobPost(source="topcv", company=f"Company {i}", url=f"https://example.com/{i}",
        salary_text="20 - 30 triệu", salary_min=20_000_000, salary_max=30_000_000, **values) for i in range(3)]
    post = JobPost(source="itviec", company="Hourly", url="https://example.com/hourly", salary_text="20 USD/hour", **values)
    selected, audit = qualify_posts(donors+[post])
    assert len(selected) == 3
    assert audit.iloc[-1].salary_group == "C"
    assert pd.isna(audit.iloc[-1].salary_comparison_midpoint)


def test_checkpoint_publication_keeps_audit_and_counts_only_qualified_new_jobs(tmp_path):
    import json
    from data_ana.collect_salary import main
    from data_ana.crawl import write_csv, merge_posts
    raw = tmp_path/"raw/jobs.csv"
    work = tmp_path/"work"
    work.mkdir()
    original = JobPost(source="topcv", title="Developer", url="https://example.com/old", salary_text="20 - 30 triệu", salary_min=20_000_000, salary_max=30_000_000)
    paid = JobPost(source="topcv", title="Developer", url="https://example.com/new", salary_text="25 - 35 triệu", salary_min=25_000_000, salary_max=35_000_000)
    missing = JobPost(source="topcv", title="Unknown job", url="https://example.com/missing")
    write_csv([original], raw)
    write_csv([paid, missing], work/"topcv_candidates.csv")
    result = main(["--sources", "topcv", "--raw", str(raw), "--archive", str(raw.with_name("jobs_archive.csv")),
                   "--work-dir", str(work), "--out-dir", str(tmp_path/"clean"), "--skip-crawl", "--no-db"])
    assert result == 0
    assert len(merge_posts([], raw)) == 2
    assert len(merge_posts([], raw.with_name("jobs_archive.csv"))) == 3
    report = json.loads((tmp_path/"clean/salary_collection_report.json").read_text(encoding="utf-8"))
    assert report["sources"]["topcv"]["new_qualified"] == 1
    assert report["sources"]["topcv"]["excluded_total"] == 1
    assert report["etl"]["clean_rows"] == 2
    assert report["status"] == "complete"
