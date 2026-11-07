from pathlib import Path
import sys

import pandas as pd
from streamlit.testing.v1 import AppTest


def test_dashboard_counts_negotiable_jobs_by_default_but_not_in_salary_statistics(tmp_path, monkeypatch):
    path = tmp_path/"jobs.csv"
    pd.DataFrame([
        {"source": "topcv", "title": "Python Developer", "company": "Public", "location": "Hà Nội", "skills": "Python", "salary_text": "20 - 30 triệu", "salary_min": 20_000_000, "salary_max": 30_000_000, "url": "https://example.com/public"},
        {"source": "itviec", "title": "Python Developer", "company": "Negotiable", "location": "Hà Nội", "skills": "Python", "salary_text": "Negotiable", "url": "https://example.com/negotiable"},
    ]).to_csv(path, index=False)
    monkeypatch.setattr(sys, "argv", ["dashboard", "--data", str(path)])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/"src/data_ana/dashboard.py"), default_timeout=40).run()
    assert not app.exception
    groups = next(w for w in app.multiselect if w.label == "Nhóm dữ liệu lương")
    assert set(groups.value) == {"A", "B", "C"}
    assert next(m for m in app.metric if m.label == "Tin tuyển dụng").value == "2"
    table = next(t.value for t in app.dataframe if "Mức lương" in t.value)
    row = table.loc[table["Công ty"].eq("Negotiable")].iloc[0]
    assert row["Nhóm lương"] == "C · Thiếu dữ liệu"
    assert pd.isna(row["Midpoint tham khảo (VND)"])
    next(r for r in app.radio if r.label == "Trang phân tích").set_value("Lương").run()
    assert not app.exception
    table = next(t.value for t in app.dataframe if "Tin có lương" in t.value)
    assert table.iloc[0]["Tổng tin"] == 2
    assert table.iloc[0]["Tin có lương"] == 1
    assert table.iloc[0]["Trung vị (triệu)"] == 25
