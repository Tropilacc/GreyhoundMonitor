import re

from playwright.sync_api import Page


def ordinal_to_position(
    ordinal: str
) -> int | None:
    """
    Convert values such as:

    1st -> 1
    2nd -> 2
    3rd -> 3
    4th -> 4
    """

    match = re.match(
        r"^(\d+)(?:st|nd|rd|th)$",
        ordinal.strip(),
        re.IGNORECASE
    )

    if not match:
        return None

    return int(
        match.group(1)
    )


def get_race_results(
    page: Page,
    race_url: str
) -> list[dict]:
    """
    Scrape finishing positions from a completed
    TAB greyhound race.

    Returns data in this format:

    [
        {
            "finish_position": 1,
            "runner_number": 4,
            "runner_name": "GREYSYND CLYDE"
        },
        {
            "finish_position": 2,
            "runner_number": 8,
            "runner_name": "WHIPSTICK BOBBI"
        }
    ]

    If TAB has not published a result yet,
    an empty list is returned.
    """

    page.goto(
        race_url,
        wait_until="domcontentloaded",
        timeout=60000
    )

    # Allow TAB's JavaScript to populate the result.
    page.wait_for_timeout(5000)

    body_text = page.locator(
        "body"
    ).inner_text()

    # --------------------------------------------------------
    # Locate the Results section.
    #
    # We only want the first official finishing-order block,
    # not the later betting table or exotic results.
    # --------------------------------------------------------

    results_start = body_text.find(
        "Results         Runner"
    )

    if results_start == -1:
        results_start = body_text.find(
            "Results"
        )

    if results_start == -1:
        return []

    results_text = body_text[
        results_start:
    ]

    # Stop before the exotic-results section so that
    # numbers such as Quinella 4-8 are not mistaken
    # for finishing positions.
    exotic_start = results_text.find(
        "Exotic Results"
    )

    if exotic_start != -1:
        results_text = results_text[
            :exotic_start
        ]

    # --------------------------------------------------------
    # Parse lines such as:
    #
    # 1st             4. GREYSYND CLYDE
    # 2nd             8. WHIPSTICK BOBBI
    # --------------------------------------------------------

    pattern = re.compile(
        r"(?m)^"
        r"(\d+(?:st|nd|rd|th))"
        r"\s+"
        r"(\d+)\.\s+"
        r"([^\r\n]+)"
    )

    results = []

    for match in pattern.finditer(
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


def get_race_winner(
    page: Page,
    race_url: str
) -> dict | None:
    """
    Return only the winning runner.

    Example:

    {
        "finish_position": 1,
        "runner_number": 4,
        "runner_name": "GREYSYND CLYDE"
    }

    Returns None when the race result has not
    yet been published.
    """

    results = get_race_results(
        page=page,
        race_url=race_url
    )

    for result in results:
        if result["finish_position"] == 1:
            return result

    return None