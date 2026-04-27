"""
SelectorStore – loads data/selectors.json and provides selectors to page objects.

Usage in page files:
    from utils.selector_store import sel
    EMAIL_INPUT = sel("login", "email_input", fallback="input[type='email']")

If selectors.json doesn't exist yet, the fallback is always returned.
Run `python discover_selectors.py` to generate the file.
"""

from __future__ import annotations

import json
from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)

_SELECTORS_FILE = Path("data/selectors.json")
_store: dict = {}


def _load():
    global _store
    if _SELECTORS_FILE.exists():
        try:
            _store = json.loads(_SELECTORS_FILE.read_text(encoding="utf-8"))
            logger.info(f"[selector-store] Loaded {_SELECTORS_FILE}")
        except Exception as exc:
            logger.warning(f"[selector-store] Failed to load {_SELECTORS_FILE}: {exc}")
            _store = {}
    else:
        logger.warning(
            f"[selector-store] {_SELECTORS_FILE} not found – using hardcoded fallbacks. "
            "Run: python discover_selectors.py"
        )


_load()


def sel(page: str, key: str, fallback: str = "") -> str:
    """Return the discovered selector for *page*/*key*, or *fallback* if missing."""
    return _store.get(page, {}).get(key) or fallback


def reload():
    """Re-read selectors.json from disk (call after running discovery)."""
    _load()
