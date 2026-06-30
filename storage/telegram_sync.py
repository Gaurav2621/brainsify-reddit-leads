"""Push each lead to your Telegram as a ready-to-act message."""
import os
import time

import requests

MAX_LEN = 4000  # Telegram hard limit is 4096; stay safely under it.


def _post(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("[telegram] missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
        return False

    if len(text) > MAX_LEN:
        text = text[: MAX_LEN - 12] + "\n… (cut)"

    for attempt in range(3):
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "disable_web_page_preview": False},
                timeout=15,
            )
        except requests.RequestException as exc:
            print(f"[telegram] send error: {type(exc).__name__}")
            return False

        if resp.status_code == 200:
            return True
        if resp.status_code == 429:
            retry_after = 2
            try:
                retry_after = int(resp.json().get("parameters", {}).get("retry_after", 2))
            except (ValueError, KeyError, requests.JSONDecodeError):
                pass
            print(f"[telegram] 429 — retrying in {retry_after}s")
            time.sleep(min(retry_after, 30))
            continue
        # Never print resp.text blindly — it could echo the token-bearing URL.
        print(f"[telegram] HTTP {resp.status_code}")
        return False

    return False


def send(item: dict) -> bool:
    """Send one lead to Telegram. Plain text (Reddit titles break Markdown)."""
    return _post(_format(item))


def notify(text: str) -> bool:
    """Send a plain status message (e.g. an AI-unavailable heads-up)."""
    return _post(text)


def _format(item: dict) -> str:
    score = item.get("ai_score", "—")
    draft = item.get("ai_draft") or "(no draft — open the post and reply manually)"
    return (
        f"🎯 NEW LEAD · {item.get('source')} · score {score}/100\n"
        f"by {item.get('author', '?')}\n\n"
        f"📌 {item.get('name')}\n"
        f"{item.get('ai_summary', '')}\n\n"
        f"✍️ Draft (copy, tweak, send):\n"
        f"{draft}\n\n"
        f"🔗 {item.get('url')}"
    )
