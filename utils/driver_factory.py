from __future__ import annotations

import pathlib

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from utils.config_loader import config
from utils.logger import get_logger

logger = get_logger(__name__)


class DriverFactory:
    def __init__(self):
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def create(self, storage_state: str | None = None) -> Page:
        self._playwright = sync_playwright().start()
        launcher = getattr(self._playwright, config.BROWSER)
        self._browser = launcher.launch(
            headless=config.HEADLESS,
            slow_mo=config.SLOW_MO,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )

        context_kwargs: dict = dict(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            java_script_enabled=True,
            accept_downloads=True,
            extra_http_headers={"Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8"},
            locale="he-IL",
        )

        if storage_state:
            context_kwargs["storage_state"] = storage_state
            logger.info(f"Restoring session state from: {storage_state}")

        self._context = self._browser.new_context(**context_kwargs)
        self._context.set_default_timeout(config.REQUEST_TIMEOUT)

        self._page = self._context.new_page()
        logger.info(
            f"Browser '{config.BROWSER}' launched "
            f"(headless={config.HEADLESS}, timeout={config.REQUEST_TIMEOUT or 'none'}, "
            f"session={'restored' if storage_state else 'fresh'})"
        )
        return self._page

    def save_session_state(self, path: str) -> None:
        if self._context is None:
            raise RuntimeError("No active context – call create() first.")
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._context.storage_state(path=path)
        logger.info(f"Session state saved → {path}")

    def quit(self):
        for obj, label in [
            (self._page, "page"),
            (self._context, "context"),
            (self._browser, "browser"),
        ]:
            if obj is None:
                continue
            try:
                if hasattr(obj, "is_closed") and obj.is_closed():
                    continue
                obj.close()
            except Exception as exc:
                logger.warning(f"Error closing {label}: {exc}")

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception as exc:
                logger.warning(f"Error stopping Playwright: {exc}")

        logger.info("Driver factory: cleanup complete.")
