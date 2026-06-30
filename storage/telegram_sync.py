"""Push each lead to your Telegram as a ready-to-act message."""
import os

import requests


def send(item: dict) -> bool:
    """Send one lead to Telegram. Plain text (Reddit titles break Markdown)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("[telegram] missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
        return False

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": _format(item),
                "disable_web_page_preview": False,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"[telegram] HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.status_code == 200
    except requests.RequestException as exc:
        print(f"[telegram] send failed: {exc}")
        return False


def _format(item: dict) -> str:
    score = item.get("ai_score", "—")
    draft = item.get("ai_draft") or "(no draft — review the post yourself)"
    return (
        f"🎯 NEW LEAD · {item.get('source')} · score {score}/100\n"
        f"by {item.get('author', '?')}\n\n"
        f"📌 {item.get('name')}\n"
        f"{item.get('ai_summary', '')}\n\n"
        f"✍️ Draft reply (copy, tweak, send):\n"
        f"{draft}\n\n"
        f"🔗 {item.get('url')}"
    )
