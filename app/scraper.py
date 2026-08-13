import re
import time

from playwright.sync_api import Page

from dev_alerts import send_dev_alert


# ============================================================
# SETTINGS
# ============================================================

PRICE_RENDER_WAIT_SECONDS = 15

PRICE_POLL_INTERVAL_MS = 1000


# ============================================================
# PRICE PARSING
# ============================================================

def parse_price(
    price_text: str
) -> float | None:
    """
    Convert a rendered TAB price into a float.

    Examples:

        "3.10"  -> 3.10
        "$3.10" -> 3.10

    Non-numeric values such as:

        SCR
        N/A
        -

    return None.
    """

    if not price_text:
        return None

    cleaned = (
        price_text
        .strip()
        .replace("$", "")
    )

    match = re.search(
        r"\d+(?:\.\d+)?",
        cleaned
    )

    if match is None:
        return None

    try:
        return float(
            match.group(0)
        )

    except ValueError:
        return None


# ============================================================
# SCRATCH DETECTION
# ============================================================

def row_is_scratched(
    row
) -> bool:
    """
    Return True when TAB explicitly marks a runner as
    scratched.

    TAB has been observed using two reliable signals:

        1. The runner row contains the CSS class:

               scratched

        2. The runner's rendered market cells display:

               SCR

    We use both signals because TAB page structure can differ
    between jurisdictions while the visible SCR state remains
    consistent.

    A missing price alone does NOT mean scratched.
    """

    # --------------------------------------------------------
    # CSS CLASS
    # --------------------------------------------------------

    try:
        class_name = (
            row.get_attribute(
                "class"
            )
            or ""
        )

        class_tokens = {
            token.strip().lower()
            for token in class_name.split()
            if token.strip()
        }

        if "scratched" in class_tokens:
            return True

    except Exception:
        pass

    # --------------------------------------------------------
    # RENDERED SCR TEXT
    #
    # Look for SCR as a standalone rendered value.
    # --------------------------------------------------------

    try:
        row_text = (
            row.inner_text()
            .strip()
        )

        if re.search(
            r"(?im)^\s*SCR\s*$",
            row_text
        ):
            return True

    except Exception:
        pass

    return False


# ============================================================
# USABLE PRICE CHECK
# ============================================================

def count_usable_prices(
    runners: list[dict]
) -> int:
    """
    Return the number of runners that currently have a
    usable Fixed Odds Win price.

    Scratched runners are not counted as usable prices.
    """

    return sum(
        1
        for runner in runners
        if (
            not runner.get(
                "scratched",
                False
            )
            and runner.get(
                "current_price"
            ) is not None
        )
    )


# ============================================================
# SCRATCH COUNT
# ============================================================

def count_scratched_runners(
    runners: list[dict]
) -> int:
    """
    Return the number of runners explicitly marked SCR.
    """

    return sum(
        1
        for runner in runners
        if runner.get(
            "scratched",
            False
        )
    )


# ============================================================
# STANDARD TAB RUNNER LAYOUT
# ============================================================

