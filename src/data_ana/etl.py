"""Clean raw snapshots and incrementally load PostgreSQL."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from bs4 import BeautifulSoup
from dotenv import load_dotenv

from data_ana.sources import canonical_url, benefits_text
from data_ana.job_profile import extract_profile
from data_ana.languages import extract_languages
from data_ana.utils import clean_text, infer_level, infer_work_model, unaccent


SKILL_ALIASES = {
    "Python": ["python"], "Java": ["java"], "JavaScript": ["javascript", "js"],
    "TypeScript": ["typescript"], "React": ["react", "reactjs", "react.js"],
    "Vue": ["vue", "vuejs", "vue.js"], "Angular": ["angular", "angularjs"],
    "NodeJS": ["nodejs", "node.js"], ".NET": [".net", "dotnet", "asp.net"],
    "C#": ["c#", "c sharp"], "C++": ["c++"], "Go": ["golang"],
    "PHP": ["php"], "Laravel": ["laravel"], "Ruby": ["ruby"], "Rails": ["rails"],
    "SQL": ["sql"], "MySQL": ["mysql"], "PostgreSQL": ["postgresql", "postgres"],
    "SQL Server": ["sql server", "mssql"], "MongoDB": ["mongodb"], "Redis": ["redis"],
    "AWS": ["aws", "amazon web services"], "Azure": ["azure"],
    "GCP": ["gcp", "google cloud"], "Docker": ["docker"], "Kubernetes": ["kubernetes", "k8s"],
    "Linux": ["linux"], "Git": ["git"], "Terraform": ["terraform"],
    "DevOps": ["devops"], "CI/CD": ["ci/cd", "cicd"],
    "AI": ["ai", "artificial intelligence"], "Machine Learning": ["machine learning"],
    "TensorFlow": ["tensorflow"], "PyTorch": ["pytorch"], "Spark": ["spark", "pyspark"],
    "Pandas": ["pandas"], "NumPy": ["numpy"], "Power BI": ["power bi"], "Tableau": ["tableau"],
    "Flutter": ["flutter"], "Dart": ["dart"], "Kotlin": ["kotlin"], "Swift": ["swift"],
    "Android": ["android"], "iOS": ["ios"], "Selenium": ["selenium"],
    "Playwright": ["playwright"], "Jira": ["jira"], "Figma": ["figma"],
    "Agile": ["agile"], "Scrum": ["scrum"], "Business Analyst": ["business analyst"],
    "Product Owner": ["product owner"], "QA": ["qa", "qa/qc"], "Testing": ["testing", "tester"],
}
SKILL_PATTERNS = {
    name: re.compile(r"(?<![\w+#.])(?:" + "|".join(re.escape(a) for a in aliases) + r")(?![\w+#])", re.I)
    for name, aliases in SKILL_ALIASES.items()
}


def extract_normalized_skills(title: str, description: str, raw_skills) -> list[str]:
    if isinstance(raw_skills, str):
        raw_skills = raw_skills.split(";")
    if not isinstance(raw_skills, list):
        raw_skills = []
    labels = [s.strip() for s in raw_skills if isinstance(s, str) and "..." not in s and "…" not in s]
    text = " ".join([title, description, *labels])
    found = {name for name, pattern in SKILL_PATTERNS.items() if pattern.search(text)}
    # Bare English 'go' is common prose, so only accept an explicit tag or role.
    if any(s.casefold() == "go" for s in labels) or re.search(r"\bgo (?:developer|engineer|programming)\b", text, re.I):
        found.add("Go")
    return sorted(found)


def decimal_number(token: str) -> Decimal:
    token = token.replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", token):
        token = re.sub(r"[.,]", "", token)
    else:
        token = token.replace(",", ".")
    return Decimal(token)


def normalize_salary(text: str, usd_vnd_rate: Decimal) -> dict:
    result = dict(salary_currency=None, salary_period=None, salary_min_original=None,
                  salary_max_original=None, salary_min=None, salary_max=None,
                  usd_vnd_rate=usd_vnd_rate)
    value = unaccent(text)
    if not value or any(w in value for w in ["thoa thuan", "negotiable", "competitive", "canh tranh", "login", "log in", "sign in", "dang nhap"]):
        return result
    amounts = re.findall(r"\d+(?:[.,]\d+)*", value)
    if not amounts:
        return result
    usd = "$" in value or "usd" in value
    million = bool(re.search(r"trieu|\d\s*(?:m|tr)\b", value))
    if not usd and not million and not re.search(r"\bvnd\b|\bdong\b|₫|\d\s*k\b", value):
        return result
    multiplier = Decimal(1_000_000 if million else 1_000 if re.search(r"\d\s*k\b", value) else 1)
    if usd and million:
        return result  # Ambiguous mixed currency: retain raw text, no guess.
    numbers = [decimal_number(a) * multiplier for a in amounts]
    if len(numbers) > 2:
        return result
    lower, upper = (min(numbers), max(numbers)) if len(numbers) == 2 else (numbers[0], numbers[0])
    if len(numbers) == 1:
        if any(w in value for w in ["toi ", "up to", "upto", "duoi ", "under "]):
            lower = None
        elif any(w in value for w in ["tu ", "from ", "tren ", "over "]):
            upper = None
    period = "month"
    for unit, pattern in [("hour", r"/\s*(?:h\b|hour)|per hour|moi gio|/gio"), ("day", r"/\s*(?:day|ngay)|per day|moi ngay"), ("year", r"/\s*(?:year|nam)|per year|annually|moi nam")]:
        if re.search(pattern, value):
            period = unit
            break
    currency = "USD" if usd else "VND"
    result.update(salary_currency=currency, salary_period=period, salary_min_original=lower, salary_max_original=upper)
    if period in {"month", "year"}:
        factor = (usd_vnd_rate if usd else Decimal(1)) / (12 if period == "year" else 1)
        result.update(salary_min=(lower * factor).quantize(Decimal("1")) if lower is not None else None,
                      salary_max=(upper * factor).quantize(Decimal("1")) if upper is not None else None)
    return result


def normalized_city(location: str) -> str:
    value = unaccent(location)
    cities = [name for name, aliases in {
        "Hồ Chí Minh": ["ho chi minh", "hcm", "sai gon"],
        "Hà Nội": ["ha noi", "hanoi"], "Đà Nẵng": ["da nang", "danang"],
    }.items() if any(alias in value for alias in aliases)]
    return "; ".join(cities) if cities else location


def parse_posted_date(text: str) -> date | None:
    for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text.split("T")[0], pattern).date()
        except ValueError:
            pass
    return None


def normalize_job(raw: dict, rate: Decimal) -> dict:
    text_fields = ["source", "job_id", "title", "company", "location", "description", "requirements", "salary_text", "posted_date", "url", "scraped_at"]
    job = {key: clean_text(str(raw.get(key) or "")) for key in text_fields}
    job["source"] = job["source"].casefold()
    job["url"] = canonical_url(job["url"])
    if job["url"] and not re.match(r"https?://[^/\s]+", job["url"]):
        raise ValueError("Link tin không hợp lệ")
    if not job["source"] or not job["title"] or not (job["job_id"] or job["url"]):
        raise ValueError("Thiếu website, tiêu đề hoặc định danh job_id/link")
    stamp = datetime.fromisoformat(job["scraped_at"].replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("scraped_at phải có múi giờ")
    job["scraped_at"] = stamp.astimezone(timezone.utc)
    if re.search(r"</?[A-Za-z][^>]*>", job["description"]):
        job["description"] = clean_text(BeautifulSoup(job["description"], "lxml").get_text(" ", strip=True))
    job["city"] = normalized_city(job["location"])
    job["level"] = raw.get("level") if raw.get("level") not in (None, "", "Unknown") else infer_level(job["title"])
    job["work_model"] = raw.get("work_model") if raw.get("work_model") not in (None, "", "Unknown") else infer_work_model(job["title"])
    if job["work_model"] not in {"Onsite", "Remote", "Hybrid"}:
        job["work_model"] = "Unknown"
    job["posted_date_text"] = job["posted_date"]
    job["posted_date"] = parse_posted_date(job["posted_date"])
    job["skills"] = extract_normalized_skills(job["title"], job["description"] + " " + job["requirements"], raw.get("skills", []))
    job["programming_languages"], job["language_evidence"] = extract_languages(job["title"], job["description"], raw.get("skills", []), job["requirements"])
    job.update(extract_profile(job["title"], job["description"], job["requirements"], raw.get("skills", []), benefits_text(raw.get("benefits", ""))))
    job.update(normalize_salary(job["salary_text"], rate))
    return job


def read_raw(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if not {"source", "title"}.issubset(reader.fieldnames or []):
                raise ValueError("CSV phải có cột source và title")
            return list(reader)
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = payload.get("jobs") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("JSON phải là danh sách tin hoặc có mảng jobs")
    return rows


def serialize(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=serialize), encoding="utf-8")
    temp.replace(path)


def run_etl(input_path: Path, output_dir: Path, *, usd_vnd_rate=Decimal("25000"), database_url: str | None = None) -> dict:
    rate = Decimal(str(usd_vnd_rate))
    if not rate.is_finite() or rate <= 0:
        raise ValueError("USD_VND_RATE phải là số dương hữu hạn")
    rows = read_raw(input_path)
    jobs, rejected = [], []
    seen_ids, seen_urls = set(), set()
    duplicates = 0
    for index, raw in enumerate(rows, start=1):
        try:
            if not isinstance(raw, dict):
                raise ValueError("Tin không phải object")
            job = normalize_job(raw, rate)
        except (ValueError, TypeError, InvalidOperation) as exc:
            rejected.append({"row": index, "reason": str(exc)})
            continue
        id_key = (job["source"], job["job_id"])
        url_key = (job["source"], job["url"])
        if (job["job_id"] and id_key in seen_ids) or (job["url"] and url_key in seen_urls):
            duplicates += 1
            continue
        if job["job_id"]:
            seen_ids.add(id_key)
        if job["url"]:
            seen_urls.add(url_key)
        jobs.append(job)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "jobs.json", {"count": len(jobs), "jobs": jobs})
    write_json(output_dir / "rejected.json", rejected)
    temp = output_dir / "jobs.csv.tmp"
    # Always write the schema, including for an empty input.
    columns = list(jobs[0]) if jobs else ["source", "title", "company", "location", "level", "work_model", "salary_text", "salary_min", "salary_max", "skills", "url", "description", "posted_date", "scraped_at"]
    with temp.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for job in jobs:
            row = {**job, "skills": ";".join(job["skills"]), "programming_languages": ";".join(job["programming_languages"]), "language_evidence": json.dumps(job["language_evidence"], ensure_ascii=False)}
            for key in ("supplementary_skills", "foreign_languages", "benefit_tags"):
                row[key] = ";".join(job[key])
            row["profile_evidence"] = json.dumps(job["profile_evidence"], ensure_ascii=False)
            writer.writerow(row)
    temp.replace(output_dir / "jobs.csv")
    report = {"input_rows": len(rows), "clean_rows": len(jobs), "duplicates": duplicates,
              "rejected": len(rejected), "usd_vnd_rate": str(rate), "database": "skipped"}
    write_json(output_dir / "etl_report.json", report)
    if database_url is not None:
        from data_ana.database import load_incremental
        if rows and not jobs:
            raise ValueError("Không có tin hợp lệ để nạp; xem rejected.json")
        report["database"] = load_incremental(jobs, database_url)
        write_json(output_dir / "etl_report.json", report)
    return report


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Làm sạch và nạp tin mới vào PostgreSQL")
    parser.add_argument("--input", type=Path, default=Path("data/raw/jobs.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--usd-vnd", default=os.getenv("USD_VND_RATE", "25000"))
    parser.add_argument("--no-db", action="store_true", help="Chỉ làm sạch, không nạp PostgreSQL")
    args = parser.parse_args()
    report = run_etl(args.input, args.out_dir, usd_vnd_rate=args.usd_vnd,
                     database_url=None if args.no_db else os.getenv("DATABASE_URL", ""))
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
