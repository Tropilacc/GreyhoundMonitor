from playwright.sync_api import Page


def get_race_prices(
    page: Page,
    race_url: str
) -> list[dict]:
    """
    Load a TAB race using an existing Playwright page
    and return the current fixed-win price for each runner.

    The browser is managed elsewhere so the same Chromium
    session can be reused across many races.
    """

    runners = []

    page.goto(
        race_url,
        wait_until="domcontentloaded",
        timeout=60000
    )

    # Wait for TAB's runner table to render.
    try:
        page.wait_for_selector(
            ".pseudo-body .row[data-testid^='runner-number-']",
            timeout=15000
        )
    except Exception:
        return runners

    rows = page.locator(
        ".pseudo-body .row[data-testid^='runner-number-']"
    )

    for index in range(rows.count()):
        row = rows.nth(index)

        runner_number_text = (
            row.locator(".number-cell")
            .inner_text()
            .strip()
        )

        runner_name = (
            row.locator(".runner-name")
            .inner_text()
            .strip()
        )

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

        try:
            runner_number = int(runner_number_text)
        except ValueError:
            continue

        runners.append(
            {
                "runner_number": runner_number,
                "runner_name": runner_name,
                "current_price": current_price
            }
        )

    return runners