def scrape_standard_runner_rows(
    page: Page
) -> list[dict]:
    """
    Scrape TAB's standard runner-table layout.

    Every returned runner contains:

        runner_number
        runner_name
        current_price
        scratched

    A scratched runner normally has:

        current_price = None
        scratched = True

    A temporarily unavailable market may have:

        current_price = None
        scratched = False

    These states must remain distinct.
    """

    runners = []

    rows = page.locator(
        ".pseudo-body "
        ".row[data-testid^='runner-number-']"
    )

    row_count = rows.count()

    if row_count == 0:
        return runners

    for index in range(
        row_count
    ):
        row = rows.nth(
            index
        )

        # ----------------------------------------------------
        # RUNNER NUMBER
        # ----------------------------------------------------

        try:
            runner_number_text = (
                row.locator(
                    ".number-cell"
                )
                .inner_text()
                .strip()
            )

        except Exception:
            continue

        number_match = re.search(
            r"\b(\d{1,2})\b",
            runner_number_text
        )

        if number_match is None:
            continue

        try:
            runner_number = int(
                number_match.group(1)
            )

        except ValueError:
            continue

        # ----------------------------------------------------
        # RUNNER NAME
        # ----------------------------------------------------

        try:
            runner_name = (
                row.locator(
                    ".runner-name"
                )
                .inner_text()
                .strip()
            )

        except Exception:
            continue

        # ----------------------------------------------------
        # SCRATCH STATUS
        # ----------------------------------------------------

        scratched = row_is_scratched(
            row
        )

        # ----------------------------------------------------
        # FIXED ODDS WIN PRICE
        #
        # ONLY Fixed Odds is used.
        #
        # Tote is ignored completely.
        # ----------------------------------------------------

        current_price = None

        if not scratched:

            fixed_price_locator = row.locator(
                "[data-id='fixed-odds-price'] "
                ".animate-odd"
            )

            if (
                fixed_price_locator.count()
                > 0
            ):
                try:
                    price_text = (
                        fixed_price_locator
                        .first
                        .inner_text()
                        .strip()
                    )

                    current_price = parse_price(
                        price_text
                    )

                except Exception:
                    current_price = None

        runners.append(
            {
                "runner_number":
                    runner_number,
                "runner_name":
                    runner_name,
                "current_price":
                    current_price,
                "scratched":
                    scratched,
            }
        )

    return runners


# ============================================================
# FALLBACK TAB RUNNER LAYOUT
# ============================================================

def scrape_fallback_runner_rows(
    page: Page
) -> list[dict]:
    """
    Scrape alternate TAB runner-table layouts.

    This fallback preserves scratched runners even when they
    have no numeric Fixed Odds price.

    Tote is ignored completely.
    """

    runners = []

    candidate_selectors = [
        "[data-testid^='runner-number-']",
        "[data-testid*='runner-number']",
        "[data-id='runner-row']",
        "div.runner-row",
        "tr.runner-row",
        "tr",
    ]

    rows = None

    for selector in candidate_selectors:

        locator = page.locator(
            selector
        )

        if locator.count() > 0:
            rows = locator
            break

    if rows is None:
        return runners

    seen_runner_numbers = set()

    for index in range(
        rows.count()
    ):
        row = rows.nth(
            index
        )

        try:
            row_text = (
                row.inner_text()
                .strip()
            )

        except Exception:
            continue

        if not row_text:
            continue

        # ----------------------------------------------------
        # RUNNER NUMBER
        # ----------------------------------------------------

        runner_number = None

        number_selectors = [
            ".number-cell",
            "[data-testid^='runner-number-']",
            "[data-testid*='runner-number']",
            ".runner-number",
        ]

        for selector in number_selectors:

            locator = row.locator(
                selector
            )

            if locator.count() == 0:
                continue

            try:
                number_text = (
                    locator
                    .first
                    .inner_text()
                    .strip()
                )

                number_match = re.search(
                    r"\b(\d{1,2})\b",
                    number_text
                )

                if number_match:
                    runner_number = int(
                        number_match.group(1)
                    )

                    break

            except Exception:
                continue

        # ----------------------------------------------------
        # FALLBACK RUNNER NUMBER FROM ROW TEXT
        # ----------------------------------------------------

        if runner_number is None:

            number_match = re.match(
                r"^\s*(\d{1,2})\b",
                row_text
            )

            if number_match:
                runner_number = int(
                    number_match.group(1)
                )

        if runner_number is None:
            continue

        if runner_number in seen_runner_numbers:
            continue

        # ----------------------------------------------------
        # RUNNER NAME
        # ----------------------------------------------------

        runner_name = None

        name_selectors = [
            ".runner-name",
            "[data-testid*='runner-name']",
            ".runner-details",
        ]

        for selector in name_selectors:

            locator = row.locator(
                selector
            )

            if locator.count() == 0:
                continue

            try:
                runner_name = (
                    locator
                    .first
                    .inner_text()
                    .strip()
                    .splitlines()[0]
                )

                if runner_name:
                    break

            except Exception:
                continue

        # ----------------------------------------------------
        # FALLBACK RUNNER NAME FROM ROW TEXT
        # ----------------------------------------------------

        if not runner_name:

            lines = [
                line.strip()
                for line
                in row_text.splitlines()
                if line.strip()
            ]

            for line in lines:

                if re.fullmatch(
                    r"\d{1,2}",
                    line
                ):
                    continue

                if re.fullmatch(
                    r"\d+(?:\.\d+)?",
                    line
                ):
                    continue

                if line.upper() in {
                    "WIN",
                    "PLACE",
                    "FIXED ODDS",
                    "TOTE",
                    "SCR",
                }:
                    continue

                if (
                    len(line) >= 2
                    and any(
                        character.isalpha()
                        for character in line
                    )
                ):
                    runner_name = line

                    break

        if not runner_name:
            continue

        # ----------------------------------------------------
        # SCRATCH STATUS
        # ----------------------------------------------------

        scratched = row_is_scratched(
            row
        )

        # ----------------------------------------------------
        # FIXED ODDS WIN PRICE
        # ----------------------------------------------------

        current_price = None

        if not scratched:

            fixed_price_selectors = [
                (
                    "[data-id='fixed-odds-price'] "
                    ".animate-odd"
                ),
                "[data-id='fixed-odds-price']",
                (
                    "[data-testid*='fixed-odds'] "
                    ".animate-odd"
                ),
                "[data-testid*='fixed-odds']",
            ]

            for selector in fixed_price_selectors:

                locator = row.locator(
                    selector
                )

                if locator.count() == 0:
                    continue

                for price_index in range(
                    locator.count()
                ):

                    try:
                        price_text = (
                            locator
                            .nth(price_index)
                            .inner_text()
                            .strip()
                        )

                    except Exception:
                        continue

                    parsed_price = parse_price(
                        price_text
                    )

                    if parsed_price is None:
                        continue

                    current_price = (
                        parsed_price
                    )

                    break

                if current_price is not None:
                    break

        # ----------------------------------------------------
        # IMPORTANT
        #
        # Keep scratched runners even though price is None.
        #
        # Ordinary runners with no price are also retained so
        # the caller can distinguish missing-price state from
        # a complete row-parsing failure.
        # ----------------------------------------------------

        seen_runner_numbers.add(
            runner_number
        )

        runners.append(
            {
                "runner_number":
                    runner_number,
                "runner_name":
                    runner_name,
                "current_price":
                    current_price,
                "scratched":
                    scratched,
            }
        )

    return runners


