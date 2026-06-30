"""
Reddit via PUBLIC RSS — no app, no login, no CAPTCHA required.

Reddit serves an Atom feed for any (multi)subreddit:
    https://www.reddit.com/r/sub1+sub2+sub3/new/.rss

We pull the combined feed in one request and keyword-filter it. This can read
posts but CANNOT post comments/DMs (that needs the authenticated API). Perfect
for the "alert me + draft" flow while a Reddit app isn't available.
"""
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

from scraper.filters import is_relevant

ATOM = "{http://www.w3.org/2005/Atom}"
HEADERS = {
    "User-Agent": "brainsify-lead-finder/1.0 (RSS reader; contact via reddit DM)",
}


def fetch(subreddits: list[str], limit: int = 60) -> list[dict]:
    """Pull newest posts across all subreddits via the combined RSS feed."""
    multi = "+".join(subreddits)
    url = f"https://www.reddit.com/r/{multi}/new/.rss?limit={limit}"
    results: list[dict] = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        if resp.status_code != 200:
            print(f"[rss] HTTP {resp.status_code} — Reddit may be rate-limiting; will retry next run")
            return results
        root = ET.fromstring(resp.content)
    except (requests.RequestException, ET.ParseError) as exc:
        print(f"[rss] fetch/parse failed: {exc}")
        return results

    for entry in root.findall(f"{ATOM}entry"):
        title = (entry.findtext(f"{ATOM}title") or "").strip()

        content_el = entry.find(f"{ATOM}content")
        body = _strip_html(content_el.text if content_el is not None else "")

        if not is_relevant(f"{title}\n{body}"):
            continue

        link_el = entry.find(f"{ATOM}link")
        post_url = link_el.get("href") if link_el is not None else ""
        id_full = entry.findtext(f"{ATOM}id") or ""          # e.g. "t3_1abc23"
        post_id = id_full.split("_")[-1] if "_" in id_full else (id_full or post_url)

        author = ""
        author_el = entry.find(f"{ATOM}author")
        if author_el is not None:
            author = (author_el.findtext(f"{ATOM}name") or "").strip()  # "/u/name"

        results.append({
            "id": post_id,
            "name": title,
            "url": post_url,
            "source": _sub_from_url(post_url),
            "author": author or "u/[unknown]",
            "body": body[:1500],
            "date_found": datetime.now(timezone.utc).isoformat(),
        })

    return results


def _strip_html(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _sub_from_url(url: str) -> str:
    match = re.search(r"/r/([^/]+)/", url or "")
    return f"r/{match.group(1)}" if match else "reddit"
