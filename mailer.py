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
    msg["Message-ID"] = make_msgid(domain="rinfo")
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
    if config.SITE_URL:
        unsubscribe.append(f"<{config.site_url('subscribe', action='unsubscribe')}>")
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


def send_confirm_link(to: str, action: str, url: str, lists: list[str] | None = None) -> None:
    """Email a one-click confirmation link for subscribe / unsubscribe."""
    names = {"weekly": "the weekly edition", "daily": "the daily brief"}
    chosen = " and ".join(names[n] for n in (lists or ["weekly"]) if n in names) or "the newsletter"
    verb = f"receive {chosen} of" if action == "subscribe" else "unsubscribe from"
    text = (f"Please confirm that you want to {verb} Rinfo, a review of new research "
            f"from arXiv.\n\nConfirm here:\n{url}\n\nThe link works for 24 hours. If you did not ask for this, "
            "ignore this email; nothing will change.\n\nRinfo")
    title = "Confirm your subscription" if action == "subscribe" else "Confirm unsubscribing"
    html = (f'<div style="font:16px/1.6 Georgia,serif;color:#151515;max-width:520px;margin:24px auto;">'
            f'<div style="font:700 26px Georgia,serif;border-bottom:3px double #151515;padding-bottom:8px;">'
            f'Rinfo</div><p>Please confirm that you want to {verb} Rinfo.</p>'
            f'<p><a href="{url}" style="display:inline-block;background:#151515;color:#fff;padding:12px 22px;'
            f'font:700 13px Helvetica,Arial,sans-serif;letter-spacing:.08em;text-decoration:none;">'
            f'{title.upper()}</a></p><p style="color:#6E6758;font-size:13px;">The link works for 24 hours. '
            f'If you did not ask for this, ignore this email; nothing will change.</p></div>')
    with _smtp() as smtp:
        smtp.send_message(_message(f"Rinfo: {title.lower()}", to, text, html))
