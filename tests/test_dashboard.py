import sys

import pandas as pd
from streamlit.testing.v1 import AppTest


def test_language_filter_and_empty_combination_keep_dashboard_working(tmp_path, monkeypatch):
    path = tmp_path / "jobs.csv"
    pd.DataFrame([
        {"source": "topcv", "title": "Python Developer", "company": "Acme", "description": "Python3 and SQL", "url": "https://example.com/1"},
        {"source": "topdev", "title": "C++ Developer", "company": "Beta", "description": "C++17", "url": "https://example.com/2"},
    ]).to_csv(path, index=False)
    monkeypatch.setattr(sys, "argv", ["dashboard", "--data", str(path)])
    from pathlib import Path
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "src/data_ana/dashboard.py"), default_timeout=30).run()
    assert not app.exception
    app.multiselect[0].set_value(["Python"]).run()
    assert not app.exception
    for table in app.dataframe:
        if "Ngôn ngữ lập trình" in table.value:
            assert table.value["Ngôn ngữ lập trình"].str.contains("Python").all()
    app.text_input[0].set_value("no-such-job").run()
    assert not app.exception


def test_english_and_benefit_filters_show_real_profile_fields(tmp_path, monkeypatch):
    path = tmp_path / "jobs.csv"
    pd.DataFrame([
        {"source": "itviec", "title": "Python Engineer", "company": "Acme", "requirements": "English IELTS 6.5 is required. Good communication skills.", "benefits": "Health insurance. 13th month bonus.", "url": "https://example.com/1"},
        {"source": "topdev", "title": "Java Engineer", "company": "Beta", "description": "Free English classes and English speaking environment.", "benefits": "Free English classes.", "url": "https://example.com/2"},
    ]).to_csv(path, index=False)
    monkeypatch.setattr(sys, "argv", ["dashboard", "--data", str(path)])
    from pathlib import Path
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "src/data_ana/dashboard.py"), default_timeout=30).run()
    assert not app.exception
    english = next(w for w in app.selectbox if w.label == "Thông tin tiếng Anh")
    english.set_value("Yêu cầu rõ ràng").run()
    assert not app.exception
    tables = [t.value for t in app.dataframe if "Phúc lợi — nội dung gốc" in t.value.columns]
    assert tables
    assert all((table["Công ty"] == "Acme").all() for table in tables)
    benefit = next(w for w in app.multiselect if w.label == "Phúc lợi mong muốn")
    benefit.set_value(["Đào tạo ngoại ngữ"]).run()
    assert not app.exception
