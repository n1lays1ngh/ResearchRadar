"""Newsletter subscribers, stored as an encrypted file on a separate branch of the GitHub repo.

The repository is public, so the list is Fernet-encrypted with SUBSCRIBERS_KEY: anyone can see the
file, nobody can read the addresses without the key. It lives on its own branch ("subscribers") so a
new signup doesn't redeploy the website or clash with the workflow's commits to main.
Both the API (add/remove) and the weekly workflow (read) go through the GitHub contents API.
Signups are confirmed by an emailed link carrying an encrypted, expiring token (make_token/read_token).

CLI (owner only):
  python subscribers.py --new-key          generate a SUBSCRIBERS_KEY
  python subscribers.py --list             show the current subscribers
  python subscribers.py --add a@b.com [--lists weekly,daily]    add or update / --remove a@b.com
"""
import argparse
import base64
import json
import re
import time
from datetime import datetime, timezone

import requests
from cryptography.fernet import Fernet, InvalidToken

import config

API = "https://api.github.com"
LISTS = ("weekly", "daily")   # the full Monday edition and the Monday-to-Friday brief
EMAIL_RE = re.compile(r"^[^@\s,;<>\"']+@[^@\s,;<>\"']+\.[A-Za-z]{2,}$")


class SubscribersError(RuntimeError):
    pass


def missing_settings() -> list[str]:
    required = {"GH_TOKEN": config.GH_TOKEN, "GITHUB_REPO": config.GITHUB_REPO,
                "SUBSCRIBERS_KEY": config.SUBSCRIBERS_KEY}
    return [name for name, value in required.items() if not value]


def normalize_email(address: str) -> str:
    """Lower-cased address, or '' if it doesn't look like a single valid email."""
    address = (address or "").strip().lower()
    return address if len(address) <= 254 and EMAIL_RE.match(address) else ""


def new_key() -> str:
    return Fernet.generate_key().decode()


def _fernet() -> Fernet:
    try:
        return Fernet(config.SUBSCRIBERS_KEY.encode())
    except (ValueError, TypeError) as exc:
        raise SubscribersError("SUBSCRIBERS_KEY is not a valid key (make one with "
                               "`python subscribers.py --new-key`)") from exc


def _api(method: str, path: str, **kwargs) -> requests.Response:
    missing = missing_settings()
    if missing:
        raise SubscribersError("Subscriptions are not configured; missing " + ", ".join(missing))
    headers = {"Authorization": f"Bearer {config.GH_TOKEN}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ResearchRadar"}
    return requests.request(method, f"{API}/repos/{config.GITHUB_REPO}/{path}",
                            headers=headers, timeout=20, **kwargs)


def _check(resp: requests.Response, what: str) -> None:
    if resp.status_code in (401, 403):
        raise SubscribersError(f"GitHub refused to {what} (HTTP {resp.status_code}); check that GH_TOKEN "
                               "has Contents read/write access to this repository.")
    if resp.status_code >= 400:
        raise SubscribersError(f"GitHub could not {what} (HTTP {resp.status_code}).")


def _read() -> tuple[list[dict], str | None]:
    """(subscribers, file sha); ([], None) when the list doesn't exist yet."""
    resp = _api("GET", f"contents/{config.SUBSCRIBERS_PATH}", params={"ref": config.SUBSCRIBERS_BRANCH})
    if resp.status_code == 404:
        return [], None
    _check(resp, "read the subscriber list")
    data = resp.json()
    try:
        items = json.loads(_fernet().decrypt(base64.b64decode(data["content"])))
    except InvalidToken as exc:
        raise SubscribersError("SUBSCRIBERS_KEY cannot decrypt the subscriber list (wrong key?).") from exc
    return items, data["sha"]


def _ensure_branch() -> None:
    """Create the subscribers branch (from the default branch) if it doesn't exist."""
    if _api("GET", f"git/ref/heads/{config.SUBSCRIBERS_BRANCH}").status_code == 200:
        return
    repo = _api("GET", "")
    _check(repo, "read the repository")
    base = _api("GET", f"git/ref/heads/{repo.json()['default_branch']}")
    _check(base, "read the default branch")
    created = _api("POST", "git/refs", json={"ref": f"refs/heads/{config.SUBSCRIBERS_BRANCH}",
                                             "sha": base.json()["object"]["sha"]})
    if created.status_code != 422:   # 422 = created meanwhile by someone else
        _check(created, "create the subscribers branch")


