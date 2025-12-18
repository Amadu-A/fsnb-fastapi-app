# /src/core/mailing/email.py
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

from src.core.config import settings
from src.app_logging import get_logger

log = get_logger("mail")


def send_verification_email_sync(to_email: str, verify_link: str) -> bool:
    """
    Простая синхронная отправка (SMTP). Для продакшена можно вынести в Celery.
    """
    subject = "Подтверждение регистрации"
    body = (
        "Для подтверждения e-mail пройдите по ссылке:\n\n"
        f"{verify_link}\n\n"
        "Если это были не вы — игнорируйте письмо."
    )
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.email.from_email
    msg["To"] = to_email

    try:
        if settings.email.use_ssl:
            with smtplib.SMTP_SSL(
                settings.email.smtp_host,
                settings.email.smtp_port,
                timeout=5
            ) as s:
                if settings.email.smtp_user:
                    s.login(settings.email.smtp_user, settings.email.smtp_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(
                settings.email.smtp_host,
                settings.email.smtp_port,
                timeout=5
            ) as s:
                # безопаснее явно послать EHLO перед STARTTLS
                s.ehlo()
                if settings.email.use_tls:
                    s.starttls()
                    s.ehlo()
                if settings.email.smtp_user:
                    s.login(settings.email.smtp_user, settings.email.smtp_password)
                s.send_message(msg)

        log.info({"event": "email_sent", "to": to_email})
        return True
    except Exception as e:
        log.info({"event": "email_fail", "to": to_email, "error": str(e)})
        return False

