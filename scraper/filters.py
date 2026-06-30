"""Fast, rule-based pre-filter — runs before any AI call to cut noise/cost."""
from pathlib import Path
import yaml

_CONFIG = None


def _config() -> dict:
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = yaml.safe_load((Path(__file__).parent.parent / "config.yaml").read_text())
    return _CONFIG


def is_relevant(text: str) -> bool:
    """True if the post text passes the keyword filters in config.yaml."""
    filters = _config().get("filters", {})
    t = (text or "").lower()

    blocked = [b.lower() for b in filters.get("blocked_keywords", [])]
    if any(b in t for b in blocked):
        return False

    required = [r.lower() for r in filters.get("required_keywords", [])]
    if not required:
        return True
    return any(r in t for r in required)
