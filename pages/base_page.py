from __future__ import annotations

import allure
from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeout

import utils.ai_agent as ai_agent
from utils.config_loader import config
from utils.logger import get_logger
from utils import selector_store

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
        # Ask the AI to find a working selector, try the action again, and save it to selectors.json if it works.
        healed = ai_agent.heal_locator(self.page, description, broken_selector=selector)
        if not healed:
            ai_agent.record_healing(selector, description, healed_selector=None, success=False)
            return False

        # Try the healed selector — keep record_healing outside the try so write_back can't cause a double-write.
        success = False
        try:
            loc = self._loc(healed).first
            # Use "attached" so hidden-until-hover elements (e.g. remove buttons) still verify.
            # force=True on click bypasses the visibility check for the same reason.
            loc.wait_for(state="attached", timeout=8_000)
            if action == "click":
                loc.click(force=True)
            elif action == "fill" and fill_value is not None:
                loc.fill(fill_value)
            success = True
        except Exception as exc:
            logger.warning(f"[self-heal] Healed selector also failed ({healed}): {exc}")

        ai_agent.record_healing(selector, description, healed_selector=healed, success=success)
        if success:
            logger.info(f"[self-heal] SUCCESS: {healed}")
            try:
                selector_store.write_back(selector, healed)
            except Exception:
                pass
        return success

    # ── Actions ───────────────────────────────────────────────────────────────

    # With timeout=0 (infinite), a broken selector hangs forever and healing never fires.
    # Cap it at 15s so failures surface quickly and the AI healer gets a chance to run.
    _HEAL_ATTEMPT_TIMEOUT = 15_000

    @property
    def _action_timeout(self) -> int:
        return self._timeout or self._HEAL_ATTEMPT_TIMEOUT

    def click(self, selector: str, description: str = "") -> None:
        desc = description or selector
        try:
            loc = self._loc(selector).first
            loc.wait_for(state="visible", timeout=self._action_timeout)
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
            loc.wait_for(state="visible", timeout=self._action_timeout)
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

    def ensure_any(self, selector: str, description: str = "") -> str:
        """Return a selector that matches ≥1 element, healing via AI if needed. Raises if healing fails."""
        if self.count(selector) > 0:
            return selector
        desc = description or selector
        logger.warning(f"[ensure_any] No elements for '{selector}' – attempting heal")
        with allure.step(f"[AI] Self-healing find – {desc}"):
            healed = ai_agent.heal_locator(self.page, desc, broken_selector=selector)
            if healed and self.count(healed) > 0:
                ai_agent.record_healing(selector, desc, healed_selector=healed, success=True)
                try:
                    selector_store.write_back(selector, healed)
                except Exception:
                    pass
                logger.info(f"[self-heal] SUCCESS: {healed}")
                return healed
            ai_agent.record_healing(selector, desc, healed_selector=healed, success=False)
        raise AssertionError(
            f"No elements found for '{selector}' and healing failed."
        )
