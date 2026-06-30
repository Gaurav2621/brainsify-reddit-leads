"""
Site-wide Reddit search via the public search RSS feed (no app, no login).

    https://www.reddit.com/search.rss?q=<query>&sort=new

This finds leads in ANY subreddit (not just the ones you watch). Reddit rate-limits
the search feed hard, so we send ONE combined OR query per run and back off on 429.
"""
import html
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

from scraper.filters import is_blocked

ATOM = "{http://www.w3.org/2005/Atom}"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; brainsify-lead-finder/1.0; RSS reader)"}


def fetch(query: str, limit: int = 100) -> list[dict]:
    """Run one site-wide search and return fresh, non-blocked, deduped posts."""
    if not query:
        return []

    url = (
        "https://www.reddit.com/search.rss?"
        f"q={urllib.parse.quote(query)}&sort=new&limit={limit}&type=link"
    )

    # Reddit blocks the search endpoint from datacenter IPs (e.g. GitHub Actions),
    # so fail FAST there (1 quick retry) instead of burning ~30s every run. From a
    # residential IP (your Mac) this succeeds and gives true site-wide coverage.
    resp = None
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=25)
        except requests.RequestException as exc:
            print(f"[search] request error: {exc}")
            return []
        if resp.status_code == 200:
            break
        if resp.status_code == 429:
            print(f"[search] 429 (search blocked from this IP) — attempt {attempt + 1}")
            time.sleep(3)
            continue
        print(f"[search] HTTP {resp.status_code}")
        return []

    if not resp or resp.status_code != 200:
        print("[search] gave up after retries")
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as exc:
        print(f"[search] parse error: {exc}")
        return []

    results: list[dict] = []
    seen: set[str] = set()
    for entry in root.findall(f"{ATOM}entry"):
        item = _parse(entry)
        if not item or item["id"] in seen:
            continue
        if is_blocked(f"{item['name']} {item['body']}"):
            continue
        seen.add(item["id"])
        results.append(item)
    return results


def _parse(entry) -> dict | None:
    title = (entry.findtext(f"{ATOM}title") or "").strip()
    if not title:
        return None
    content_el = entry.find(f"{ATOM}content")
    body = _strip_html(content_el.text if content_el is not None else "")

    link_el = entry.find(f"{ATOM}link")
    post_url = link_el.get("href") if link_el is not None else ""
    id_full = entry.findtext(f"{ATOM}id") or ""
    post_id = id_full.split("_")[-1] if "_" in id_full else (id_full or post_url)

    author_el = entry.find(f"{ATOM}author")
    author = (author_el.findtext(f"{ATOM}name") if author_el is not None else "") or "u/[unknown]"

    return {
        "id": post_id,
        "name": title,
        "url": post_url,
        "source": _sub_from_url(post_url),
        "author": author,
        "body": body[:1500],
        "date_found": datetime.now(timezone.utc).isoformat(),
    }


def _strip_html(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _sub_from_url(url: str) -> str:
    match = re.search(r"/r/([^/]+)/", url or "")
    return f"r/{match.group(1)}" if match else "reddit"
