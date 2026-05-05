"""
AI Agent – self-healing locators + failure analysis.
Both features use the plain OpenAI sync client — simple, no event loop conflicts.

Healer: fetches page HTML in the main thread, sends it to the LLM, returns a CSS selector.
Analyzer: sends error + stack trace to the LLM, returns a formatted analysis string.

Toggle in .env:
  AI_ENABLED=false                  → disables everything
  AI_SELF_HEALING_ENABLED=false     → disables only locator healing
  AI_FAILURE_ANALYSIS_ENABLED=false → disables only failure analysis
"""
from __future__ import annotations

import re
from datetime import datetime

from openai import OpenAI
from playwright.sync_api import Page  # type: ignore[import-untyped]

from utils.config_loader import config
from utils.logger import get_logger

logger = get_logger(__name__)


def _is_active(feature_flag: bool) -> bool:
    # Master switch (AI_ENABLED) must be on, plus the individual feature flag.
    return config.AI_ENABLED and feature_flag


# ── Feature 1 – Locator self-healing ─────────────────────────────────────────
#
# Uses plain OpenAI sync client — pydantic-ai's run_sync can't start an event
# loop inside an already-running Playwright context, so we use the sync client directly.

_sync_client: OpenAI | None = None


def _get_sync_client() -> OpenAI | None:
    global _sync_client
    if _sync_client is not None:
        return _sync_client
    if not config.AI_ENABLED:
        return None
    if config.OLLAMA_BASE_URL:
        _sync_client = OpenAI(base_url=config.OLLAMA_BASE_URL, api_key="ollama", timeout=config.AI_TIMEOUT)
    elif config.OPENAI_API_KEY and config.OPENAI_API_KEY != "your_key_here":
        _sync_client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=config.AI_TIMEOUT)
    else:
        logger.warning("[AI] No backend configured – set OLLAMA_BASE_URL or OPENAI_API_KEY")
    return _sync_client


def heal_locator(page: Page, description: str, broken_selector: str = "") -> str | None:
    if not _is_active(config.AI_SELF_HEALING_ENABLED):
        return None

    client = _get_sync_client()
    if client is None:
        return None

   

    # Fetch HTML in the main thread before calling the LLM
    try:
        html = page.content()
    except Exception as exc:
        logger.warning(f"[AI] Could not get page content: {exc}")
        return None

    # Extract data-test-id selectors from interactive elements
    test_ids = sorted(set(re.findall(
        r'<(?:button|input|a|div|li|section)\b[^>]*data-test-id=["\']([^"\']+)["\']',
        html,
    )))
    data_test_id_lines = [f'[data-test-id="{tid}"]' for tid in test_ids]

    # Also extract class-based selectors from interactive elements
    # (needed for elements with no data-test-id, e.g. search cards, close/remove buttons)
    class_candidates: set[str] = set()
    for tag in ("li", "button", "div", "a"):
        for classes_str in re.findall(rf'<{tag}\b[^>]*class=["\']([^"\']+)["\']', html):
            for cls in classes_str.split():
                if len(cls) < 5:
                    continue
                class_candidates.add(f'{tag}[class*="{cls}"]')
                # Strip CSS-module hash suffix (e.g. "final-price_3jX" → "final-price")
                # so the AI can match semantic names like div[class*="final-price"]
                semantic = re.sub(r'_[A-Za-z0-9]{3,}$', '', cls)
                if semantic and semantic != cls and len(semantic) >= 4:
                    class_candidates.add(f'{tag}[class*="{semantic}"]')

    candidates = "\n".join(data_test_id_lines) or "(none)"
    if class_candidates:
        candidates += "\n\nClass-based selectors (li / button / div / a):\n"
        candidates += "\n".join(sorted(class_candidates)[:60])

    logger.info(f"[AI] Healing locator for: '{description}'")
    try:
        response = client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[
                {"role": "system", "content": (
                    "You are a QA automation engineer fixing broken Playwright selectors. "
                    "The broken selector was deliberately broken by inserting 'BROKEN' or 'BROKEN-' "
                    "into the real selector. Always try removing 'BROKEN-' or 'BROKEN' from the "
                    "broken selector first — that often gives the real selector directly. "
                    "When the broken selector uses class*= matching, prefer class-based candidates. "
                    "Return ONLY the CSS selector — no explanation, no markdown, no code fences."
                )},
                {"role": "user", "content": (
                    f"Broken selector: '{broken_selector}'\n"
                    f"Element to find: {description}\n\n"
                    f"Available selectors on the page:\n{candidates}"
                )},
            ],
            max_tokens=100,
            temperature=0,
        )
        selector = response.choices[0].message.content.strip().strip("'\"` ")

        logger.info(f"[AI] Healed selector: {selector}")
        return selector
    except Exception as exc:
        logger.warning(f"[AI] Healing failed: {exc}")
        return None


# ── Feature 2 – Failure analysis ─────────────────────────────────────────────


def analyze_failure(error_message: str, stack_trace: str, screenshot_path: str | None = None) -> str:  # called by the pytest hook after every failed test
    if not _is_active(config.AI_FAILURE_ANALYSIS_ENABLED):
        return "[AI disabled] Failure analysis skipped."

    client = _get_sync_client()
    if client is None:
        return "[AI] No backend configured."

    logger.info("[AI] Requesting failure analysis …")
    try:
        response = client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a senior QA automation engineer. Be concise."},
                {"role": "user", "content": (
                    f"A Playwright test on terminalx.com failed.\n\n"
                    f"ERROR: {error_message}\n"
                    f"STACK: {stack_trace}\n"
                    f"SCREENSHOT: {screenshot_path or 'not available'}\n\n"
                    "Reply in exactly this format:\n"
                    "Root Cause: <one sentence>\n"
                    "Fix: <one sentence>\n"
                    "Prevention: <one sentence>\n"
                    "Confidence: Low | Medium | High"
                )},
            ],
            max_tokens=300,
            temperature=0,
        )
        analysis = response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning(f"[AI] Analysis failed: {exc}")
        analysis = "[AI] Analysis unavailable."

    report_path = config.AI_FAILURE_REPORT
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "a", encoding="utf-8") as fh:
            fh.write("=" * 72 + "\n")
            fh.write(f"ERROR: {error_message[:300]}\n\n")
            fh.write(f"AI ANALYSIS:\n{analysis}\n\n")
    except Exception as exc:
        logger.warning(f"[AI] Could not write report: {exc}")

    return analysis


# ── Shared – record healing events ───────────────────────────────────────────

def record_healing(  # appends one healing event to reports/self_healing_report.txt
    broken_selector: str,
    description: str,
    healed_selector: str | None,
    success: bool,
) -> None:
    report_path = config.AI_FAILURE_REPORT.parent / "self_healing_report.txt"
    status = "SUCCESS" if success else "FAILED"
    sep = "=" * 72
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = (
        f"{sep}\n"
        f"TIMESTAMP  : {ts}\n"
        f"DESCRIPTION: {description}\n"
        f"BROKEN     : {broken_selector}\n"
        f"HEALED     : {healed_selector or '(none)'}\n"
        f"RESULT     : {status}\n"
        f"{sep}\n\n"
    )
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "a", encoding="utf-8") as fh:
            fh.write(entry)
    except Exception as exc:
        logger.warning(f"[AI] Could not write healing report: {exc}")
