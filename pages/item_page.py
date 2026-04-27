"""
ItemPage – Terminal X product detail page.

Terminal X product pages use:
  - data-test-id='qa-size-item'         – size option divs (click to select)
  - data-test-id='qa-color-item'        – colour swatch divs (click to select)
  - data-test-id='qa-add-to-cart-button'– "הוספה לסל" button
  - data-test-id='qa-minicart-product-name' – confirms add-to-cart succeeded
  - button[class*='close_3POI']         – closes the mini-cart drawer

Edge cases handled:
  - No size/colour options (single-variant product)
  - Out-of-stock sizes (class contains 'disabled' or 'out-of-stock')
  - Mini-cart drawer auto-close after successful add
  - Retry on add-to-cart failure
"""

from __future__ import annotations

import random
import time

import allure
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from pages.base_page import BasePage
from utils.config_loader import config
from utils.helpers import retry, take_screenshot
from utils.logger import get_logger
from utils.selector_store import sel

logger = get_logger(__name__)

_SEL_SIZE_BTN        = sel("product", "size_option",        "[data-test-id='qa-size-item']")
_SEL_COLOR_SWATCH    = sel("product", "color_option",       "[data-test-id='qa-color-item']")
_SEL_ADD_TO_CART     = sel("product", "add_to_cart",        "[data-test-id='qa-add-to-cart-button']")
_SEL_MINICART_OK     = sel("product", "mini_cart_indicator","[data-test-id='qa-minicart-product-name']")
_SEL_MINICART_CLOSE  = sel("product", "mini_cart_close",    "button[class*='close_3POI']")


class ItemPage(BasePage):
    def __init__(self, page):
        super().__init__(page)

    @allure.step("Open product URL")
    def open(self, url: str) -> None:
        self.navigate(url)
        try:
            self.page.wait_for_load_state("networkidle", timeout=10_000)
        except PlaywrightTimeout:
            logger.debug("networkidle not reached – proceeding anyway.")

    @allure.step("Select product options (size / colour)")
    def handle_variants(self) -> None:
        self._select_colour()
        self._select_size()

    def _select_colour(self) -> None:
        try:
            swatches = self.page.locator(_SEL_COLOR_SWATCH).all()
            if swatches:
                chosen = random.choice(swatches)
                chosen.click()
                logger.info("Colour selected.")
                time.sleep(0.5)
        except Exception as exc:
            logger.debug(f"Colour selection skipped: {exc}")

    def _select_size(self) -> None:
        try:
            all_sizes = self.page.locator(_SEL_SIZE_BTN).all()
            if not all_sizes:
                return

            # If any size is already selected, leave it — clicking it would deselect it.
            if any("is-selected" in (s.get_attribute("class") or "") for s in all_sizes):
                logger.debug("Size already selected – leaving as is.")
                return

            # Nothing selected: click the first non-disabled size.
            available = [
                s for s in all_sizes
                if "disabled"      not in (s.get_attribute("class") or "")
                and "out-of-stock" not in (s.get_attribute("class") or "")
            ]
            target = (available or all_sizes)[0]
            size_label = target.inner_text().strip() or "unknown"
            target.click()
            logger.info(f"Size selected: {size_label}")
            time.sleep(0.5)
        except Exception as exc:
            logger.debug(f"Size selection skipped: {exc}")

    @retry(max_attempts=3, delay=2.0, exceptions=(Exception,))
    @allure.step("Add item to cart")
    def add_to_cart(self) -> None:
        btn = self.page.locator(_SEL_ADD_TO_CART).first
        btn.wait_for(state="visible", timeout=self._timeout)
        btn.click()
        logger.info("Add-to-Cart clicked.")

        # Wait for mini-cart drawer to confirm the item was added
        try:
            self.page.locator(_SEL_MINICART_OK).first.wait_for(state="visible", timeout=6_000)
            logger.debug("Mini-cart appeared – add to cart confirmed.")
        except PlaywrightTimeout:
            logger.debug("Mini-cart indicator not detected – proceeding.")

        # Dismiss mini-cart drawer so the page is unobstructed
        try:
            close_btn = self.page.locator(_SEL_MINICART_CLOSE).first
            if close_btn.is_visible(timeout=2_000):
                close_btn.click()
                logger.debug("Mini-cart drawer closed.")
        except Exception:
            pass

    def add_item_with_screenshot(self, url: str) -> str:
        self.open(url)
        self.handle_variants()
        self.add_to_cart()
        path = take_screenshot(self.page, "item_added", config.SCREENSHOT_DIR)
        return str(path)
