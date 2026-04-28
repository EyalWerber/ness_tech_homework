"""
All selectors live in data/selectors.json.
If the AI healer finds a better selector, write_back() saves it there.
Next run picks up the updated value automatically.
"""

import json
from pathlib import Path

_FILE = Path("data/selectors.json")
_store: dict = {}


def _load():
    global _store
    if _FILE.exists():
        _store = json.loads(_FILE.read_text(encoding="utf-8"))


_load()  # runs once at import time


def sel(page: str, key: str) -> str:
    """Look up a selector from selectors.json by page + key."""
    return _store.get(page, {}).get(key, "")


def write_back(broken: str, healed: str) -> bool:
    """Scan selectors.json for the broken value, replace it, and save the file."""
    for page, keys in _store.items():
        for key, value in keys.items():
            if value == broken:
                _store[page][key] = healed
                _FILE.write_text(json.dumps(_store, ensure_ascii=False, indent=2), encoding="utf-8")
                return True
    return False  # broken selector wasn't from selectors.json (e.g. a test-injected broken one)
