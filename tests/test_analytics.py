from pathlib import Path

import pandas as pd
import pytest

from data_ana.analytics import prepare_jobs, summary, time_summary, skill_changes, cluster_jobs


def frame(rows):
    return prepare_jobs(pd.DataFrame([{"source":"itviec", "url":f"https://example.com/{i}", "title":"Developer", **row} for i,row in enumerate(rows)]))


def test_salary_open_bounds_are_excluded_and_multi_city_not_double_counted_within_city():
    df = frame([
        {"skills":"Python;Python;SQL", "salary_min":10_000_000, "salary_max":20_000_000, "city":"Hà Nội; Hồ Chí Minh; Hà Nội", "company":" Acme "},
        {"skills":"Python", "salary_min":30_000_000, "salary_max":"", "city":"Hà Nội", "company":"ACME"},
        {"skills":"SQL", "salary_min":"", "salary_max":20_000_000, "city":"", "company":""},
    ])
    python = summary(df,"skill").set_index("skill").loc["Python"]
    assert python.job_count == 2 and python.salary_count == 1 and python.median_salary == 15_000_000
    cities = summary(df,"city").set_index("city")
    assert cities.loc["Hà Nội","job_count"] == 2
    assert cities.loc["Hồ Chí Minh","job_count"] == 1
    assert cities.job_count.sum() == 4
    assert len(summary(df,"company")) == 1


def test_listing_identity_deduplicates_within_source_only():
    df = frame([{"source":"itviec", "url":"https://example.com/job?track=1"},
                {"source":"itviec", "url":"https://example.com/job?track=2"},
                {"source":"topdev", "url":"https://example.com/job"}])
    assert len(df) == 2


def test_persisted_technical_labels_are_authoritative_for_bi():
    original = pd.DataFrame([{"skills":"Python", "programming_languages":"Go;R", "requirements":"Java, Git and AWS required"}])
    original.attrs["skills_normalized"] = True
    df = prepare_jobs(original)
    assert df._skills.iloc[0] == ["Go", "Python", "R"]


def test_calendar_zero_filling_and_missing_posted_date_never_uses_scrape_date():
    df = frame([{"posted_date":"2026-10-05", "scraped_at":"2026-11-01T18:00:00Z"},
                {"posted_date":"2026-10-19"},
                {"posted_date":"2 days ago", "scraped_at":"2026-10-21T10:00:00Z"}])
    table = time_summary(df)
    assert table.job_count.tolist() == [1,0,1]
    assert int(table.job_count.sum()) == 2
    assert df._date_observed.iloc[0] == pd.Timestamp("2026-11-02")


def test_skill_changes_report_share_points_and_do_not_divide_by_zero():
    df = frame([{"posted_date":"2026-10-05", "skills":"Python"},
                {"posted_date":"2026-10-12", "skills":"Python"},
                {"posted_date":"2026-10-13", "skills":"Java"}])
    change = skill_changes(df).set_index("skill")
    assert change.loc["Python","count_change"] == 0
    assert change.loc["Python","share_change_pp"] == -50
    assert change.loc["Java","share_change_pp"] == 50
    assert pd.isna(change.loc["Java","growth_pct"])
    assert skill_changes(df.iloc[:1]).empty


def test_clustering_is_reproducible_and_leaves_unskilled_jobs_unassigned():
    df = frame([{"skills":"Python;Pandas;SQL"}, {"skills":"Python;Pandas"},
                {"skills":"Java;Angular"}, {"skills":"Java;Spring"}, {"skills":""}])
    assignments, groups, meta = cluster_jobs(df,2)
    again, _, same_meta = cluster_jobs(df,2)
    assert assignments.cluster.tolist()[:-1] == again.cluster.tolist()[:-1]
    assert pd.isna(assignments.cluster.iloc[-1])
    assert groups.job_count.sum() == 4 and meta["excluded"] == 1
    assert meta == same_meta and meta["k"] == 2
    assert cluster_jobs(df.iloc[:1])[2]["status"] == "insufficient"
    with pytest.raises(ValueError):
        cluster_jobs(df,50)


def test_empty_input_keeps_csv_schemas():
    df = prepare_jobs(pd.DataFrame())
    assert summary(df,"skill").empty
    assert time_summary(df).columns.tolist() == ["period","job_count"]
    assert skill_changes(df).empty


def test_analysis_writes_tables_charts_and_metadata(tmp_path):
    from data_ana.analyze import analyze
    import json
    rows = frame([{"skills":"Python;SQL", "posted_date":"2026-10-01", "salary_min":10_000_000,"salary_max":20_000_000},
                  {"skills":"Python", "posted_date":"2026-10-10"},
                  {"skills":"Java", "posted_date":"2026-10-20"}])
    path = tmp_path / "jobs.csv"
    rows.to_csv(path,index=False)
    result = analyze(path,tmp_path / "out")
    assert result["jobs"] == 3
    assert (tmp_path / "out/weekly_jobs.png").is_file()
    salaries = pd.read_csv(tmp_path / "out/salary_by_skill.csv")
    assert salaries.set_index("skill").loc["Python", "salary_count"] == 1
    metadata = json.loads((tmp_path / "out/analysis_metadata.json").read_text(encoding="utf-8"))
    assert metadata["jobs"] == 3 and metadata["salary_complete"] == 1
