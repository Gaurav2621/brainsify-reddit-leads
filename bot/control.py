"""
Telegram-controlled site-wide search bot. Runs on a residential IP (your Mac).

You control it entirely from Telegram:
  /start  – begin auto-searching all of Reddit for clients (every N min)
  /stop   – pause searching (the bot stays online, just idle)
  /status – is it running? last scan? leads sent?
  /scan   – run one search right now

Run:  python -m bot.control   (kept alive by launchd — see SETUP)
"""
import json
import os
import threading
import time
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

load_dotenv()

from scraper.sources import reddit_search       # noqa: E402
from storage import telegram_sync               # noqa: E402

ROOT = Path(__file__).parent.parent
STATE_PATH = ROOT / "data" / "control.json"
SEEN_PATH = ROOT / "data" / "seen.local.json"

_config = yaml.safe_load((ROOT / "config.yaml").read_text())
SCAN_INTERVAL = int(_config.get("scan_interval_seconds", 600))
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

_lock = threading.Lock()
_scan_lock = threading.Lock()
_last_scan = [0.0]


# ── persistent on/off state ────────────────────────────────────────────────
def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"active": True, "sent": 0}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state))


_state = _load_state()


# ── dedup memory (separate from the GitHub bot's seen.json) ─────────────────
def _load_seen() -> set:
    if SEEN_PATH.exists():
        try:
            return set(json.loads(SEEN_PATH.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def _save_seen(seen: set) -> None:
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(seen, key=lambda i: (len(i), i))[-5000:]
    SEEN_PATH.write_text(json.dumps(ordered))


def _context() -> str:
    for name in ("context.local.md", "context.md"):
        p = ROOT / "profile" / name
        if p.exists():
            return p.read_text()
    return ""


# ── one search scan ─────────────────────────────────────────────────────────
def run_scan() -> int:
    """Search all of Reddit, score, and send new leads. Returns count sent."""
    if not _scan_lock.acquire(blocking=False):
        return 0  # a scan is already in progress
    try:
        items = reddit_search.fetch(_config.get("search_query", ""), limit=_config.get("scan_limit", 100))
        seen = _load_seen()
        fresh = [i for i in items if i["id"] not in seen]
        if not fresh:
            return 0

        if os.environ.get("GEMINI_API_KEY"):
            from ai.pipeline import analyse_batch
            fresh = analyse_batch(fresh, context=_context())

        min_score = _config.get("ai", {}).get("min_score", 0)
        sent = 0
        for item in fresh:
            if item.get("ai_failed"):
                continue
            if item.get("ai_score", 100) < min_score:
                seen.add(item["id"])
                continue
            if telegram_sync.send(item):
                seen.add(item["id"])
                sent += 1
                time.sleep(1)
        _save_seen(seen)
        return sent
    finally:
        _scan_lock.release()


# ── telegram command handling ────────────────────────────────────────────────
def _tg(method: str, payload: dict) -> dict:
    try:
        return requests.post(
            f"https://api.telegram.org/bot{TOKEN}/{method}", json=payload, timeout=40
        ).json()
    except requests.RequestException:
        return {}


def _reply(chat_id, text: str) -> None:
    _tg("sendMessage", {"chat_id": chat_id, "text": text})


def _handle(text: str, chat_id) -> None:
    cmd = text.lower().lstrip("/").split("@")[0].split()[0] if text.strip("/ ") else ""

    if cmd == "start":
        with _lock:
            _state["active"] = True
            _save_state(_state)
        _reply(chat_id, "✅ Search bot STARTED — hunting all of Reddit for clients every "
                        f"{SCAN_INTERVAL // 60} min. I'll ping you the moment I find one.")
    elif cmd == "stop":
        with _lock:
            _state["active"] = False
            _save_state(_state)
        _reply(chat_id, "⏸️ Search bot STOPPED. I'm still online — send /start anytime to resume.")
    elif cmd == "status":
        running = "🟢 running" if _state.get("active") else "🔴 stopped"
        ago = int(time.time() - _last_scan[0]) if _last_scan[0] else None
        last = f"{ago // 60}m {ago % 60}s ago" if ago is not None else "not yet"
        _reply(chat_id, f"Status: {running}\nLast scan: {last}\nLeads sent: {_state.get('sent', 0)}\n"
                        f"Scan interval: every {SCAN_INTERVAL // 60} min")
    elif cmd == "scan":
        _reply(chat_id, "🔍 Scanning all of Reddit now…")
        n = run_scan()
        _reply(chat_id, f"Done — {n} new lead(s) sent." if n else "Done — no new leads right now.")
    else:  # /help and anything else
        _reply(chat_id, "🤖 Brainsify client finder\n"
                        "/start – begin auto-search\n/stop – pause\n"
                        "/status – check state\n/scan – search right now")


def _poll_loop() -> None:
    offset = None
    while True:
        payload = {"timeout": 30, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        data = _tg("getUpdates", payload)
        for upd in data.get("result", []):
            offset = upd["update_id"] + 1
            msg = upd.get("message") or {}
            text = msg.get("text", "")
            chat_id = msg.get("chat", {}).get("id")
            if text.startswith("/") and chat_id:
                try:
                    _handle(text, chat_id)
                except Exception as exc:
                    print(f"[control] command error: {exc}")


def _scan_loop() -> None:
    while True:
        with _lock:
            active = _state.get("active", False)
        if active and (time.time() - _last_scan[0]) >= SCAN_INTERVAL:
            _last_scan[0] = time.time()
            try:
                n = run_scan()
                if n:
                    with _lock:
                        _state["sent"] = _state.get("sent", 0) + n
                        _save_state(_state)
                    print(f"[control] scan sent {n} lead(s)")
            except Exception as exc:
                print(f"[control] scan error: {exc}")
        time.sleep(5)


def main() -> None:
    # Register the command menu so the buttons show up in Telegram.
    _tg("setMyCommands", {"commands": [
        {"command": "start", "description": "Start auto-searching for clients"},
        {"command": "stop", "description": "Pause searching"},
        {"command": "status", "description": "Check bot status"},
        {"command": "scan", "description": "Search Reddit right now"},
    ]})
    state = "running 🟢" if _state.get("active") else "stopped 🔴"
    telegram_sync.notify(f"🤖 Brainsify client finder is online ({state}).\n"
                         "Send /status, /stop to pause, /start to resume.")
    threading.Thread(target=_scan_loop, daemon=True).start()
    _poll_loop()


if __name__ == "__main__":
    main()
