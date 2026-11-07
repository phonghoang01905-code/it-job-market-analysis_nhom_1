"""Expand all three sources and publish only salary-qualified listings."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

import pandas as pd
from dotenv import load_dotenv

from data_ana.crawl import crawl, load_config, merge_posts, today, write_csv, write_daily_json
from data_ana.etl import run_etl, write_json
from data_ana.logging_config import configure_logging
from data_ana.salary_selection import qualify_posts

LIMITS = {
    "itviec": dict(max_pages=16, max_jobs=250),
    "topdev": dict(max_pages=20, max_jobs=250, fetch_missing_details_only=True),
    "topcv": dict(max_pages=8, max_jobs=300, max_detail_jobs=60, detail_salary_first=True),
}


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    load_dotenv()
    parser = argparse.ArgumentParser(description="Crawl mở rộng; chỉ xuất tin có lương công khai hoặc đủ căn cứ ước tính")
    parser.add_argument("--config", type=Path, default=Path("config/sites.example.json"))
    parser.add_argument("--raw", type=Path, default=Path("data/raw/jobs.csv"))
    parser.add_argument("--archive", type=Path, default=Path("data/raw/jobs_archive.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--work-dir", type=Path, default=Path("outputs/salary_collection")/today())
    parser.add_argument("--sources", nargs="+")
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--max-jobs", type=int, help="Số tin mới tối đa mỗi nguồn trước khi lọc lương")
    parser.add_argument("--no-db", action="store_true")
    parser.add_argument("--skip-crawl", action="store_true", help="Chỉ phân loại lại archive và checkpoint đã lưu")
    args = parser.parse_args(argv)
    for value in (args.max_pages, args.max_jobs):
        if value is not None and value < 1:
            parser.error("Giới hạn phải >= 1")
    config = load_config(args.config)
    names = {site["name"] for site in config["sites"]}
    if args.sources and set(args.sources)-names:
        parser.error("Tên website không có trong cấu hình")
    configure_logging(Path("logs/salary_collection"))
    args.work_dir.mkdir(parents=True, exist_ok=True)
    report = dict(started_at=datetime.now(timezone.utc).isoformat(), sources={}, status="running")
    archive = merge_posts([], args.archive if args.archive.exists() else args.raw)
    if not (args.work_dir/"before.csv").exists():
        write_csv(archive, args.work_dir/"before.csv")
    baseline = merge_posts([], args.work_dir/"before.csv")
    original_keys = {(p.source, p.job_id or p.url) for p in baseline}
    write_csv(archive, args.archive)
    sites = [s for s in config["sites"] if s["name"] in args.sources] if args.sources else [s for s in config["sites"] if s.get("enabled")]

    def worker(original):
        name = original["name"]
        path = args.work_dir/f"{name}_candidates.csv"
        if args.skip_crawl:
            status_path = path.with_suffix(".status.json")
            status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {"status": "checkpoint", "message": "Đọc lại checkpoint, không gửi request"}
            return name, merge_posts([], path), status
        site = {**original, **LIMITS.get(name, {}), "checkpoint_path": str(path)}
        if args.max_pages is not None:
            site["max_pages"] = args.max_pages
        if args.max_jobs is not None:
            site["max_jobs"] = args.max_jobs
        site["skip_known_urls"] = [p.url for p in archive if p.source == name]
        site["skip_known_ids"] = [p.job_id for p in archive if p.source == name and p.job_id]
        if name == "itviec":
            site["list_urls"] = ["https://itviec.com/it-jobs?salary_ranges%5B%5D=500&salary_ranges%5B%5D=10000&salary_ranges_changed=true", *original["list_urls"]]
        statuses = {}
        try:
            posts = crawl({**config, "request": {**config.get("request", {}), "retries": 0}, "sites": [site]}, statuses=statuses)
        except Exception as exc:
            posts = merge_posts([], path)
            statuses[name] = {"status": "error", "message": f"{type(exc).__name__}: {exc}", "collected": len(posts)}
        write_csv(posts, path)
        write_daily_json(posts, args.work_dir/f"{today()}_{name}.json", name)
        print(f"{name}: hoàn tất lượt crawl, {len(posts)} tin mới trước khi lọc lương", flush=True)
        return name, posts, statuses.get(name, {})

    fresh = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(worker, site) for site in sites]
        for future in as_completed(futures):
            name, posts, status = future.result()
            report["sources"][name] = status
            if status.get("status") == "partial" and not status.get("detail_errors") and status.get("message", "").startswith("Thu được "):
                status.update(status="ok", message=f"Đã duyệt danh sách trong giới hạn cho phép; thu thêm {len(posts)} tin. max_jobs là giới hạn trên, không phải số tin cam kết có trên website.")
            fresh.extend(posts)
            write_json(args.work_dir/"progress.json", report)
    archive = merge_posts(fresh, args.archive)
    write_csv(archive, args.archive)
    selected, assessed = qualify_posts(archive)
    if not selected:
        raise RuntimeError("Không có tin đủ tiêu chí lương; chưa thay đổi file dữ liệu chính")
    write_csv(selected, args.raw)
    # Export the audit with machine-readable values; never put estimates into
    # the observed salary_min/salary_max columns of raw data or PostgreSQL.
    audit = assessed.drop(columns=["language_evidence", "profile_evidence"], errors="ignore").copy()
    audit["salary_peers"] = audit.salary_peers.map(lambda rows: json.dumps(rows, ensure_ascii=False))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    audit.to_csv(args.out_dir/"salary_collection_audit.csv", index=False, encoding="utf-8-sig")
    for name in names:
        rows = assessed.loc[assessed.source.eq(name)]
        new_mask = pd.Series([(r.source, r.job_id or r.url) not in original_keys for r in rows.itertuples()], index=rows.index, dtype=bool)
        stats = report["sources"].setdefault(name, {"status": "not_requested"})
        stats.update(archive_rows=len(rows), qualified_total=int(rows.salary_group.isin(["A", "B"]).sum()),
                     public_total=int(rows.salary_group.eq("A").sum()), estimated_total=int(rows.salary_group.eq("B").sum()),
                     excluded_total=int(rows.salary_group.eq("C").sum()), new_candidates=int(new_mask.sum()),
                     new_qualified=int((new_mask & rows.salary_group.isin(["A", "B"])).sum()))
    report.update(finished_at=datetime.now(timezone.utc).isoformat(), archive_rows=len(archive), qualified_rows=len(selected),
                  status="complete" if all(s.get("status") in {"ok", "checkpoint", "not_requested"} for s in report["sources"].values()) else "partial")
    status_path = args.raw.parent/"crawl_status.json"
    old_statuses = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    old_statuses.update({name: state for name, state in report["sources"].items() if state.get("status") != "not_requested"})
    write_json(status_path, old_statuses)
    report["etl"] = run_etl(args.raw, args.out_dir, usd_vnd_rate=os.getenv("USD_VND_RATE", "25000"),
        database_url=None if args.no_db or not os.getenv("DATABASE_URL") else os.environ["DATABASE_URL"])
    write_json(args.out_dir/"salary_collection_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
