"""
E2E tests for Terminal X shopping flow — four independent test functions.

Tests share state via the session-scoped `flow_state` fixture so that results
from earlier steps (collected URLs, added item count) are available to later
steps without repeating work. The Terminal X cart is server-side, so items
added in test_add_items_to_cart persist to test_assert_cart_total_not_exceeds
even though each test opens a fresh browser context.

Run order (pytest executes in file order):
  1. test_authentication
  2. test_search_with_price_filter
  3. test_add_items_to_cart
  4. test_assert_cart_total_not_exceeds
"""

from __future__ import annotations

import json
from pathlib import Path

import allure
import pytest

from pages.cart_page import CartPage
from pages.item_page import ItemPage
from pages.login_page import LoginPage
from pages.search_page import SearchPage
from utils.config_loader import config
from utils.helpers import load_json
from utils.logger import get_logger

logger = get_logger(__name__)

_DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "test_data.json"


# ── Session-scoped fixtures ───────────────────────────────────────────────────

@pytest.fixture(scope="session")
def test_data() -> dict:
    """Load test parameters once for the entire session."""
    raw = load_json(_DATA_FILE)
    return {
        "query":           raw["query"],
        "max_price":       float(raw["max_price"]),
        "limit":           int(raw.get("limit", 5)),
        "budget_per_item": float(raw.get("budget_per_item", raw["max_price"])),
    }


@pytest.fixture(scope="session")
def flow_state() -> dict:
    """
    Mutable container for passing results between the four test functions.
    Keys populated during the run:
      urls         – list[str] from test_search_with_price_filter
      added_count  – int       from test_add_items_to_cart
    """
    return {"urls": [], "added_count": 0}


# ── Test class ────────────────────────────────────────────────────────────────

@allure.epic("Terminal X Automation")
@allure.feature("Shopping Flow")
class TestE2EFlow:

    # ── 0 ─────────────────────────────────────────────────────────────────────

    @allure.title("Clear cart before test run")
    @allure.story("Cart")
    @allure.severity(allure.severity_level.NORMAL)
    def test_clear_cart(self, authenticated_driver):
        """Remove all items from the cart so each run starts with an empty cart."""
        CartPage(authenticated_driver).clear_cart()

    # ── 1 ─────────────────────────────────────────────────────────────────────

    @allure.title("Authentication – verify active session")
    @allure.story("Authentication")
    @allure.severity(allure.severity_level.BLOCKER)
    def test_authentication(self, authenticated_driver):
        """Restore saved session and confirm the profile button is visible."""
        driver = authenticated_driver
        login_page = LoginPage(driver)

        login_page.navigate("https://www.terminalx.com")
        try:
            driver.wait_for_load_state("networkidle", timeout=12_000)
        except Exception:
            pass

        if not login_page.is_logged_in():
            logger.warning("[auth] Session expired – re-authenticating …")
            login_page.login(config.TERMINALX_USERNAME, config.TERMINALX_PASSWORD)

        assert login_page.is_logged_in(), (
            "Authentication failed – profile button not visible after login."
        )
        logger.info("[auth] Session confirmed.")

    # ── 2 ─────────────────────────────────────────────────────────────────────

    @allure.title("Search items with price filter")
    @allure.story("Search")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_search_with_price_filter(self, authenticated_driver, test_data, flow_state):
        """Search Terminal X and collect product URLs whose price ≤ max_price."""
        search_page = SearchPage(authenticated_driver)

        urls = search_page.search_items_by_name_under_price(
            query=test_data["query"],
            max_price=test_data["max_price"],
            limit=test_data["limit"],
        )

        allure.attach(
            "\n".join(urls),
            name="Collected URLs",
            attachment_type=allure.attachment_type.TEXT,
        )

        assert urls, (
            f"No products found for query='{test_data['query']}' "
            f"under ₪{test_data['max_price']}."
        )

        flow_state["urls"] = urls
        logger.info(f"Search collected {len(urls)} URL(s) ≤ ₪{test_data['max_price']}.")

    # ── 3 ─────────────────────────────────────────────────────────────────────

    @allure.title("Add items to cart")
    @allure.story("Cart")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_add_items_to_cart(self, authenticated_driver, flow_state):
        """Navigate to each collected product URL and add the item to the cart."""
        urls = flow_state.get("urls", [])
        assert urls, (
            "No product URLs available – "
            "test_search_with_price_filter must pass first."
        )

        item_page = ItemPage(authenticated_driver)
        added_count = 0
        failed_urls: list[str] = []

        for idx, url in enumerate(urls, start=1):
            with allure.step(f"Item {idx}/{len(urls)}: {url[:70]}"):
                try:
                    screenshot = item_page.add_item_with_screenshot(url)
                    added_count += 1
                    logger.info(f"Item {idx} added.")
                    allure.attach.file(
                        screenshot,
                        name=f"item_{idx}_added",
                        attachment_type=allure.attachment_type.PNG,
                    )
                except Exception as exc:
                    logger.warning(f"Item {idx} FAILED: {url[:70]} | {exc}")
                    failed_urls.append(url)

        if failed_urls:
            allure.attach(
                "\n".join(failed_urls),
                name="Failed URLs",
                attachment_type=allure.attachment_type.TEXT,
            )

        flow_state["added_count"] = added_count
        assert added_count > 0, (
            f"Could not add any of the {len(urls)} item(s) to cart."
        )
        logger.info(f"{added_count}/{len(urls)} item(s) added to cart.")

    # ── 4 ─────────────────────────────────────────────────────────────────────

    @allure.title("Assert cart total does not exceed budget")
    @allure.story("Cart")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_assert_cart_total_not_exceeds(self, authenticated_driver, test_data, flow_state):
        """Open the cart and assert the grand total ≤ budget_per_item × items added."""
        added_count = flow_state.get("added_count", 0)
        assert added_count > 0, (
            "No items were added – test_add_items_to_cart must pass first."
        )

        threshold = test_data["budget_per_item"] * added_count
        cart_page = CartPage(authenticated_driver)
        cart_page.open_cart()
        cart_page.assert_total_not_exceeds(threshold)
        logger.info(f"Cart total ≤ ₪{threshold:.2f} — PASSED.")

    # ── 5 ─────────────────────────────────────────────────────────────────────

    @allure.title("Verify: self-healer wrote corrected selector back to selectors.json")
    @allure.story("Self-Healing")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_verify_selector_writeback(self, flow_state):
        """Assert selectors.json was patched by the healer during test_add_items_to_cart."""
        assert flow_state.get("added_count", 0) > 0, (
            "No items were added — test_add_items_to_cart must pass first."
        )

        sel_file = Path(__file__).resolve().parents[1] / "data" / "selectors.json"
        data = json.loads(sel_file.read_text(encoding="utf-8"))
        healed_value = data["product"]["add_to_cart"]

        allure.attach(
            f"selectors.json → product.add_to_cart = {healed_value}",
            name="Healed selector value",
            attachment_type=allure.attachment_type.TEXT,
        )

        assert "BROKEN" not in healed_value, (
            f"selectors.json was NOT updated — value still contains BROKEN: {healed_value!r}"
        )
        assert healed_value == "[data-test-id='qa-add-to-cart-button']", (
            f"Healed to unexpected value: {healed_value!r}"
        )
        logger.info(f"[write-back] selectors.json correctly healed to: {healed_value}")
