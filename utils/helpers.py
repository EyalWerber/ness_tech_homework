from __future__ import annotations

import functools
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Tuple, Type, TypeVar

from playwright.sync_api import Page

from utils.logger import get_logger

logger = get_logger(__name__)
F = TypeVar("F", bound=Callable[..., Any])


def parse_price(text: str) -> float:
    """
    Extract a numeric price from strings like:
        '₪1,234'  →  1234.0
        '499.90'  →  499.9
        '1,299'   →  1299.0
    Returns 0.0 on failure.
    """
    if not text:
        return 0.0
    # Strip currency symbols (₪, ILS, $) and whitespace, keep digits and dot
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    if not cleaned or cleaned.count(".") > 1:
        cleaned = cleaned.split(".")[0] if "." in cleaned else cleaned
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        logger.warning(f"parse_price: could not parse '{text}' → 0.0")
        return 0.0


def retry(
    max_attempts: int = 3,
    delay: float = 1.5,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception = RuntimeError("No attempts made")
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    logger.warning(
                        f"[retry] {func.__name__} attempt {attempt}/{max_attempts}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    if attempt < max_attempts:
                        time.sleep(delay)
            raise last_exc
        return wrapper  # type: ignore[return-value]
    return decorator


def take_screenshot(page: Page, name: str, screenshot_dir: Path) -> Path:
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
