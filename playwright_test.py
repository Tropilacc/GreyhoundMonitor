from playwright.sync_api import sync_playwright


RACE_URL = (
    "https://www.tab.com.au/racing/"
    "2026-08-04/MANDURAH/MRD/G/8"
)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=False
    )

    page = browser.new_page()

    page.goto(
        RACE_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(10000)

    rows = page.locator(
        ".pseudo-body .row[data-testid^='runner-number-']"
    )

    print(f"Runners found: {rows.count()}")
    print()

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

        if fixed_price_locator.count() > 0:
            current_price = fixed_price_locator.last.inner_text().strip()
        else:
            current_price = "Unavailable"

        print(
            f"{runner_number}. "
            f"{runner_name} | "
            f"Fixed Win: ${current_price}"
        )

    input("\nPress Enter to close...")

    browser.close()