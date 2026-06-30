"""Fast, rule-based pre-filter — runs before any AI call to cut noise/cost."""
from pathlib import Path
import yaml

_CONFIG = None


def _config() -> dict:
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = yaml.safe_load((Path(__file__).parent.parent / "config.yaml").read_text())
    return _CONFIG


def is_blocked(text: str) -> bool:
    """True if the text contains any blocked_keyword (an obvious ad / non-lead)."""
    blocked = [b.lower() for b in _config().get("filters", {}).get("blocked_keywords", [])]
    t = (text or "").lower()
    return any(b in t for b in blocked)


def is_relevant(text: str) -> bool:
    """True if the post passes the keyword filters in config.yaml."""
    if is_blocked(text):
        return False

    required = [r.lower() for r in _config().get("filters", {}).get("required_keywords", [])]
    if not required:
        return True
    return any(r in (text or "").lower() for r in required)
