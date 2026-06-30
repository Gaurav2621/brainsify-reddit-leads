"""
Orchestrator: scan Reddit -> dedup -> AI score + draft -> Telegram alert.
Run:  python -m scraper.main

Source modes (config.yaml `source:`):
  rss    -> watch your subreddits' /new feeds (no app)
  search -> site-wide keyword search (no app)
  hybrid -> both, deduped (recommended)
  api    -> logged-in PRAW (needs a Reddit app)
"""
import json
import os
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from storage import telegram_sync           # noqa: E402

ROOT = Path(__file__).parent.parent
# SEEN_FILE env lets a second runner (e.g. the local Mac search job) keep its own
# dedup memory without clobbering the git-tracked seen.json used by GitHub Actions.
SEEN_PATH = Path(os.environ["SEEN_FILE"]) if os.environ.get("SEEN_FILE") else ROOT / "data" / "seen.json"
STATE_PATH = ROOT / "data" / "state.json"
SEND_DELAY = 1.0          # seconds between Telegram sends (avoid per-chat rate limit)
AI_ALERT_EVERY = 3600     # at most one "AI unavailable" heads-up per hour


def load_seen() -> set:
    if SEEN_PATH.exists():
        try:
            return set(json.loads(SEEN_PATH.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def save_seen(seen: set) -> None:
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Keep newest ~5000 by Reddit's base36 ids (longer id => newer, then lexical).
    ordered = sorted(seen, key=lambda i: (len(i), i))[-5000:]
    SEEN_PATH.write_text(json.dumps(ordered, indent=2))


def _load_context() -> str:
    # Prefer a gitignored local file so real contact details never hit the public repo.
    for name in ("context.local.md", "context.md"):
        p = ROOT / "profile" / name
        if p.exists():
            return p.read_text()
    return ""


def _gather(config: dict) -> list[dict]:
    subs = config.get("subreddits", [])
    limit = config.get("scan_limit", 100)
    src = config.get("source", "rss")
    items: list[dict] = []

    if src == "api":
        from scraper.sources import reddit
        return reddit.fetch(subs, limit=limit)

    if src in ("rss", "hybrid"):
        from scraper.sources import reddit_rss
        items += reddit_rss.fetch(subs, limit=limit)
    if src in ("search", "hybrid"):
        from scraper.sources import reddit_search
        items += reddit_search.fetch(config.get("search_query", ""), limit=limit)

    # Deduplicate across sources by post id.
    uniq: dict[str, dict] = {}
    for it in items:
        uniq.setdefault(it["id"], it)
    return list(uniq.values())


def _maybe_alert_ai_down(n_failed: int) -> None:
    """Tell the user once/hour when AI scoring is unavailable (e.g. quota exhausted)."""
    now = time.time()
    state = {}
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            state = {}
    if now - state.get("last_ai_alert", 0) < AI_ALERT_EVERY:
        return
    telegram_sync.notify(
        f"⚠️ AI scoring is unavailable right now — {n_failed} lead(s) held and will "
        f"be retried automatically. Likely Gemini quota/rate limit (resets daily)."
    )
    state["last_ai_alert"] = now
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state))


def main() -> None:
    config = yaml.safe_load((ROOT / "config.yaml").read_text())
    min_score = config.get("ai", {}).get("min_score", 0)

    items = _gather(config)
    print(f"Fetched {len(items)} keyword-matching posts")

    seen = load_seen()
    fresh = [i for i in items if i["id"] not in seen]
    print(f"{len(fresh)} new after dedup")
    if not fresh:
        return

    if config.get("ai", {}).get("enabled") and os.environ.get("GEMINI_API_KEY"):
        from ai.pipeline import analyse_batch
        fresh = analyse_batch(fresh, context=_load_context())
    else:
        print("[AI] disabled or GEMINI_API_KEY missing — sending raw posts")

    sent = 0
    failed = 0
    for item in fresh:
        # AI couldn't score it -> HOLD: do NOT mark seen, so it retries next run.
        if item.get("ai_failed"):
            failed += 1
            continue
        # Genuinely below the bar -> mark seen (evaluated; conserves AI quota).
        if item.get("ai_score", 100) < min_score:
            seen.add(item["id"])
            continue
        # A real lead: only mark seen once Telegram actually accepted it, so a
        # transient send failure is retried next run instead of lost.
        if telegram_sync.send(item):
            seen.add(item["id"])
            sent += 1
            time.sleep(SEND_DELAY)

    save_seen(seen)
    print(f"Done — {sent} sent, {failed} held (AI unavailable)")

    if failed and sent == 0:
        _maybe_alert_ai_down(failed)


if __name__ == "__main__":
    main()
