from collections import defaultdict
from datetime import datetime, timedelta

from browser_session import BrowserSession
from database import (
    connect_database,
    create_tables,
    get_unchecked_alert_runners,
    save_finish_position,
)
from result_scraper import (
    build_form_url,
    scrape_results_from_url,
)


RESULT_CHECK_DELAY_MINUTES = 20


# ============================================================
# RESULT POSITION RULES
#
# FINISHPOSITION meanings:
#
#     NULL
#         Result has not yet been established.
#         RESULTCHECKED remains 0.
#
#     1
#         Runner finished 1st AND TAB paid a
#         Fixed Odds dividend.
#
#         Power BI:
#             Win
#
#     2-98
#         Runner was explicitly listed in that finishing
#         position AND TAB paid a Fixed Odds dividend.
#
#         Power BI:
#             Place
#
#     99
#         Did not place for Fixed Odds purposes.
#
#         This includes:
#
#             - runner explicitly listed in the result,
#               but NO Fixed Odds dividend was paid
#
#             - runner not listed in the published
#               TAB/Form result rows
#
#     100
#         SCRATCHED.
#
#         This takes priority over Fixed Odds dividend
#         status because a scratched runner will naturally
#         have no Fixed Odds dividend.
#
# IMPORTANT:
#
# A finishing position by itself does NOT mean the runner
# placed.
#
# The Fixed Odds settlement dividend determines whether
# a non-scratched runner is treated as:
#
#     Win
#     Place
#     Did not Place
#
# SCRATCHED is handled separately and always remains 100.
#
# Tote is ignored completely.
# ============================================================

DID_NOT_PLACE_POSITION = 99

SCRATCHED_POSITION = 100


