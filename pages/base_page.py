from __future__ import annotations

import allure
from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeout

import utils.ai_agent as ai_agent
from utils.config_loader import config
from utils.logger import get_logger

logger = get_logger(__name__)


class BasePage:
    def __init__(self, page: Page) -> None:
        self.page = page
        self._timeout = config.REQUEST_TIMEOUT  # 0 = no timeout

    # ── Navigation ────────────────────────────────────────────────────────────

    def navigate(self, url: str) -> None:
        logger.info(f"Navigating → {url}")
        self.page.goto(url, wait_until="domcontentloaded", timeout=self._timeout)

    # ── Locator ───────────────────────────────────────────────────────────────

    def _loc(self, selector: str) -> Locator:
        return self.page.locator(selector)

    def _try_heal(self, selector: str, description: str, action: str, fill_value: str | None = None) -> bool:
        try:
            html = self.page.content()
        except Exception:
            return False

        healed = ai_agent.heal_locator(html, description)
        if not healed:
            return False

        try:
            loc = self._loc(healed).first
            loc.wait_for(state="visible", timeout=self._timeout)
            if action == "click":
                loc.click()
            elif action == "fill" and fill_value is not None:
                loc.fill(fill_value)
            logger.info(f"[self-heal] SUCCESS: {healed}")
            return True
        except Exception as exc:
            logger.warning(f"[self-heal] Healed selector also failed ({healed}): {exc}")
            return False

    # ── Actions ───────────────────────────────────────────────────────────────

    def click(self, selector: str, description: str = "") -> None:
        desc = description or selector
        try:
            loc = self._loc(selector).first
            loc.wait_for(state="visible", timeout=self._timeout)
            loc.click()
        except (PlaywrightTimeout, Exception) as exc:
            logger.warning(f"[click] Failed '{selector}': {exc}")
            with allure.step(f"[AI] Self-healing click – {desc}"):
                if not self._try_heal(selector, desc, "click"):
                    raise

    def fill(self, selector: str, value: str, description: str = "") -> None:
        desc = description or selector
        try:
            loc = self._loc(selector).first
            loc.wait_for(state="visible", timeout=self._timeout)
            loc.fill(value)
        except (PlaywrightTimeout, Exception) as exc:
            logger.warning(f"[fill] Failed '{selector}': {exc}")
            with allure.step(f"[AI] Self-healing fill – {desc}"):
                if not self._try_heal(selector, desc, "fill", value):
                    raise

    # ── Utilities ─────────────────────────────────────────────────────────────

    def wait_for_selector(self, selector: str, state: str = "visible") -> None:
        self._loc(selector).first.wait_for(state=state, timeout=self._timeout)

    def is_visible(self, selector: str) -> bool:
        try:
            return self._loc(selector).first.is_visible()
        except Exception:
            return False

    def get_text(self, selector: str) -> str:
        return self._loc(selector).inner_text()

    def count(self, selector: str) -> int:
        try:
            return self._loc(selector).count()
        except Exception:
            return 0
