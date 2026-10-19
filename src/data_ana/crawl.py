from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime
from pathlib import Path
from urllib import robotparser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from data_ana.models import JobPost
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
    "posted_date",
    "job_id",
    "skills",
    "url",
    "scraped_at",
]


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
        skill_labels = list_from(card, selectors["skills"])
        link = card.select_one(selectors["url"])
        href = link.get("href") if link else ""
        description_selector = selectors.get("description", "")
        description = text_from(card, description_selector) if description_selector else ""
        posted_date = text_from(card, selectors.get("posted_date", ""))
        context = " ".join(
            [title, company, location, salary_text, description, " ".join(skill_labels)]
        )
        salary_min, salary_max = parse_salary_vnd(salary_text)

        posts.append(
            JobPost(
                source=site["name"],
                title=title,
                company=company,
                location=location,
                level=infer_level(context),
                work_model=infer_work_model(context),
                salary_text=salary_text,
                salary_min=salary_min,
                salary_max=salary_max,
                description=description,
                posted_date=posted_date,
                job_id=clean_text(card.get("data-job-id", "")),
                skills=sorted(set(skill_labels + extract_skills(context))),
                url=absolute_url(site["base_url"], href),
            )
        )

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
        print(f"Skip TopCV: could not read robots.txt ({exc}).")
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
) -> None:
    detail_selectors = site.get("detail_selectors", {})
    selector = detail_selectors.get("description", "")
    if not selector or not post.url:
        return
    if not robots_parser.can_fetch(user_agent, post.url):
        return

    response = session.get(post.url, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    for candidate_selector in selector.split(","):
        element = soup.select_one(candidate_selector.strip())
        if element:
            post.description = clean_text(element.get_text(" ", strip=True))
            if post.description:
                return


def crawl(config: dict, max_pages: int | None = None) -> list[JobPost]:
    request_config = config.get("request", {})
    user_agent = request_config.get("user_agent", "DataAnaStudentProject/1.0")
    delay = float(request_config.get("delay_seconds", 2.5))
    timeout = int(request_config.get("timeout_seconds", 20))
    retries = int(request_config.get("retries", 3))
    session = make_session(retries)
    session.headers.update({"User-Agent": user_agent})
    posts: list[JobPost] = []
    stop_crawling = False

    for site in config.get("sites", []):
        if not site.get("enabled", False):
            continue

        page_limit = int(max_pages if max_pages is not None else site.get("max_pages", 1))
        if page_limit < 1:
            raise ValueError("max_pages must be at least 1")
        robots_parser = load_robots_parser(session, site["robots_url"], timeout)
        if robots_parser is None:
            continue
        seen_urls: set[str] = set()
        for list_url in site.get("list_urls", []):
            if not robots_parser.can_fetch(user_agent, list_url):
                print(f"Skip {list_url}: robots.txt does not allow this crawler.")
                continue
            time.sleep(delay)

            for page in range(1, page_limit + 1):
                url = make_page_url(list_url, page, site.get("page_param", "page"))
                if url in seen_urls:
                    break
                seen_urls.add(url)
                try:
                    response = session.get(url, timeout=timeout)
                    response.raise_for_status()
                except requests.RequestException as exc:
                    print(f"Stop crawling {url}: {exc}", flush=True)
                    stop_crawling = "429" in str(exc)
                    break
                page_posts = parse_cards(response.text, site)
                if not page_posts:
                    break
                posts.extend(page_posts)
                print(f"Fetched {len(page_posts)} jobs from page {page}: {url}", flush=True)
                time.sleep(delay)

                if site.get("fetch_descriptions", False):
                    for index, post in enumerate(page_posts, start=1):
                        try:
                            fetch_description(
                                session, post, site, user_agent, robots_parser, timeout
                            )
                        except requests.RequestException as exc:
                            print(f"Description unavailable for {post.url}: {exc}", flush=True)
                            if "429" in str(exc):
                                print("TopCV rate limited this run; stopping detail requests.", flush=True)
                                stop_crawling = True
                                break
                        else:
                            print(f"Fetched description {index}/{len(page_posts)}", flush=True)
                        time.sleep(delay)
                    if stop_crawling:
                        break
            if stop_crawling:
                break
        if stop_crawling:
            break

    return posts


def write_csv(posts: list[JobPost], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for post in posts:
            writer.writerow(post.to_row())


def write_daily_json(posts: list[JobPost], out_path: Path, source: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": source,
        "scraped_date": datetime.now().astimezone().date().isoformat(),
        "count": len(posts),
        "jobs": [post.to_row() for post in posts],
    }
    with out_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl public IT job listings.")
    parser.add_argument("--config", type=Path, default=Path("config/sites.json"))
    parser.add_argument("--out", type=Path, default=Path("data/raw/jobs.csv"))
    parser.add_argument("--raw-out", type=Path)
    parser.add_argument("--max-pages", type=int)
    args = parser.parse_args()

    config = load_config(args.config)
    posts = crawl(config, max_pages=args.max_pages)
    if not posts:
        raise RuntimeError("No job posts were collected; no output files were written.")
    write_csv(posts, args.out)
    print(f"Saved {len(posts)} rows to {args.out}")
    sources = sorted({post.source for post in posts})
    source = sources[0] if len(sources) == 1 else "multiple"
    raw_out = args.raw_out or Path(
        f"data/raw/{datetime.now().astimezone().date().isoformat()}_{source}.json"
    )
    write_daily_json(posts, raw_out, source)
    print(f"Saved raw JSON to {raw_out}")


if __name__ == "__main__":
    main()

