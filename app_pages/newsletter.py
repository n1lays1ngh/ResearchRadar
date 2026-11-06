"""Newsletter page: read any edition, download it as PDF/HTML, and subscribe or unsubscribe.

Subscribing is double opt-in: a 6-digit code is emailed to the address and must be entered here,
so nobody can sign up (or remove) someone else's address.
"""
import glob
import hmac
import os
import secrets
import time
from datetime import datetime

import streamlit as st

import config
import mailer
import subscribers

CODE_TTL = 15 * 60        # seconds a code stays valid
MAX_TRIES = 5             # wrong guesses per code
RESEND_GAP = 60           # seconds between codes to the same address
MAX_PER_HOUR = 4          # codes per address per hour (across all visitors)
MAX_PER_SESSION = 6       # codes per browser session
ACTIONS = {"subscribe": "Subscribe", "unsubscribe": "Unsubscribe"}

ss = st.session_state
ss.setdefault("sub", None)        # pending confirmation: email, action, code, expires, tries
ss.setdefault("sub_sent", 0)
ss.setdefault("sub_msg", None)    # (kind, text) shown once


# --- editions ----------------------------------------------------------------------
def editions() -> list[str]:
    """Edition dates (YYYY-MM-DD), newest first."""
    paths = glob.glob(os.path.join(config.EDITIONS_DIR, "*.html"))
    return sorted((os.path.basename(p)[:-5] for p in paths), reverse=True)


def edition_label(date: str) -> str:
    try:
        return datetime.strptime(date, "%Y-%m-%d").strftime("%A, %-d %B %Y")
    except ValueError:
        return date


@st.cache_data(show_spinner=False, max_entries=20)
def read_bytes(path: str, mtime: float) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


# --- double opt-in -------------------------------------------------------------------
@st.cache_resource
def code_log() -> dict[str, list[float]]:
    """When codes were sent to each address; shared by all visitors of this app instance."""
    return {}


def notify(kind: str, text: str) -> None:
    ss.sub_msg = (kind, text)


def start(email_input: str, action: str) -> None:
    missing = mailer.missing_settings(need_recipients=False) + subscribers.missing_settings()
    if missing:
        notify("error", "Subscriptions aren't set up on this server yet (missing: " + ", ".join(missing) + ").")
        return
    email = subscribers.normalize_email(email_input)
    if not email:
        notify("error", "Please enter a valid email address.")
        return
    now = time.time()
    sent = [t for t in code_log().get(email, []) if now - t < 3600]
    if ss.sub_sent >= MAX_PER_SESSION or len(sent) >= MAX_PER_HOUR:
        notify("error", "Too many codes requested. Please try again in an hour.")
        return
    if sent and now - sent[-1] < RESEND_GAP:
        notify("error", f"A code was just sent. Wait {int(RESEND_GAP - (now - sent[-1]))} s before asking again.")
        return
    code = f"{secrets.randbelow(10**6):06d}"
    try:
        mailer.send_code(email, code, action)
    except Exception as exc:
        print(f"  ! confirmation email failed: {type(exc).__name__}: {exc}")
        notify("error", "Couldn't send the confirmation email. Please try again later.")
        return
    code_log()[email] = sent + [now]
    ss.sub_sent += 1
    ss.sub = {"email": email, "action": action, "code": code, "expires": now + CODE_TTL, "tries": 0}
    notify("info", f"We've emailed a 6-digit code to {email}. It expires in 15 minutes.")


