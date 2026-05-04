"""
SearchPage – Terminal X search results page.

Terminal X search URL pattern:
  https://www.terminalx.com/catalogsearch/result/?q=<query>

Price filter:
  Terminal X uses React-controlled range sliders for price filtering, which
  are unreliable to manipulate via Playwright. Price filtering is applied
  in-memory after extracting product cards from the DOM.

Product cards:
  Each card is an <li class*="listing-product"> containing an <a class*="title">
  for the product URL and a <div class*="final-price"> for the price.

Public API:
  search_items_by_name_under_price(query, max_price, limit) → list[str]
"""

from __future__ import annotations

import allure
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from pages.base_page import BasePage
from utils.helpers import parse_price
from utils.logger import get_logger
from utils.selector_store import sel

logger = get_logger(__name__)

_SEARCH_URL = "https://www.terminalx.com/catalogsearch/result/?q={query}"

_SEL_PRODUCT_CARD = sel("search", "product_card")


class SearchPage(BasePage):
    def __init__(self, page):
        super().__init__(page)

    @allure.step("Search for '{query}'")
    def search(self, query: str) -> None:
        url = _SEARCH_URL.format(query=query.replace(" ", "+"))
        logger.info(f"Opening search results URL: {url}")
        self.navigate(url)
        try:
            self.page.wait_for_load_state("networkidle", timeout=15_000)
        except PlaywrightTimeout:
            self.page.wait_for_load_state("domcontentloaded")

    @allure.step("Apply max-price filter: ₪{max_price}")
    def apply_price_filter(self, max_price: float) -> None:
        logger.info(f"Price filter ≤ ₪{max_price} applied in-memory during URL collection.")

    @allure.step("Collect up to {limit} item URLs ≤ ₪{max_price}")
    def collect_item_urls(self, max_price: float, limit: int = 5) -> list[str]:
        card_selector = self._assert_has_results()

        products: list[dict] = self.page.evaluate("""(selector) => {
            return Array.from(document.querySelectorAll(selector))
                .filter(el => el.offsetParent !== null)
                .map(card => {
                    const link  = card.querySelector('a[class*="title"]');
                    const price = card.querySelector('div[class*="final-price"]');
                    return {
                        url:       link  ? link.href              : '',
                        priceText: price ? price.innerText.trim() : '',
                    };
                })
                .filter(p => p.url);
        }""", card_selector)

        urls: list[str] = []
        for item in products:
            if len(urls) >= limit:
                break
            href = item.get("url", "")
            if not href:
                continue
            item_price = parse_price(item.get("priceText", ""))
            if item_price <= 0:
                continue
            if item_price > max_price:
                logger.debug(f"  Skipped ₪{item_price:.0f} > ₪{max_price}: {href[:60]}")
                continue
            urls.append(href)
            logger.info(f"  + ₪{item_price:.0f}  {href[:80]}")

        logger.info(f"Collected {len(urls)} URL(s) matching ≤ ₪{max_price}.")
        return urls[:limit]

    def search_items_by_name_under_price(
        self, query: str, max_price: float, limit: int = 5
    ) -> list[str]:
        with allure.step(f"searchItemsByNameUnderPrice('{query}', ₪{max_price}, {limit})"):
            self.search(query)
            self.apply_price_filter(max_price)
            return self.collect_item_urls(max_price=max_price, limit=limit)

    def _assert_has_results(self) -> str:
        return self.ensure_any(_SEL_PRODUCT_CARD, "product search result card")
