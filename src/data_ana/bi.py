"""Create read-only BI credentials and idempotently provision four Metabase dashboards."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import urlparse

from dotenv import set_key
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
import requests

from data_ana.data_access import database_url, initialize_analytics
from data_ana.database import connect

COLLECTION = "IT Job Market - Nhom 1"
DB_NAME = "IT Job Market (read-only)"

# name, SQL, display, x column, y column. Kept in code for reproducible provisioning.
DASHBOARDS = {
    "01 - Tổng quan thị trường": [
        ("Số tin", "SELECT count(*) AS jobs FROM analytics_jobs", "scalar", None, None),
        ("Số công ty", "SELECT count(DISTINCT company_id) AS companies FROM analytics_jobs", "scalar", None, None),
        ("Số thành phố đã biết", "SELECT count(*) AS cities FROM analytics_top_cities WHERE city <> 'Chưa xác định'", "scalar", None, None),
        ("Tin theo website", "SELECT source, count(*) AS jobs FROM analytics_jobs GROUP BY source ORDER BY jobs DESC", "bar", "source", "jobs"),
        ("Top thành phố", "SELECT city, job_count FROM analytics_top_cities ORDER BY job_count DESC, city LIMIT 15", "bar", "city", "job_count"),
        ("Độ đầy đủ", "SELECT count(*) AS jobs, count(posted_date) AS dated_jobs, count(salary_midpoint) AS salary_samples, max(scraped_at) AS latest_observation FROM analytics_jobs", "table", None, None)],
    "02 - Kỹ năng và xu hướng": [
        ("Top kỹ năng", "SELECT skill, job_count FROM analytics_top_skills ORDER BY job_count DESC, skill LIMIT 15", "bar", "skill", "job_count"),
        ("Số tin mỗi tuần đăng", "SELECT week, job_count FROM analytics_weekly_jobs ORDER BY week", "line", "week", "job_count"),
        ("Số tin mỗi tháng đăng", "SELECT month, job_count FROM analytics_monthly_jobs ORDER BY month", "line", "month", "job_count"),
        ("Kỹ năng theo tháng", "SELECT date_trunc('month', posted_date)::date AS month, skill, count(DISTINCT id) AS job_count FROM analytics_job_skills WHERE posted_date IS NOT NULL GROUP BY 1, skill ORDER BY 1, skill", "table", None, None),
        ("Kỹ năng thay đổi - mẫu hai tuần cuối", "SELECT * FROM analytics_skill_changes ORDER BY share_change_pp DESC, skill", "table", None, None)],
    "03 - Lương": [
        ("Midpoint theo kỹ năng (n >= 3)", "SELECT skill, salary_count, median_salary/1000000 AS median_million_vnd FROM analytics_salary_by_skill WHERE salary_count >= 3 ORDER BY median_salary DESC, skill LIMIT 15", "bar", "skill", "median_million_vnd"),
        ("Lương theo cấp bậc và số mẫu", "SELECT * FROM analytics_salary_by_level ORDER BY level", "table", None, None),
        ("Lương theo thành phố và số mẫu", "SELECT * FROM analytics_salary_by_city ORDER BY salary_count DESC, city", "table", None, None),
        ("Độ đầy đủ lương theo website", "SELECT source, count(*) AS jobs, count(salary_midpoint) AS salary_samples FROM analytics_jobs GROUP BY source ORDER BY source", "table", None, None)],
    "04 - Công ty và vị trí nổi bật": [
        ("Top công ty", "SELECT company, job_count FROM analytics_top_companies ORDER BY job_count DESC, company LIMIT 15", "bar", "company", "job_count"),
        ("Tiêu đề vị trí nổi bật", "SELECT title, count(*) AS job_count FROM analytics_jobs GROUP BY title ORDER BY job_count DESC, title LIMIT 20", "table", None, None),
        ("Tin và link gốc", "SELECT source, title, company, location, level, salary_text, url FROM analytics_jobs ORDER BY scraped_at DESC, id DESC LIMIT 100", "table", None, None)]}


def private_value(key: str, default: str) -> str:
    value = os.getenv(key)
    if not value:
        value = default
        set_key(Path.cwd() / ".env", key, value)
        os.environ[key] = value
    return value


def create_reader() -> dict:
    url = database_url()
    initialize_analytics()
    password = private_value("BI_READER_PASSWORD", secrets.token_urlsafe(24))
    role = "data_ana_bi"
    with connect(url) as connection:
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
            connection.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
        else:
            connection.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
        connection.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(sql.Identifier(role)))
        connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
        views = connection.execute("SELECT viewname FROM pg_catalog.pg_views WHERE schemaname='public' AND viewname LIKE 'analytics\\_%' ESCAPE '\\'").fetchall()
        for (view,) in views:
            connection.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(sql.Identifier("public", view), sql.Identifier(role)))
    details = conninfo_to_dict(url)
    return {"host": details.get("host", "127.0.0.1"), "port": int(details.get("port", 5432)),
        "dbname": details.get("dbname", "it_job_market"), "user": role, "password": password,
        "ssl": details.get("sslmode", "prefer") in {"require", "verify-ca", "verify-full"}}


class Metabase:
    def __init__(self, base_url: str):
        self.url = base_url.rstrip("/")
        self.session = requests.Session()

    def call(self, method, path, body=None):
        response = self.session.request(method, self.url + "/api" + path, json=body, timeout=90)
        if not response.ok:
            raise RuntimeError(f"Metabase API {method} {path}: HTTP {response.status_code}; kiểm tra cấu hình hoặc logs/metabase.log")
        return response.json() if response.content else {}

    def login(self):
        properties = self.call("GET", "/session/properties")
        token = properties.get("setup-token")
        local = urlparse(self.url).hostname in {"localhost", "127.0.0.1"}
        email = os.getenv("METABASE_ADMIN_EMAIL")
        password = os.getenv("METABASE_ADMIN_PASSWORD")
        if token and local:
            email = private_value("METABASE_ADMIN_EMAIL", "admin@local.example")
            password = private_value("METABASE_ADMIN_PASSWORD", "Aa1!" + secrets.token_urlsafe(22))
        if not email or not password:
            raise ValueError("Điền METABASE_ADMIN_EMAIL và METABASE_ADMIN_PASSWORD trong .env")
        if token:
            self.call("POST", "/setup", {"token": token, "user": {"email": email, "password": password, "first_name": "Nhom", "last_name": "1"},
                "prefs": {"site_name": "IT Job Market", "allow_tracking": False}})
        session = self.call("POST", "/session", {"username": email, "password": password})
        self.session.headers["X-Metabase-Session"] = session["id"]


def _items(response):
    return response.get("data", []) if isinstance(response, dict) else response


def provision(client: Metabase, details: dict) -> dict:
    collection = next((row for row in _items(client.call("GET", "/collection")) if row.get("name") == COLLECTION), None)
    if not collection:
        collection = client.call("POST", "/collection", {"name": COLLECTION, "color": "#6688f5", "description": "Managed by data_ana.bi"})
    cid = collection["id"]
    database = next((row for row in _items(client.call("GET", "/database")) if row.get("name") == DB_NAME), None)
    payload = {"name": DB_NAME, "engine": "postgres", "details": details, "is_full_sync": True}
    database = client.call("PUT", f"/database/{database['id']}", payload) if database else client.call("POST", "/database", payload)
    database_id = database["id"]
    items = _items(client.call("GET", f"/collection/{cid}/items"))
    found = {(row.get("model"), row.get("name")): row for row in items}
    links = {}
    for name, cards in DASHBOARDS.items():
        old = found.get(("dashboard", name))
        description = "Mẫu tin đã thu thập; không phải toàn thị trường. Lương chỉ dùng đủ khoảng VND/tháng; xem số mẫu. Thời gian theo ngày đăng chính xác; kỳ đầu/cuối có thể thiếu quan sát."
        dashboard = client.call("PUT", f"/dashboard/{old['id']}", {"description": description}) if old else client.call("POST", "/dashboard", {"name": name, "collection_id": cid, "description": description})
        did = dashboard["id"]
        existing = {c.get("card_id"): c for c in dashboard.get("dashcards", [])}
        layout = []
        row, col, row_height = 0, 0, 0
        graphs = sum(display not in {"scalar", "table"} for _, _, display, _, _ in cards)
        graph_index = 0
        for i, (label, query, display, x, y) in enumerate(cards):
            card_name = name[:2] + " · " + label
            settings = {"graph.dimensions": [x], "graph.metrics": [y]} if x else {}
            if display == "bar":
                display = "row"
            body = {"name": card_name, "collection_id": cid, "display": display, "visualization_settings": settings,
                "dataset_query": {"database": database_id, "type": "native", "native": {"query": query, "template-tags": {}}}}
            old_card = found.get(("card", card_name))
            card = client.call("PUT", f"/card/{old_card['id']}", body) if old_card else client.call("POST", "/card", body)
            # Execute each question to catch SQL/permission failures before reporting success.
            check = client.call("POST", f"/card/{card['id']}/query", {})
            if check.get("status") == "failed":
                raise RuntimeError(f"Câu hỏi '{label}' chưa truy vấn được PostgreSQL")
            prior = existing.get(card["id"], {})
            if display == "scalar":
                width, height = 8, 4
            elif display == "table":
                width, height = 24, 7
            else:
                width, height = (24 if graphs % 2 and graph_index == 0 else 12), 9
                graph_index += 1
            if col + width > 24:
                row, col, row_height = row + row_height, 0, 0
            layout.append({"id": prior.get("id", -i-1), "card_id": card["id"], "row": row, "col": col,
                "size_x": width, "size_y": height, "parameter_mappings": []})
            col += width
            row_height = max(row_height, height)
            if col == 24:
                row, col, row_height = row + row_height, 0, 0
        client.call("PUT", f"/dashboard/{did}", {"dashcards": layout})
        links[name] = f"{client.url}/dashboard/{did}#refresh=60"
    return links


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Analytics views + read-only BI + 4 Metabase dashboards")
    parser.add_argument("--metabase", action="store_true")
    parser.add_argument("--url", default="http://localhost:3000")
    parser.add_argument("--db-host", help="Host PostgreSQL nhìn từ Metabase, ví dụ host.docker.internal hoặc db")
    parser.add_argument("--db-port", type=int)
    args = parser.parse_args()
    try:
        details = create_reader()
        if args.db_host:
            details["host"] = args.db_host
        if args.db_port:
            details["port"] = args.db_port
        if args.metabase:
            client = Metabase(args.url)
            client.login()
            links = provision(client, details)
            Path("outputs").mkdir(exist_ok=True)
            Path("outputs/metabase_links.json").write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(links, ensure_ascii=False, indent=2))
        else:
            print("Analytics views và user data_ana_bi đã sẵn sàng. BI_READER_PASSWORD lưu riêng trong .env.")
    except Exception as exc:
        # Do not echo request/connection objects or their credentials.
        message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "Kiểm tra PostgreSQL/DATABASE_URL và Metabase đang chạy."
        parser.exit(1, message + "\n")


if __name__ == "__main__":
    main()
