"""
LoginPage – Terminal X sign-in flow.

Terminal X uses a slide-in account drawer triggered from the header icon,
OR a dedicated /customer/account/login page (Magento-based backend).
The page object tries the dedicated URL first, which is more stable for automation.

Flow:
  1. Navigate to /customer/account/login
  2. Fill email → fill password → submit
  3. Handle any post-login modal or verification prompt
  4. Verify by checking the account icon shows a logged-in state
"""

from __future__ import annotations

import allure
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from pages.base_page import BasePage
from utils.config_loader import config
from utils.helpers import take_screenshot
from utils.logger import get_logger
from utils.selector_store import sel

logger = get_logger(__name__)

_LOGIN_URL = "https://www.terminalx.com/customer/account/login"

# ── Selectors (discovered at runtime; hardcoded values are fallbacks) ─────────
_SEL_EMAIL = sel("login", "email_input",          "input#qa-login-email-input")
_SEL_PASSWORD = sel("login", "password_input",    "input#qa-login-password-input")
_SEL_SUBMIT = sel("login", "submit_button",       "[data-test-id='qa-login-submit']")
_SEL_LOGGED_IN = sel("login", "logged_in_indicator",
    "[data-test-id='qa-header-profile-button']"
)
_SEL_POPUP_CLOSE = sel("login", "popup_close",
    "button[class*='close_3POI']"
)

_SEL_VERIFY_INPUT = "input[name='otp'], input[aria-label*='verification'], input[name='code']"


class LoginPage(BasePage):
    """Handles Terminal X authentication."""

    def __init__(self, page):
        super().__init__(page)

    @allure.step("Log in to Terminal X")
    def login(self, username: str, password: str) -> None:
        logger.info("Starting Terminal X login …")
        self._navigate_to_login()
        self._submit_credentials(username, password)
        self._dismiss_popups()
        self._assert_logged_in()

    # ── Private steps ─────────────────────────────────────────────────────────

    @allure.step("Open login page")
    def _navigate_to_login(self) -> None:
        self.navigate(_LOGIN_URL)
        try:
            # Use a fixed timeout here – timeout=0 would deadlock if the site
            # redirects away from the login page (e.g. when already authenticated).
            self.page.locator(_SEL_EMAIL).first.wait_for(state="visible", timeout=15_000)
        except PlaywrightTimeout:
            raise RuntimeError(
                "Login page email field not found. "
                "The site may have redirected (already logged in?) or is down."
            )

    @allure.step("Submit credentials")
    def _submit_credentials(self, username: str, password: str) -> None:
        self.fill(_SEL_EMAIL, username, description="email input")
        self.fill(_SEL_PASSWORD, password, description="password input")
        self.click(_SEL_SUBMIT, description="Login submit button")
        self.page.wait_for_load_state("domcontentloaded")
        self._handle_verification()

    def _handle_verification(self) -> None:
        """Wait indefinitely for manual verification code entry if prompted."""
        try:
            self.page.locator(_SEL_VERIFY_INPUT).wait_for(state="visible", timeout=4_000)
            logger.warning(
                "[LOGIN] Verification code prompt detected – enter the code manually."
            )
            allure.attach(
                "Verification code required – enter it manually in the browser.",
                name="Verification Notice",
                attachment_type=allure.attachment_type.TEXT,
            )
            # No timeout – wait for the input to disappear after manual submission
            self.page.locator(_SEL_VERIFY_INPUT).wait_for(state="hidden")
            self.page.wait_for_load_state("domcontentloaded")
        except PlaywrightTimeout:
            pass  # No verification prompt – normal flow

    def _dismiss_popups(self) -> None:
        """Close newsletter or welcome modals that appear after login."""
        try:
            btn = self.page.locator(_SEL_POPUP_CLOSE).first
            btn.wait_for(state="visible", timeout=4_000)
            btn.click()
            logger.debug("Dismissed post-login popup.")
        except PlaywrightTimeout:
            pass

    @allure.step("Verify login success")
    def _assert_logged_in(self) -> None:
        try:
            self.page.locator(_SEL_LOGGED_IN).wait_for(
                state="visible", timeout=self._timeout
            )
            take_screenshot(self.page, "login_success", config.SCREENSHOT_DIR)
            logger.info("[LOGIN] Successfully authenticated.")
        except PlaywrightTimeout:
            take_screenshot(self.page, "login_failed", config.SCREENSHOT_DIR)
            raise RuntimeError(
                "Login failed – logged-in indicator not visible. "
                "Check credentials or Terminal X's bot-detection."
            )

    def is_logged_in(self) -> bool:
        return self.is_visible(_SEL_LOGGED_IN)
