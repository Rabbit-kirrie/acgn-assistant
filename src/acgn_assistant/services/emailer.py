from __future__ import annotations

import os
import logging
import smtplib
from email.header import Header
from email.message import EmailMessage
from email.utils import parseaddr

from acgn_assistant.core.config import get_settings

logger = logging.getLogger(__name__)


def send_email(*, to_email: str, subject: str, text: str) -> None:
    settings = get_settings()

    # Pytest should never require network SMTP.
    if os.getenv("PYTEST_CURRENT_TEST"):
        logger.info("PYTEST mode; skipping SMTP send to=%s subject=%s", to_email, subject)
        logger.info("EMAIL_TO=%s\nSUBJECT=%s\n\n%s", to_email, subject, text)
        return

    # In dev/test debug mode we return the code via API responses.
    # Avoid hitting real SMTP to keep local dev/tests deterministic.
    if settings.env != "prod" and getattr(settings, "email_debug_return_code", False):
        logger.info(
            "EMAIL_DEBUG_RETURN_CODE enabled; skipping SMTP send to=%s subject=%s",
            to_email,
            subject,
        )
        logger.info("EMAIL_TO=%s\nSUBJECT=%s\n\n%s", to_email, subject, text)
        return

    host = (settings.smtp_host or "").strip()
    if not host:
        # Dev/test fallback: log to server output.
        # In prod, callers should treat this as a configuration error.
        logger.warning("SMTP not configured; skipping email send to=%s subject=%s", to_email, subject)
        logger.info("EMAIL_TO=%s\nSUBJECT=%s\n\n%s", to_email, subject, text)
        return

    # QQ 邮箱对 From 头非常严格：为了稳定，From 头使用“纯邮箱地址”，不带显示名。
    raw_from = str(getattr(settings, "smtp_from", "") or "").strip()
    _from_name, from_addr = parseaddr(raw_from)
    preferred_from = str(getattr(settings, "smtp_username", "") or "").strip()
    if preferred_from:
        from_addr = preferred_from
    if not (from_addr or "").strip():
        from_addr = "no-reply@localhost"

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_email
    msg["Subject"] = str(Header(subject, "utf-8"))
    msg.set_content(text)

    # Some providers (including QQ) are picky about the SMTP envelope-from.
    # Prefer the authenticated username, falling back to the address in the From header.
    envelope_from = (settings.smtp_username or "").strip()
    if not envelope_from:
        _name, addr = parseaddr(raw_from)
        envelope_from = (addr or "").strip()
    if not envelope_from:
        envelope_from = "no-reply@localhost"

    # Debug headers (no body) to help diagnose picky SMTP providers.
    try:
        logger.info(
            "SMTP headers preview: From=%s To=%s Subject=%s",
            msg.get("From"),
            msg.get("To"),
            msg.get("Subject"),
        )
    except Exception:
        pass

    timeout = int(getattr(settings, "smtp_timeout_seconds", 15) or 15)

    smtp = None
    sent = False
    try:
        if settings.smtp_use_ssl:
            smtp = smtplib.SMTP_SSL(host, settings.smtp_port, timeout=timeout)
        else:
            smtp = smtplib.SMTP(host, settings.smtp_port, timeout=timeout)

        smtp.ehlo()
        if (not settings.smtp_use_ssl) and settings.smtp_use_tls:
            smtp.starttls()
            smtp.ehlo()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)

        smtp.send_message(msg, from_addr=envelope_from, to_addrs=[to_email])
        sent = True
    except Exception:
        # Background tasks should not crash the request handler; log and continue.
        logger.exception("SMTP send failed to=%s subject=%s", to_email, subject)
    finally:
        if smtp is not None:
            try:
                # Some servers (including QQ in some cases) may drop the connection on QUIT.
                # If we already sent the message, treat QUIT/close errors as non-fatal.
                smtp.quit()
            except Exception:
                if sent:
                    logger.warning("SMTP quit failed after successful send; ignoring", exc_info=True)
                else:
                    logger.exception("SMTP quit failed")
            try:
                smtp.close()
            except Exception:
                pass
