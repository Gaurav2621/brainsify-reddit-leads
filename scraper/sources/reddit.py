"""
Reddit source — scans the `new` feed of each configured subreddit and
keeps only posts that pass the keyword filter.

Auth: read-only OAuth using a Reddit "script" app (client id + secret only).
No username/password needed because we only read public posts.
"""
import os
from datetime import datetime, timezone

import praw

from scraper.filters import is_relevant


def _client() -> praw.Reddit:
    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "lead-finder/1.0 by u/unknown"),
        check_for_async=False,
    )
    reddit.read_only = True
    return reddit


def fetch(subreddits: list[str], limit: int = 60) -> list[dict]:
    """Return keyword-matching posts across all subreddits (normalised schema)."""
    reddit = _client()
    results: list[dict] = []

    for sub in subreddits:
        try:
            for post in reddit.subreddit(sub).new(limit=limit):
                blob = f"{post.title}\n{post.selftext or ''}"
                if not is_relevant(blob):
                    continue
                results.append(_normalise(post, sub))
        except Exception as exc:  # one bad sub shouldn't kill the whole run
            print(f"[reddit] r/{sub} failed: {exc}")

    return results


def _normalise(post, sub: str) -> dict:
    return {
        "id": post.id,
        "name": post.title,
        "url": f"https://www.reddit.com{post.permalink}",
        "source": f"r/{sub}",
        "author": f"u/{post.author}" if post.author else "u/[deleted]",
        "body": (post.selftext or "")[:1500],
        "date_found": datetime.now(timezone.utc).isoformat(),
    }
