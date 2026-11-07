from decimal import Decimal

import pandas as pd
import pytest

from test_database import isolated_database
from data_ana import database, data_access
from data_ana.etl import normalize_job
from data_ana.analytics import prepare_jobs, summary, time_summary, skill_changes


def test_sql_python_agree_on_counts_salary_calendar_and_skill_changes(isolated_database, monkeypatch):
    rows = []
    for i, values in enumerate([
        {"skills":["Python","C++"],"salary_text":"10 - 20 triệu", "posted_date":"2026-10-05", "location":"Hà Nội; Hồ Chí Minh"},
        {"skills":["Python"],"salary_text":"Từ 30 triệu", "posted_date":"2026-10-19", "location":"Hà Nội"},
        {"skills":["Java"],"salary_text":"Thoả thuận", "posted_date":"2026-10-20", "location":""},
    ]):
        rows.append(normalize_job({"source":"itviec", "job_id":str(i), "url":f"https://example.com/{i}",
            "title":"Developer", "company":"ACME", "scraped_at":"2026-10-30T07:00:00+07:00", **values}, Decimal("25000")))
    database.load_incremental(rows,"test")
    monkeypatch.setattr(data_access,"connect", isolated_database)
    monkeypatch.setattr(data_access,"database_url", lambda:"test")
    df = prepare_jobs(data_access.read_database())
    from data_ana.dashboard import prepare_dashboard_jobs
    via_dashboard = prepare_jobs(prepare_dashboard_jobs(data_access.read_database()))
    assert summary(df,"skill").set_index("skill").job_count.to_dict() == summary(via_dashboard,"skill").set_index("skill").job_count.to_dict()
    assert summary(df,"city").set_index("city").job_count.to_dict() == summary(via_dashboard,"city").set_index("city").job_count.to_dict()
    with isolated_database(None) as connection:
        sql_skills = {row[0]:(row[1],row[2],row[3]) for row in connection.execute("SELECT skill,job_count,salary_count,median_salary FROM analytics_top_skills")}
        py_skills = summary(df,"skill").set_index("skill")
        assert set(sql_skills) == set(py_skills.index)
        for skill, (count, n, median) in sql_skills.items():
            assert count == py_skills.loc[skill,"job_count"]
            assert n == py_skills.loc[skill,"salary_count"]
            assert (pd.isna(py_skills.loc[skill,"median_salary"]) and median is None) or median == py_skills.loc[skill,"median_salary"]
        weeks = connection.execute("SELECT job_count FROM analytics_weekly_jobs ORDER BY week").fetchall()
        assert [row[0] for row in weeks] == time_summary(df).job_count.tolist() == [1,0,2]
        sql_change = {row[0]:float(row[1]) for row in connection.execute("SELECT skill,share_change_pp FROM analytics_skill_changes")}
        assert sql_change == skill_changes(df).set_index("skill").share_change_pp.to_dict()
        sql_cities = dict(connection.execute("SELECT city,job_count FROM analytics_top_cities").fetchall())
        assert sql_cities == summary(df,"city").set_index("city").job_count.to_dict()


def test_postgres_dashboard_reads_new_committed_data(isolated_database, monkeypatch):
    from pathlib import Path
    import sys
    from streamlit.testing.v1 import AppTest
    def listing(i):
        return normalize_job({"source":"itviec","job_id":str(i),"url":f"https://example.com/{i}","title":"Python Developer", "skills":["Python"],
            "company":"ACME", "salary_text":"20 triệu", "scraped_at":"2026-10-30T07:00:00+07:00"},Decimal("25000"))
    database.load_incremental([listing(1)],"test")
    monkeypatch.setattr(data_access,"connect",isolated_database)
    monkeypatch.setattr(data_access,"database_url",lambda:"test")
    monkeypatch.setattr(sys,"argv",["dashboard","--source","postgres","--refresh-seconds","15"])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "src/data_ana/dashboard.py"),default_timeout=40).run()
    assert not app.exception
    assert next(m for m in app.metric if m.label == "Tin tuyển dụng").value == "1"
    database.load_incremental([listing(2)],"test")
    next(b for b in app.button if b.label == "Đọc lại dữ liệu ngay").click().run()
    assert not app.exception
    assert next(m for m in app.metric if m.label == "Tin tuyển dụng").value == "2"
