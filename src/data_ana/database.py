from __future__ import annotations

from importlib.resources import files

import psycopg


def connect(database_url: str):
    if not database_url:
        raise ValueError("Thiếu DATABASE_URL. Điền trong .env hoặc dùng --no-db để chỉ làm sạch.")
    return psycopg.connect(database_url, connect_timeout=10)


def initialize(connection) -> None:
    connection.execute(files("data_ana").joinpath("schema.sql").read_text(encoding="utf-8"))


def load_incremental(jobs: list[dict], database_url: str) -> dict:
    counts = {"inserted": 0, "skipped": 0}
    # One transaction for schema + all four tables. Any failure rolls back.
    with connect(database_url) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(78219051)")
        initialize(connection)
        for job in jobs:
            existing = connection.execute(
                "SELECT id FROM jobs WHERE source = %s AND (source_job_id = %s OR url = %s) LIMIT 1",
                (job["source"], job["job_id"] or None, job["url"] or None),
            ).fetchone()
            if existing:
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
            for skill in job["skills"]:
                connection.execute("INSERT INTO skills (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (skill,))
                skill_id = connection.execute("SELECT id FROM skills WHERE name = %s", (skill,)).fetchone()[0]
                connection.execute("INSERT INTO job_skills (job_id, skill_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (row[0], skill_id))
            counts["inserted"] += 1
    return counts
