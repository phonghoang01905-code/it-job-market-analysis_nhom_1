from pathlib import Path
import sys

import pandas as pd
from streamlit.testing.v1 import AppTest


def test_cv_demo_parse_review_rank_stale_input_and_clear(tmp_path, monkeypatch):
    path = tmp_path / "jobs.csv"
    pd.DataFrame([
        {"source": "itviec", "title": "Python Developer", "company": "Python Team", "skills": "Python;SQL;PostgreSQL;JavaScript;Docker;Git;AWS", "requirements": "Python, SQL, PostgreSQL, JavaScript, Docker, Git, AWS. At least 2 years of experience. English IELTS 6.5 required.", "url": "https://example.com/python"},
        {"source": "topdev", "title": "Java Developer", "company": "Java Team", "skills": "Java;Angular", "requirements": "Java and Angular required. At least 4 years of experience building enterprise services.", "url": "https://example.com/java"},
    ]).to_csv(path, index=False)
    monkeypatch.setattr(sys, "argv", ["dashboard", "--data", str(path)])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "src/data_ana/dashboard.py"), default_timeout=40).run()
    assert not app.exception
    assert any(tab.label == "CV → Việc làm phù hợp" for tab in app.tabs)
    next(b for b in app.button if b.label == "Dùng CV minh họa").click().run()
    assert not app.exception
    next(b for b in app.button if b.label == "Đọc CV").click().run()
    assert not app.exception
    skills = next(w for w in app.multiselect if w.label == "Kỹ năng chuyên môn trong hồ sơ")
    assert "Python" in skills.value
    next(b for b in app.button if b.label == "Xếp hạng việc làm phù hợp").click().run()
    assert not app.exception
    tables = [t.value for t in app.dataframe if "Điểm khớp /100" in t.value.columns]
    assert tables and tables[0].iloc[0]["Công ty"] == "Python Team"
    assert tables[0].iloc[0]["Ưu tiên"] == "Cao"
    # Editing a CV cannot leave the old high rating visible.
    next(w for w in app.text_area if w.label == "Nội dung CV").set_value("A different CV with Java and Angular and 4 years of experience.").run()
    assert not app.exception
    assert not [t for t in app.dataframe if "Điểm khớp /100" in t.value.columns]
    next(b for b in app.button if b.label == "Xóa CV và kết quả trong phiên").click().run()
    assert not app.exception
    assert "cv_detected" not in app.session_state
