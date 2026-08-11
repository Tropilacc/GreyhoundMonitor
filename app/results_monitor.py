from collections import defaultdict
from datetime import datetime, timedelta

from browser_session import BrowserSession
from database import (
    connect_database,
    create_tables,
    get_unchecked_alert_runners,
    save_finish_position,
)
from result_scraper import get_race_results


RESULT_CHECK_DELAY_MINUTES = 20


def build_race_url(
    meeting_date: str,
    meeting_name: str,
    venue_code: str,
    race_number: int
) -> str:
    """
    Build the normal TAB URL for a greyhound race.

    Example:

    meeting_date:
        2026-08-10

    meeting_name:
        SHEPPARTON

    venue_code:
        SHE

    race_number:
        6

    Result:
        https://www.tab.com.au/racing/
        2026-08-10/SHEPPARTON/SHE/G/6

    result_scraper.py is responsible for attempting
    the TAB Form fallback when required.
    """

    meeting_slug = (
        meeting_name
        .strip()
        .upper()
        .replace(" ", "-")
    )

    return (
        "https://www.tab.com.au/racing/"
        f"{meeting_date}/"
        f"{meeting_slug}/"
        f"{venue_code}/G/"
        f"{race_number}"
    )


def parse_runner_race_start(
    runner: dict
) -> datetime | None:
    """
    Read the race start time stored against an
    unchecked alerted runner.

    Returns None if race_start is unavailable.
    """

    race_start = runner.get(
        "race_start"
    )

    if not race_start:
        return None

    try:
        return datetime.strptime(
            race_start,
            "%Y-%m-%d %H:%M"
        )

    except ValueError:
        return None


def race_is_ready_for_result_check(
    alerted_runners: list[dict],
    now: datetime
) -> bool:
    """
    Return True only when at least 20 minutes have
    passed since the scheduled race start.

    All runners in this list belong to the same race,
    so only the first runner needs to be inspected.
    """

    if not alerted_runners:
        return False

    race_start = parse_runner_race_start(
        alerted_runners[0]
    )

    if race_start is None:
        return False

    result_check_time = (
        race_start
        + timedelta(
            minutes=RESULT_CHECK_DELAY_MINUTES
        )
    )

    return now >= result_check_time


def process_race_results(
    race_url: str,
    alerted_runners: list[dict]
) -> bool:
    """
    Visit one completed TAB race and process the
    official finishing positions for alerted runners.

    Returns:

        True
            TAB published an official result.

        False
            No official result was available yet.

    IMPORTANT:

    A runner is only considered processed when an
    actual finishing position has been found.

    If an official race result exists but a particular
    alerted runner is missing from the parsed finishing
    positions, that runner remains unchecked so the
    tracker can retry it later.
    """

    browser_session = BrowserSession()

    try:
        browser_session.start()

        page = browser_session.get_page()

        results = get_race_results(
            page=page,
            race_url=race_url
        )

    except Exception as error:
        print(
            f"ERROR scraping race result: "
            f"{error}"
        )

        return False

    finally:
        browser_session.close()

    if not results:
        print(
            "Official result not available yet."
        )

        return False

    # ========================================================
    # BUILD FINISHING POSITION LOOKUP
    #
    # Example:
    #
    # {
    #     4: 1,
    #     8: 2,
    #     3: 3,
    #     7: 4
    # }
    # ========================================================

    finish_positions = {
        result["runner_number"]:
        result["finish_position"]
        for result in results
    }

    database = connect_database()

    try:
        create_tables(database)

        for alerted_runner in alerted_runners:

            runner_number = (
                alerted_runner[
                    "runner_number"
                ]
            )

            runner_id = (
                alerted_runner[
                    "runner_id"
                ]
            )

            runner_name = (
                alerted_runner[
                    "runner_name"
                ]
            )

            finish_position = (
                finish_positions.get(
                    runner_number
                )
            )

            # =================================================
            # FINISHING POSITION FOUND
            #
            # save_finish_position() stores the position and
            # marks RESULTCHECKED = 1.
            # =================================================

            if finish_position is not None:

                save_finish_position(
                    database,
                    runner_id,
                    finish_position
                )

                if finish_position == 1:
                    result_text = "WINNER"

                else:
                    result_text = (
                        f"finished "
                        f"{finish_position}"
                    )

                print(
                    f"Result saved: "
                    f"{alerted_runner['venue_code']} "
                    f"R{alerted_runner['race_number']} "
                    f"#{runner_number} "
                    f"{runner_name} — "
                    f"{result_text}"
                )

            # =================================================
            # RUNNER NOT FOUND IN PARSED RESULTS
            #
            # DO NOT mark RESULTCHECKED.
            #
            # We know that some form of official result was
            # returned, but we do not know this runner's actual
            # finishing position.
            #
            # Leaving RESULTCHECKED = 0 ensures that
            # get_unchecked_alert_runners() returns this runner
            # again and the tracker can retry later.
            # =================================================

            else:
                print(
                    f"Result incomplete: "
                    f"{alerted_runner['venue_code']} "
                    f"R{alerted_runner['race_number']} "
                    f"#{runner_number} "
                    f"{runner_name} — "
                    f"finishing position not found; "
                    f"leaving result unchecked."
                )

    finally:
        database.close()

    return True


def check_unprocessed_results() -> None:
    """
    Find alerted runners whose results have not yet
    been processed.

    Runners are grouped by race so TAB is only visited
    once for each race.

    Result checks occur only when:

        scheduled race start + 20 minutes

    has been reached.

    A runner will stop being returned by
    get_unchecked_alert_runners() only after an actual
    finishing position has been stored.
    """

    database = connect_database()

    try:
        create_tables(database)

        unchecked_runners = (
            get_unchecked_alert_runners(
                database
            )
        )

    finally:
        database.close()

    if not unchecked_runners:
        return

    # ========================================================
    # GROUP ALERTED RUNNERS BY RACE
    # ========================================================

    races = defaultdict(list)

    for runner in unchecked_runners:

        race_key = (
            runner["meeting_date"],
            runner["meeting_name"],
            runner["venue_code"],
            runner["race_number"]
        )

        races[
            race_key
        ].append(
            runner
        )

    now = datetime.now()

    races_checked = 0

    # ========================================================
    # PROCESS ELIGIBLE RACES
    # ========================================================

    for (
        meeting_date,
        meeting_name,
        venue_code,
        race_number
    ), alerted_runners in races.items():

        # ----------------------------------------------------
        # WAIT UNTIL +20 MINUTES
        # ----------------------------------------------------

        if not race_is_ready_for_result_check(
            alerted_runners,
            now
        ):
            continue

        race_url = build_race_url(
            meeting_date=meeting_date,
            meeting_name=meeting_name,
            venue_code=venue_code,
            race_number=race_number
        )

        print()

        print(
            f"Checking result: "
            f"{meeting_name} "
            f"R{race_number}"
        )

        result_found = (
            process_race_results(
                race_url=race_url,
                alerted_runners=alerted_runners
            )
        )

        if result_found:
            races_checked += 1

    if races_checked > 0:
        print(
            f"Result check complete. "
            f"Processed "
            f"{races_checked} race(s)."
        )