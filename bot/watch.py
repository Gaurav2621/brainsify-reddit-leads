"""
Always-on watcher: live-streams Reddit, AI-scores + drafts a reply, and pushes
each lead to Telegram with one-tap action buttons.

Run:  python -m bot.watch   (keep it running — see README for staying alive 24/7)
"""
import os
import threading
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from bot import reddit_actions, store, telegram_bot   # noqa: E402
from scraper.filters import is_relevant               # noqa: E402

ROOT = Path(__file__).parent.parent


def _config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def _enrich(item: dict, context: str) -> dict:
    """Score + draft via Gemini if available; otherwise pass through."""
    if os.environ.get("GEMINI_API_KEY"):
        from ai.pipeline import analyse_batch
        return analyse_batch([item], context=context)[0]
    return {**item, "ai_score": 100, "ai_summary": "", "ai_draft": ""}


def stream_reddit(config: dict, context: str) -> None:
    reddit = reddit_actions.client()
    min_score = config.get("ai", {}).get("min_score", 0)

    subs = reddit_actions.valid_subreddits(config.get("subreddits", []))
    if not subs:
        print("[watch] no valid subreddits — check config.yaml")
        return
    multi = "+".join(subs)
    print(f"[watch] logged in as u/{reddit.user.me()} — streaming {len(subs)} subs live…")

    for submission in reddit.subreddit(multi).stream.submissions(skip_existing=True):
        try:
            blob = f"{submission.title}\n{submission.selftext or ''}"
            if not is_relevant(blob):
                continue

            item = _enrich({
                "id": submission.id,
                "name": submission.title,
                "url": f"https://www.reddit.com{submission.permalink}",
                "source": f"r/{submission.subreddit.display_name}",
                "author": f"u/{submission.author}" if submission.author else "u/[deleted]",
                "body": (submission.selftext or "")[:1500],
            }, context)

            if item.get("ai_score", 100) < min_score:
                continue

            store.add_pending({
                "id": item["id"],
                "post_id": item["id"],
                "author": str(submission.author) if submission.author else "",
                "url": item["url"],
                "title": item["name"],
                "draft": item.get("ai_draft", ""),
            })
            telegram_bot.send_lead(item)
            print(f"[watch] lead → {item.get('ai_score')} · {item['name'][:60]}")

        except Exception as exc:
            print(f"[watch] submission error: {exc}")
            time.sleep(2)


def handle_callback(cq: dict) -> None:
    data = cq.get("data", "")
    chat_id = cq["message"]["chat"]["id"]
    message_id = cq["message"]["message_id"]
    cq_id = cq["id"]

    action, _, lead_id = data.partition(":")
    lead = store.get_pending(lead_id)
    if not lead:
        telegram_bot.answer_callback(cq_id, "Expired or already handled")
        return

    try:
        if action == "x":
            telegram_bot.answer_callback(cq_id, "Skipped")
            telegram_bot.edit_message(chat_id, message_id, f"🗑 Skipped\n{lead['url']}")

        elif action == "c":
            link = reddit_actions.post_comment(lead["post_id"], lead["draft"])
            telegram_bot.answer_callback(cq_id, "Comment posted ✅")
            telegram_bot.edit_message(chat_id, message_id, f"✅ Commented\n{link}")

        elif action == "d":
            if not lead.get("author"):
                telegram_bot.answer_callback(cq_id, "No author to DM")
                return
            reddit_actions.send_dm(lead["author"], "About your post", lead["draft"])
            telegram_bot.answer_callback(cq_id, "DM sent ✅")
            telegram_bot.edit_message(chat_id, message_id, f"✅ DM sent to u/{lead['author']}\n{lead['url']}")

        store.remove_pending(lead_id)

    except Exception as exc:
        telegram_bot.answer_callback(cq_id, f"Failed: {exc}")
        print(f"[watch] action '{action}' failed: {exc}")


def telegram_loop() -> None:
    offset = [None]
    while True:
        try:
            telegram_bot.poll(handle_callback, offset)
        except Exception as exc:
            print(f"[watch] telegram loop error: {exc}")
            time.sleep(5)


def main() -> None:
    config = _config()
    ctx_path = ROOT / "profile" / "context.md"
    context = ctx_path.read_text() if ctx_path.exists() else ""

    threading.Thread(target=telegram_loop, daemon=True).start()

    while True:  # auto-reconnect if the Reddit stream drops
        try:
            stream_reddit(config, context)
        except Exception as exc:
            print(f"[watch] stream dropped, reconnecting in 30s: {exc}")
            time.sleep(30)


if __name__ == "__main__":
    main()
