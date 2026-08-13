import time
from datetime import datetime

from browser_session import BrowserSession
from heartbeat import send_heartbeat
from monitor import monitor_race
from race_finder import get_todays_greyhound_races
from reminders import check_race_reminders
from results_monitor import check_unprocessed_results
from stats_report import get_stats, send_to_discord, create_chart


# ============================================================
# TIMING SETTINGS
# ============================================================

MAIN_LOOP_SECONDS = 30

RESULT_CHECK_INTERVAL_SECONDS = 60

HEARTBEAT_INTERVAL_SECONDS = 5 * 60

STATS_REPORT_INTERVAL_SECONDS = 6 * 60 * 60


# ============================================================
# STATISTICS REPORT
# ============================================================

def run_stats_report() -> None:
    """
    Generate and send the current 7-day statistics report.

    This function is deliberately isolated from the main
    monitoring loop so a statistics/reporting failure cannot
    stop race monitoring.
    """

    print()
    print(
        "Generating scheduled 7-day "
        "statistics report..."
    )

    stats = get_stats()

    if not stats:
        print(
            "No resolved alerted runners found "
            "for statistics report."
        )
        return

    chart_created = create_chart(
        stats
    )

    if not chart_created:
        print(
            "Statistics chart could not be created."
        )
        return

    send_to_discord(
        stats
    )

    print(
        "Discord statistics report "
        "sent successfully."
    )


# ============================================================
# RACE POLLING INTERVAL
# ============================================================

def get_poll_interval(
    minutes_to_start: float
) -> int:
    """
    Return how often a race should be checked.

    60-180 min:
        every 10 minutes

    30-60 min:
        every 5 minutes

    10-30 min:
        every 2 minutes

    -5 to 10 min:
        every 1 minute
    """

    if minutes_to_start > 60:
        return 10 * 60

    if minutes_to_start > 30:
        return 5 * 60

    if minutes_to_start > 10:
        return 2 * 60

    return 60


# ============================================================
# RACE KEY
# ============================================================

def get_race_key(
    race: dict
) -> str:
    """
    Create a unique race key.
    """

    return (
        f"{race['meeting_date']}|"
        f"{race['venue_code']}|"
        f"{race['race_number']}"
    )


# ============================================================
# PARSE RACE START
# ============================================================

def parse_race_start(
    race: dict
) -> datetime:
    """
    Convert race_start into datetime.
    """

    return datetime.strptime(
        race["race_start"],
        "%Y-%m-%d %H:%M"
    )


# ============================================================
# MAIN MONITOR
# ============================================================

def run_monitor() -> None:
    """
    Run GreyhoundMonitor.

    PRICE MONITORING:
        -3 hours through +5 minutes.

    PRE-RACE REMINDER:
        One Discord reminder per race when an
        alerted runner is due to run within
        approximately 2 minutes.

    RESULT MONITORING:
        Begins at +20 minutes for alerted runners.

    STATUSCAKE:
        Immediate heartbeat on startup, followed
        by a heartbeat approximately every 5 minutes.

    STATISTICS:
        Immediate 7-day statistics report on startup,
        followed by another report approximately
        every 6 hours while the monitor is running.
    """

    print()
    print("Greyhound Price Monitor")
    print("=======================")
    print()
    print("Monitor started.")
    print("Press Ctrl + C to stop.")
    print()

    # ========================================================
    # INITIAL STATUSCAKE HEARTBEAT
    #
    # Send immediately on startup so StatusCake knows the
    # tracker is running before race monitoring begins.
    # ========================================================

    try:
        send_heartbeat()

        print(
            "Initial StatusCake heartbeat sent."
        )

    except Exception as error:
        print(
            f"ERROR sending initial StatusCake "
            f"heartbeat: {error}"
        )

    # ========================================================
    # INITIAL STATISTICS REPORT
    #
    # Every fresh start/restart of main.py sends the current
    # 7-day statistics report immediately.
    # ========================================================

    try:
        run_stats_report()

    except Exception as error:
        print()
        print(
            f"ERROR sending initial statistics "
            f"report: {error}"
        )

    print()

    # ========================================================
    # IN-MEMORY PRICE POLLING HISTORY
    # ========================================================

    last_checked = {}

    # ========================================================
    # RESULT TIMER
    # ========================================================

    last_result_check = 0.0

    # ========================================================
    # STATUSCAKE TIMER
    #
    # Start the normal heartbeat timer from startup.
    # This prevents another heartbeat being sent immediately
    # after the first monitoring cycle.
    # ========================================================

    last_heartbeat = time.monotonic()

    # ========================================================
    # STATISTICS TIMER
    #
    # The initial report has already been sent above.
    #
    # Start the 6-hour timer now so the next report occurs
    # approximately 6 hours after startup/restart.
    # ========================================================

    last_stats_report = time.monotonic()

    while True:
        try:
            now = datetime.now()

            # =================================================
            # DISCOVER RACES
            # =================================================

            races = (
                get_todays_greyhound_races()
            )

            print(
                f"Eligible races: {len(races)}"
            )

            races_checked_this_cycle = 0

            # =================================================
            # PRE-RACE REMINDERS
            # =================================================

            try:
                check_race_reminders(
                    races
                )

            except Exception as error:
                print(
                    f"ERROR checking race reminders: "
                    f"{error}"
                )

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

                if minutes_to_start < -5:
                    continue

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
            # CLEAN OLD POLLING KEYS
            # =================================================

            active_race_keys = {
                get_race_key(race)
                for race in races
            }

            expired_keys = [
                race_key
                for race_key in last_checked
                if race_key not in active_race_keys
            ]

            for race_key in expired_keys:
                del last_checked[
                    race_key
                ]

            # =================================================
            # RESULT MONITORING
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
            # STATISTICS REPORT
            # =================================================

            current_monotonic = (
                time.monotonic()
            )

            seconds_since_stats_report = (
                current_monotonic
                - last_stats_report
            )

            if (
                seconds_since_stats_report
                >= STATS_REPORT_INTERVAL_SECONDS
            ):
                try:
                    run_stats_report()

                except Exception as error:
                    print()
                    print(
                        f"ERROR sending scheduled "
                        f"statistics report: {error}"
                    )

                finally:
                    # Reset the timer even if Discord/report
                    # generation failed. This prevents a failed
                    # report from being retried every 30 seconds.
                    last_stats_report = (
                        time.monotonic()
                    )

            # =================================================
            # STATUSCAKE HEARTBEAT
            # =================================================

            current_monotonic = (
                time.monotonic()
            )

            seconds_since_heartbeat = (
                current_monotonic
                - last_heartbeat
            )

            if (
                seconds_since_heartbeat
                >= HEARTBEAT_INTERVAL_SECONDS
            ):
                try:
                    send_heartbeat()

                    print(
                        "StatusCake heartbeat sent."
                    )

                    last_heartbeat = (
                        time.monotonic()
                    )

                except Exception as error:
                    print(
                        f"ERROR sending StatusCake "
                        f"heartbeat: {error}"
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