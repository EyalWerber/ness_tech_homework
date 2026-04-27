from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=True)


class Config:
    # ── AI ────────────────────────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "qwen2.5")
    AI_TIMEOUT: int = int(os.getenv("AI_TIMEOUT", "15"))

    AI_ENABLED: bool = os.getenv("AI_ENABLED", "false").lower() == "true"
    AI_SELF_HEALING_ENABLED: bool = os.getenv("AI_SELF_HEALING_ENABLED", "true").lower() == "true"
    AI_FAILURE_ANALYSIS_ENABLED: bool = os.getenv("AI_FAILURE_ANALYSIS_ENABLED", "true").lower() == "true"

    # ── Browser ───────────────────────────────────────────────────────────────
    BROWSER: str = os.getenv("BROWSER", "chromium")
    HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"
    # 0 = no timeout (Playwright native behaviour)
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "0"))
    # milliseconds added between every Playwright action (0 = no delay)
    SLOW_MO: int = int(os.getenv("SLOW_MO", "700"))

    # ── Paths ─────────────────────────────────────────────────────────────────
    SCREENSHOT_DIR: Path = Path(os.getenv("SCREENSHOT_DIR", "reports/screenshots"))
    AI_FAILURE_REPORT: Path = Path("reports/ai_failure_analysis.txt")

    # ── Credentials ───────────────────────────────────────────────────────────
    TERMINALX_USERNAME: str = os.getenv("TERMINALX_USERNAME", "")
    TERMINALX_PASSWORD: str = os.getenv("TERMINALX_PASSWORD", "")
    SESSION_STATE_PATH: Path = Path(os.getenv("SESSION_STATE_PATH", "reports/session_state.json"))

    # ── Site ──────────────────────────────────────────────────────────────────
    BASE_URL: str = "https://www.terminalx.com"


config = Config()
