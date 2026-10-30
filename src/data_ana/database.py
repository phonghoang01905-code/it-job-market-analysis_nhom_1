from __future__ import annotations

from importlib.resources import files

import psycopg
from psycopg.types.json import Jsonb
from data_ana.job_profile import extract_profile


def connect(database_url: str):
    if not database_url:
        raise ValueError("Thiếu DATABASE_URL. Điền trong .env hoặc dùng --no-db để chỉ làm sạch.")
    return psycopg.connect(database_url, connect_timeout=10)


def initialize(connection) -> None:
    connection.execute(files("data_ana").joinpath("schema.sql").read_text(encoding="utf-8"))


def update_profile(connection, job_id: int, job: dict, old_benefits="", old_requirements="") -> None:
    fields = ("supplementary_skills", "foreign_languages", "english_requirement", "english_status", "benefits", "benefit_tags", "profile_evidence")
    fallback = (old_benefits and not job.get("benefits")) or (old_requirements and not job.get("requirements"))
    if all(key in job for key in fields) and not fallback:
        # ETL extracted these from the original site tags, including English.
        # Normalized technical skills alone cannot reconstruct spoken languages.
        profile = {key: job[key] for key in fields}
    else:
        profile = extract_profile(job["title"], job.get("description", ""), job.get("requirements") or old_requirements,
            job.get("skills", []), job.get("benefits") or old_benefits)
    connection.execute("""UPDATE jobs SET supplementary_skills=%s, foreign_languages=%s,
        english_requirement=%s, english_status=%s, benefits=%s, benefit_tags=%s, profile_evidence=%s
        WHERE id=%s""", (profile["supplementary_skills"], profile["foreign_languages"], profile["english_requirement"],
        profile["english_status"], profile["benefits"], profile["benefit_tags"], Jsonb(profile["profile_evidence"]), job_id))


def load_incremental(jobs: list[dict], database_url: str) -> dict:
    counts = {"inserted": 0, "skipped": 0}
    # One transaction for schema + all four tables. Any failure rolls back.
    with connect(database_url) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(78219051)")
        initialize(connection)
        for job in jobs:
            existing = connection.execute(
                "SELECT id, benefits, requirements FROM jobs WHERE source = %s AND (source_job_id = %s OR url = %s) LIMIT 1",
                (job["source"], job["job_id"] or None, job["url"] or None),
            ).fetchone()
            if existing:
                # Enrich the new fields on historical jobs without overwriting
                # their existing salary, description, or original scrape time.
                connection.execute(
                    """UPDATE jobs SET programming_languages=%s, language_evidence=%s,
                       requirements=CASE WHEN %s <> '' THEN %s ELSE requirements END
                       WHERE id=%s""",
                    (job.get("programming_languages", []), Jsonb(job.get("language_evidence", {})), job.get("requirements", ""), job.get("requirements", ""), existing[0]),
                )
                update_profile(connection, existing[0], job, existing[1], existing[2])
                counts["skipped"] += 1
                continue
            company_id = None
            if job["company"]:
                key = " ".join(job["company"].casefold().split())
                connection.execute(
                    "INSERT INTO companies (name, name_key) VALUES (%s, %s) ON CONFLICT (name_key) DO NOTHING",
                    (job["company"], key),
                )
                company_id = connection.execute("SELECT id FROM companies WHERE name_key = %s", (key,)).fetchone()[0]
            values = {**job, "company_id": company_id, "source_job_id": job["job_id"] or None, "url": job["url"] or None}
            row = connection.execute(
                """INSERT INTO jobs (
                    source, source_job_id, url, title, company_id, location, city, level, work_model,
                    description, salary_text, salary_currency, salary_period, salary_min_original,
                    salary_max_original, salary_min, salary_max, usd_vnd_rate, posted_date, posted_date_text, scraped_at
                ) VALUES (
                    %(source)s, %(source_job_id)s, %(url)s, %(title)s, %(company_id)s, %(location)s,
                    %(city)s, %(level)s, %(work_model)s, %(description)s, %(salary_text)s,
                    %(salary_currency)s, %(salary_period)s, %(salary_min_original)s, %(salary_max_original)s,
                    %(salary_min)s, %(salary_max)s, %(usd_vnd_rate)s, %(posted_date)s, %(posted_date_text)s, %(scraped_at)s
                ) ON CONFLICT DO NOTHING RETURNING id""", values,
            ).fetchone()
            if not row:
                counts["skipped"] += 1
                continue
            connection.execute("UPDATE jobs SET requirements=%s, programming_languages=%s, language_evidence=%s WHERE id=%s",
                (job.get("requirements", ""), job.get("programming_languages", []), Jsonb(job.get("language_evidence", {})), row[0]))
            update_profile(connection, row[0], job)
            for skill in job["skills"]:
                connection.execute("INSERT INTO skills (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (skill,))
                skill_id = connection.execute("SELECT id FROM skills WHERE name = %s", (skill,)).fetchone()[0]
                connection.execute("INSERT INTO job_skills (job_id, skill_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (row[0], skill_id))
            counts["inserted"] += 1
    return counts
