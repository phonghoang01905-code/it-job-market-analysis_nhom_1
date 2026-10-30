from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from data_ana.alerts import send_alert
from data_ana.crawl import crawl, load_config, merge_posts, today, write_csv, write_daily_json
from data_ana.etl import run_etl, write_json
from data_ana.locking import single_instance
from data_ana.logging_config import configure_logging

logger = logging.getLogger(__name__)


def add_arguments(parser):
    parser.add_argument("--config", type=Path, default=Path("config/sites.example.json"))
    parser.add_argument("--sources", nargs="+")
    parser.add_argument("--max-pages", type=int, help="Override per-site page limits")
    parser.add_argument("--max-jobs", type=int, help="Override per-site unique job limits")
    parser.add_argument("--raw", type=Path, default=Path("data/raw/jobs.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--log-dir", type=Path, default=Path("logs"))
    parser.add_argument("--skip-crawl", action="store_true", help="Xử lý dữ liệu đã lưu, không gọi website")
    parser.add_argument("--skip-db", action="store_true", help="Chỉ crawl + làm sạch, không nạp DB")


def run_pipeline(args) -> int:
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "status": "running", "sources": {}}
    try:
        logger.info("Bắt đầu pipeline")
        if not args.skip_db and not os.getenv("DATABASE_URL"):
            raise ValueError("Thiếu DATABASE_URL. Cấu hình .env/GitHub Secrets hoặc dùng --skip-db.")
        if not args.skip_crawl:
            config = load_config(args.config)
            if args.max_pages is not None and args.max_pages < 1:
                raise ValueError("--max-pages phải >= 1")
            known = {s["name"] for s in config["sites"]}
            if args.sources and set(args.sources) - known:
                raise ValueError("Tên nguồn không có trong cấu hình")
            sites = [s for s in config["sites"] if s["name"] in args.sources] if args.sources else [s for s in config["sites"] if s.get("enabled")]
            if not sites:
                raise ValueError("Không có nguồn được bật")
            if getattr(args, "max_jobs", None) is not None:
                sites = [dict(s, max_jobs=args.max_jobs) for s in sites]
            posts = []
            statuses = report["sources"]
            for site in sites:
                try:
                    collected = crawl({**config, "sites": [dict(site, enabled=True)]}, args.max_pages, statuses=statuses)
                    posts.extend(collected)
                    if collected:
                        write_daily_json(collected, args.raw.parent / f"{today()}_{site['name']}.json", site["name"])
                except Exception:
                    logger.exception("Lỗi nguồn %s", site["name"])
                    statuses[site["name"]] = {"status": "error", "message": "Lỗi xử lý nguồn; xem pipeline.log", "collected": 0, "attempted_at": datetime.now(timezone.utc).isoformat()}
            status_path = args.raw.parent / "crawl_status.json"
            old_statuses = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
            old_statuses.update(statuses)
            write_json(status_path, old_statuses)
            if posts:
                write_csv(merge_posts(posts, args.raw), args.raw)
                logger.info("Đã lưu %s tin mới/thu thập lại", len(posts))
            elif not args.raw.exists():
                raise RuntimeError("Không crawl được tin và chưa có dữ liệu cũ để xử lý")
        # Even a partial crawl can load valid existing data. The final exit code
        # still marks the partial run as a failure for the scheduler/Actions.
        report["etl"] = run_etl(args.raw, args.out_dir,
            usd_vnd_rate=os.getenv("USD_VND_RATE", "25000"),
            database_url=None if args.skip_db else os.getenv("DATABASE_URL", ""))
        incomplete = any(s.get("status") != "ok" for s in report["sources"].values())
        incomplete = incomplete or report["etl"]["rejected"] > 0
        report["status"] = "partial" if incomplete else "ok"
        logger.info("Kết quả ETL: %s", report["etl"])
    except Exception:
        report["status"] = "error"
        report["message"] = "Pipeline lỗi; xem logs/pipeline.log để biết chi tiết"
        logger.exception("Pipeline không hoàn tất")
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    if report["status"] != "ok":
        summary = {s: item.get("status") for s, item in report["sources"].items()}
        report["alerts"] = send_alert(f"IT Job Market: {report['status']}\nNguồn: {summary}\nKết thúc: {report['finished_at']}\nXem pipeline.log và latest_run.json.")
    write_json(args.log_dir / "latest_run.json", report)
    logger.info("Kết thúc pipeline: %s", report["status"])
    return 0 if report["status"] == "ok" else 1


def execute(args) -> int:
    load_dotenv()
    configure_logging(args.log_dir)
    lock = single_instance(args.log_dir / "pipeline.lock")
    try:
        lock.__enter__()
    except OSError:
        logger.warning("Đã có pipeline khác đang chạy; bỏ qua lần chạy trùng")
        return 2
    try:
        return run_pipeline(args)
    finally:
        lock.__exit__(None, None, None)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Crawl → ETL → PostgreSQL → báo cáo/cảnh báo")
    add_arguments(parser)
    return execute(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
