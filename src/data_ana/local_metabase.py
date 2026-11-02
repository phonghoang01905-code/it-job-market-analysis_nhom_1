"""Run the pinned Metabase JAR locally when Docker Desktop is unavailable."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
import requests

from data_ana.bi import private_value
from data_ana.data_access import database_url

VERSION = "v0.64.1"


def run():
    try:
        health = requests.get("http://localhost:3000/api/health", timeout=2)
        if health.ok and health.json().get("status") == "ok":
            print("Metabase is already running: http://localhost:3000", flush=True)
            return
    except (requests.RequestException, ValueError):
        pass
    url = database_url()
    if not shutil.which("java"):
        raise RuntimeError("Cần Java 21+ hoặc dùng Docker Compose theo README.")
    use_postgres_app = False
    with psycopg.connect(url, autocommit=True, connect_timeout=10) as connection:
        use_postgres_app = connection.info.server_version >= 140000
        if use_postgres_app:
            password = private_value("METABASE_APP_PASSWORD", os.urandom(24).hex())
            if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname='data_ana_metabase'").fetchone():
                connection.execute(sql.SQL("CREATE ROLE data_ana_metabase LOGIN PASSWORD {}").format(sql.Literal(password)))
            if not connection.execute("SELECT 1 FROM pg_database WHERE datname='it_job_metabase'").fetchone():
                connection.execute("CREATE DATABASE it_job_metabase OWNER data_ana_metabase")
    target = Path(".tools/metabase") / VERSION / "metabase.jar"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".download")
        print(f"Downloading official Metabase {VERSION} JAR...", flush=True)
        with requests.get(f"https://downloads.metabase.com/{VERSION}/metabase.jar", stream=True, timeout=(20, 120)) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_content(1024*1024):
                    output.write(chunk)
        temporary.replace(target)
    config = conninfo_to_dict(url)
    env = {**os.environ, "MB_JETTY_HOST": "127.0.0.1", "MB_JETTY_PORT": "3000", "JAVA_TIMEZONE": "Asia/Ho_Chi_Minh",
           "MB_PLUGINS_DIR": str(Path(".tools/metabase/plugins").resolve()),
           "MB_ANON_TRACKING_ENABLED": "false", "MB_CHECK_FOR_UPDATES": "false",
           "MB_ENCRYPTION_SECRET_KEY": private_value("METABASE_ENCRYPTION_SECRET_KEY", os.urandom(32).hex()),
           "MB_SESSION_SECRET_KEY": private_value("METABASE_SESSION_SECRET_KEY", os.urandom(32).hex())}
    if use_postgres_app:
        env.update(MB_DB_TYPE="postgres", MB_DB_DBNAME="it_job_metabase", MB_DB_USER="data_ana_metabase", MB_DB_PASS=password,
                   MB_DB_HOST=config.get("host", "127.0.0.1"), MB_DB_PORT=config.get("port", "5432"))
    else:
        app_db = Path(".tools/metabase/appdb/metabase")
        app_db.parent.mkdir(parents=True, exist_ok=True)
        env.update(MB_DB_TYPE="h2", MB_DB_FILE=str(app_db.resolve()))
        print("Local demo: H2 stores Metabase settings because local PostgreSQL is older than 14. Job analytics still query PostgreSQL.", flush=True)
    print("Metabase: http://localhost:3000. Ctrl+C to stop. Application DB is separate from job data.", flush=True)
    subprocess.run(["java", "-Xmx1g", "-jar", str(target.resolve())], env=env, check=True)


def main():
    try:
        run()
    except KeyboardInterrupt:
        pass
    except Exception:
        raise SystemExit("Metabase chưa khởi động. Kiểm tra Java 21+, PostgreSQL và kết nối tải JAR chính thức.") from None


if __name__ == "__main__":
    main()
