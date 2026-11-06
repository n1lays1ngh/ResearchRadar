"""Send email over SMTP (SSL on port 465, otherwise STARTTLS).

The digest goes to each recipient as a separate message, so subscribers never see each other's address.
"""
import smtplib
import ssl
from contextlib import contextmanager
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import config


def missing_settings(need_recipients: bool = True) -> list[str]:
    """Names of required SMTP settings that are not set."""
    required = {"SMTP_USER": config.SMTP_USER, "SMTP_PASS": config.SMTP_PASS, "MAIL_FROM": config.MAIL_FROM}
    if need_recipients:
        required["MAIL_TO"] = config.MAIL_TO
    return [name for name, value in required.items() if not value]


@contextmanager
def _smtp():
    context = ssl.create_default_context()
    if config.SMTP_PORT == 465:
        smtp = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=context, timeout=60)
    else:
        smtp = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=60)
        smtp.starttls(context=context)
    try:
        smtp.login(config.SMTP_USER, config.SMTP_PASS)
        yield smtp
    finally:
        try:
            smtp.quit()
        except smtplib.SMTPException:
            pass


def _message(subject: str, to: str, text: str, html: str = "") -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.MAIL_FROM
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="research-radar")
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def send(subject: str, html: str, text: str, recipients: list[str] | None = None) -> list[str]:
    """Send the digest to every recipient (default MAIL_TO), one message each.

    Returns the addresses that failed; raises if every recipient failed.
    """
    recipients = recipients or config.MAIL_TO
    unsubscribe = [f"<mailto:{config.MAIL_FROM}?subject=unsubscribe>"]
    if config.CHAT_APP_URL:
        unsubscribe.append(f"<{config.app_url(action='unsubscribe')}>")
    failed: list[str] = []
    pending = list(recipients)
    for _ in range(2):   # second pass reconnects if Gmail dropped the connection mid-way
        retry: list[str] = []
        try:
            with _smtp() as smtp:
                for i, to in enumerate(pending):
                    msg = _message(subject, to, text, html)
                    msg["List-Unsubscribe"] = ", ".join(unsubscribe)
                    try:
                        smtp.send_message(msg)
                    except smtplib.SMTPServerDisconnected:
                        retry = pending[i:]
                        break
                    except smtplib.SMTPException:
                        failed.append(to)
        except smtplib.SMTPServerDisconnected:
            retry = retry or pending
        if not retry:
            break
        pending = retry
    else:
        failed += pending
    if failed and len(failed) == len(recipients):
        raise RuntimeError(f"all {len(recipients)} deliveries failed")
    return failed


def send_code(to: str, code: str, action: str) -> None:
    """Email a one-time confirmation code for subscribe / unsubscribe."""
    verb = "subscribe to" if action == "subscribe" else "unsubscribe from"
    text = (f"Your confirmation code is: {code}\n\n"
            f"Enter it in the Research Radar app to {verb} the weekly newsletter. "
            "It expires in 15 minutes.\n\n"
            "If you did not request this, ignore this email; nothing will change.\n\n"
            "The Research Radar")
    with _smtp() as smtp:
        smtp.send_message(_message(f"The Research Radar: your confirmation code is {code}", to, text))
