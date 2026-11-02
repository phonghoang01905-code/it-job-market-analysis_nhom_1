"""Reproducible EDA, tables and charts from CSV or PostgreSQL."""
from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import version
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from data_ana.analytics import prepare_jobs, summary, time_summary, skill_timeseries, skill_changes, cluster_jobs


def write_charts(tables: dict, out_dir: Path) -> list[str]:
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False})
    figures = []
    for name, dimension, title in [("skills_summary", "skill", "Kỹ năng được nhắc nhiều nhất"),
                                    ("companies_summary", "company", "Công ty có nhiều tin nhất"),
                                    ("cities_summary", "city", "Thành phố tuyển dụng")]:
        table = tables[name].head(12).iloc[::-1]
        if table.empty:
            continue
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.barh(table[dimension], table.job_count, color="#527de6")
        ax.set(title=title, xlabel="Số tin trong mẫu")
        fig.tight_layout()
        filename = name + ".png"
        fig.savefig(out_dir / filename, dpi=150)
        plt.close(fig)
        figures.append(filename)
    weekly = tables["weekly_jobs"]
    if not weekly.empty:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(weekly.period, weekly.job_count, marker="o", color="#0c9478")
        ax.set(title="Số tin/tuần theo ngày đăng chính xác", ylabel="Số tin trong mẫu", xlabel="Thứ Hai đầu tuần")
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(out_dir / "weekly_jobs.png", dpi=150)
        plt.close(fig)
        figures.append("weekly_jobs.png")
    salary = tables["salary_by_skill"].query("salary_count >= 3").sort_values("median_salary").tail(12)
    if not salary.empty:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.barh(salary.skill, salary.median_salary/1_000_000, color="#0c9478")
        ax.set(title="Trung vị midpoint khoảng lương (n ≥ 3)", xlabel="Triệu VND/tháng; không phải lương thực nhận")
        fig.tight_layout()
        fig.savefig(out_dir / "salary_by_skill.png", dpi=150)
        plt.close(fig)
        figures.append("salary_by_skill.png")
    return figures


def analyze(input_path: Path | None, out_dir: Path, *, use_database=False, k=None) -> dict:
    if use_database:
        from data_ana.data_access import read_database
        original = read_database()
    else:
        original = pd.read_csv(input_path, keep_default_na=False)
    df = prepare_jobs(original)
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = {"skills_summary": summary(df, "skill"), "companies_summary": summary(df, "company"),
              "cities_summary": summary(df, "city"), "positions_summary": summary(df, "title"),
              "salary_by_skill": summary(df, "skill"), "salary_by_level": summary(df, "level"),
              "salary_by_city": summary(df, "city"), "weekly_jobs": time_summary(df),
              "monthly_jobs": time_summary(df, frequency="month"),
              "weekly_observed": time_summary(df, basis="observed"),
              "skills_weekly": skill_timeseries(df), "skills_monthly": skill_timeseries(df, frequency="month"),
              "skill_changes": skill_changes(df)}
    assignments, clusters, cluster_info = cluster_jobs(df, k)
    tables.update(cluster_assignments=assignments, clusters=clusters)
    for name, table in tables.items():
        table.to_csv(out_dir / f"{name}.csv", index=False, encoding="utf-8-sig")
    metadata = {"generated_at": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
        "source": "PostgreSQL" if use_database else str(input_path), "jobs": len(df),
        "companies": int(df.loc[df.company_key.ne(""), "company_key"].nunique()),
        "known_cities": len({city for cities in df._cities for city in cities if city != "Chưa xác định"}),
        "sources": {str(key): int(value) for key, value in df.source.value_counts().items()},
        "salary_complete": int(df.salary_midpoint.count()), "posted_dates": int(df._date_posted.count()),
        "salary_samples_by_source": {str(key): int(value) for key, value in df.groupby("source").salary_midpoint.count().items()},
        "first_posted": str(df._date_posted.min().date()) if df._date_posted.notna().any() else None,
        "last_posted": str(df._date_posted.max().date()) if df._date_posted.notna().any() else None,
        "salary_median": float(df.salary_midpoint.median()) if df.salary_midpoint.notna().any() else None,
        "libraries": {name: version(name) for name in ["pandas", "scikit-learn"]},
        "cluster": cluster_info}
    (out_dir / "analysis_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    write_charts(tables, out_dir)
    return metadata


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="EDA + KMeans + bảng CSV và biểu đồ")
    parser.add_argument("--input", type=Path, default=Path("data/processed/jobs.csv"))
    parser.add_argument("--database", action="store_true", help="Đọc DATABASE_URL trong môi trường/.env")
    parser.add_argument("--out-dir", type=Path, default=Path("outputs/analysis"))
    parser.add_argument("--clusters", type=int, help="Bỏ trống: chọn k=2..6 theo silhouette cosine")
    args = parser.parse_args()
    try:
        result = analyze(args.input, args.out_dir, use_database=args.database, k=args.clusters)
    except Exception:
        parser.exit(1, "Phân tích chưa hoàn tất. Kiểm tra file CSV/thư viện hoặc PostgreSQL và chạy ETL để tạo analytics views.\n")
    print(f"Analyzed {result['jobs']} jobs. Tables, charts and metadata: {args.out_dir}")


if __name__ == "__main__":
    main()
