"""Persist pending leads so a button tap can find the right draft (survives restarts)."""
import json
import threading
from pathlib import Path

ROOT = Path(__file__).parent.parent
PENDING = ROOT / "data" / "pending.json"
_lock = threading.Lock()


def _load() -> dict:
    if PENDING.exists():
        try:
            return json.loads(PENDING.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save(data: dict) -> None:
    PENDING.parent.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(json.dumps(data, indent=2))


def add_pending(lead: dict) -> None:
    with _lock:
        data = _load()
        data[lead["id"]] = lead
        _save(data)


def get_pending(lead_id: str) -> dict | None:
    with _lock:
        return _load().get(lead_id)


def remove_pending(lead_id: str) -> None:
    with _lock:
        data = _load()
        data.pop(lead_id, None)
        _save(data)
