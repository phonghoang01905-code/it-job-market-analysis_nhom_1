"""Read-only dashboard/report access; credentials never appear in returned data."""
from __future__ import annotations

import json
import os

import pandas as pd
from dotenv import load_dotenv
from psycopg.rows import dict_row

from data_ana.database import connect, initialize


def database_url() -> str:
    load_dotenv()
    return os.getenv("DATABASE_URL", "")


def initialize_analytics() -> None:
    with connect(database_url()) as connection:
        initialize(connection)


def read_database() -> pd.DataFrame:
    with connect(database_url()) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout = '15s'")
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT * FROM analytics_jobs ORDER BY id")
            rows = cursor.fetchall()
            columns = [column.name for column in cursor.description]
    df = pd.DataFrame(rows, columns=columns)
    df["job_id"] = df["source_job_id"].fillna("")
    for field in ["programming_languages", "supplementary_skills", "foreign_languages", "benefit_tags"]:
        df[field] = df[field].map(lambda values: "; ".join(values or []))
    for field in ["language_evidence", "profile_evidence"]:
        df[field] = df[field].map(lambda value: json.dumps(value or {}, ensure_ascii=False))
    for field in ["posted_date", "scraped_at"]:
        df[field] = df[field].map(lambda value: value.isoformat() if value else "")
    df.attrs["skills_normalized"] = True
    return df
