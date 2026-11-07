from pathlib import Path
import sys

import pandas as pd
from streamlit.testing.v1 import AppTest

from test_salary_estimation import sample


def test_estimates_survive_source_filter_and_salary_analysis_keeps_provenance(tmp_path, monkeypatch):
    rows = sample()
    for row in rows:
        row["scraped_at"] = pd.Timestamp.now(tz="UTC").isoformat()
    rows[-1]["title"] = "Backend Developer Python (target)"
    path = tmp_path / "jobs.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    monkeypatch.setattr(sys, "argv", ["dashboard", "--data", str(path)])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/"src/data_ana/dashboard.py"), default_timeout=40).run()
    assert not app.exception
    next(w for w in app.multiselect if w.label == "Website tuyển dụng").set_value(["ITviec"]).run()
    assert not app.exception
    table = next(t.value for t in app.dataframe if "Mức lương" in t.value)
    assert len(table) == 1 and table.iloc[0]["Nhóm lương"] == "B · Ước tính"
    assert table.iloc[0]["Tin đối chiếu"] == 3
    assert pd.notna(table.iloc[0]["Midpoint tham khảo (VND)"])
    # The donors remain available as evidence even though their website is filtered.
    peers = next(t.value for t in app.dataframe if "Lương công khai / tháng" in t.value)
    assert len(peers) == 3
    next(r for r in app.radio if r.label == "Trang phân tích").set_value("Lương").run()
    assert not app.exception
    table = next(t.value for t in app.dataframe if "B · Ước tính" in t.value)
    assert table["Tin có lương"].gt(0).any() and table["B · Ước tính"].gt(0).any()
    next(r for r in app.radio if r.label == "Dữ liệu dùng để so sánh lương").set_value("Chỉ lương công khai").run()
    assert not app.exception
    table = next(t.value for t in app.dataframe if "B · Ước tính" in t.value)
    assert table["Tin có lương"].eq(0).all()
    next(r for r in app.radio if r.label == "Trang phân tích").set_value("Tổng quan & website").run()
    next(w for w in app.multiselect if w.label == "Nhóm dữ liệu lương").set_value(["C"]).run()
    assert not app.exception
    assert not [t for t in app.dataframe if "Mức lương" in t.value]
