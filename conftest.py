from __future__ import annotations

import traceback
from pathlib import Path

import allure
import pytest
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

import utils.ai_agent as ai_agent
from pages.login_page import LoginPage
from utils.config_loader import config
from utils.helpers import take_screenshot
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Fixture lifecycle ─────────────────────────────────────────────────────────
#
#  SESSION (once per pytest run)
#  ├── playwright_instance  — Playwright process, started once
#  ├── browser              — Browser process, launched once (~1-2s, expensive)
#  └── session_state_path   — Login once, save cookies; all tests reuse them
#
#  PER TEST (fresh every test, browser process stays alive)
#  ├── context  — New isolated profile (cookies, localStorage, etc.)
#  └── page     — New tab inside that context
#
# Why this split: launching the browser is slow; creating a context is fast.
# Each test gets full isolation without paying the browser startup cost every time.

# ── Shared context settings ───────────────────────────────────────────────────

_CONTEXT_KWARGS: dict = dict(
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


def _new_context(browser: Browser, storage_state: str | None = None) -> BrowserContext:
    """Open a fresh browser context (isolated cookies/storage) from the shared browser."""
    ctx = browser.new_context(**_CONTEXT_KWARGS, **({"storage_state": storage_state} if storage_state else {}))
    ctx.set_default_timeout(config.REQUEST_TIMEOUT)
    return ctx


# ── SESSION fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def clear_ai_reports():
    """Wipe AI report files before each test session so they don't accumulate across runs."""
    for report_file in (config.AI_FAILURE_REPORT, config.AI_FAILURE_REPORT.parent / "self_healing_report.txt"):
        try:
            report_file.unlink(missing_ok=True)
        except Exception:
            pass


@pytest.fixture(scope="session")
def playwright_instance():
    """Start the Playwright driver process — shared for the whole session."""
    pw = sync_playwright().start()
    yield pw
    pw.stop()


@pytest.fixture(scope="session")
def browser(playwright_instance) -> Browser:
    """Launch the browser once for the whole session. Contexts (below) handle per-test isolation."""
    launcher = getattr(playwright_instance, config.BROWSER)
    b = launcher.launch(
        headless=config.HEADLESS,
        slow_mo=config.SLOW_MO,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
    )
    yield b
    b.close()  # called once, after all tests finish


@pytest.fixture(scope="session")
def session_state_path(browser) -> str:
    """Log in once and save cookies to disk. Every test that needs auth loads this file."""
    state_path = str(config.SESSION_STATE_PATH)

    if Path(state_path).exists():
        logger.info(f"[session] Reusing saved session: {state_path}")
        return state_path

    if not config.TERMINALX_USERNAME or not config.TERMINALX_PASSWORD:
        raise RuntimeError("TERMINALX_USERNAME and TERMINALX_PASSWORD must be set in .env.")

    logger.info("[session] No saved session – performing fresh login …")
    ctx = _new_context(browser)
    page = ctx.new_page()
    try:
        LoginPage(page).login(config.TERMINALX_USERNAME, config.TERMINALX_PASSWORD)
        Path(state_path).parent.mkdir(parents=True, exist_ok=True)
        ctx.storage_state(path=state_path)
        logger.info(f"[session] Login complete. State saved → {state_path}")
    finally:
        ctx.close()

    return state_path


# ── PER-TEST fixtures ─────────────────────────────────────────────────────────
# Both fixtures below create a NEW context for every test, then close it when
# the test ends. The browser process (above) stays alive the whole time.

@pytest.fixture(scope="function")
def authenticated_driver(browser, session_state_path) -> Page:
    """Fresh context + page, pre-loaded with the saved login session."""
    ctx = _new_context(browser, storage_state=session_state_path)
    yield ctx.new_page()
    ctx.close()  # also discards the page — next test starts completely clean


@pytest.fixture(scope="function")
def driver(browser) -> Page:
    """Fresh context + page, no login state."""
    ctx = _new_context(browser)
    yield ctx.new_page()
    ctx.close()


# ── Failure hook ──────────────────────────────────────────────────────────────

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    if report.when != "call" or not report.failed:
        return

    page = item.funcargs.get("authenticated_driver") or item.funcargs.get("driver")
    screenshot_path: str | None = None

    if page is not None:
        try:
            if not page.is_closed():
                path = take_screenshot(page, "FAILURE", config.SCREENSHOT_DIR)
                screenshot_path = str(path)
                with open(screenshot_path, "rb") as fh:
                    allure.attach(
                        fh.read(),
                        name="failure_screenshot",
                        attachment_type=allure.attachment_type.PNG,
                    )
        except Exception as exc:
            logger.warning(f"Could not capture failure screenshot: {exc}")

    try:
        error_msg = str(report.longrepr) if report.longrepr else "Unknown error"
        analysis = ai_agent.analyze_failure(
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            screenshot_path=screenshot_path,
        )
        allure.attach(
            analysis,
            name="AI Failure Analysis",
            attachment_type=allure.attachment_type.TEXT,
        )
    except Exception as exc:
        logger.warning(f"AI failure analysis hook error: {exc}")
