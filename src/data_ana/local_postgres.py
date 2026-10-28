"""Manage an isolated project PostgreSQL cluster using existing server binaries."""
from __future__ import annotations

import argparse
import os
import secrets
import socket
import subprocess
import tempfile
from pathlib import Path

import psycopg
from dotenv import dotenv_values, load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "postgres"
PORT = 55432


def binary_dir() -> Path:
    candidates = []
    if os.getenv("POSTGRES_BIN"):
        candidates.append(Path(os.environ["POSTGRES_BIN"]))
    program_files = Path(os.getenv("ProgramFiles", "C:/Program Files"))
    candidates.extend(program_files.glob("PostgreSQL/*/bin"))
    candidates.extend(program_files.glob("Odoo */PostgreSQL/bin"))
    for path in candidates:
        if (path / "pg_ctl.exe").exists() and (path / "initdb.exe").exists():
            return path
    raise RuntimeError("Chưa tìm được PostgreSQL bin. Điền POSTGRES_BIN trong .env hoặc dùng PostgreSQL/Docker riêng theo README.")


def command(binary: str, *arguments, check=True):
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    # A server started by pg_ctl can inherit pipe handles on Windows. Use a
    # regular file so waiting for pg_ctl never waits for the server to exit.
    (ROOT / "logs").mkdir(exist_ok=True)
    with (ROOT / "logs/postgres-control.log").open("a+", encoding="utf-8", errors="replace") as output:
        start_offset = output.tell()
        result = subprocess.run([str(binary_dir() / binary), *map(str, arguments)], cwd=ROOT,
            stdout=output, stderr=subprocess.STDOUT, timeout=60, creationflags=flags)
        output.seek(start_offset)
        result.stdout, result.stderr = output.read(), ""
    if check and result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result


def is_running() -> bool:
    return DATA.exists() and command("pg_ctl.exe", "-D", DATA, "status", check=False).returncode == 0


def start() -> None:
    if is_running():
        print("PostgreSQL của dự án đã chạy trên port 55432")
        return
    if not (DATA / "PG_VERSION").exists():
        raise RuntimeError("Chưa có cluster dự án. Chạy local_postgres init trước.")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", PORT))
    (ROOT / "logs").mkdir(exist_ok=True)
    command("pg_ctl.exe", "-D", DATA, "-l", ROOT / "logs/postgres.log", "-o", f"-h 127.0.0.1 -p {PORT}", "-w", "-t", "30", "start")
    print("Đã khởi động PostgreSQL riêng tại 127.0.0.1:55432")


def init() -> None:
    binary_dir()
    if (DATA / "PG_VERSION").exists():
        start()
        ensure_database()
        return
    env_path = ROOT / ".env"
    existing = dotenv_values(env_path) if env_path.exists() else {}
    if os.getenv("DATABASE_URL") or existing.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL đã được cấu hình; dùng database đó hoặc bỏ cấu hình trước khi khởi tạo cluster riêng.")
    password = secrets.token_urlsafe(24)
    DATA.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=ROOT, prefix=".pg-init-", delete=False) as file:
        password_path = Path(file.name)
        file.write(password + "\n")
    try:
        command("initdb.exe", "-D", DATA, "-U", "data_ana", "--encoding=UTF8", "--locale=C", "--auth=scram-sha-256", f"--pwfile={password_path}")
    finally:
        password_path.unlink(missing_ok=True)
    url = f"postgresql://data_ana:{password}@127.0.0.1:{PORT}/it_job_market"
    base = env_path.read_text(encoding="utf-8") if env_path.exists() else "# Local project configuration; do not commit\nALERT_CHANNEL=none\nUSD_VND_RATE=25000\n"
    env_path.write_text(base.rstrip() + f"\nDATABASE_URL={url}\n", encoding="utf-8")
    # Keep connection details out of command-line process listings and output.
    start()
    ensure_database()
    print("Đã tạo database it_job_market. Mật khẩu ngẫu nhiên lưu trong .env (không in ra terminal).")


def ensure_database():
    from psycopg.conninfo import conninfo_to_dict
    url = dotenv_values(ROOT / ".env").get("DATABASE_URL")
    if not url:
        raise RuntimeError("Thiếu cấu hình .env cho cluster dự án")
    details = conninfo_to_dict(url)
    if details.get("host") != "127.0.0.1" or details.get("port") != str(PORT) or details.get("dbname") != "it_job_market":
        raise RuntimeError("DATABASE_URL không trỏ tới cluster riêng của dự án")
    details["dbname"] = "postgres"
    with psycopg.connect(**details, autocommit=True, connect_timeout=10) as connection:
        if not connection.execute("SELECT 1 FROM pg_database WHERE datname = 'it_job_market'").fetchone():
            connection.execute("CREATE DATABASE it_job_market")


def main():
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="PostgreSQL riêng cho dự án; dùng bộ binary có sẵn trên Windows")
    parser.add_argument("action", choices=["init", "start", "stop", "status"])
    args = parser.parse_args()
    if args.action == "init":
        init()
    elif args.action == "start":
        start()
    elif args.action == "stop":
        if is_running():
            command("pg_ctl.exe", "-D", DATA, "-m", "fast", "-w", "stop")
        print("PostgreSQL riêng của dự án đã dừng")
    else:
        print("running" if is_running() else "stopped")


if __name__ == "__main__":
    main()
