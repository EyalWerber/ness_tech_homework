from __future__ import annotations

import traceback
from pathlib import Path

import allure
import pytest

import utils.ai_agent as ai_agent
from pages.login_page import LoginPage
from utils.config_loader import config
from utils.driver_factory import DriverFactory
from utils.helpers import take_screenshot
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Session-level login ───────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def session_state_path() -> str:
    """
    Log in once per pytest session and persist cookies to SESSION_STATE_PATH.
    Subsequent test functions restore the saved state instead of logging in again.
    """
    state_path = str(config.SESSION_STATE_PATH)

    if Path(state_path).exists():
        logger.info(f"[session] Reusing saved session: {state_path}")
        return state_path

    if not config.TERMINALX_USERNAME or not config.TERMINALX_PASSWORD:
        raise RuntimeError(
            "TERMINALX_USERNAME and TERMINALX_PASSWORD must be set in .env."
        )

    logger.info("[session] No saved session – performing fresh login …")
    factory = DriverFactory()
    page = factory.create()
    try:
        LoginPage(page).login(config.TERMINALX_USERNAME, config.TERMINALX_PASSWORD)
        factory.save_session_state(state_path)
        logger.info(f"[session] Login complete. State saved → {state_path}")
    finally:
        factory.quit()

    return state_path


# ── Per-test authenticated page ───────────────────────────────────────────────

@pytest.fixture(scope="function")
def authenticated_driver(session_state_path):
    """Yields a Playwright page with the saved Terminal X session restored."""
    factory = DriverFactory()
    page = factory.create(storage_state=session_state_path)
    yield page
    factory.quit()


# ── Plain (unauthenticated) page ──────────────────────────────────────────────

@pytest.fixture(scope="function")
def driver():
    """Yields a plain unauthenticated Playwright page."""
    factory = DriverFactory()
    page = factory.create()
    yield page
    factory.quit()


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
