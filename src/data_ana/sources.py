"""Adapters for public job pages, without authentication or private APIs."""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from data_ana.models import JobPost
from data_ana.languages import refresh_languages
from data_ana.job_profile import refresh_profile
from data_ana.utils import clean_text, extract_skills, infer_level, infer_work_model, parse_salary_vnd


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def html_text(value: str) -> str:
    return clean_text(BeautifulSoup(value, "lxml").get_text(" ", strip=True))


def benefits_text(value) -> str:
    if isinstance(value, list):
        parts = [benefits_text(item) for item in value]
        return "\n".join(dict.fromkeys(p for p in parts if p))
    if isinstance(value, dict):
        return benefits_text(value.get("value") or value.get("description") or value.get("name") or "")
    if not isinstance(value, str) or not value:
        return ""
    if not re.search(r"</?[A-Za-z][^>]*>", value):
        return "\n".join(clean_text(line) for line in value.splitlines() if clean_text(line))
    soup = BeautifulSoup(value, "lxml")
    leaves = [li for li in soup.select("li") if li.find("li") is None]
    blocks = leaves or soup.select("p")
    return "\n".join(dict.fromkeys(clean_text(b.get_text(" ", strip=True)) for b in blocks if clean_text(b.get_text(" ", strip=True)))) if blocks else clean_text(soup.get_text(" ", strip=True))


def heading_block(heading):
    return heading.find_parent(class_="paragraph") or heading.find_parent(class_="box-job-information-detail-item") or heading.parent


def without_heading(heading) -> str:
    text = clean_text(heading_block(heading).get_text(" ", strip=True))
    prefix = clean_text(heading.get_text(" ", strip=True))
    return text[len(prefix):].strip() if text.startswith(prefix) else text


def structured_jobs(soup: BeautifulSoup) -> list[dict]:
    jobs = []

    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            if value.get("@type") == "JobPosting":
                jobs.append(value)
            visit(value.get("@graph", []))

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.get_text())
            if isinstance(payload, str):
                payload = json.loads(payload)
            visit(payload)
        except (ValueError, TypeError):
            continue
    return jobs


def nextjs_chunks(soup: BeautifulSoup) -> list[str]:
    chunks = []
    decoder = json.JSONDecoder()
    for script in soup.select("script"):
        text = script.get_text()
        for match in re.finditer(r"self\.__next_f\.push\(", text):
            try:
                payload, _ = decoder.raw_decode(text, match.end())
                if len(payload) > 1 and payload[0] == 1 and isinstance(payload[1], str):
                    chunks.append(payload[1])
            except (ValueError, TypeError):
                continue
    return chunks


def topdev_text_references(soup: BeautifulSoup) -> dict[str, str]:
    """Resolve public HTML text records, whose length is measured in UTF-8 bytes."""
    stream = "".join(nextjs_chunks(soup)).encode("utf-8")
    texts = {}
    for match in re.finditer(rb"([0-9a-f]+):T([0-9a-f]+),", stream):
        length = int(match.group(2), 16)
        end = match.end() + length
        if end <= len(stream):
            try:
                texts[match.group(1).decode()] = stream[match.end():end].decode("utf-8")
            except UnicodeDecodeError:
                continue
    return texts


def topdev_metadata(soup: BeautifulSoup) -> dict[str, dict]:
    """Read category metadata embedded in the public server-rendered page."""
    chunks = nextjs_chunks(soup)
    decoder = json.JSONDecoder()
    records = {}

    def visit(value):
        if isinstance(value, dict):
            if "job_category_id" in value and "title" in value and "id" in value:
                records[str(value["id"])] = value
                return
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    # A record can span multiple transport chunks; complete independent chunks
    # also work when a preceding length-prefixed text record has no newline.
    for stream in ["".join(chunks), *chunks]:
        for match in re.finditer(r"(?:^|\n)[0-9a-f]+:", stream):
            try:
                payload, _ = decoder.raw_decode(stream, match.end())
                visit(payload)
            except ValueError:
                continue
    return records


