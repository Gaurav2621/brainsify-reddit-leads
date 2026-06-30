"""
Orchestrator: scan Reddit -> dedup -> AI score + draft -> Telegram alert.
Run:  python -m scraper.main
"""
import json
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from storage import telegram_sync           # noqa: E402

ROOT = Path(__file__).parent.parent
SEEN_PATH = ROOT / "data" / "seen.json"


def load_seen() -> set:
    if SEEN_PATH.exists():
        try:
            return set(json.loads(SEEN_PATH.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def save_seen(seen: set) -> None:
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Keep the file bounded so it doesn't grow forever.
    SEEN_PATH.write_text(json.dumps(sorted(seen)[-5000:], indent=2))


def main() -> None:
    config = yaml.safe_load((ROOT / "config.yaml").read_text())
    subs = config.get("subreddits", [])
    min_score = config.get("ai", {}).get("min_score", 0)

    # Pick the data source. "rss" needs no Reddit app; "api" uses logged-in PRAW.
    if config.get("source", "rss") == "api":
        from scraper.sources import reddit as source
    else:
        from scraper.sources import reddit_rss as source

    items = source.fetch(subs, limit=config.get("scan_limit", 60))
    print(f"Fetched {len(items)} keyword-matching posts")

    seen = load_seen()
    fresh = [i for i in items if i["id"] not in seen]
    print(f"{len(fresh)} new after dedup")
    if not fresh:
        return

    if config.get("ai", {}).get("enabled") and os.environ.get("GEMINI_API_KEY"):
        from ai.pipeline import analyse_batch
        ctx_path = ROOT / "profile" / "context.md"
        context = ctx_path.read_text() if ctx_path.exists() else ""
        fresh = analyse_batch(fresh, context=context)
    else:
        print("[AI] disabled or GEMINI_API_KEY missing — sending raw posts")

    sent = 0
    for item in fresh:
        seen.add(item["id"])  # mark seen regardless so we don't re-evaluate
        if item.get("ai_score", 100) < min_score:
            continue
        if telegram_sync.send(item):
            sent += 1

    save_seen(seen)
    print(f"Done — {sent} lead(s) sent to Telegram")


if __name__ == "__main__":
    main()
