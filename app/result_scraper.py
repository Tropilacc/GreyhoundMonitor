import re
from urllib.parse import urlparse

from playwright.sync_api import Page


# ============================================================
# TAB FORM VENUE CODES
#
# TAB's normal racing pages and TAB Form pages use different
# venue identifiers.
#
# Example:
#
# Normal:
# https://www.tab.com.au/racing/2026-08-10/GRAFTON/GRA/G/8
#
# Form:
# https://form.tab.com.au/racing/2026-08-10/GRAFTON/S/G/8
#
# TAB Form displays Grafton as "SG":
#
#     S = Form venue code
#     G = Greyhound
#
# The URL already contains /G/, so only "S" is needed in
# the venue-code position.
# ============================================================

TAB_FORM_VENUE_CODES = {
    "MAITLAND": "I",
    "DUBBO": "C",
    "GRAFTON": "S",
    "TRARALGON": "Y",
    "SANDOWN-PARK": "M",
    "SHEPPARTON": "E",
    "WARRNAMBOOL": "P",
    "SHEPPARTON-EXTRA": "N",
    "WARRNAMBOOL-EXTRA": "H",
    "ANGLE-PARK": "A",
    "HOBART": "T",
    "Q-STRAIGHT": "B",
    "NORTHAM": "W",
    "HARLOW": "F",
    "DONCASTER": "V",
    "MONMORE": "R",
    "Q-STRAIGHT-EXTRA": "D",
    "NOTTINGHAM": "U",
    "GREAT-YARMOUTH": "U",
    "SUNDERLAND": "O",
    "CENTRAL-PARK": "X",
    "DUNSTALL-PARK": "Q",
    "HARLOW-EXTRA": "G",
    "KINSLEY": "G",
    "ROMFORD": "Z",
    "YOUGHAL": "K",
}


def ordinal_to_position(
    ordinal: str
) -> int | None:
    """
    Convert an ordinal finishing position into an integer.

    Examples:

        1st -> 1
        2nd -> 2
        3rd -> 3
        4th -> 4
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


def build_form_url(
    race_url: str
) -> str | None:
    """
    Convert a normal TAB greyhound race URL into the
    corresponding historical TAB Form URL.

    Example:

        Normal:
        https://www.tab.com.au/racing/
        2026-08-10/GRAFTON/GRA/G/8

        Form:
        https://form.tab.com.au/racing/
        2026-08-10/GRAFTON/S/G/8

    Returns None when no Form venue code has been
    configured for the meeting.
    """

    parsed_url = urlparse(
        race_url
    )

    path_parts = [
        part
        for part in parsed_url.path.split("/")
        if part
    ]

    # Expected structure:
    #
    # [
    #     "racing",
    #     "2026-08-10",
    #     "GRAFTON",
    #     "GRA",
    #     "G",
    #     "8"
    # ]
    #
    if len(path_parts) < 6:
        print(
            f"WARNING: Unable to parse TAB race URL: "
            f"{race_url}"
        )

        return None

    meeting_date = path_parts[1]

    meeting_slug = (
        path_parts[2]
        .strip()
        .upper()
    )

    race_type = (
        path_parts[4]
        .strip()
        .upper()
    )

    race_number = path_parts[5]

    form_venue_code = (
        TAB_FORM_VENUE_CODES.get(
            meeting_slug
        )
    )

    if form_venue_code is None:
        print(
            f"WARNING: No TAB Form venue code "
            f"configured for {meeting_slug}."
        )

        return None

    return (
        "https://form.tab.com.au/racing/"
        f"{meeting_date}/"
        f"{meeting_slug}/"
        f"{form_venue_code}/"
        f"{race_type}/"
        f"{race_number}"
    )


def parse_results(
    body_text: str
) -> list[dict]:
    """
    Parse the official finishing-order block from either:

        - Normal TAB race page
        - Historical TAB Form page

    Actual rendered TAB Form format:

        Results         Runner          Tote
        1st             3. WHAT'S THE PRICE
        TMARK KNOWLESProp169043
        $5.50
        $1.70
        2nd             4. WHERE'S THE BOSS
        ...
        Exotic Results

    Only the finishing-position lines are extracted.
    Trainer names, dividends and exotic results are ignored.
    """

    # ========================================================
    # LOCATE RESULTS BLOCK
    # ========================================================

    results_match = re.search(
        r"(?im)^Results\s+Runner",
        body_text
    )

    if results_match is None:
        return []

    results_text = body_text[
        results_match.start():
    ]

    # ========================================================
    # STOP BEFORE EXOTIC RESULTS
    #
    # Prevent combinations such as:
    #
    #     Quinella
    #     3-4
    #
    # from ever being interpreted as finishing positions.
    # ========================================================

    exotic_match = re.search(
        r"(?im)^Exotic Results\b",
        results_text
    )

    if exotic_match is not None:
        results_text = results_text[
            :exotic_match.start()
        ]

    # ========================================================
    # PARSE FINISHING POSITIONS
    #
    # Matches:
    #
    #     1st             3. WHAT'S THE PRICE
    #     2nd             4. WHERE'S THE BOSS
    #     3rd             2. SPLENDACIOUS
    #     4th             1. CHAD'S A STAR
    #
    # The runner name ends at the newline, so trainer and
    # dividend information on later lines is ignored.
    # ========================================================

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
                "finish_position": finish_position,
                "runner_number": runner_number,
                "runner_name": runner_name
            }
        )

    results.sort(
        key=lambda result:
        result["finish_position"]
    )

    return results


def scrape_results_from_url(
    page: Page,
    race_url: str
) -> list[dict]:
    """
    Load one TAB race page and parse its official results.
    """

    print(
        f"Result URL: {race_url}"
    )

    page.goto(
        race_url,
        wait_until="domcontentloaded",
        timeout=60000
    )

    # Give TAB's JavaScript time to render the page.
    page.wait_for_timeout(
        5000
    )

    body_text = page.locator(
        "body"
    ).inner_text()

    results = parse_results(
        body_text
    )

    if results:
        print(
            f"Parsed {len(results)} "
            f"finishing position(s)."
        )

        for result in results:
            print(
                f"  {result['finish_position']}: "
                f"#{result['runner_number']} "
                f"{result['runner_name']}"
            )

    return results


def get_race_results(
    page: Page,
    race_url: str
) -> list[dict]:
    """
    Retrieve the official finishing positions for a TAB
    greyhound race.

    Recovery sequence:

        1. Try the normal TAB race page.

        2. If no finishing order is available there,
           construct the historical TAB Form URL using
           the Form-specific venue code.

        3. Try the TAB Form page.

        4. If neither source can provide an official
           finishing order, return [].

    Returning [] means the database result remains
    unchecked, so results_monitor.py will retry it later.
    """

    # ========================================================
    # NORMAL TAB PAGE
    # ========================================================

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

    # ========================================================
    # HISTORICAL TAB FORM PAGE
    # ========================================================

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


def get_race_winner(
    page: Page,
    race_url: str
) -> dict | None:
    """
    Return only the winning runner.

    Example:

        {
            "finish_position": 1,
            "runner_number": 3,
            "runner_name": "WHAT'S THE PRICE"
        }

    Returns None when an official result cannot
    currently be obtained.
    """

    results = get_race_results(
        page=page,
        race_url=race_url
    )

    for result in results:
        if (
            result["finish_position"]
            == 1
        ):
            return result

    return None