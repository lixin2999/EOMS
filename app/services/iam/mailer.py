from __future__ import annotations

import smtplib
import ssl
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("eoms.mailer")


def send_email(recipients: list[str], subject: str, content: str) -> None:
    if not settings.smtp_host:
        logger.info("SMTP 未配置，跳过邮件发送: %s", subject)
        return
    message = MIMEText(content, "plain", "utf-8")
    message["Subject"] = str(Header(subject, "utf-8"))
    message["From"] = formataddr(("EOMS 系统", settings.smtp_from or settings.smtp_user))
    message["To"] = ", ".join(recipients)

    timeout = 10
    if settings.smtp_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=timeout, context=context) as server:
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from or settings.smtp_user, recipients, message.as_string())
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout) as server:
            server.starttls(context=ssl.create_default_context())
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from or settings.smtp_user, recipients, message.as_string())