def build_race_url(
    meeting_date: str,
    meeting_name: str,
    venue_code: str,
    race_number: int
) -> str:
    """
    Build the normal TAB URL for a race.

    Example:

        https://www.tab.com.au/racing/
        2026-08-11/BULLI/BUL/G/2
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

    Returns None if race_start is unavailable
    or malformed.
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


def parse_runner_meeting_date(
    runner: dict
) -> datetime | None:
    """
    Read MEETINGDATE for an alerted runner.

    Expected format:

        YYYY-MM-DD

    Returns None if unavailable or malformed.
    """

    meeting_date = runner.get(
        "meeting_date"
    )

    if not meeting_date:
        return None

    try:
        return datetime.strptime(
            meeting_date,
            "%Y-%m-%d"
        )

    except ValueError:
        return None


def race_is_ready_for_result_check(
    alerted_runners: list[dict],
    now: datetime
) -> bool:
    """
    Determine whether a race can be checked for results.

    Normal behaviour:

        RACESTART exists
            -> wait until RACESTART + 20 minutes

    Historical fallback:

        RACESTART is missing
        AND MEETINGDATE is before today
            -> allow result check

    Safety behaviour:

        RACESTART is missing
        AND MEETINGDATE is today or in the future
            -> do not check

        RACESTART and MEETINGDATE are both unusable
            -> do not check
    """

    if not alerted_runners:
        return False

    runner = alerted_runners[0]

    # ========================================================
    # PRIMARY RULE — USE RACESTART WHEN AVAILABLE
    # ========================================================

    race_start = parse_runner_race_start(
        runner
    )

    if race_start is not None:

        result_check_time = (
            race_start
            + timedelta(
                minutes=RESULT_CHECK_DELAY_MINUTES
            )
        )

        return now >= result_check_time

    # ========================================================
    # HISTORICAL FALLBACK
    # ========================================================

    meeting_date = parse_runner_meeting_date(
        runner
    )

    if meeting_date is None:
        return False

    today = now.date()

    if meeting_date.date() < today:
        print(
            f"Historical result fallback: "
            f"RACESTART missing for "
            f"{runner['venue_code']} "
            f"R{runner['race_number']}; "
            f"MEETINGDATE "
            f"{runner['meeting_date']} "
            f"is in the past."
        )

        return True

    return False


def results_have_fixed_odds_status(
    results: list[dict]
) -> bool:
    """
    Return True only when every parsed result has enough
    settlement information for final classification.

    NORMAL RESULT:

        fixed_odds_paid must be True or False.

    SCRATCHED RESULT:

        finish_position = 100

        Fixed Odds dividend status is irrelevant because
        the runner did not participate.

    This means a SCR record remains usable even though
    fixed_odds_paid will normally be False.

    The legacy flattened-text fallback contains:

        fixed_odds_paid = None

    for ordinary finishing positions, so those results are
    not sufficient for final classification.

    Tote is ignored completely.
    """

    if not results:
        return False

    for result in results:

        finish_position = (
            result.get(
                "finish_position"
            )
        )

        try:
            finish_position = int(
                finish_position
            )

        except (
            TypeError,
            ValueError
        ):
            return False

        # ----------------------------------------------------
        # SCRATCHED RESULT
        #
        # No Fixed Odds settlement is required.
        # ----------------------------------------------------

        if (
            finish_position
            == SCRATCHED_POSITION
        ):
            continue

        fixed_odds_paid = (
            result.get(
                "fixed_odds_paid"
            )
        )

        if fixed_odds_paid is None:
            return False

    return True


def get_results_with_isolated_sessions(
    race_url: str
) -> list[dict]:
    """
    Retrieve official race results using completely
    separate browser sessions for normal TAB and TAB Form.

    Fixed Odds settlement information is mandatory for
    ordinary results.

    SCRATCHED results are accepted as:

        FINISHPOSITION = 100

    without requiring a Fixed Odds dividend.

    If the normal TAB page returns finishing positions but
    Fixed Odds settlement status is unknown, that result is
    NOT accepted.

    TAB Form is then attempted in a fresh BrowserSession.

    This preserves the browser-isolation behaviour proven
    necessary for TAB Form historical pages.
    """

    # ========================================================
    # ATTEMPT 1 — NORMAL TAB
    # ========================================================

    normal_session = BrowserSession()

    try:
        normal_session.start()

        normal_page = (
            normal_session.get_page()
        )

        results = scrape_results_from_url(
            page=normal_page,
            race_url=race_url
        )

        if results:

            if results_have_fixed_odds_status(
                results
            ):
                print(
                    "Official result with Fixed Odds "
                    "settlement / scratch status found "
                    "on normal TAB page."
                )

                return results

            print(
                "Normal TAB result found, but "
                "Fixed Odds settlement status "
                "could not be determined."
            )

            print(
                "Trying TAB Form in a fresh "
                "browser session."
            )

        else:
            print(
                "No result found on normal TAB page."
            )

    except Exception as error:
        print(
            f"Normal TAB result page failed: "
            f"{error}"
        )

    finally:
        normal_session.close()

    # ========================================================
    # BUILD TAB FORM URL
    # ========================================================

    form_url = build_form_url(
        race_url
    )

    if form_url is None:
        return []

    # ========================================================
    # ATTEMPT 2 — TAB FORM
    #
    # Completely separate BrowserSession.
    # ========================================================

    form_session = BrowserSession()

    try:
        form_session.start()

        form_page = (
            form_session.get_page()
        )

        results = scrape_results_from_url(
            page=form_page,
            race_url=form_url
        )

        if results:

            if results_have_fixed_odds_status(
                results
            ):
                print(
                    "Official result with Fixed Odds "
                    "settlement / scratch status found "
                    "on TAB Form page."
                )

                return results

            print(
                "TAB Form result found, but "
                "Fixed Odds settlement status "
                "could not be determined."
            )

            print(
                "Leaving result unresolved rather than "
                "using Tote or guessing payout status."
            )

        else:
            print(
                "No result found on TAB Form page."
            )

    except Exception as error:
        print(
            f"TAB Form result page failed: "
            f"{error}"
        )

    finally:
        form_session.close()

    return []


def process_race_results(
    race_url: str,
    alerted_runners: list[dict]
) -> tuple[bool, int]:
    """
    Process the official Fixed Odds result for one race.

    Returns:

        (True, resolved_runner_count)

            At least one usable official result was
            published with known settlement / scratch
            status and alerted runners were processed.

        (False, 0)

            No usable result was available.

    FINAL CLASSIFICATION:

        Runner explicitly marked SCR:
            FINISHPOSITION = 100
            -> SCR

        Runner listed 1st
        AND Fixed Odds dividend paid:
            FINISHPOSITION = 1
            -> Win

        Runner listed 2nd or lower
        AND Fixed Odds dividend paid:
            FINISHPOSITION = exact position
            -> Place

        Runner explicitly listed
        BUT no Fixed Odds dividend paid:
            FINISHPOSITION = 99
            -> Did not Place

        Runner absent from published result rows:
            FINISHPOSITION = 99
            -> Did not Place

        SCR takes priority over Fixed Odds settlement.

        Tote is ignored completely.
    """

    results = get_results_with_isolated_sessions(
        race_url
    )

    # ========================================================
    # NO USABLE RESULT YET
    # ========================================================

    if not results:
        print(
            "Official Fixed Odds result / scratch status "
            "not available yet."
        )

        return False, 0

    # ========================================================
    # BUILD PUBLISHED RESULT LOOKUP
    # ========================================================

    published_results = {}

    for result in results:

        runner_number = (
            result.get(
                "runner_number"
            )
        )

        finish_position = (
            result.get(
                "finish_position"
            )
        )

        fixed_odds_paid = (
            result.get(
                "fixed_odds_paid"
            )
        )

        fixed_odds_values = (
            result.get(
                "fixed_odds_values",
                []
            )
        )

        scratched = (
            result.get(
                "scratched",
                False
            )
        )

        if runner_number is None:
            continue

        if finish_position is None:
            continue

        try:
            runner_number = int(
                runner_number
            )

            finish_position = int(
                finish_position
            )

        except (
            TypeError,
            ValueError
        ):
            continue

        # ----------------------------------------------------
        # FINISHPOSITION 100 IS AUTHORITATIVE.
        #
        # Also preserve an explicit scratched=True flag if
        # result_scraper.py provides one.
        # ----------------------------------------------------

        is_scratched = (
            finish_position
            == SCRATCHED_POSITION
            or bool(
                scratched
            )
        )

        if is_scratched:
            finish_position = (
                SCRATCHED_POSITION
            )

            fixed_odds_paid = False

            fixed_odds_values = []

        elif fixed_odds_paid is None:
            continue

        published_results[
            runner_number
        ] = {
            "finish_position":
                finish_position,
            "fixed_odds_paid":
                bool(
                    fixed_odds_paid
                ),
            "fixed_odds_values":
                fixed_odds_values,
            "scratched":
                is_scratched,
        }

    # ========================================================
    # SAFETY CHECK
    # ========================================================

    if not published_results:
        print(
            "Official result data was returned, "
            "but no usable Fixed Odds settlement "
            "or scratch records could be parsed."
        )

        print(
            "Leaving alerted runners unchecked."
        )

        return False, 0

    print(
        f"Official published result contains "
        f"{len(published_results)} "
        f"runner(s) with known settlement "
        f"or scratch status."
    )

    # ========================================================
    # SAVE RESULTS
    # ========================================================

    database = connect_database()

    resolved_runner_count = 0

    try:
        create_tables(
            database
        )

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

            published_result = (
                published_results.get(
                    runner_number
                )
            )

            # =================================================
            # RUNNER NOT LISTED IN OFFICIAL RESULT ROWS
            #
            # Did not Place.
            # =================================================

            if published_result is None:

                save_finish_position(
                    database,
                    runner_id,
                    DID_NOT_PLACE_POSITION
                )

                resolved_runner_count += 1

                print(
                    f"Result saved: "
                    f"{alerted_runner['venue_code']} "
                    f"R{alerted_runner['race_number']} "
                    f"#{runner_number} "
                    f"{runner_name} - "
                    f"DID NOT PLACE "
                    f"(not listed in TAB/Form "
                    f"result rows)"
                )

                continue

            finish_position = (
                published_result[
                    "finish_position"
                ]
            )

            fixed_odds_paid = (
                published_result[
                    "fixed_odds_paid"
                ]
            )

            fixed_odds_values = (
                published_result[
                    "fixed_odds_values"
                ]
            )

            scratched = (
                published_result[
                    "scratched"
                ]
            )

            # =================================================
            # SCRATCHED
            #
            # THIS MUST BE CHECKED BEFORE:
            #
            #     if not fixed_odds_paid
            #
            # because a scratched runner naturally has no
            # Fixed Odds dividend.
            #
            # SCR is always:
            #
            #     FINISHPOSITION = 100
            #
            # save_finish_position() also marks:
            #
            #     RESULTCHECKED = 1
            # =================================================

            if (
                scratched
                or finish_position
                == SCRATCHED_POSITION
            ):

                save_finish_position(
                    database,
                    runner_id,
                    SCRATCHED_POSITION
                )

                resolved_runner_count += 1

                print(
                    f"Result saved: "
                    f"{alerted_runner['venue_code']} "
                    f"R{alerted_runner['race_number']} "
                    f"#{runner_number} "
                    f"{runner_name} - "
                    f"SCR"
                )

                continue

            # =================================================
            # LISTED BUT NO FIXED ODDS DIVIDEND
            #
            # Example:
            #
            #     4th GOLD CARD
            #
            # Tote may show a dividend elsewhere,
            # but Fixed Odds result cell is blank.
            #
            #     -> DID NOT PLACE
            # =================================================

            if not fixed_odds_paid:

                save_finish_position(
                    database,
                    runner_id,
                    DID_NOT_PLACE_POSITION
                )

                resolved_runner_count += 1

                print(
                    f"Result saved: "
                    f"{alerted_runner['venue_code']} "
                    f"R{alerted_runner['race_number']} "
                    f"#{runner_number} "
                    f"{runner_name} - "
                    f"DID NOT PLACE "
                    f"(finished {finish_position}, "
                    f"no Fixed Odds dividend)"
                )

                continue

            # =================================================
            # FIXED ODDS DIVIDEND PAID
            #
            # 1st:
            #     WIN
            #
            # 2nd+:
            #     PLACE
            # =================================================

            save_finish_position(
                database,
                runner_id,
                finish_position
            )

            resolved_runner_count += 1

            fixed_text = (
                ", ".join(
                    f"${value:.2f}"
                    for value
                    in fixed_odds_values
                )
            )

            if finish_position == 1:

                result_text = (
                    "1st - WIN"
                )

            else:

                result_text = (
                    f"{finish_position} - PLACE"
                )

            if fixed_text:
                result_text += (
                    f" "
                    f"(Fixed: {fixed_text})"
                )

            print(
                f"Result saved: "
                f"{alerted_runner['venue_code']} "
                f"R{alerted_runner['race_number']} "
                f"#{runner_number} "
                f"{runner_name} - "
                f"{result_text}"
            )

    finally:
        database.close()

    return (
        True,
        resolved_runner_count
    )


def get_unresolved_summary() -> tuple[int, int]:
    """
    Return:

        unresolved_race_count,
        unresolved_runner_count

    based on ALERT_HISTORY records where
    RESULTCHECKED = 0.
    """

    database = connect_database()

    try:
        create_tables(
            database
        )

        unresolved_runners = (
            get_unchecked_alert_runners(
                database
            )
        )

    finally:
        database.close()

    unresolved_runner_count = len(
        unresolved_runners
    )

    unresolved_races = set()

    for runner in unresolved_runners:

        race_key = (
            runner["meeting_date"],
            runner["meeting_name"],
            runner["venue_code"],
            runner["race_number"]
        )

        unresolved_races.add(
            race_key
        )

    unresolved_race_count = len(
        unresolved_races
    )

    return (
        unresolved_race_count,
        unresolved_runner_count
    )


def check_unprocessed_results() -> None:
    """
    Find alerted runners whose results have not yet
    been processed.

    Runners are grouped by race so TAB is only visited
    once for each race.

    Prints a summary showing:

        races processed this run
        runners resolved this run
        unresolved races remaining
        unresolved runners remaining
    """

    database = connect_database()

    try:
        create_tables(
            database
        )

        unchecked_runners = (
            get_unchecked_alert_runners(
                database
            )
        )

    finally:
        database.close()

    if not unchecked_runners:
        print()
        print(
            "No unresolved alerted results."
        )

        print()
        print(
            "RESULT MONITOR SUMMARY"
        )
        print(
            "----------------------"
        )
        print(
            "Processed races: 0"
        )
        print(
            "Resolved runners: 0"
        )
        print(
            "Unresolved races: 0"
        )
        print(
            "Unresolved runners: 0"
        )

        return

    # ========================================================
    # GROUP ALERTED RUNNERS BY RACE
    # ========================================================

    races = defaultdict(
        list
    )

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

    initial_unresolved_races = len(
        races
    )

    initial_unresolved_runners = len(
        unchecked_runners
    )

    print()
    print(
        "RESULT MONITOR START"
    )
    print(
        "--------------------"
    )

    print(
        f"Unresolved races: "
        f"{initial_unresolved_races}"
    )

    print(
        f"Unresolved runners: "
        f"{initial_unresolved_runners}"
    )

    now = datetime.now()

    races_checked = 0
    runners_resolved = 0
    races_skipped_missing_meeting = 0
    races_not_ready = 0

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
        # MISSING MEETING NAME
        # ----------------------------------------------------

        if not meeting_name:

            races_skipped_missing_meeting += 1

            print()

            print(
                f"Skipping result: "
                f"{venue_code} "
                f"R{race_number}"
            )

            print(
                "Reason: MEETINGNAME is missing "
                "from RUNNERS."
            )

            for runner in alerted_runners:
                print(
                    f"  Unresolved runner: "
                    f"#{runner['runner_number']} "
                    f"{runner['runner_name']}"
                )

            continue

        # ----------------------------------------------------
        # RESULT-CHECK TIMING
        # ----------------------------------------------------

        if not race_is_ready_for_result_check(
            alerted_runners,
            now
        ):
            races_not_ready += 1

            print()

            print(
                f"Skipping result: "
                f"{meeting_name} "
                f"R{race_number}"
            )

            print(
                "Reason: race is not yet eligible "
                "for a result check."
            )

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

        (
            result_found,
            resolved_runner_count
        ) = process_race_results(
            race_url=race_url,
            alerted_runners=alerted_runners
        )

        if result_found:
            races_checked += 1

            runners_resolved += (
                resolved_runner_count
            )

    # ========================================================
    # FINAL UNRESOLVED STATE
    # ========================================================

    (
        unresolved_race_count,
        unresolved_runner_count
    ) = get_unresolved_summary()

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print(
        "RESULT MONITOR SUMMARY"
    )
    print(
        "----------------------"
    )

    print(
        f"Processed races: "
        f"{races_checked}"
    )

    print(
        f"Resolved runners: "
        f"{runners_resolved}"
    )

    print(
        f"Unresolved races: "
        f"{unresolved_race_count}"
    )

    print(
        f"Unresolved runners: "
        f"{unresolved_runner_count}"
    )

    if races_skipped_missing_meeting > 0:
        print(
            f"Missing meeting-name races: "
            f"{races_skipped_missing_meeting}"
        )

    if races_not_ready > 0:
        print(
            f"Not-yet-eligible races: "
            f"{races_not_ready}"
        )


if __name__ == "__main__":
    check_unprocessed_results()