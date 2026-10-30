import json
from dataclasses import asdict
from pathlib import Path

import requests

from data_ana.crawl import crawl, make_page_url, merge_posts, parse_cards, write_csv
from data_ana.models import JobPost
from data_ana.sources import enrich_detail, parse_topdev


ROOT = Path(__file__).resolve().parents[1]


def config_site(name):
    config = json.loads((ROOT / "config/sites.example.json").read_text(encoding="utf-8"))
    return next(site for site in config["sites"] if site["name"] == name)


def test_itviec_extracts_company_location_model_and_correct_job_link():
    html = '''<div class="job-card" data-job-key="id-1">
    <a href="/companies/acme"><img></a>
    <div class="ipy-2"><div><span class="small-text">Posted 2 hours ago</span></div></div>
    <h3><a href="/it-jobs/python-dev-123?tracking=abc">Python Developer</a></h3>
    <span class="small-text"><a href="/companies/acme">Acme</a></span>
    <div class="salary">Sign in to view salary</div>
    <div class="text-rich-grey flex-shrink-0">Hybrid</div>
    <div class="text-truncate" title="Ha Noi">Ha Noi</div>
    <a data-responsive-tag-list-target="tag">Python</a></div>'''
    post, = parse_cards(html, config_site("itviec"))
    assert (post.company, post.location, post.work_model) == ("Acme", "Ha Noi", "Hybrid")
    assert post.url == "https://itviec.com/it-jobs/python-dev-123"
    assert post.posted_date == "Posted 2 hours ago"
    assert post.salary_min is None and post.salary_max is None


def topdev_html():
    jobs = [
        {"id": 1, "title": "Python Dev", "job_category_id": 1, "company": {"display_name": "Acme"}, "job_types_str": "Trực tiếp", "published": {"date": "28-10-2026"}},
        {"id": 2, "title": "Sales", "job_category_id": 14},
    ]
    record = '15:' + json.dumps({"jobs": jobs}, ensure_ascii=True) + '\n'
    # Next can split a JSON record across script chunks.
    transport = "".join(f'<script>self.__next_f.push({json.dumps([1, chunk])})</script>' for chunk in [record[:32], record[32:]])
    cards = "".join(f'''<div class="text-card-foreground">
        <a href="/detail-jobs/role-{i}">{title}</a>
        <span class="text-[#e4007f]">Login to view salary</span>
        <div class="grid-cols-2"><span class="line-clamp-1">Hồ Chí Minh</span></div>
        <a href="/jobs/search?keyword=Python">Python</a></div>''' for i, title in [(1, "Python Dev"), (2, "Sales")])
    return cards + transport


def test_topdev_only_keeps_visible_it_cards_and_handles_split_metadata():
    post, = parse_topdev(topdev_html(), config_site("topdev"))
    assert post.title == "Python Dev"
    assert post.company == "Acme"
    assert post.location == "Hồ Chí Minh"
    assert post.work_model == "Onsite"
    assert post.posted_date == "28-10-2026"
    assert post.salary_min is None and post.salary_max is None
    assert parse_topdev('<a href="/detail-jobs/role-1">Unknown category</a>', config_site("topdev")) == []


def test_detail_uses_jobposting_description_and_keeps_hidden_salary_unknown():
    post = JobPost(source="topdev", title="Python Dev")
    job = {"@type": "JobPosting", "description": "<p>Build <b>Python</b> services</p>", "datePosted": "2026-10-28", "skills": "Python, Docker", "baseSalary": {"value": 100000000}}
    html = '<script type="application/ld+json">' + json.dumps({"@graph": [job]}) + '</script>'
    enrich_detail(post, html, {})
    assert post.description == "Build Python services"
    assert post.posted_date == "2026-10-28"
    assert "docker" in {skill.lower() for skill in post.skills}
    assert post.salary_min is None and post.salary_max is None


def test_merge_preserves_other_sites_and_existing_description(tmp_path):
    path = tmp_path / "jobs.csv"
    original = [JobPost(source="topcv", title="Original", url="https://www.topcv.vn/job/1?a=1"), JobPost(source="itviec", title="Dev", description="Old description", url="https://itviec.com/it-jobs/1")]
    write_csv(original, path)
    fresh = JobPost(source="itviec", title="Refreshed", url="https://itviec.com/it-jobs/1?new=1")
    merged = merge_posts([fresh], path)
    assert len(merged) == 2
    assert merged[0].title == "Original"
    assert merged[1].title == "Refreshed" and merged[1].description == "Old description"
    write_csv(merged, path)
    assert [asdict(p) for p in merge_posts([], path)] == [asdict(p) for p in merged]


