from __future__ import annotations

import functools
import json
import re
import time
from pathlib import Path

from playwright.sync_api import Page

from utils.logger import get_logger

logger = get_logger(__name__)


def parse_price(text: str) -> float:
    """Turn '₪1,234' or '499.90' into a float. Returns 0.0 if it can't parse."""
    if not text:
        return 0.0
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    # Edge case: multiple dots like "1.234.56" — keep only first segment
    if cleaned.count(".") > 1:
        cleaned = cleaned.split(".")[0]
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def retry(max_attempts=3, delay=1.5, exceptions=(Exception,)):
    """Decorator: re-run a function up to max_attempts times if it raises."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = RuntimeError("No attempts made")
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    logger.warning(f"[retry] {func.__name__} attempt {attempt}/{max_attempts}: {exc}")
                    if attempt < max_attempts:
                        time.sleep(delay)
            raise last_exc
        return wrapper
    return decorator


def take_screenshot(page: Page, name: str, screenshot_dir: Path) -> Path:
    # Saves a full-page PNG with a timestamp in the name. Never raises — returns path regardless.
    screenshot_dir = Path(screenshot_dir)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = screenshot_dir / f"{name}_{ts}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        logger.info(f"Screenshot saved → {path}")
    except Exception as exc:
        logger.warning(f"Screenshot failed: {exc}")
    return path


def load_json(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
