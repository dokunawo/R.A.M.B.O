"""Echo outbound messaging — email via SMTP (env-gated, best-effort).

Configure with environment variables (no creds = DEGRADED, never crashes):
  SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASS,
  SMTP_FROM (default = SMTP_USER), ECHO_DEFAULT_TO (default recipient).

For Gmail: SMTP_HOST=smtp.gmail.com, SMTP_PORT=587, SMTP_USER=<you>@gmail.com,
SMTP_PASS=<app password>.  Health: status() reports CONNECTED / OFFLINE.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage


def _cfg() -> dict:
    return {
        "host": os.environ.get("SMTP_HOST", "").strip(),
        "port": int(os.environ.get("SMTP_PORT", "587") or "587"),
        "user": os.environ.get("SMTP_USER", "").strip(),
        "password": os.environ.get("SMTP_PASS", "").strip(),
        "sender": (os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or "").strip(),
        "default_to": os.environ.get("ECHO_DEFAULT_TO", "").strip(),
    }


def is_configured() -> bool:
    c = _cfg()
    return bool(c["host"] and c["user"] and c["password"] and c["sender"])


def status() -> dict:
    """Health check for Echo: CONNECTED when SMTP creds are present, else OFFLINE."""
    c = _cfg()
    return {
        "agent": "echo",
        "channel": "email/smtp",
        "status": "CONNECTED" if is_configured() else "OFFLINE",
        "has_default_recipient": bool(c["default_to"]),
    }


def send_email(subject: str, body: str, to: str | None = None) -> dict:
    """Send an email. Returns {"sent": bool, "detail": str}. Never raises."""
    c = _cfg()
    if not is_configured():
        return {"sent": False, "detail": "Echo is OFFLINE — SMTP credentials not configured."}
    recipient = (to or c["default_to"]).strip()
    if not recipient:
        return {"sent": False, "detail": "No recipient (set ECHO_DEFAULT_TO or pass one)."}

    msg = EmailMessage()
    msg["Subject"] = subject or "(no subject)"
    msg["From"] = c["sender"]
    msg["To"] = recipient
    msg.set_content(body or "")

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(c["host"], c["port"], timeout=20) as server:
            server.starttls(context=ctx)
            server.login(c["user"], c["password"])
            server.send_message(msg)
        return {"sent": True, "detail": f"Email sent to {recipient}."}
    except Exception as e:
        return {"sent": False, "detail": f"Send failed: {e}"}
