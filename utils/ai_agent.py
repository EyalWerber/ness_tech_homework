"""
AI Agent – self-healing locators + failure analysis.

Toggle in .env:
  AI_ENABLED=false                  → disables everything
  AI_SELF_HEALING_ENABLED=false     → disables only locator healing
  AI_FAILURE_ANALYSIS_ENABLED=false → disables only failure analysis
"""

from __future__ import annotations

import textwrap
from typing import Optional

from utils.config_loader import config
from utils.logger import get_logger

logger = get_logger(__name__)

_client = None


def _is_active(feature_flag: bool) -> bool:
    return config.AI_ENABLED and feature_flag


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not config.AI_ENABLED:
        return None
    try:
        from openai import OpenAI

        if config.OLLAMA_BASE_URL:
            _client = OpenAI(base_url=config.OLLAMA_BASE_URL, api_key="ollama")
            logger.info(f"[AI] Ollama client → {config.OLLAMA_BASE_URL} ({config.MODEL_NAME})")
        elif config.OPENAI_API_KEY and config.OPENAI_API_KEY != "your_key_here":
            _client = OpenAI(api_key=config.OPENAI_API_KEY)
            logger.info(f"[AI] OpenAI client ({config.MODEL_NAME})")
        else:
            logger.warning("[AI] No backend configured – set OLLAMA_BASE_URL or OPENAI_API_KEY")
    except ImportError:
        logger.warning("[AI] 'openai' package not installed.")
    except Exception as exc:
        logger.warning(f"[AI] Client init failed: {exc}")
    return _client


def _chat(prompt: str, system: str = "You are a senior QA automation engineer.") -> Optional[str]:
    client = _get_client()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            timeout=config.AI_TIMEOUT,
            max_tokens=512,
            temperature=0,
        )
        text = response.choices[0].message.content
        return text.strip() if text else None
    except Exception as exc:
        logger.warning(f"[AI] Call failed: {type(exc).__name__}: {exc}")
        return None


# ── Feature 1 – Locator self-healing ─────────────────────────────────────────

_MAX_HTML_CHARS = 8_000


def heal_locator(html: str, description: str) -> Optional[str]:
    if not _is_active(config.AI_SELF_HEALING_ENABLED):
        return None

    trimmed = html[:_MAX_HTML_CHARS]
    prompt = textwrap.dedent(f"""
        A Playwright test on terminalx.com failed to locate an element.

        ELEMENT DESCRIPTION: {description}

        PAGE HTML (truncated):
        {trimmed}

        RULES:
        - Return ONLY the CSS or XPath selector, nothing else.
        - Prefer data-testid, aria-label, id, then stable class names.
        - Must work with Playwright's page.locator().
        - No surrounding quotes or backticks.
    """).strip()

    logger.info(f"[AI] Healing locator for: '{description}'")
    result = _chat(prompt)
    if result:
        result = result.strip().strip("'\"` ")
        logger.info(f"[AI] Suggested selector: {result}")
    return result or None


# ── Feature 2 – Failure analysis ─────────────────────────────────────────────

def analyze_failure(
    error_message: str,
    stack_trace: str,
    screenshot_path: Optional[str] = None,
) -> str:
    if not _is_active(config.AI_FAILURE_ANALYSIS_ENABLED):
        return "[AI disabled] Failure analysis skipped."

    prompt = textwrap.dedent(f"""
        A Playwright automation test on terminalx.com has failed.

        ERROR: {error_message}
        STACK TRACE: {stack_trace}
        SCREENSHOT: {screenshot_path or "not available"}

        Provide:
        1. Root Cause (2-3 sentences)
        2. Most Likely Fix (actionable steps)
        3. Prevention (make the test more resilient)
        4. Confidence (Low / Medium / High + reason)
    """).strip()

    logger.info("[AI] Requesting failure analysis …")
    analysis = _chat(prompt) or "[AI] Analysis unavailable."

    report_path = config.AI_FAILURE_REPORT
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "a", encoding="utf-8") as fh:
            fh.write("=" * 72 + "\n")
            fh.write(f"ERROR    : {error_message[:300]}\n")
            fh.write(f"SCREENSHOT: {screenshot_path or 'N/A'}\n\n")
            fh.write("AI ANALYSIS:\n")
            fh.write(analysis + "\n\n")
        logger.info(f"[AI] Analysis saved → {report_path}")
    except Exception as exc:
        logger.warning(f"[AI] Could not write report: {exc}")

    return analysis
