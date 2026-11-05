"""Send the digest over SMTP (SSL on port 465, otherwise STARTTLS)."""
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import config


def missing_settings() -> list[str]:
    """Names of required SMTP settings that are not set."""
    required = {"SMTP_USER": config.SMTP_USER, "SMTP_PASS": config.SMTP_PASS,
                "MAIL_FROM": config.MAIL_FROM, "MAIL_TO": config.MAIL_TO}
    return [name for name, value in required.items() if not value]


def send(subject: str, html: str, text: str) -> None:
    """Send a multipart (plain text + HTML) email to every MAIL_TO address."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.MAIL_FROM
    msg["To"] = ", ".join(config.MAIL_TO)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="research-radar")
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    context = ssl.create_default_context()
    if config.SMTP_PORT == 465:
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=context, timeout=60) as smtp:
            smtp.login(config.SMTP_USER, config.SMTP_PASS)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=60) as smtp:
            smtp.starttls(context=context)
            smtp.login(config.SMTP_USER, config.SMTP_PASS)
            smtp.send_message(msg)