def _update(change) -> bool:
    """Read-modify-write with retries on concurrent edits. change(items) -> new items, or None = no-op."""
    for attempt in range(3):
        items, sha = _read()
        new_items = change(list(items))
        if new_items is None:
            return False
        if sha is None:
            _ensure_branch()
        token = _fernet().encrypt(json.dumps(new_items).encode())
        body = {"message": "Update subscribers",   # never put addresses in public commit messages
                "content": base64.b64encode(token).decode(), "branch": config.SUBSCRIBERS_BRANCH}
        if sha:
            body["sha"] = sha
        resp = _api("PUT", f"contents/{config.SUBSCRIBERS_PATH}", json=body)
        if resp.status_code in (409, 422) and attempt < 2:   # someone else wrote first; retry
            time.sleep(1 + attempt)
            continue
        _check(resp, "save the subscriber list")
        return True
    return False


def normalize_lists(lists) -> list[str]:
    """Valid newsletter names in canonical order; defaults to the weekly edition."""
    chosen = [name for name in LISTS if name in (lists or [])]
    return chosen or ["weekly"]


def lists_of(item: dict) -> list[str]:
    return normalize_lists(item.get("lists"))   # records from before daily briefs: weekly only


def add(email: str, lists=("weekly",)) -> str:
    """Subscribe or update preferences: 'added', 'updated' or 'unchanged'."""
    email, lists = normalize_email(email), normalize_lists(lists)
    if not email:
        raise ValueError("invalid email address")
    outcome = {"value": "added"}

    def change(items):
        for item in items:
            if item["email"] == email:
                if lists_of(item) == lists:
                    outcome["value"] = "unchanged"
                    return None
                item["lists"] = lists
                outcome["value"] = "updated"
                return items
        return items + [{"email": email, "lists": lists,
                         "since": datetime.now(timezone.utc).isoformat(timespec="seconds")}]
    _update(change)
    return outcome["value"]


def remove(email: str) -> bool:
    """Remove an address; False if it wasn't subscribed."""
    email = normalize_email(email)

    def change(items):
        kept = [i for i in items if i["email"] != email]
        return None if len(kept) == len(items) else kept
    return _update(change)


def emails(newsletter: str | None = None) -> list[str]:
    """All subscribers, or those who get the given newsletter ('weekly' / 'daily')."""
    return [i["email"] for i in _read()[0] if newsletter is None or newsletter in lists_of(i)]


# --- confirmation links (stateless double opt-in for serverless hosting) ----------------------
CONFIRM_TTL = 24 * 3600


def make_token(email: str, action: str, lists=("weekly",)) -> str:
    """Encrypted, expiring token for a confirm link; only the key holder can mint or read it."""
    payload = json.dumps({"purpose": "confirm", "email": normalize_email(email), "action": action,
                          "lists": normalize_lists(lists)})
    return _fernet().encrypt(payload.encode()).decode()


def read_token(token: str) -> tuple[str, str, list[str]]:
    """(email, action, lists) from a confirm token; raises SubscribersError if invalid or expired."""
    try:
        data = json.loads(_fernet().decrypt(token.encode(), ttl=CONFIRM_TTL))
    except (InvalidToken, ValueError, TypeError) as exc:
        raise SubscribersError("This link is invalid or has expired.") from exc
    if not isinstance(data, dict) or data.get("purpose") != "confirm" or \
            data.get("action") not in ("subscribe", "unsubscribe") or not normalize_email(data.get("email", "")):
        raise SubscribersError("This link is invalid or has expired.")
    return data["email"], data["action"], normalize_lists(data.get("lists"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage Research Radar subscribers")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--new-key", action="store_true", help="print a new SUBSCRIBERS_KEY")
    group.add_argument("--list", action="store_true", help="list current subscribers")
    group.add_argument("--add", metavar="EMAIL")
    parser.add_argument("--lists", default="weekly", help="with --add: weekly, daily or weekly,daily")
    group.add_argument("--remove", metavar="EMAIL")
    args = parser.parse_args()
    if args.new_key:
        print(new_key())
    elif args.list:
        items = _read()[0]
        for item in items:
            print(f"{item['email']:40} {'+'.join(lists_of(item))}")
        print(f"{len(items)} subscriber(s): {len(emails('weekly'))} weekly, {len(emails('daily'))} daily")
    elif args.add:
        print(add(args.add, args.lists.split(",")))
    else:
        print("removed" if remove(args.remove) else "was not subscribed")