# ============================================================
# MAIN PRICE SCRAPER
# ============================================================

def get_race_prices(
    page: Page,
    race_url: str
) -> list[dict]:
    """
    Load a TAB race and return runner market state.

    Every returned runner contains:

        runner_number
        runner_name
        current_price
        scratched

    PROCESS:

        1. Load TAB race page.

        2. Poll the standard runner layout.

        3. Accept the standard parse when at least one usable
           Fixed Odds price appears.

           Scratched runners are preserved alongside those
           priced runners.

        4. If runner rows exist but no usable prices appear,
           wait for TAB's market to populate.

        5. If standard parsing cannot obtain any prices,
           try the fallback parser.

        6. If both fail to obtain a usable market, send a DEV
           warning.

    Tote prices are ignored completely.
    """

    try:
        page.goto(
            race_url,
            wait_until="domcontentloaded",
            timeout=60000
        )

    except Exception as error:
        print(
            f"ERROR loading TAB race page: "
            f"{error}"
        )

        send_dev_alert(
            source="SCRAPER",
            message=(
                "TAB race page could not be loaded."
            ),
            error=error,
            severity="ERROR",
            details={
                "Race URL":
                    race_url,
            },
        )

        return []

    # ========================================================
    # POLL STANDARD TAB LAYOUT
    # ========================================================

    start_time = time.monotonic()

    last_standard_runners = []

    runner_rows_seen = False

    waiting_message_printed = False

    while (
        time.monotonic()
        - start_time
        < PRICE_RENDER_WAIT_SECONDS
    ):

        try:
            standard_runners = (
                scrape_standard_runner_rows(
                    page
                )
            )

        except Exception as error:
            print(
                f"ERROR parsing standard TAB "
                f"runner layout: {error}"
            )

            send_dev_alert(
                source="SCRAPER",
                message=(
                    "Standard TAB runner layout "
                    "raised an exception."
                ),
                error=error,
                severity="WARNING",
                details={
                    "Race URL":
                        race_url,
                },
            )

            standard_runners = []

        last_standard_runners = (
            standard_runners
        )

        if standard_runners:
            runner_rows_seen = True

        usable_price_count = (
            count_usable_prices(
                standard_runners
            )
        )

        scratched_count = (
            count_scratched_runners(
                standard_runners
            )
        )

        if usable_price_count > 0:

            elapsed = (
                time.monotonic()
                - start_time
            )

            print(
                f"Parsed "
                f"{len(standard_runners)} "
                f"runner(s) with "
                f"{usable_price_count} "
                f"usable Fixed Odds price(s) "
                f"and "
                f"{scratched_count} "
                f"scratched runner(s) "
                f"after {elapsed:.1f}s."
            )

            return standard_runners

        if (
            standard_runners
            and not waiting_message_printed
        ):
            print(
                f"Found "
                f"{len(standard_runners)} "
                f"runner row(s), but no usable "
                f"Fixed Odds prices are populated yet. "
                f"Scratchings detected: "
                f"{scratched_count}. "
                f"Waiting..."
            )

            waiting_message_printed = True

        page.wait_for_timeout(
            PRICE_POLL_INTERVAL_MS
        )

    # ========================================================
    # STANDARD PARSER DID NOT PRODUCE USABLE PRICES
    # ========================================================

    if runner_rows_seen:
        print(
            "TAB runner rows were found, but no usable "
            "Fixed Odds prices appeared within "
            f"{PRICE_RENDER_WAIT_SECONDS} seconds."
        )

    else:
        print(
            "Standard TAB runner layout returned "
            "no runner rows."
        )

    print(
        "Trying fallback parser..."
    )

    # ========================================================
    # FALLBACK LAYOUT
    # ========================================================

    try:
        fallback_runners = (
            scrape_fallback_runner_rows(
                page
            )
        )

    except Exception as error:
        print(
            f"ERROR parsing fallback TAB "
            f"runner layout: {error}"
        )

        send_dev_alert(
            source="SCRAPER",
            message=(
                "Fallback TAB runner layout "
                "could not be parsed."
            ),
            error=error,
            severity="ERROR",
            details={
                "Race URL":
                    race_url,
            },
        )

        fallback_runners = []

    fallback_price_count = (
        count_usable_prices(
            fallback_runners
        )
    )

    fallback_scratched_count = (
        count_scratched_runners(
            fallback_runners
        )
    )

    if fallback_price_count > 0:

        print(
            f"Fallback TAB parser recovered "
            f"{len(fallback_runners)} runner(s) "
            f"with {fallback_price_count} "
            f"usable Fixed Odds price(s) "
            f"and {fallback_scratched_count} "
            f"scratched runner(s)."
        )

        return fallback_runners

    # ========================================================
    # COMPLETE PRICE SCRAPE FAILURE
    # ========================================================

    print(
        "No usable runner prices found."
    )

    try:
        page_title = (
            page.title()
        )

    except Exception:
        page_title = ""

    try:
        body_text = (
            page.locator(
                "body"
            )
            .inner_text(
                timeout=5000
            )
        )

        body_characters = len(
            body_text
        )

        body_upper = (
            body_text.upper()
        )

        fixed_odds_present = (
            "FIXED ODDS"
            in body_upper
        )

    except Exception:
        body_characters = 0
        fixed_odds_present = False

    send_dev_alert(
        source="SCRAPER",
        message=(
            "Race page produced no usable "
            "Fixed Odds runner prices."
        ),
        severity="WARNING",
        details={
            "Race URL":
                race_url,
            "Page title":
                page_title,
            "Runner rows detected":
                len(
                    last_standard_runners
                ),
            "Scratched runners detected":
                count_scratched_runners(
                    last_standard_runners
                ),
            "Usable standard prices":
                count_usable_prices(
                    last_standard_runners
                ),
            "Usable fallback prices":
                fallback_price_count,
            "Fallback scratches":
                fallback_scratched_count,
            "Body characters":
                body_characters,
            "Fixed Odds text present":
                fixed_odds_present,
            "Price wait seconds":
                PRICE_RENDER_WAIT_SECONDS,
        },
    )

    return []