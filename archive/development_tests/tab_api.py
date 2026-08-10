from playwright.sync_api import sync_playwright


def get_race_prices(race_url: str) -> list[dict]:
    runners = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=False
        )

        page = browser.new_page()

        page.goto(
            race_url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(10000)

        rows = page.locator(
            ".pseudo-body .row[data-testid^='runner-number-']"
        )

        for index in range(rows.count()):
            row = rows.nth(index)

            runner_number = row.locator(
                ".number-cell"
            ).inner_text().strip()

            runner_name = row.locator(
                ".runner-name"
            ).inner_text().strip()

            fixed_price_locator = row.locator(
                "[data-id='fixed-odds-price'] .animate-odd"
            )

            current_price = None

            if fixed_price_locator.count() > 0:
                price_text = (
                    fixed_price_locator
                    .last
                    .inner_text()
                    .strip()
                )

                try:
                    current_price = float(price_text)
                except ValueError:
                    current_price = None

            runners.append(
                {
                    "runner_number": int(runner_number),
                    "runner_name": runner_name,
                    "current_price": current_price
                }
            )

        browser.close()

    return runners