def parse_topdev(html: str, site: dict) -> list[JobPost]:
    soup = BeautifulSoup(html, "lxml")
    metadata = topdev_metadata(soup)
    posts = {}
    for link in soup.select('a[href^="/detail-jobs/"]'):
        url = canonical_url(urljoin(site["base_url"], link["href"]))
        match = re.search(r"-(\d+)$", url)
        if not match:
            continue
        job_id = match.group(1)
        data = metadata.get(job_id, {})
        # The old IT landing page now includes non-IT jobs. Fail closed if the
        # current page no longer provides the category needed to identify IT.
        if data.get("job_category_id") != site.get("it_category_id", 1):
            continue
        card = link.find_parent("div", class_=lambda value: value and "text-card-foreground" in value)
        if card is None:
            continue
        title = clean_text(link.get_text(" ", strip=True))
        salary = card.select_one('span[class*="text-[#e4007f]"]')
        salary_text = clean_text(salary.get_text(" ", strip=True)) if salary else ""
        location = card.select_one('div[class*="grid-cols-2"] span.line-clamp-1')
        skills = [clean_text(a.get_text(" ", strip=True)) for a in card.select('a[href^="/jobs/search?keyword="]')]
        context = " ".join([title, data.get("job_types_str", ""), " ".join(skills)])
        salary_min, salary_max = parse_salary_vnd(salary_text)
        posts[url] = JobPost(
            source=site["name"], title=title,
            company=clean_text(data.get("company", {}).get("display_name", "")),
            location=clean_text(location.get_text(" ", strip=True)) if location else "",
            salary_text=salary_text, salary_min=salary_min, salary_max=salary_max,
            level=infer_level(title + " " + data.get("job_levels_str", "")),
            work_model=infer_work_model(data.get("job_types_str", "")),
            skills=sorted(set(skills + extract_skills(context))),
            posted_date=clean_text(data.get("published", {}).get("date", "")),
            job_id=job_id, url=url,
        )
    for post in posts.values():
        refresh_languages(post)
        refresh_profile(post)
    return list(posts.values())


def enrich_detail(post: JobPost, html: str, selectors: dict) -> bool:
    soup = BeautifulSoup(html, "lxml")
    jobs = structured_jobs(soup)
    recognized = bool(jobs)
    if jobs:
        # JobPosting belongs to this detail page; salary fields are deliberately
        # not used because these sites can require sign-in to reveal salary.
        data = jobs[0]
        post.description = html_text(str(data.get("description") or ""))
        post.posted_date = str(data.get("datePosted") or post.posted_date)
        benefit = benefits_text(data.get("jobBenefits"))
        if benefit:
            post.benefits = benefit
        skills = data.get("skills") or []
        if isinstance(skills, str):
            skills = re.split(r"[,;]", skills)
        post.skills = sorted(set(post.skills + [clean_text(s) for s in skills if isinstance(s, str) and clean_text(s)]))
    if not post.description:
        for selector in selectors.get("description", "").split(","):
            if selector.strip():
                elements = soup.select(selector.strip())
                if elements:
                    post.description = clean_text(" ".join(e.get_text(" ", strip=True) for e in elements))
                    recognized = True
                    break
    # Prefer the actual requirement section over general company/benefit text.
    for heading in soup.select("h2, h3"):
        title = clean_text(heading.get_text(" ", strip=True)).casefold()
        if title in {"your skills and experience", "yêu cầu ứng viên", "yêu cầu công việc", "requirements", "job requirements"}:
            post.requirements = without_heading(heading)
            recognized = True
            break
    for heading in soup.select("h2, h3"):
        title = clean_text(heading.get_text(" ", strip=True)).casefold().rstrip(":")
        if title in {"why you'll love working here", "why you’ll love working here", "why you will love working here", "quyền lợi", "quyền lợi được hưởng", "phúc lợi", "benefits", "benefits for you"}:
            if not post.benefits:
                post.benefits = benefits_text(str(heading_block(heading)))
            recognized = True
            break
    if post.source == "topdev":
        metadata = topdev_metadata(soup).get(post.job_id, {})
        references = topdev_text_references(soup)
        def resolve(value):
            if isinstance(value, str):
                reference = re.fullmatch(r"\$([0-9a-f]+)", value)
                return references.get(reference.group(1), "") if reference else value
            if isinstance(value, list):
                return [resolve(item) for item in value]
            if isinstance(value, dict):
                return {key: resolve(item) for key, item in value.items()}
            return value
        if not post.requirements:
            value = resolve(metadata.get("requirements_original", ""))
            post.requirements = benefits_text(value)
        if not post.benefits:
            post.benefits = benefits_text(resolve(metadata.get("benefits_original") or metadata.get("benefits_v2") or []))
        recognized = recognized or bool(metadata)
    post.skills = sorted(set(post.skills + extract_skills(post.description + " " + post.requirements)))
    refresh_languages(post)
    refresh_profile(post)
    return recognized
