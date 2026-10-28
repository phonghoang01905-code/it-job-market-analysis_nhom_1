from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

import requests

logger = logging.getLogger(__name__)


def send_alert(message: str) -> dict[str, bool]:
    from data_ana.logging_config import redact

    channel = os.getenv("ALERT_CHANNEL", "none").lower().strip()
    if channel == "none":
        logger.warning("Cảnh báo chỉ ghi log: ALERT_CHANNEL=none")
        return {}
    if channel not in {"telegram", "email", "both"}:
        logger.error("ALERT_CHANNEL không hợp lệ")
        return {"configuration": False}
    message = redact(message)[:3500]
    results = {}
    if channel in {"telegram", "both"}:
        try:
            token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
            if not token or not chat:
                raise ValueError("Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID")
            response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat, "text": message}, timeout=15)
            response.raise_for_status()
            if not response.json().get("ok"):
                raise RuntimeError("Telegram từ chối thông báo")
            results["telegram"] = True
        except Exception as exc:
            logger.error("Không gửi được Telegram: %s", exc)
            results["telegram"] = False
    if channel in {"email", "both"}:
        try:
            host, sender, recipient = os.getenv("SMTP_HOST"), os.getenv("ALERT_FROM"), os.getenv("ALERT_TO")
            if not all((host, sender, recipient)):
                raise ValueError("Thiếu SMTP_HOST, ALERT_FROM hoặc ALERT_TO")
            security = os.getenv("SMTP_SECURITY", "starttls").lower()
            if security not in {"starttls", "ssl"}:
                raise ValueError("SMTP_SECURITY phải là starttls hoặc ssl")
            port = int(os.getenv("SMTP_PORT", "465" if security == "ssl" else "587"))
            email = EmailMessage()
            email["Subject"] = "[IT Job Market] Pipeline lỗi hoặc thiếu dữ liệu"
            email["From"], email["To"] = sender, recipient
            email.set_content(message)
            factory = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
            kwargs = {"context": ssl.create_default_context()} if security == "ssl" else {}
            with factory(host, port, timeout=15, **kwargs) as server:
                if security == "starttls":
                    server.starttls(context=ssl.create_default_context())
                if os.getenv("SMTP_USERNAME"):
                    server.login(os.environ["SMTP_USERNAME"], os.getenv("SMTP_PASSWORD", ""))
                server.send_message(email)
            results["email"] = True
        except Exception as exc:
            logger.error("Không gửi được email: %s", exc)
            results["email"] = False
    return results
