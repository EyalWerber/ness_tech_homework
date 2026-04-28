"""
CartPage – Terminal X shopping cart (/checkout/cart).

Terminal X cart page exposes:
  - data-test-id='qa-cart-product-name'            – each item row link
  - data-test-id='qa-order-totals-total-order'     – grand total (₪)
  - data-test-id='qa-proceed-to-checkout-button'   – checkout button

Public API:
  open_cart()
  get_total()                          → float (ILS)
  assert_total_not_exceeds(threshold)  → None
"""

from __future__ import annotations

import time

import allure
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from pages.base_page import BasePage
from utils.config_loader import config
from utils.helpers import parse_price, take_screenshot
from utils.logger import get_logger
from utils.selector_store import sel

logger = get_logger(__name__)

_CART_URL = "https://www.terminalx.com/checkout/cart"

_SEL_ORDER_TOTAL = sel("cart", "order_total")
_SEL_CART_ITEM   = sel("cart", "cart_item")
_SEL_EMPTY_CART  = sel("cart", "empty_cart")
_SEL_REMOVE_ITEM = sel("cart", "remove_item")


class CartPage(BasePage):
    def __init__(self, page):
        super().__init__(page)

    @allure.step("Open cart page")
    def open_cart(self) -> None:
        self.navigate(_CART_URL)
        # Use a fixed timeout — self._timeout may be 0 (infinite), which hangs
        # on the cart page because Terminal X uses long-lived polling connections.
        try:
            self.page.wait_for_load_state("networkidle", timeout=15_000)
        except PlaywrightTimeout:
            logger.debug("networkidle not reached on cart – proceeding.")

    @allure.step("Clear all items from cart")
    def clear_cart(self) -> None:
        self.open_cart()
        time.sleep(2)  # let React fully render cart items after networkidle

        removed = 0
        for _ in range(50):  # safety cap
            try:
                # Using page.evaluate (raw JS) because locator.click() can race-condition:
                # the element detaches between "find" and "click" during React re-renders.
                clicked = self.page.evaluate(
                    """() => {
                        const btn = document.querySelector(
                            "button[class*='remove_wqPe']:not([class*='close_3POI'])"
                        );
                        if (btn) { btn.click(); return true; }
                        return false;
                    }"""
                )
            except Exception as exc:
                logger.debug(f"Cart remove evaluate error (item {removed + 1}): {exc}")
                break

            if not clicked:
                break

            time.sleep(2)  # wait for AJAX removal before next iteration

            # Close any info/mini-cart drawer that opened after the removal
            try:
                self.page.evaluate(
                    """() => {
                        const btn = document.querySelector("button[class*='close_3POI']");
                        if (btn) { btn.click(); }
                    }"""
                )
                time.sleep(0.5)
            except Exception:
                pass

            removed += 1

        logger.info(f"Cart cleared – {removed} item(s) removed.")

    @allure.step("Extract cart total (₪)")
    def get_total(self) -> float:
        # If the total element is absent, the cart is likely empty
        try:
            self.page.locator(_SEL_ORDER_TOTAL).first.wait_for(
                state="visible", timeout=8_000
            )
        except PlaywrightTimeout:
            logger.warning("Cart total element not visible – cart may be empty, returning 0.0.")
            return 0.0

        raw = self.page.locator(_SEL_ORDER_TOTAL).first.inner_text()
        total = parse_price(raw)
        logger.info(f"Cart total: ₪{total:.2f}")
        return total

    @allure.step("Assert cart total does not exceed threshold")
    def assert_total_not_exceeds(self, threshold: float) -> None:
        screenshot_path = take_screenshot(self.page, "cart_total_check", config.SCREENSHOT_DIR)
        allure.attach.file(
            str(screenshot_path),
            name="cart_screenshot",
            attachment_type=allure.attachment_type.PNG,
        )

        total = self.get_total()
        item_count = self.count(_SEL_CART_ITEM)

        logger.info(
            f"Cart check → total=₪{total:.2f}, threshold=₪{threshold:.2f}, items={item_count}"
        )
        assert total <= threshold, (
            f"Cart total ₪{total:.2f} EXCEEDS threshold ₪{threshold:.2f}. "
            f"Items in cart: {item_count}."
        )
        logger.info("Cart assertion PASSED ✓")