def test_429_on_one_source_does_not_prevent_next_source(monkeypatch):
    from data_ana import crawl as module

    class FakeSession:
        headers = {}

        def get(self, url, timeout):
            response = requests.Response()
            response.url = url
            response.status_code = 429 if "first" in url else 200
            response._content = b'<article><h3>Developer</h3><a href="/job/1">Open</a></article>'
            return response

        def close(self):
            pass

    class Robots:
        def can_fetch(self, *args):
            return True

    monkeypatch.setattr(module, "make_session", lambda retries: FakeSession())
    monkeypatch.setattr(module, "load_robots_parser", lambda *args: Robots())
    selectors = {"card": "article", "title": "h3", "url": "a", "company": "", "location": "", "salary": "", "skills": ""}
    sites = [dict(name=name, enabled=True, base_url=f"https://{name}.example", robots_url="unused", list_urls=[f"https://{name}.example/jobs"], selectors=selectors) for name in ["first", "second"]]
    statuses = {}
    posts = crawl({"request": {"delay_seconds": 0}, "sites": sites}, statuses=statuses)
    assert [p.source for p in posts] == ["second"]
    assert statuses["first"]["status"] == "error"
    assert statuses["second"]["status"] == "ok"


def test_pagination_retains_filters():
    assert make_page_url("https://topdev.vn/jobs/search?keyword=Python", 2) == "https://topdev.vn/jobs/search?keyword=Python&page=2"


def test_crawl_target_counts_unique_jobs_across_pages(monkeypatch):
    from data_ana import crawl as module
    pages = {
        "https://jobs.example/list": '<article data-job-id="1"><h3>One</h3><a href="/1"></a></article><article data-job-id="1"><h3>One</h3><a href="/1"></a></article><article data-job-id="2"><h3>Two</h3><a href="/2"></a></article>',
        "https://jobs.example/list?page=2": '<article data-job-id="2"><h3>Two</h3><a href="/changed-slug"></a></article><article data-job-id="3"><h3>Three</h3><a href="/3"></a></article><article data-job-id="4"><h3>Four</h3><a href="/4"></a></article>',
    }
    calls = []
    class Session:
        headers = {}
        def get(self, url, timeout):
            calls.append(url)
            response = requests.Response()
            response.status_code = 200
            response._content = pages[url].encode()
            return response
        def close(self):
            pass
    class Robots:
        def can_fetch(self, *args):
            return True
    monkeypatch.setattr(module, "make_session", lambda retries: Session())
    monkeypatch.setattr(module, "load_robots_parser", lambda *args: Robots())
    selectors = {"card": "article", "title": "h3", "url": "a", "company": "", "location": "", "salary": "", "skills": ""}
    config = {"request": {"delay_seconds": 0}, "sites": [{"name": "test", "enabled": True, "base_url": "https://jobs.example", "robots_url": "unused", "list_urls": ["https://jobs.example/list"], "max_pages": 4, "max_jobs": 3, "selectors": selectors}]}
    statuses = {}
    posts = module.crawl(config, statuses=statuses)
    assert [p.job_id for p in posts] == ["1", "2", "3"]
    assert len(calls) == 2
    assert statuses["test"]["status"] == "ok"


def test_topdev_requirements_resolve_public_utf8_text_reference():
    from data_ana.sources import enrich_detail
    requirement = "<p>Yêu cầu: Python3 và C++17, ưu tiên JavaScript.</p>"
    job = {"id": 123, "title": "Developer", "job_category_id": 1, "requirements_original": "$2f"}
    props = '15:' + json.dumps({"job": job}) + '\n'
    record = f"2f:T{len(requirement.encode('utf-8')):x}," + requirement
    html = ''.join('<script>self.__next_f.push(' + json.dumps([1, s]) + ')</script>' for s in [props, record[:19], record[19:]])
    post = JobPost(source="topdev", title="Developer", job_id="123")
    enrich_detail(post, html, {})
    assert post.requirements == "Yêu cầu: Python3 và C++17, ưu tiên JavaScript."
    assert post.programming_languages == ["C++", "JavaScript", "Python"]
    assert post.language_evidence["Python"]["source"] == "Yêu cầu ứng viên"
