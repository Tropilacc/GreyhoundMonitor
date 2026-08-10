import time
from datetime import datetime

from browser_session import BrowserSession
from monitor import monitor_race
from notifications import send_startup_notification
from race_finder import get_todays_greyhound_races
from results_monitor import check_unprocessed_results


MAIN_LOOP_SECONDS = 30

# Don't run the result checker every 30 seconds.
# Once per minute is sufficient.
RESULT_CHECK_INTERVAL_SECONDS = 60


def get_poll_interval(
    minutes_to_start: float
) -> int:
    """
    Return how often a race should be checked,
    based on its scheduled start time.

    60-180 minutes away:
        every 10 minutes

    30-60 minutes away:
        every 5 minutes

    10-30 minutes away:
        every 2 minutes

    -5 to 10 minutes:
        every 1 minute
    """

    if minutes_to_start > 60:
        return 10 * 60

    if minutes_to_start > 30:
        return 5 * 60

    if minutes_to_start > 10:
        return 2 * 60

    return 60


def get_race_key(
    race: dict
) -> str:
    """
    Create a unique key for each race.
    """

    return (
        f"{race['meeting_date']}|"
        f"{race['venue_code']}|"
        f"{race['race_number']}"
    )


def parse_race_start(
    race: dict
) -> datetime:
    """
    Convert race_start into a datetime.
    """

    return datetime.strptime(
        race["race_start"],
        "%Y-%m-%d %H:%M"
    )


def run_monitor() -> None:
    """
    Run the Greyhound Price Monitor.

    PRICE MONITORING:
        Begins when a race is within 3 hours.
        Continues until 5 minutes after scheduled start.

    RESULT MONITORING:
        Only applies to runners that generated alerts.
        Begins 20 minutes after scheduled race start.
        Retries until TAB publishes an official result.

    STARTUP:
        Polling history starts fresh every time
        the program is launched.
    """

    print()
    print("Greyhound Price Monitor")
    print("=======================")
    print()
    print("Monitor started.")
    print("Press Ctrl + C to stop.")
    print()

    # ========================================================
    # STARTUP DISCORD NOTIFICATION
    #
    # This runs ONCE per program launch.
    # ========================================================

    try:
        send_startup_notification()

        print(
            "Startup Discord notification sent."
        )

    except Exception as error:
        print(
            f"ERROR sending startup "
            f"Discord notification: {error}"
        )

    print()

    # ========================================================
    # PRICE POLLING HISTORY
    #
    # Kept only in memory.
    #
    # Restarting the tracker resets this, which means
    # eligible races are checked immediately again.
    # ========================================================

    last_checked = {}

    # ========================================================
    # RESULT CHECK TIMER
    #
    # Start at zero so pending results are evaluated
    # immediately when the tracker launches.
    #
    # results_monitor.py itself enforces the +20-minute
    # scheduled-start rule.
    # ========================================================

    last_result_check = 0.0

    while True:
        try:
            now = datetime.now()

            # =================================================
            # FIND ELIGIBLE GREYHOUND RACES
            # =================================================

            races = (
                get_todays_greyhound_races()
            )

            print(
                f"Eligible races: {len(races)}"
            )

            races_checked_this_cycle = 0

            # =================================================
            # PRICE MONITORING
            # =================================================

            for race in races:
                race_start = (
                    parse_race_start(
                        race
                    )
                )

                minutes_to_start = (
                    race_start - now
                ).total_seconds() / 60

                # --------------------------------------------
                # Stop price monitoring once the race is
                # more than 5 minutes past scheduled start.
                # --------------------------------------------

                if minutes_to_start < -5:
                    continue

                # --------------------------------------------
                # Don't monitor prices more than
                # 3 hours before scheduled start.
                # --------------------------------------------

                if minutes_to_start > 180:
                    continue

                race_key = (
                    get_race_key(
                        race
                    )
                )

                poll_interval = (
                    get_poll_interval(
                        minutes_to_start
                    )
                )

                previous_check = (
                    last_checked.get(
                        race_key
                    )
                )

                if previous_check is not None:
                    seconds_since_check = (
                        now
                        - previous_check
                    ).total_seconds()

                    if (
                        seconds_since_check
                        < poll_interval
                    ):
                        continue

                # --------------------------------------------
                # Console timing description
                # --------------------------------------------

                if minutes_to_start >= 0:
                    timing_text = (
                        f"{minutes_to_start:.0f} "
                        f"min to start"
                    )

                else:
                    timing_text = (
                        f"{abs(minutes_to_start):.0f} "
                        f"min past scheduled start"
                    )

                print()
                print(
                    f"Monitoring "
                    f"{race['meeting_name']} "
                    f"R{race['race_number']} "
                    f"({timing_text})"
                )

                browser_session = (
                    BrowserSession()
                )

                try:
                    browser_session.start()

                    page = (
                        browser_session.get_page()
                    )

                    monitor_race(
                        page=page,
                        race_url=race[
                            "race_url"
                        ],
                        meeting_date=race[
                            "meeting_date"
                        ],
                        meeting_name=race[
                            "meeting_name"
                        ],
                        venue_code=race[
                            "venue_code"
                        ],
                        race_number=race[
                            "race_number"
                        ],
                        race_start=race[
                            "race_start"
                        ]
                    )

                    last_checked[
                        race_key
                    ] = datetime.now()

                    races_checked_this_cycle += 1

                except Exception as error:
                    print(
                        f"ERROR monitoring "
                        f"{race['meeting_name']} "
                        f"R{race['race_number']}: "
                        f"{error}"
                    )

                finally:
                    browser_session.close()

            # =================================================
            # CLEAN OLD PRICE-POLLING KEYS
            # =================================================

            active_race_keys = {
                get_race_key(race)
                for race in races
            }

            expired_keys = [
                race_key
                for race_key
                in last_checked
                if race_key
                not in active_race_keys
            ]

            for race_key in expired_keys:
                del last_checked[
                    race_key
                ]

            # =================================================
            # RESULT MONITORING
            #
            # Only alerted runners are considered.
            #
            # results_monitor.py checks RACESTART and will
            # refuse to scrape a result until:
            #
            # scheduled start + 20 minutes
            #
            # If TAB has not published a result yet, the
            # runner remains pending and will be retried.
            # =================================================

            current_monotonic = (
                time.monotonic()
            )

            seconds_since_result_check = (
                current_monotonic
                - last_result_check
            )

            if (
                seconds_since_result_check
                >= RESULT_CHECK_INTERVAL_SECONDS
            ):
                try:
                    check_unprocessed_results()

                except Exception as error:
                    print()
                    print(
                        f"ERROR checking "
                        f"race results: {error}"
                    )

                finally:
                    last_result_check = (
                        time.monotonic()
                    )

            # =================================================
            # CYCLE COMPLETE
            # =================================================

            print()
            print(
                f"Cycle complete. "
                f"Checked "
                f"{races_checked_this_cycle} "
                f"race(s)."
            )

            print(
                f"Waiting "
                f"{MAIN_LOOP_SECONDS} "
                f"seconds..."
            )

            time.sleep(
                MAIN_LOOP_SECONDS
            )

        except KeyboardInterrupt:
            print()
            print()
            print(
                "Monitor stopped."
            )

            break

        except Exception as error:
            print()
            print(
                f"ERROR in monitor cycle: "
                f"{error}"
            )

            print(
                f"Retrying in "
                f"{MAIN_LOOP_SECONDS} "
                f"seconds..."
            )

            time.sleep(
                MAIN_LOOP_SECONDS
            )


if __name__ == "__main__":
    run_monitor()