def confirm(code_input: str) -> None:
    pending = ss.sub
    if time.time() > pending["expires"]:
        ss.sub = None
        notify("error", "That code has expired. Please request a new one.")
        return
    pending["tries"] += 1
    if not hmac.compare_digest(code_input.strip(), pending["code"]):
        left = MAX_TRIES - pending["tries"]
        if left <= 0:
            ss.sub = None
            notify("error", "Too many wrong codes. Please request a new one.")
        else:
            notify("error", f"That code isn't right. {left} attempt(s) left.")
        return
    email, action = pending["email"], pending["action"]
    try:
        if action == "subscribe":
            changed = subscribers.add(email)
            text = ("You're subscribed. The next edition arrives on Monday morning." if changed
                    else "You're already subscribed.")
        else:
            changed = subscribers.remove(email)
            text = "You've been unsubscribed. Sorry to see you go." if changed else "That address wasn't subscribed."
    except Exception as exc:
        print(f"  ! subscriber update failed: {type(exc).__name__}: {exc}")
        notify("error", "Couldn't update the subscriber list right now. Please try again later.")
        return
    ss.sub = None
    notify("success", text)


def cancel() -> None:
    ss.sub = None
    ss.sub_msg = None


def subscribe_box() -> None:
    st.subheader("Get it every Monday")
    if ss.sub is None:
        wanted = st.query_params.get("action", "subscribe")
        with st.form("sub_form", border=False):
            action = st.radio("I want to", list(ACTIONS), format_func=ACTIONS.get, horizontal=True,
                              index=list(ACTIONS).index(wanted) if wanted in ACTIONS else 0)
            email = st.text_input("Email address", placeholder="you@example.com")
            if st.form_submit_button("Email me a confirmation code", use_container_width=True):
                start(email, action)
                st.rerun()
    else:
        with st.form("code_form", border=False):
            code = st.text_input(f"Code sent to {ss.sub['email']}", max_chars=6, placeholder="123456")
            if st.form_submit_button(f"Confirm: {ACTIONS[ss.sub['action']].lower()}",
                                     use_container_width=True, type="primary"):
                confirm(code)
                st.rerun()
        st.button("Use a different address", on_click=cancel, use_container_width=True)
    if ss.sub_msg:
        kind, text = ss.sub_msg
        getattr(st, kind)(text)
        if kind != "info" or ss.sub is None:
            ss.sub_msg = None
    st.caption("Free, weekly, one email. Your address is stored encrypted and only used to send "
               "the newsletter. Unsubscribe here at any time.")


# --- page ----------------------------------------------------------------------------
st.title("📰 The Research Radar")
st.caption("A weekly review of new research from the arXiv preprint server.")

dates = editions()
left, right = st.columns([2, 1], gap="large")
with right, st.container(border=True):
    subscribe_box()

with left:
    if not dates:
        st.info("No editions have been published yet. The first one appears after the next weekly run "
                "(or run `python run_digest.py --dry-run` locally).")
        st.stop()
    date = st.selectbox("Edition", dates, format_func=edition_label,
                        help="Every past edition is archived here.")
    html_path = os.path.join(config.EDITIONS_DIR, date + ".html")
    pdf_path = os.path.join(config.EDITIONS_DIR, date + ".pdf")
    html = read_bytes(html_path, os.path.getmtime(html_path))
    c1, c2 = st.columns(2)
    if os.path.exists(pdf_path):
        c1.download_button("⬇️ Download PDF", read_bytes(pdf_path, os.path.getmtime(pdf_path)),
                           file_name=f"Research-Radar-{date}.pdf", mime="application/pdf",
                           use_container_width=True, type="primary")
    else:
        c1.button("⬇️ PDF not available", disabled=True, use_container_width=True)
    c2.download_button("⬇️ Download HTML", html, file_name=f"Research-Radar-{date}.html",
                       mime="text/html", use_container_width=True)
    st.caption(f"{len(dates)} edition(s) in the archive.")

# Our own generated edition (all dynamic text escaped by email_builder). Links open in a new tab,
# since arXiv and most sites refuse to load inside a frame.
page = html.decode("utf-8").replace("<head>", '<head><base target="_blank">', 1)
if hasattr(st, "iframe"):
    st.iframe(page, height=1600)
else:   # Streamlit < 1.52
    import streamlit.components.v1 as components
    components.html(page, height=1600, scrolling=True)
