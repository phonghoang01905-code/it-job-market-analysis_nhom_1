"""Fetch supplementary information for existing jobs without adding new listings."""
from __future__ import annotations

import argparse
import hashlib
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from data_ana.crawl import load_config, make_session, load_robots_parser, merge_posts, write_csv, write_daily_json, today
from data_ana.etl import write_json
from data_ana.sources import enrich_detail
from data_ana.logging_config import configure_logging

logger = logging.getLogger("data_ana.enrichment")


def main():
    parser = argparse.ArgumentParser(description="Bổ sung kỹ năng, ngoại ngữ, phúc lợi cho các tin đã lưu")
    parser.add_argument("--input", type=Path, default=Path("data/raw/jobs.csv"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--config", type=Path, default=Path("config/sites.example.json"))
    parser.add_argument("--sources", nargs="+")
    parser.add_argument("--limit", type=int, help="Giới hạn số tin mỗi website")
    parser.add_argument("--refresh", action="store_true", help="Bỏ qua HTML đã lưu và đọc lại website")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit phải >= 1")
    configure_logging(Path("logs/enrichment") / ("_".join(args.sources) if args.sources else "all"))
    config = load_config(args.config)
    site_map = {s["name"]: s for s in config["sites"]}
    if args.sources and set(args.sources) - set(site_map):
        parser.error("Nguồn không có trong cấu hình")
    posts = merge_posts([], args.input)
    output = args.output or args.input
    agent = config.get("request", {}).get("user_agent", "DataAnaStudentProject/1.3")
    timeout = int(config.get("request", {}).get("timeout_seconds", 20))
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "sources": {}}
    for name, site in site_map.items():
        if args.sources and name not in args.sources:
            continue
        selected = sorted([p for p in posts if p.source == name], key=lambda p: p.scraped_at, reverse=True)
        if args.limit:
            selected = selected[:args.limit]
        status = {"total": len(selected), "fetched": 0, "cached": 0, "unavailable": 0, "errors": []}
        report["sources"][name] = status
        session = make_session(int(config.get("request", {}).get("retries", 2)))
        session.headers.update({"User-Agent": agent})
        robots = load_robots_parser(session, site["robots_url"], timeout)
        delay = float(site.get("delay_seconds", config.get("request", {}).get("delay_seconds", 4)))
        last_request = time.monotonic()
        cache_dir = Path("outputs/detail_cache") / name
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            for index, post in enumerate(selected, 1):
                cache = cache_dir / (hashlib.sha256(post.url.encode()).hexdigest() + ".html")
                try:
                    if cache.exists() and not args.refresh:
                        html = cache.read_text(encoding="utf-8")
                        if not enrich_detail(post, html, site.get("detail_selectors", {})):
                            raise ValueError("HTML lưu trước đó không có nội dung việc làm")
                        status["cached"] += 1
                    else:
                        if robots is None or not robots.can_fetch(agent, post.url):
                            raise ValueError("Không đọc được hoặc không được robots.txt cho phép")
                        time.sleep(max(0, delay-(time.monotonic()-last_request)))
                        try:
                            response = session.get(post.url, timeout=timeout)
                        finally:
                            last_request = time.monotonic()
                        response.raise_for_status()
                        if not enrich_detail(post, response.text, site.get("detail_selectors", {})):
                            raise ValueError("Trang không có nội dung việc làm đọc được")
                        cache.write_text(response.text, encoding="utf-8")
                        status["fetched"] += 1
                    logger.info("%s %s/%s: phụ trợ=%s, ngoại ngữ=%s, phúc lợi=%s", name, index, len(selected), len(post.supplementary_skills), len(post.foreign_languages), bool(post.benefits))
                except (requests.RequestException, ValueError) as exc:
                    status["unavailable"] += 1
                    code = exc.response.status_code if isinstance(exc, requests.HTTPError) and exc.response is not None else None
                    status["errors"].append({"url": post.url, "status": code, "reason": str(exc)})
                    logger.warning("Không đọc được %s: %s", post.url, exc)
                    if code in (403, 429) or robots is None:
                        break
                if index % 10 == 0:
                    write_csv(posts, output)
                    write_json(output.parent / "enrichment_report.json", report)
        finally:
            session.close()
        status.update(with_benefits=sum(bool(p.benefits) for p in selected), with_foreign_languages=sum(bool(p.foreign_languages) for p in selected), with_supplementary_skills=sum(bool(p.supplementary_skills) for p in selected))
        status["pending"] = max(0, status["total"]-status["fetched"]-status["cached"]-status["unavailable"])
        status["status"] = "partial" if status["unavailable"] or status["pending"] else "ok"
        write_daily_json(selected, output.parent / f"{today()}_{name}_profile.json", name)
    write_csv(posts, output)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["status"] = "partial" if any(s["status"] != "ok" for s in report["sources"].values()) else "ok"
    write_json(output.parent / "enrichment_report.json", report)
    logger.info("Đã lưu dữ liệu bổ sung vào %s", output)
    return 1 if report["status"] == "partial" else 0


if __name__ == "__main__":
    raise SystemExit(main())
