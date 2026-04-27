# Terminal X Automation

E2E test suite for [terminalx.com](https://www.terminalx.com) using Playwright + Python.
Covers login → search with price filter → add items to cart → assert total.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

Add your credentials to `.env`:

```
TERMINALX_USERNAME=your@email.com
TERMINALX_PASSWORD=yourpassword
```

Run the tests:

```bash
pytest tests/ -v --alluredir=reports/allure-results
allure serve reports/allure-results
```

## Test Flow

The suite runs 5 tests in order:

1. **Clear cart** — empties the cart so each run starts fresh
2. **Authentication** — restores saved session, re-logs in if expired
3. **Search with price filter** — searches Terminal X and collects product URLs under `max_price`
4. **Add items to cart** — navigates to each URL and adds the item (handles size/colour selection)
5. **Assert cart total** — opens the cart and checks the grand total ≤ `budget_per_item × items added`

## Configuration

`data/test_data.json` controls what gets tested:

```json
{
  "query": "מקסי",
  "max_price": 500,
  "limit": 5,
  "budget_per_item": 500
}
```

- `max_price` — only products at or below this price are collected
- `limit` — max number of products to add
- `budget_per_item` — used in the final assertion: cart total must be ≤ this × items added

## Project Structure

```
terminalx_automation/
├── tests/
│   └── test_e2e_flow.py
├── pages/
│   ├── base_page.py        ← shared navigation + AI self-healing
│   ├── login_page.py
│   ├── search_page.py
│   ├── item_page.py
│   └── cart_page.py
├── utils/
│   ├── config_loader.py
│   ├── driver_factory.py   ← browser + session state
│   ├── helpers.py
│   └── ai_agent.py         ← self-healing + failure analysis
├── data/
│   └── test_data.json
└── reports/
```

## AI Features

**Self-healing locators** — if a selector fails, the page HTML is sent to an AI model which suggests a working replacement. Enabled by default, toggle with `AI_SELF_HEALING_ENABLED=false`.

**Failure analysis** — on test failure, the error and stack trace are sent to AI for a root cause summary. The result is attached to the Allure report. Toggle with `AI_FAILURE_ANALYSIS_ENABLED=false`.

## Session Reuse

Login runs once and cookies are saved to `reports/session_state.json`. Every test restores that file instead of logging in again. Delete the file to force a fresh login.

## Why Terminal X?

Most e-commerce sites (Amazon, eBay, ASOS) block automation with CAPTCHAs or SMS verification on new devices — neither of which can be automated without external services.

Terminal X doesn't use either, so the full flow runs unattended from any machine with just email and password.

## Notes

- The site is in Hebrew; `locale: he-IL` is set on the browser context
- Price filtering is done in-memory — the React range slider on the search page is unreliable with Playwright
- Cart state is server-side, so items persist across browser sessions (that's why the suite clears the cart first)
- `SLOW_MO=700` in `.env` adds a 700ms delay between actions — useful for watching tests run
