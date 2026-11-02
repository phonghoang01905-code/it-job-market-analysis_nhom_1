from pathlib import Path
import sys

import pandas as pd
from streamlit.testing.v1 import AppTest

from data_ana.analytics_dashboard import PAGES


def test_all_eda_pages_work_and_empty_filters_are_handled(tmp_path,monkeypatch):
    path = tmp_path / "jobs.csv"
    pd.DataFrame([{"source":"itviec", "title":"Python Developer", "company":"ACME", "skills":"Python;SQL", "salary_min":10_000_000,"salary_max":20_000_000,"posted_date":"2026-10-20","url":"https://example.com/1"},
                  {"source":"topdev", "title":"Java Developer", "company":"Beta", "skills":"Java", "posted_date":"2026-10-28","url":"https://example.com/2"}]).to_csv(path,index=False)
    monkeypatch.setattr(sys,"argv",["dashboard","--data",str(path)])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "src/data_ana/dashboard.py"),default_timeout=40).run()
    for page in PAGES[1:]:
        next(r for r in app.radio if r.label == "Trang phân tích").set_value(page).run()
        assert not app.exception
    next(b for b in app.button if b.label == "Phân cụm bộ dữ liệu đang lọc").click().run()
    assert not app.exception
    next(w for w in app.text_input if w.label == "Vị trí, công ty hoặc kỹ năng").set_value("no-such-role").run()
    assert not app.exception
