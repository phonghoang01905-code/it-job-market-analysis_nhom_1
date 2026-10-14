from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from urllib import robotparser

import requests
from bs4 import BeautifulSoup

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
    "skills",
    "url",
    "scraped_at",
]


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def robots_allows(robots_url: str, user_agent: str, target_url: str) -> bool:
    parser = robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except Exception:
        return False
    return parser.can_fetch(user_agent, target_url)


def text_from(card: BeautifulSoup, selector: str) -> str:
    element = card.select_one(selector)
    return clean_text(element.get_text(" ", strip=True)) if element else ""


def list_from(card: BeautifulSoup, selector: str) -> list[str]:
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
        context = " ".join([title, company, location, salary_text, " ".join(skill_labels)])
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
                skills=sorted(set(skill_labels + extract_skills(context))),
                url=absolute_url(site["base_url"], href),
            )
        )

    return posts


def crawl(config: dict) -> list[JobPost]:
    request_config = config.get("request", {})
    user_agent = request_config.get("user_agent", "DataAnaStudentProject/1.0")
    delay = float(request_config.get("delay_seconds", 2.5))
    timeout = int(request_config.get("timeout_seconds", 20))
    headers = {"User-Agent": user_agent}
    posts: list[JobPost] = []

    for site in config.get("sites", []):
        if not site.get("enabled", False):
            continue

        for url in site.get("list_urls", []):
            if not robots_allows(site["robots_url"], user_agent, url):
                print(f"Skip {url}: robots.txt does not allow this crawler.")
                continue

            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            posts.extend(parse_cards(response.text, site))
            time.sleep(delay)

    return posts


def write_csv(posts: list[JobPost], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for post in posts:
            writer.writerow(post.to_row())


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl public IT job listings.")
    parser.add_argument("--config", type=Path, default=Path("config/sites.json"))
    parser.add_argument("--out", type=Path, default=Path("data/raw/jobs.csv"))
    args = parser.parse_args()

    config = load_config(args.config)
    posts = crawl(config)
    write_csv(posts, args.out)
    print(f"Saved {len(posts)} rows to {args.out}")


if __name__ == "__main__":
    main()

