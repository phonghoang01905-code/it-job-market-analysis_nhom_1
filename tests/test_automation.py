import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from data_ana import alerts, pipeline
from data_ana.logging_config import RedactingFormatter
from data_ana.locking import single_instance
from data_ana.scheduler import next_run


def test_schedule_converts_vietnam_time_and_waits_next_day():
    zone = ZoneInfo("Asia/Ho_Chi_Minh")
    assert next_run(datetime(2026, 10, 28, 0, 0, tzinfo=timezone.utc), "07:15", zone).isoformat() == "2026-10-28T07:15:00+07:00"
    assert next_run(datetime(2026, 10, 28, 0, 16, tzinfo=timezone.utc), "07:15", zone).isoformat() == "2026-10-29T07:15:00+07:00"


def test_overlap_lock_is_released_after_exception(tmp_path):
    import pytest
    path = tmp_path / "pipeline.lock"
    with single_instance(path):
        with pytest.raises(OSError):
            with single_instance(path):
                pass
    with single_instance(path):
        pass


def test_log_redacts_secrets_in_traceback(monkeypatch):
    monkeypatch.setenv("SMTP_PASSWORD", "secret-smtp-123")
    formatter = RedactingFormatter("%(message)s")
    try:
        raise RuntimeError("secret-smtp-123 postgresql://user:password@host/db")
    except RuntimeError:
        import sys
        record = logging.LogRecord("test", logging.ERROR, "", 0, "failed", (), sys.exc_info())
    output = formatter.format(record)
    assert "secret-smtp-123" not in output and "password@host" not in output
    assert "[REDACTED]" in output


def test_telegram_uses_configured_chat_and_checks_api_result(monkeypatch):
    monkeypatch.setenv("ALERT_CHANNEL", "telegram")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "my-test-chat")
    called = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": False}

    def post(url, json, timeout):
        called.append(json)
        return Response()

    monkeypatch.setattr(alerts.requests, "post", post)
    assert alerts.send_alert("failed") == {"telegram": False}
    assert called == [{"chat_id": "my-test-chat", "text": "failed"}]


def test_email_enables_tls_and_uses_configured_recipient(monkeypatch):
    for key, value in {"ALERT_CHANNEL": "email", "SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587",
        "SMTP_SECURITY": "starttls", "SMTP_USERNAME": "test-user", "SMTP_PASSWORD": "test-pass",
        "ALERT_FROM": "from@example.com", "ALERT_TO": "to@example.com"}.items():
        monkeypatch.setenv(key, value)
    actions = []

    class SMTP:
        def __init__(self, host, port, timeout):
            assert (host, port) == ("smtp.example.com", 587)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self, context):
            actions.append("tls")

        def login(self, user, password):
            actions.append("login")

        def send_message(self, message):
            actions.append(message["To"])

    monkeypatch.setattr(alerts.smtplib, "SMTP", SMTP)
    assert alerts.send_alert("failed") == {"email": True}
    assert actions == ["tls", "login", "to@example.com"]


def test_partial_crawl_still_runs_etl_and_returns_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "configured-but-not-connected")
    args = argparse.Namespace(skip_crawl=False, skip_db=False, config=Path("unused"), sources=None,
        max_pages=1, raw=tmp_path / "jobs.csv", out_dir=tmp_path / "clean", log_dir=tmp_path / "logs")
    args.raw.write_text("already collected", encoding="utf-8")
    monkeypatch.setattr(pipeline, "load_config", lambda _: {"sites": [{"name": "topcv", "enabled": True}]})

    def crawl(config, max_pages, statuses):
        statuses["topcv"] = {"status": "error", "collected": 0}
        return []

    monkeypatch.setattr(pipeline, "crawl", crawl)
    monkeypatch.setattr(pipeline, "run_etl", lambda *a, **k: {"rejected": 0, "database": {"inserted": 0, "skipped": 77}})
    notifications = []
    monkeypatch.setattr(pipeline, "send_alert", lambda text: notifications.append(text) or {"telegram": True})
    assert pipeline.run_pipeline(args) == 1
    report = json.loads((args.log_dir / "latest_run.json").read_text(encoding="utf-8"))
    assert report["status"] == "partial" and report["etl"]["database"]["skipped"] == 77
    assert len(notifications) == 1
