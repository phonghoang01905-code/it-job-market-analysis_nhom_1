from __future__ import annotations

import logging
import os
import re
import sys
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def redact(message: str) -> str:
    for key in ("DATABASE_URL", "TELEGRAM_BOT_TOKEN", "SMTP_PASSWORD"):
        value = os.getenv(key, "")
        if value:
            message = message.replace(value, "[REDACTED]")
    message = re.sub(r"postgres(?:ql)?://[^\s]+", "postgresql://[REDACTED]", message)
    return re.sub(r"api\.telegram\.org/bot[^/\s]+", "api.telegram.org/bot[REDACTED]", message)


class RedactingFormatter(logging.Formatter):
    converter = time.gmtime

    def format(self, record):
        return redact(super().format(record))


def configure_logging(directory: Path) -> logging.Logger:
    directory.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("data_ana")
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = RedactingFormatter("%(asctime)s UTC | %(levelname)s | %(name)s | %(message)s")
    file = TimedRotatingFileHandler(directory / "pipeline.log", when="midnight", utc=True, backupCount=30, encoding="utf-8")
    console = logging.StreamHandler(sys.stdout)
    for handler in (file, console):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger
