import csv
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page

from dev_notifications import (
    send_missing_form_venue_alert,
)


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

TAB_FORM_VENUES_CSV = (
    PROJECT_ROOT
    / "data"
    / "tab_form_venues.csv"
)


# ============================================================
# RESULT CODES
# ============================================================

SCRATCHED_POSITION = 100


# ============================================================
# RESULT SCRAPER TIMING
# ============================================================

NORMAL_TAB_MAX_WAIT_SECONDS = 8
FORM_TAB_MAX_WAIT_SECONDS = 20

FORM_TAB_MAX_ATTEMPTS = 2

RESULT_POLL_INTERVAL_MS = 1000


# ============================================================
# TAB FORM VENUE MAPPINGS
# ============================================================

def load_tab_form_venue_codes() -> dict[str, dict]:
    """
    Load TAB Form venue mappings from CSV.

    Required columns:

        MEETINGNAME
        NORMALVENUECODE
        FORMVENUECODE
    """

    if not TAB_FORM_VENUES_CSV.exists():
        raise RuntimeError(
            "TAB Form venue mapping CSV "
            f"does not exist: "
            f"{TAB_FORM_VENUES_CSV}"
        )

    required_columns = {
        "MEETINGNAME",
        "NORMALVENUECODE",
        "FORMVENUECODE",
    }

    mappings = {}

    with open(
        TAB_FORM_VENUES_CSV,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as csv_file:

        reader = csv.DictReader(
            csv_file
        )

        fieldnames = (
            set(reader.fieldnames or [])
        )

        missing_columns = (
            required_columns
            - fieldnames
        )

        if missing_columns:
            raise RuntimeError(
                "TAB Form venue mapping CSV "
                "is missing required column(s): "
                + ", ".join(
                    sorted(
                        missing_columns
                    )
                )
            )

        for row_number, row in enumerate(
            reader,
            start=2
        ):

            meeting_name = (
                row.get(
                    "MEETINGNAME",
                    ""
                )
                .strip()
                .upper()
                .replace(" ", "-")
            )

            normal_venue_code = (
                row.get(
                    "NORMALVENUECODE",
                    ""
                )
                .strip()
                .upper()
            )

            form_venue_code = (
                row.get(
                    "FORMVENUECODE",
                    ""
                )
                .strip()
                .upper()
            )

            if (
                not meeting_name
                and not normal_venue_code
                and not form_venue_code
            ):
                continue

            if not meeting_name:
                print(
                    f"WARNING: Ignoring TAB Form venue "
                    f"CSV row {row_number}: "
                    f"MEETINGNAME is blank."
                )
                continue

            if not form_venue_code:
                print(
                    f"WARNING: Ignoring TAB Form venue "
                    f"CSV row {row_number}: "
                    f"FORMVENUECODE is blank "
                    f"for {meeting_name}."
                )
                continue

            if meeting_name in mappings:
                raise RuntimeError(
                    "Duplicate MEETINGNAME in "
                    "TAB Form venue CSV: "
                    f"{meeting_name}"
                )

            mappings[
                meeting_name
            ] = {
                "normal_venue_code":
                    normal_venue_code,
                "form_venue_code":
                    form_venue_code,
            }

    if not mappings:
        raise RuntimeError(
            "TAB Form venue mapping CSV "
            "contains no usable mappings."
        )

    return mappings


TAB_FORM_VENUE_CODES = (
    load_tab_form_venue_codes()
)


# ============================================================
# HELPERS
# ============================================================

def ordinal_to_position(
    ordinal: str
) -> int | None:
    """
    Convert ordinal finishing positions to integers.

    Examples:

        1st -> 1
        2nd -> 2
        3rd -> 3
        4th -> 4
        10th -> 10
        21st -> 21
    """

    match = re.fullmatch(
        r"(\d+)(?:st|nd|rd|th)",
        ordinal.strip(),
        re.IGNORECASE
    )

    if not match:
        return None

    return int(
        match.group(1)
    )


def extract_dollar_values(
    text: str
) -> list[float]:
    """
    Extract dollar amounts from one Fixed Odds result cell.

    Examples:

        "$8.00\\n$2.20"
            -> [8.0, 2.2]

        "$1.80"
            -> [1.8]

        ""
            -> []

    Tote values are never passed into this function.
    """

    matches = re.findall(
        r"\$([0-9]+(?:\.[0-9]+)?)",
        text or ""
    )

    values = []

    for value in matches:
        try:
            values.append(
                float(value)
            )

        except ValueError:
            continue

    return values


def page_is_tab_form(
    page: Page
) -> bool:
    """
    Return True only when the currently loaded page is
    hosted on form.tab.com.au.

    TAB Form uses a dedicated Scratchings section that can
    be parsed safely.

    The normal TAB site must NOT use the same parser because
    its flattened body text can contain unrelated race,
    navigation, meeting and market numbers.
    """

    try:
        parsed_url = urlparse(
            page.url
        )

        return (
            parsed_url.netloc
            .lower()
            == "form.tab.com.au"
        )

    except Exception:
        return False


# ============================================================
# TAB FORM SCRATCHING PARSER
# ============================================================

def parse_scratched_runner_numbers(
    body_text: str
) -> list[int]:
    """
    Parse runner numbers from TAB Form's dedicated
    Scratchings section.

    IMPORTANT:

    This function is ONLY valid for TAB Form body text.

    It must not be used against the normal TAB website.

    There is deliberately NO hard-coded upper limit on
    runner number.

    This keeps the parser compatible with:

        - greyhounds
        - reserves
        - thoroughbreds
        - larger race fields
    """

    if not body_text:
        return []

    scratchings_match = re.search(
        r"(?is)"
        r"\bScratchings\b"
        r"\s*"
        r"(.*?)"
        r"(?="
        r"\bSubstitutes\b"
        r"|"
        r"\bFIXED ODDS\b"
        r"|"
        r"\bLast Updated\b"
        r"|"
        r"$"
        r")",
        body_text
    )

    if scratchings_match is None:
        return []

    scratchings_text = (
        scratchings_match
        .group(1)
        .strip()
    )

    if not scratchings_text:
        return []

    if scratchings_text.upper() in {
        "NIL",
        "NONE",
        "NO SCRATCHINGS",
    }:
        return []

    runner_numbers = []

    matches = re.findall(
        r"(?<!\d)"
        r"(\d{1,2})"
        r"(?:\([A-Z]+\))?"
        r"(?!\d)",
        scratchings_text,
        re.IGNORECASE
    )

    for value in matches:
        try:
            runner_number = int(
                value
            )

        except ValueError:
            continue

        if runner_number not in runner_numbers:
            runner_numbers.append(
                runner_number
            )

    return runner_numbers


def get_runner_name_for_number(
    page: Page,
    runner_number: int
) -> str:
    """
    Attempt to retrieve a scratched runner's name.

    Matching ultimately occurs by runner number, so the
    placeholder is acceptable on historical TAB Form pages
    where the scratched runner name is unavailable.
    """

    selectors = [
        (
            f'[data-testid="runner-number-{runner_number}"] '
            f'.runner-name'
        ),
        (
            f'#runner-number-{runner_number} '
            f'.runner-name'
        ),
    ]

    for selector in selectors:

        try:
            locator = page.locator(
                selector
            )

            if locator.count() == 0:
                continue

            runner_name = (
                locator
                .first
                .inner_text()
                .strip()
            )

            if runner_name:
                return runner_name

        except Exception:
            continue

    return "SCRATCHED RUNNER"


def add_scratched_runners(
    page: Page,
    results: list[dict],
    body_text: str
) -> list[dict]:
    """
    Add scratched runners to an already-published TAB Form
    result.

    Scratchings are deliberately ignored on normal TAB
    pages by this function.

    Scratchings by themselves never make a race count as
    resulted.
    """

    if not results:
        return results

    # ========================================================
    # CRITICAL SAFETY CHECK
    #
    # The body-text Scratchings parser is designed only for
    # TAB Form.
    #
    # Never run it against www.tab.com.au.
    # ========================================================

    if not page_is_tab_form(
        page
    ):
        return results

    scratched_runner_numbers = (
        parse_scratched_runner_numbers(
            body_text
        )
    )

    if not scratched_runner_numbers:
        return results

    existing_runner_numbers = {
        result.get(
            "runner_number"
        )
        for result in results
    }

    for runner_number in scratched_runner_numbers:

        if runner_number in existing_runner_numbers:
            continue

        runner_name = (
            get_runner_name_for_number(
                page=page,
                runner_number=runner_number
            )
        )

        results.append(
            {
                "finish_position":
                    SCRATCHED_POSITION,
                "runner_number":
                    runner_number,
                "runner_name":
                    runner_name,
                "fixed_odds_paid":
                    False,
                "fixed_odds_values":
                    [],
                "scratched":
                    True,
            }
        )

    results.sort(
        key=lambda result:
        result[
            "finish_position"
        ]
    )

    return results


# ============================================================
# BUILD TAB FORM URL
# ============================================================

def build_form_url(
    race_url: str
) -> str | None:
    """
    Convert a normal TAB race URL into the corresponding
    TAB Form URL using data/tab_form_venues.csv.
    """

    parsed_url = urlparse(
        race_url
    )

    path_parts = [
        part
        for part in parsed_url.path.split("/")
        if part
    ]

    if len(path_parts) < 6:
        print(
            f"WARNING: Unable to parse TAB race URL: "
            f"{race_url}"
        )
        return None

    meeting_date = (
        path_parts[1]
        .strip()
    )

    meeting_slug = (
        path_parts[2]
        .strip()
        .upper()
        .replace(" ", "-")
    )

    normal_venue_code = (
        path_parts[3]
        .strip()
        .upper()
    )

    race_type = (
        path_parts[4]
        .strip()
        .upper()
    )

    race_number = (
        path_parts[5]
        .strip()
    )

    venue_mapping = (
        TAB_FORM_VENUE_CODES.get(
            meeting_slug
        )
    )

    if venue_mapping is None:
        print(
            f"WARNING: No TAB Form venue code "
            f"configured for {meeting_slug} "
            f"({normal_venue_code})."
        )

        try:
            send_missing_form_venue_alert(
                meeting_name=meeting_slug,
                normal_venue_code=normal_venue_code,
                meeting_date=meeting_date
            )

        except Exception as error:
            print(
                f"ERROR while attempting missing venue "
                f"notification: {error}"
            )

        return None

    configured_normal_code = (
        venue_mapping[
            "normal_venue_code"
        ]
    )

    form_venue_code = (
        venue_mapping[
            "form_venue_code"
        ]
    )

    if (
        configured_normal_code
        and configured_normal_code
        != normal_venue_code
    ):
        print(
            f"WARNING: TAB Form CSV normal venue code "
            f"for {meeting_slug} is "
            f"{configured_normal_code}, "
            f"but race URL uses "
            f"{normal_venue_code}."
        )

    return (
        "https://form.tab.com.au/racing/"
        f"{meeting_date}/"
        f"{meeting_slug}/"
        f"{form_venue_code}/"
        f"{race_type}/"
        f"{race_number}"
    )


# ============================================================
# LEGACY TEXT RESULT PARSER
# ============================================================

def parse_results(
    body_text: str
) -> list[dict]:
    """
    Parse finishing positions from rendered body text.

    This fallback deliberately does not determine Fixed Odds
    settlement status.
    """

    results_match = re.search(
        r"(?im)^Results\s+Runner",
        body_text
    )

    if results_match is None:
        return []

    results_text = body_text[
        results_match.start():
    ]

    exotic_match = re.search(
        r"(?im)^Exotic Results\b",
        results_text
    )

    if exotic_match is not None:
        results_text = results_text[
            :exotic_match.start()
        ]

    result_pattern = re.compile(
        r"(?im)^"
        r"\s*"
        r"(\d+(?:st|nd|rd|th))"
        r"\s+"
        r"(\d+)"
        r"\.\s*"
        r"([^\r\n]+?)"
        r"\s*$"
    )

    results = []

    for match in result_pattern.finditer(
        results_text
    ):
        finish_position = (
            ordinal_to_position(
                match.group(1)
            )
        )

        if finish_position is None:
            continue

        runner_number = int(
            match.group(2)
        )

        runner_name = (
            match.group(3)
            .strip()
        )

        results.append(
            {
                "finish_position":
                    finish_position,
                "runner_number":
                    runner_number,
                "runner_name":
                    runner_name,
                "fixed_odds_paid":
                    None,
                "fixed_odds_values":
                    [],
                "scratched":
                    False,
            }
        )

    results.sort(
        key=lambda result:
        result["finish_position"]
    )

    return results


# ============================================================
# STRUCTURED DOM RESULT PARSER
# ============================================================

def parse_results_from_dom(
    page: Page
) -> list[dict]:
    """
    Parse official finishing positions and Fixed Odds
    settlement dividends.

    TAB Form scratches are added separately.

    Tote is ignored completely.
    """

    result_table = page.locator(
        'table[data-id="race-results"]'
    )

    if result_table.count() == 0:
        return []

    result_rows = result_table.locator(
        "tbody tr.result-item"
    )

    row_count = result_rows.count()

    if row_count == 0:
        return []

    results = []

    for row_index in range(
        row_count
    ):
        row = result_rows.nth(
            row_index
        )

        cells = row.locator(
            "td"
        )

        cell_count = cells.count()

        if cell_count < 4:
            continue

        # ----------------------------------------------------
        # FINISHING POSITION
        # ----------------------------------------------------

        position_text = (
            cells.nth(0)
            .inner_text()
            .strip()
        )

        finish_position = (
            ordinal_to_position(
                position_text
            )
        )

        if finish_position is None:
            continue

        # ----------------------------------------------------
        # RUNNER
        # ----------------------------------------------------

        runner_details_text = (
            cells.nth(2)
            .inner_text()
            .strip()
        )

        runner_first_line = (
            runner_details_text
            .splitlines()[0]
            .strip()
            if runner_details_text
            else ""
        )

        runner_match = re.match(
            r"^\s*(\d+)\.\s*(.+?)\s*$",
            runner_first_line
        )

        if runner_match is None:
            continue

        runner_number = int(
            runner_match.group(1)
        )

        runner_name = (
            runner_match.group(2)
            .strip()
        )

        # ----------------------------------------------------
        # FIXED ODDS SETTLEMENT COLUMN
        #
        # ONLY Fixed Odds is inspected.
        #
        # Tote is deliberately ignored.
        # ----------------------------------------------------

        fixed_odds_text = (
            cells.nth(3)
            .inner_text()
            .strip()
        )

        fixed_odds_values = (
            extract_dollar_values(
                fixed_odds_text
            )
        )

        fixed_odds_paid = (
            len(fixed_odds_values) > 0
        )

        results.append(
            {
                "finish_position":
                    finish_position,
                "runner_number":
                    runner_number,
                "runner_name":
                    runner_name,
                "fixed_odds_paid":
                    fixed_odds_paid,
                "fixed_odds_values":
                    fixed_odds_values,
                "scratched":
                    False,
            }
        )

    if not results:
        return []

    # ========================================================
    # SCRATCHINGS
    #
    # Only TAB Form has the dedicated Scratchings parser.
    # ========================================================

    if page_is_tab_form(
        page
    ):

        try:
            body_text = (
                page.locator(
                    "body"
                )
                .inner_text(
                    timeout=5000
                )
            )

        except Exception:
            body_text = ""

        results = add_scratched_runners(
            page=page,
            results=results,
            body_text=body_text
        )

    return results


# ============================================================
# POLLING
# ============================================================

def poll_page_for_results(
    page: Page,
    max_wait_seconds: int,
    attempt_label: str
) -> tuple[list[dict], str]:
    """
    Poll the currently loaded page until official results
    become available.

    Priority:

        1. Structured DOM parser
           -> Fixed Odds settlement status
           -> TAB Form scratches

        2. Legacy body-text parser
           -> finishing position only
    """

    start_time = time.monotonic()

    poll_attempt = 0

    last_body_text = ""

    while (
        time.monotonic()
        - start_time
        < max_wait_seconds
    ):
        poll_attempt += 1

        try:
            # =================================================
            # STRUCTURED DOM PARSER
            # =================================================

            results = parse_results_from_dom(
                page
            )

            if results:
                elapsed = (
                    time.monotonic()
                    - start_time
                )

                finishers = [
                    result
                    for result in results
                    if not result.get(
                        "scratched",
                        False
                    )
                ]

                scratches = [
                    result
                    for result in results
                    if result.get(
                        "scratched",
                        False
                    )
                ]

                print(
                    f"Parsed "
                    f"{len(finishers)} "
                    f"finishing position(s)"
                    f" and "
                    f"{len(scratches)} "
                    f"scratching(s) "
                    f"after {elapsed:.1f}s "
                    f"({attempt_label})."
                )

                for result in results:

                    if result.get(
                        "scratched",
                        False
                    ):
                        print(
                            f"  SCR: "
                            f"#{result['runner_number']} "
                            f"{result['runner_name']}"
                        )
                        continue

                    if (
                        result[
                            "fixed_odds_paid"
                        ]
                    ):
                        fixed_text = (
                            ", ".join(
                                f"${value:.2f}"
                                for value
                                in result[
                                    "fixed_odds_values"
                                ]
                            )
                        )

                    else:
                        fixed_text = (
                            "NO FIXED ODDS DIVIDEND"
                        )

                    print(
                        f"  "
                        f"{result['finish_position']}: "
                        f"#{result['runner_number']} "
                        f"{result['runner_name']} "
                        f"| Fixed: {fixed_text}"
                    )

                return (
                    results,
                    last_body_text
                )

            # =================================================
            # BODY TEXT FOR DIAGNOSTICS / FALLBACK
            # =================================================

            body_text = page.locator(
                "body"
            ).inner_text(
                timeout=5000
            )

            last_body_text = body_text

            fallback_results = parse_results(
                body_text
            )

            if fallback_results:
                elapsed = (
                    time.monotonic()
                    - start_time
                )

                # ------------------------------------------------
                # Only TAB Form may augment fallback results with
                # dedicated Scratchings-section data.
                # ------------------------------------------------

                if page_is_tab_form(
                    page
                ):
                    fallback_results = (
                        add_scratched_runners(
                            page=page,
                            results=fallback_results,
                            body_text=body_text
                        )
                    )

                print(
                    f"Parsed "
                    f"{len(fallback_results)} "
                    f"result record(s) "
                    f"using text fallback "
                    f"after {elapsed:.1f}s "
                    f"({attempt_label})."
                )

                print(
                    "WARNING: Fixed Odds settlement "
                    "status could not be determined "
                    "for ordinary finishers from "
                    "the text fallback."
                )

                return (
                    fallback_results,
                    last_body_text
                )

        except Exception as error:
            print(
                f"Result parse poll "
                f"{poll_attempt} failed "
                f"({attempt_label}): "
                f"{error}"
            )

        page.wait_for_timeout(
            RESULT_POLL_INTERVAL_MS
        )

    return (
        [],
        last_body_text
    )


# ============================================================
# DIAGNOSTICS
# ============================================================

def print_page_diagnostics(
    body_text: str,
    max_wait_seconds: int,
    attempt_label: str,
    is_form_page: bool
) -> None:
    """
    Print diagnostics for an unsuccessful result scrape.

    Scratchings are only parsed/displayed for TAB Form.
    """

    body_contains_results = (
        "Results"
        in body_text
    )

    body_contains_results_runner = (
        re.search(
            r"(?im)^Results\s+Runner",
            body_text
        )
        is not None
    )

    body_contains_first = (
        re.search(
            r"(?im)^\s*1st\b",
            body_text
        )
        is not None
    )

    body_contains_fourth = (
        re.search(
            r"(?im)^\s*4th\b",
            body_text
        )
        is not None
    )

    print(
        f"No finishing positions parsed "
        f"after {max_wait_seconds}s "
        f"({attempt_label})."
    )

    print(
        "Page diagnostics:"
    )

    print(
        f"  Body characters: "
        f"{len(body_text)}"
    )

    print(
        f"  Results text present: "
        f"{body_contains_results}"
    )

    print(
        f"  Results/Runner header present: "
        f"{body_contains_results_runner}"
    )

    print(
        f"  1st position present: "
        f"{body_contains_first}"
    )

    print(
        f"  4th position present: "
        f"{body_contains_fourth}"
    )

    if is_form_page:

        scratchings = (
            parse_scratched_runner_numbers(
                body_text
            )
        )

        print(
            f"  TAB Form scratchings detected: "
            f"{scratchings}"
        )

    else:

        print(
            "  Scratchings check: "
            "SKIPPED on normal TAB page"
        )


# ============================================================
# SCRAPE ONE URL
# ============================================================

def scrape_results_from_url(
    page: Page,
    race_url: str
) -> list[dict]:
    """
    Load one TAB race page and parse its official results.

    Normal TAB:
        Result parsing only.

        TAB Form Scratchings parser is NEVER used.

    TAB Form:
        Result parsing plus dedicated Scratchings section.
    """

    print(
        f"Result URL: {race_url}"
    )

    parsed_url = urlparse(
        race_url
    )

    is_form_page = (
        parsed_url.netloc
        .lower()
        == "form.tab.com.au"
    )

    # ========================================================
    # NORMAL TAB PAGE
    # ========================================================

    if not is_form_page:

        page.goto(
            race_url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        (
            results,
            last_body_text
        ) = poll_page_for_results(
            page=page,
            max_wait_seconds=(
                NORMAL_TAB_MAX_WAIT_SECONDS
            ),
            attempt_label="normal TAB"
        )

        if results:
            return results

        print_page_diagnostics(
            body_text=last_body_text,
            max_wait_seconds=(
                NORMAL_TAB_MAX_WAIT_SECONDS
            ),
            attempt_label="normal TAB",
            is_form_page=False
        )

        return []

    # ========================================================
    # TAB FORM PAGE
    # ========================================================

    for form_attempt in range(
        1,
        FORM_TAB_MAX_ATTEMPTS + 1
    ):

        attempt_label = (
            f"TAB Form attempt "
            f"{form_attempt}/"
            f"{FORM_TAB_MAX_ATTEMPTS}"
        )

        if form_attempt == 1:

            print(
                "Loading TAB Form page..."
            )

            page.goto(
                race_url,
                wait_until="domcontentloaded",
                timeout=60000
            )

        else:

            print(
                "TAB Form result was not available "
                "on the first attempt."
            )

            print(
                "Reloading TAB Form page for "
                "one final attempt..."
            )

            try:
                page.reload(
                    wait_until="domcontentloaded",
                    timeout=60000
                )

            except Exception as reload_error:
                print(
                    f"TAB Form reload failed: "
                    f"{reload_error}"
                )

                print(
                    "Attempting direct navigation "
                    "to the Form URL again..."
                )

                page.goto(
                    race_url,
                    wait_until="domcontentloaded",
                    timeout=60000
                )

        (
            results,
            last_body_text
        ) = poll_page_for_results(
            page=page,
            max_wait_seconds=(
                FORM_TAB_MAX_WAIT_SECONDS
            ),
            attempt_label=attempt_label
        )

        if results:

            if form_attempt > 1:
                print(
                    "TAB Form result recovered "
                    "after reload."
                )

            return results

        print_page_diagnostics(
            body_text=last_body_text,
            max_wait_seconds=(
                FORM_TAB_MAX_WAIT_SECONDS
            ),
            attempt_label=attempt_label,
            is_form_page=True
        )

    print(
        "TAB Form result unavailable after "
        f"{FORM_TAB_MAX_ATTEMPTS} attempts."
    )

    return []


# ============================================================
# LEGACY COMBINED GETTER
# ============================================================

def get_race_results(
    page: Page,
    race_url: str
) -> list[dict]:
    """
    Retrieve official race results using the supplied page.

    Normal TAB is attempted first, followed by TAB Form.
    """

    try:
        results = scrape_results_from_url(
            page=page,
            race_url=race_url
        )

        if results:
            print(
                "Official result found "
                "on normal TAB page."
            )

            return results

        print(
            "No result found on normal TAB page."
        )

    except Exception as error:
        print(
            f"Normal TAB result page failed: "
            f"{error}"
        )

    form_url = build_form_url(
        race_url
    )

    if form_url is None:
        return []

    try:
        results = scrape_results_from_url(
            page=page,
            race_url=form_url
        )

        if results:
            print(
                "Official result found "
                "on TAB Form page."
            )

            return results

        print(
            "No result found on TAB Form page."
        )

    except Exception as error:
        print(
            f"TAB Form result page failed: "
            f"{error}"
        )

    return []


# ============================================================
# WINNER HELPER
# ============================================================

def get_race_winner(
    page: Page,
    race_url: str
) -> dict | None:
    """
    Return only the explicitly listed winning runner.
    """

    results = get_race_results(
        page=page,
        race_url=race_url
    )

    for result in results:

        if result.get(
            "scratched",
            False
        ):
            continue

        if (
            result["finish_position"]
            == 1
        ):
            return result

    return None