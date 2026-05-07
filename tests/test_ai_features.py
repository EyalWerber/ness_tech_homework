"""
Tests that demonstrate the two AI features.

Requires AI_ENABLED=true in .env plus a working Ollama or OpenAI backend.
Both tests are auto-skipped when AI is disabled so they don't break the normal run.

  test_self_healing_locator  – broken selector → AI reads the page HTML → suggests
                               the real selector → click succeeds
  test_failure_analysis      – calls analyze_failure() with a synthetic error and
                               asserts the AI returns a non-empty analysis
"""

from __future__ import annotations

import allure
import pytest

from pages.base_page import BasePage
from utils import ai_agent
from utils.config_loader import config

# Skip the whole module when AI is off
pytestmark = pytest.mark.skipif(
    not config.AI_ENABLED,
    reason="Set AI_ENABLED=true in .env to run AI feature tests",
)


@allure.epic("Terminal X Automation")
@allure.feature("AI Features")
class TestAIFeatures:

    @allure.title("Self-healing locator – broken selector gets fixed by AI")
    @allure.story("Self-Healing")
    @allure.severity(allure.severity_level.NORMAL)
    def test_self_healing_locator(self, authenticated_driver):
        """
        Navigates to the Terminal X home page and attempts to click the search
        button using a deliberately wrong selector.

        BasePage.click() catches the failure, sends the full page HTML to the AI,
        and gets back the real selector. The click then succeeds.

        The @allure.step '[AI] Self-healing click' in the report shows the healed selector.
        """
        page = BasePage(authenticated_driver)
        page.navigate("https://www.terminalx.com")
        authenticated_driver.wait_for_load_state("networkidle", timeout=15_000)

        # Use a short timeout so the broken selector fails fast while the page is
        # still open — with timeout=0 (the global default) Playwright waits
        # indefinitely and the page closes before healing gets a chance to run.
        page._timeout = 6_000

        # Real selector is [data-test-id='qa-header-search-button'] —
        # the broken one forces the self-healing path.
        with allure.step("Click search button with intentionally broken selector"):
            page.click(
                "[data-test-id='qa-BROKEN-search-button']",
                description="search button in the site header",
            )

        # If we reach this line, the AI healed the selector successfully.
        allure.attach(
            "Self-healing succeeded — AI identified the correct selector from the page HTML.",
            name="Result",
            attachment_type=allure.attachment_type.TEXT,
        )

    @allure.title("Failure analysis – AI explains a test failure")
    @allure.story("Failure Analysis")
    @allure.severity(allure.severity_level.NORMAL)
    def test_failure_analysis(self):
        """
        Calls analyze_failure() directly with a realistic synthetic error.

        In a real run the conftest failure hook calls this automatically on any
        failing test. Here we invoke it explicitly so the output is visible in
        the Allure report without needing an actual failure.
        """
        synthetic_error = (
            "AssertionError: Cart total ₪1,850.00 EXCEEDS threshold ₪500.00. "
            "Items in cart: 5."
        )
        synthetic_trace = (
            "tests/test_e2e_flow.py:192 in test_assert_cart_total_not_exceeds\n"
            "  assert total <= threshold\n"
            "pages/cart_page.py:95 in assert_total_not_exceeds"
        )

        with allure.step("Request AI failure analysis"):
            analysis = ai_agent.analyze_failure(
                error_message=synthetic_error,
                stack_trace=synthetic_trace,
            )

        allure.attach(
            analysis,
            name="AI Analysis",
            attachment_type=allure.attachment_type.TEXT,
        )

        assert analysis and len(analysis) > 50, (
            "AI returned an empty or very short analysis — check the AI backend."
        )
