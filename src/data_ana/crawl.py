from __future__ import annotations

import argparse
import csv
import json
import logging
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import robotparser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from data_ana.models import JobPost
from data_ana.languages import refresh_languages
from data_ana.job_profile import refresh_profile
from data_ana.sources import canonical_url, enrich_detail, parse_topdev
from data_ana.utils import (
    absolute_url,
    clean_text,
    extract_skills,
    infer_level,
    infer_work_model,
    parse_salary_vnd,
)


FIELDNAMES = [
    "source",
    "title",
    "company",
    "location",
    "level",
    "work_model",
    "salary_text",
    "salary_min",
    "salary_max",
    "description",
    "requirements",
    "programming_languages",
    "language_evidence",
    "supplementary_skills",
    "foreign_languages",
    "english_requirement",
    "english_status",
    "benefits",
    "benefit_tags",
    "profile_evidence",
    "posted_date",
    "job_id",
    "skills",
    "url",
    "scraped_at",
]

LOCAL_TZ = timezone(timedelta(hours=7))
logger = logging.getLogger("data_ana.crawl")


def today() -> str:
    return datetime.now(LOCAL_TZ).date().isoformat()


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def text_from(card: BeautifulSoup, selector: str) -> str:
    if not selector:
        return ""
    element = card.select_one(selector)
    return clean_text(element.get_text(" ", strip=True)) if element else ""


def list_from(card: BeautifulSoup, selector: str) -> list[str]:
    if not selector:
        return []
    return [clean_text(item.get_text(" ", strip=True)) for item in card.select(selector)]


def parse_cards(html: str, site: dict) -> list[JobPost]:
    if site.get("adapter") == "topdev":
        return parse_topdev(html, site)
    soup = BeautifulSoup(html, "lxml")
    selectors = site["selectors"]
    posts: list[JobPost] = []

    for card in soup.select(selectors["card"]):
        title = text_from(card, selectors["title"])
        if not title:
            continue

        company = text_from(card, selectors["company"])
        location = text_from(card, selectors["location"])
        salary_text = text_from(card, selectors["salary"])
        skill_labels = [s for s in list_from(card, selectors["skills"]) if "..." not in s and "…" not in s]
        link = card.select_one(selectors["url"])
        href = link.get("href") if link else ""
        description_selector = selectors.get("description", "")
        description = text_from(card, description_selector) if description_selector else ""
        posted_date = text_from(card, selectors.get("posted_date", ""))
        model = text_from(card, selectors.get("work_model", ""))
        context = " ".join(
            [title, description, " ".join(skill_labels)]
        )
        salary_min, salary_max = parse_salary_vnd(salary_text)

        posts.append(
            JobPost(
                source=site["name"],
                title=title,
                company=company,
                location=location,
                level=infer_level(context),
                work_model=infer_work_model(model or title),
                salary_text=salary_text,
                salary_min=salary_min,
                salary_max=salary_max,
                description=description,
                posted_date=posted_date,
                job_id=clean_text(card.get("data-job-id", "") or card.get("data-job-key", "")),
                skills=sorted(set(skill_labels + extract_skills(context))),
                url=canonical_url(absolute_url(site["base_url"], href)),
            )
        )

    for post in posts:
        refresh_languages(post)
        refresh_profile(post)
    return posts


