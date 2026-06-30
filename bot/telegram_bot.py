"""Telegram: send each lead with action buttons, and long-poll for button taps."""
import os

import requests

_API = "https://api.telegram.org/bot{token}/{method}"


def _token() -> str:
    return os.environ["TELEGRAM_BOT_TOKEN"]


def _call(method: str, payload: dict) -> dict:
    try:
        resp = requests.post(
            _API.format(token=_token(), method=method), json=payload, timeout=40
        )
        if not resp.ok:
            print(f"[telegram] {method} HTTP {resp.status_code}: {resp.text[:200]}")
            return {}
        return resp.json()
    except requests.RequestException as exc:
        print(f"[telegram] {method} error: {exc}")
        return {}


def send_lead(item: dict) -> None:
    """Send a lead with Comment / DM / Skip buttons."""
    lead_id = item["id"]
    keyboard = {
        "inline_keyboard": [[
            {"text": "💬 Comment", "callback_data": f"c:{lead_id}"},
            {"text": "✉️ DM author", "callback_data": f"d:{lead_id}"},
            {"text": "🗑 Skip", "callback_data": f"x:{lead_id}"},
        ]]
    }
    _call("sendMessage", {
        "chat_id": os.environ["TELEGRAM_CHAT_ID"],
        "text": _format(item),
        "reply_markup": keyboard,
        "disable_web_page_preview": False,
    })


def poll(handler, offset_holder: list) -> None:
    """Long-poll getUpdates and dispatch callback_query updates to `handler`."""
    payload = {"timeout": 30, "allowed_updates": ["callback_query"]}
    if offset_holder[0] is not None:
        payload["offset"] = offset_holder[0]

    resp = _call("getUpdates", payload)
    for upd in resp.get("result", []):
        offset_holder[0] = upd["update_id"] + 1
        if cq := upd.get("callback_query"):
            handler(cq)


def answer_callback(cq_id: str, text: str = "") -> None:
    _call("answerCallbackQuery", {"callback_query_id": cq_id, "text": text[:200]})


def edit_message(chat_id, message_id, text: str) -> None:
    _call("editMessageText", {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "disable_web_page_preview": True,
    })


def _format(item: dict) -> str:
    score = item.get("ai_score", "—")
    draft = item.get("ai_draft") or "(no draft — open the post and reply manually)"
    return (
        f"🎯 NEW LEAD · {item.get('source')} · score {score}/100\n"
        f"by {item.get('author', '?')}\n\n"
        f"📌 {item.get('name')}\n"
        f"{item.get('ai_summary', '')}\n\n"
        f"✍️ Draft:\n{draft}\n\n"
        f"🔗 {item.get('url')}"
    )
