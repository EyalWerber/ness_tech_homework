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
        launcher = getattr(self._playwright, config.BROWSER)  # e.g. playwright.chromium
        self._browser = launcher.launch(
            headless=config.HEADLESS,
            slow_mo=config.SLOW_MO,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )

        # Browser context = one isolated "profile" (cookies, storage, viewport, headers).
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
            # Restore saved cookies/localStorage so we don't need to log in again.
            context_kwargs["storage_state"] = storage_state

        self._context = self._browser.new_context(**context_kwargs)
        self._context.set_default_timeout(config.REQUEST_TIMEOUT)
        self._page = self._context.new_page()
        return self._page

    def save_session_state(self, path: str) -> None:
        # Dump cookies + localStorage to a JSON file so the next run can skip login.
        if self._context is None:
            raise RuntimeError("No active context – call create() first.")
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._context.storage_state(path=path)

    def quit(self):
        try:
            if self._page and not self._page.is_closed():
                self._page.close()
        except Exception:
            pass
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