def make_page_url(url: str, page: int, page_param: str = "page") -> str:
    if page <= 1:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[page_param] = str(page)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def make_session(retries: int) -> requests.Session:
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def load_robots_parser(
    session: requests.Session,
    robots_url: str,
    timeout: int,
) -> robotparser.RobotFileParser | None:
    try:
        response = session.get(robots_url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Could not read %s: %s", robots_url, exc)
        return None

    parser = robotparser.RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    return parser


def fetch_description(
    session: requests.Session,
    post: JobPost,
    site: dict,
    user_agent: str,
    robots_parser: robotparser.RobotFileParser,
    timeout: int,
) -> bool:
    detail_selectors = site.get("detail_selectors", {})
    if not post.url:
        return False
    if not robots_parser.can_fetch(user_agent, post.url):
        return False

    response = session.get(post.url, timeout=timeout)
    response.raise_for_status()
    recognized = enrich_detail(post, response.text, detail_selectors)
    if recognized:
        import hashlib
        cache = Path("outputs/detail_cache") / site["name"]
        cache.mkdir(parents=True, exist_ok=True)
        (cache / (hashlib.sha256(post.url.encode()).hexdigest() + ".html")).write_text(response.text, encoding="utf-8")
    return recognized and bool(post.description)


def crawl(
    config: dict, max_pages: int | None = None, *,
    statuses: dict | None = None,
) -> list[JobPost]:
    request_config = config.get("request", {})
    user_agent = request_config.get("user_agent", "DataAnaStudentProject/1.0")
    default_delay = float(request_config.get("delay_seconds", 2.5))
    timeout = int(request_config.get("timeout_seconds", 20))
    retries = int(request_config.get("retries", 3))
    session = make_session(retries)
    session.headers.update({"User-Agent": user_agent})
    posts: list[JobPost] = []
    statuses = statuses if statuses is not None else {}

    for site in config.get("sites", []):
        if not site.get("enabled", False):
            continue
        delay = float(site.get("delay_seconds", default_delay))
        stop_crawling = False
        site_posts: list[JobPost] = []
        seen_jobs: set[str] = set()
        seen_ids: set[str] = set()
        status = {
            "attempted_at": datetime.now(timezone.utc).isoformat(),
            "status": "running", "message": "", "pages": 0,
            "collected": 0, "with_description": 0, "detail_errors": 0,
        }
        statuses[site["name"]] = status
        logger.info("Starting %s", site["name"])
        page_limit = int(max_pages if max_pages is not None else site.get("max_pages", 1))
        if page_limit < 1:
            raise ValueError("max_pages must be at least 1")
        job_limit = site.get("max_jobs")
        if job_limit is not None:
            job_limit = int(job_limit)
            if job_limit < 1:
                raise ValueError("max_jobs must be at least 1")
        status["target_jobs"] = job_limit
        robots_parser = load_robots_parser(session, site["robots_url"], timeout)
        if robots_parser is None:
            status.update(status="blocked", message="Không đọc được robots.txt; chưa gửi request lấy tin.")
            continue
        seen_urls: set[str] = set()
        for list_url in site.get("list_urls", []):
            if not robots_parser.can_fetch(user_agent, list_url):
                logger.warning("Skip %s: robots.txt does not allow this crawler", list_url)
                status.update(status="blocked", message="robots.txt không cho phép đường dẫn danh sách.")
                continue
            time.sleep(delay)

            for page in range(1, page_limit + 1):
                url = make_page_url(list_url, page, site.get("page_param", "page"))
                if url in seen_urls:
                    break
                if not robots_parser.can_fetch(user_agent, url):
                    status.update(status="blocked", message="robots.txt không cho phép trang này.")
                    break
                seen_urls.add(url)
                try:
                    response = session.get(url, timeout=timeout)
                    response.raise_for_status()
                except requests.RequestException as exc:
                    logger.warning("Stop crawling %s: %s", url, exc)
                    status.update(status="partial" if site_posts else "error", message=str(exc))
                    stop_crawling = True
                    break
                page_posts = parse_cards(response.text, site)
                unique_page = {}
                for post in page_posts:
                    if post.url and post.url not in seen_jobs and (not post.job_id or post.job_id not in seen_ids):
                        unique_page[post.job_id or post.url] = post
                page_posts = list(unique_page.values())
                if job_limit is not None:
                    page_posts = page_posts[:max(0, job_limit - len(site_posts))]
                if not page_posts:
                    if not site_posts:
                        status.update(status="empty", message="Không tìm thấy tin IT; kiểm tra cấu trúc trang hoặc bộ lọc.")
                    break
                seen_jobs.update(p.url for p in page_posts)
                seen_ids.update(p.job_id for p in page_posts if p.job_id)
                posts.extend(page_posts)
                site_posts.extend(page_posts)
                status["pages"] += 1
                logger.info("Fetched %s jobs from page %s: %s", len(page_posts), page, url)
                time.sleep(delay)

                if site.get("fetch_descriptions", False):
                    for index, post in enumerate(page_posts, start=1):
                        try:
                            found = fetch_description(
                                session, post, site, user_agent, robots_parser, timeout
                            )
                            if not found:
                                status["detail_errors"] += 1
                                status.update(status="partial", message="Một số trang chi tiết không có mô tả đọc được hoặc bị robots.txt chặn.")
                        except requests.RequestException as exc:
                            logger.warning("Description unavailable for %s: %s", post.url, exc)
                            status["detail_errors"] += 1
                            status.update(status="partial", message=str(exc))
                            code = exc.response.status_code if exc.response is not None else None
                            if code in (403, 429):
                                logger.warning("%s limited this run; stopping this source", site["name"])
                                stop_crawling = True
                                break
                        else:
                            logger.info("Description %s/%s: %s", index, len(page_posts), "saved" if found else "unavailable")
                        time.sleep(delay)
                    if stop_crawling:
                        break
                if job_limit is not None and len(site_posts) >= job_limit:
                    break
            if stop_crawling:
                break
            if job_limit is not None and len(site_posts) >= job_limit:
                break
        status["collected"] = len(site_posts)
        status["with_description"] = sum(bool(p.description) for p in site_posts)
        status["with_requirements"] = sum(bool(p.requirements) for p in site_posts)
        status["with_programming_languages"] = sum(bool(p.programming_languages) for p in site_posts)
        if status["status"] == "running":
            status["status"] = "ok" if site_posts else "empty"
            if job_limit and 0 < len(site_posts) < job_limit:
                status.update(status="partial", message=f"Thu được {len(site_posts)}/{job_limit} tin trong giới hạn trang; không thêm tin trùng để đủ số.")

    session.close()
    return posts


def write_csv(posts: list[JobPost], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temp = out_path.with_suffix(out_path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for post in posts:
            writer.writerow(post.to_row())
    temp.replace(out_path)


def merge_posts(posts: list[JobPost], path: Path) -> list[JobPost]:
    """Keep other websites and fill missing values when refreshing an existing URL."""
    merged = {}
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                row = {key: value for key, value in row.items() if key in FIELDNAMES}
                row["skills"] = [s for s in row.get("skills", "").split(";") if s]
                row["programming_languages"] = [s for s in row.get("programming_languages", "").split(";") if s]
                row["language_evidence"] = json.loads(row.get("language_evidence") or "{}")
                for key in ("supplementary_skills", "foreign_languages", "benefit_tags"):
                    row[key] = [s for s in row.get(key, "").split(";") if s]
                row["profile_evidence"] = json.loads(row.get("profile_evidence") or "{}")
                for key in ("salary_min", "salary_max"):
                    row[key] = int(float(row[key])) if row.get(key) else None
                row["url"] = canonical_url(row.get("url", ""))
                post = JobPost(**row)
                merged[(post.source, post.url or post.job_id)] = post
    for post in posts:
        post.url = canonical_url(post.url)
        key = (post.source, post.url or post.job_id)
        previous = merged.get(key)
        if previous:
            for field in ("description", "requirements", "benefits", "posted_date", "company", "location", "job_id"):
                if not getattr(post, field):
                    setattr(post, field, getattr(previous, field))
        merged[key] = post
    for post in merged.values():
        refresh_languages(post)
        refresh_profile(post)
    return list(merged.values())


def write_daily_json(posts: list[JobPost], out_path: Path, source: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": source,
        "scraped_date": today(),
        "count": len(posts),
        "jobs": [asdict(post) for post in posts],
    }
    with out_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def main() -> None:
    from data_ana.logging_config import configure_logging
    configure_logging(Path("logs"))
    parser = argparse.ArgumentParser(description="Crawl public IT job listings.")
    parser.add_argument("--config", type=Path, default=Path("config/sites.example.json"))
    parser.add_argument("--out", type=Path, default=Path("data/raw/jobs.csv"))
    parser.add_argument("--raw-out", type=Path)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--max-jobs", type=int, help="Maximum unique jobs per source")
    parser.add_argument("--sources", nargs="+", help="Only crawl these sources, e.g. itviec topdev")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.max_jobs is not None:
        for site in config["sites"]:
            site["max_jobs"] = args.max_jobs
    if args.sources:
        names = {s["name"] for s in config["sites"]}
        if set(args.sources) - names:
            parser.error(f"Unknown sources: {set(args.sources) - names}")
        config["sites"] = [dict(s, enabled=True) for s in config["sites"] if s["name"] in args.sources]
    statuses = {}
    posts = crawl(config, max_pages=args.max_pages, statuses=statuses)
    status_path = args.out.parent / "crawl_status.json"
    old_statuses = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    old_statuses.update(statuses)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(old_statuses, ensure_ascii=False, indent=2), encoding="utf-8")
    if not posts:
        raise RuntimeError("No job posts were collected; no output files were written.")
    combined = merge_posts(posts, args.out)
    write_csv(combined, args.out)
    print(f"Saved {len(posts)} new/refreshed jobs; {len(combined)} total rows in {args.out}")
    sources = sorted({post.source for post in posts})
    source = sources[0] if len(sources) == 1 else "multiple"
    for name in sources:
        raw_out = args.out.parent / f"{today()}_{name}.json"
        write_daily_json([p for p in posts if p.source == name], raw_out, name)
        print(f"Saved raw JSON to {raw_out}")
    if args.raw_out:
        write_daily_json(posts, args.raw_out, source)


if __name__ == "__main__":
    main()

