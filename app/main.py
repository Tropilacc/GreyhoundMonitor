import time
from datetime import datetime

from browser_session import BrowserSession
from dev_alerts import send_dev_alert
from heartbeat import send_heartbeat
from monitor_tab import monitor_race
from monitor_sportsbet import monitor_sportsbet_race
from race_finder_tab import get_todays_greyhound_schedule
from race_finder_sportsbet import get_todays_sportsbet_greyhound_schedule
from reminders import check_race_reminders
from results_monitor import check_unprocessed_results
from stats_report import (
    create_chart,
    get_stats,
    send_to_discord,
)


# ============================================================
# TIMING SETTINGS
# ============================================================

MAIN_LOOP_SECONDS = 30

RESULT_CHECK_INTERVAL_SECONDS = 60

HEARTBEAT_INTERVAL_SECONDS = 5 * 60

STATS_REPORT_INTERVAL_SECONDS = 6 * 60 * 60

ODDS_MONITOR_WINDOW_MINUTES = 5 * 60
ODDS_POST_START_GRACE_MINUTES = 5

ODDS_POLLING_RULES = (
    {
        "minimum_minutes_to_start": 30,
        "interval_seconds": 5 * 60,
    },
    {
        "minimum_minutes_to_start": (
            -ODDS_POST_START_GRACE_MINUTES
        ),
        "interval_seconds": 60,
    },
)


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

        send_dev_alert(
            source="STATS REPORT",
            message=(
                "Statistics data was available, "
                "but the chart could not be created."
            ),
            severity="WARNING",
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

def get_race_discovery_interval(
    minutes_to_next_race: float | None
) -> int:
    """
    Return how often TAB and Sportsbet race schedules
    should be rediscovered.

    No known future race:
        every 30 minutes

    More than 5 hours away:
        every 30 minutes

    60-300 minutes:
        every 10 minutes

    30-60 minutes:
        every 5 minutes

    Under 30 minutes:
        every 2 minutes
    """

    if minutes_to_next_race is None:
        return 30 * 60

    if minutes_to_next_race > 300:
        return 30 * 60

    if minutes_to_next_race > 60:
        return 10 * 60

    if minutes_to_next_race > 30:
        return 5 * 60

    return 2 * 60

def get_poll_interval(
    minutes_to_start: float
) -> int:
    """
    Return how often a race should be checked.

    Polling behaviour is controlled by
    ODDS_POLLING_RULES.
    """

    for rule in ODDS_POLLING_RULES:
        if (
            minutes_to_start
            >= rule["minimum_minutes_to_start"]
        ):
            return rule["interval_seconds"]

    return ODDS_POLLING_RULES[-1][
        "interval_seconds"
    ]


def format_poll_interval(
    seconds: int
) -> str:
    """
    Format a polling interval for display.
    """

    minutes = seconds // 60

    unit = (
        "minute"
        if minutes == 1
        else "minutes"
    )

    return f"Every {minutes} {unit}"


def send_startup_alert() -> None:
    """
    Send startup configuration to Discord.

    Polling values are generated from the same
    configuration used by get_poll_interval().
    """

    long_rule = ODDS_POLLING_RULES[0]
    short_rule = ODDS_POLLING_RULES[1]

    monitor_hours = (
        ODDS_MONITOR_WINDOW_MINUTES
        // 60
    )

    threshold_minutes = (
        long_rule[
            "minimum_minutes_to_start"
        ]
    )

    send_dev_alert(
        source="MAIN / STARTUP",
        message="Greyhound Price Monitor started.",
        severity="INFO",
        details={
            (
                f"{threshold_minutes} mins "
                f"to {monitor_hours} hrs"
            ):
                format_poll_interval(
                    long_rule[
                        "interval_seconds"
                    ]
                ),
            (
                f"Less than "
                f"{threshold_minutes} mins"
            ):
                format_poll_interval(
                    short_rule[
                        "interval_seconds"
                    ]
                ),
            "Post-start grace":
                (
                    f"{ODDS_POST_START_GRACE_MINUTES} "
                    f"minutes"
                ),
        },
    )


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
        -5 hours through +5 minutes.

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

    DEV ALERTS:
        Operational errors and meaningful faults are
        sent to DISCORD_DEV_WEBHOOK_URL.

        Expected operating conditions are NOT sent
        to the DEV channel.
    """

    print()
    print("Greyhound Price Monitor")
    print("=======================")
    print()
    print("Monitor started.")
    print("Press Ctrl + C to stop.")
    print()

    # ========================================================
    # STARTUP CONFIGURATION ALERT
    # ========================================================

    send_startup_alert()


    # ========================================================
    # INITIAL STATUSCAKE HEARTBEAT
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

        send_dev_alert(
            source="MAIN / STATUSCAKE",
            message=(
                "Initial StatusCake heartbeat failed."
            ),
            error=error,
            severity="WARNING",
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

        send_dev_alert(
            source="MAIN / STATS REPORT",
            message=(
                "Initial 7-day statistics report failed."
            ),
            error=error,
            severity="ERROR",
        )

    print()

    # ========================================================
    # IN-MEMORY PRICE POLLING HISTORY
    # ========================================================

    last_checked_tab = {}
    last_checked_sportsbet = {}

    # ========================================================
    # RACE DISCOVERY CACHE
    #
    # Race schedules do not need to be downloaded every
    # 30-second main-loop cycle. These values allow the
    # latest discovered schedules to be reused until the
    # next scheduled discovery refresh.
    # ========================================================

    races = []
    sportsbet_races = []

    tab_next_future_race = None
    sportsbet_next_future_race = None

    last_race_discovery = 0.0
    race_discovery_interval = 0

    # ========================================================
    # RESULT TIMER
    # ========================================================

    last_result_check = 0.0

    # ========================================================
    # STATUSCAKE TIMER
    # ========================================================

    last_heartbeat = time.monotonic()

    # ========================================================
    # STATISTICS TIMER
    #
    # The initial report has already been attempted above.
    #
    # Next report:
    #     approximately 6 hours after startup
    # ========================================================

    last_stats_report = time.monotonic()

    while True:
        try:
            cycle_started_at = time.monotonic()
            now = datetime.now()

            # =================================================
            # DISCOVER RACES
            #
            # The main loop still runs every 30 seconds for
            # results, reminders, statistics and StatusCake.
            #
            # TAB and Sportsbet schedules are only downloaded
            # when the discovery timer says a refresh is due.
            # =================================================

            current_monotonic = time.monotonic()

            seconds_since_race_discovery = (
                current_monotonic
                - last_race_discovery
            )

            should_discover_races = (
                last_race_discovery == 0.0
                or seconds_since_race_discovery
                >= race_discovery_interval
            )

            if should_discover_races:

                tab_discovery_ok = True
                sportsbet_discovery_ok = True

                # =============================================
                # TAB DISCOVERY
                # =============================================

                try:
                    tab_schedule = (
                        get_todays_greyhound_schedule()
                    )

                    races = tab_schedule[
                        "eligible_races"
                    ]

                    tab_next_future_race = (
                        tab_schedule[
                            "next_future_race"
                        ]
                    )

                except Exception as error:
                    tab_discovery_ok = False

                    print()
                    print(
                        f"ERROR discovering today's "
                        f"TAB greyhound races: {error}"
                    )

                    send_dev_alert(
                        source="MAIN / RACE FINDER",
                        message=(
                            "Failed to discover today's "
                            "TAB greyhound races."
                        ),
                        error=error,
                        severity="ERROR",
                    )

                print(
                    f"TAB eligible races: "
                    f"{len(races)}"
                )

                # =============================================
                # SPORTSBET DISCOVERY
                # =============================================

                try:
                    sportsbet_schedule = (
                        get_todays_sportsbet_greyhound_schedule()
                    )

                    sportsbet_races = (
                        sportsbet_schedule[
                            "eligible_races"
                        ]
                    )

                    sportsbet_next_future_race = (
                        sportsbet_schedule[
                            "next_future_race"
                        ]
                    )

                except Exception as error:
                    sportsbet_discovery_ok = False

                    print()
                    print(
                        f"ERROR discovering Sportsbet "
                        f"greyhound races: {error}"
                    )

                    send_dev_alert(
                        source=(
                            "MAIN / SPORTSBET RACE FINDER"
                        ),
                        message=(
                            "Failed to discover Sportsbet "
                            "greyhound races."
                        ),
                        error=error,
                        severity="ERROR",
                    )

                print(
                    f"Sportsbet eligible races: "
                    f"{len(sportsbet_races)}"
                )

                # =============================================
                # FIND NEAREST KNOWN FUTURE RACE
                # =============================================

                future_race_times = []

                for race in (
                    races
                    + sportsbet_races
                ):
                    try:
                        race_start = (
                            parse_race_start(
                                race
                            )
                        )

                    except Exception:
                        continue

                    if race_start > now:
                        future_race_times.append(
                            race_start
                        )

                for future_race in (
                    tab_next_future_race,
                    sportsbet_next_future_race,
                ):
                    if future_race is None:
                        continue

                    try:
                        race_start = (
                            parse_race_start(
                                future_race
                            )
                        )

                    except Exception:
                        continue

                    if race_start > now:
                        future_race_times.append(
                            race_start
                        )

                if future_race_times:
                    next_race_start = min(
                        future_race_times
                    )

                    minutes_to_next_race = (
                        next_race_start
                        - now
                    ).total_seconds() / 60

                else:
                    minutes_to_next_race = None

                # =============================================
                # NEXT DISCOVERY INTERVAL
                # =============================================

                if (
                    not tab_discovery_ok
                    or not sportsbet_discovery_ok
                ):
                    # Retry failed discovery quickly.
                    race_discovery_interval = (
                        MAIN_LOOP_SECONDS
                    )

                else:
                    race_discovery_interval = (
                        get_race_discovery_interval(
                            minutes_to_next_race
                        )
                    )

                last_race_discovery = (
                    time.monotonic()
                )

                if minutes_to_next_race is None:
                    print(
                        "No future race currently known."
                    )

                else:
                    print(
                        f"Next known race in "
                        f"{minutes_to_next_race:.0f} "
                        f"minute(s)."
                    )

                print(
                    "Next race discovery refresh in "
                    f"{race_discovery_interval // 60} "
                    "minute(s)."
                    if race_discovery_interval >= 60
                    else
                    "Next race discovery refresh in "
                    f"{race_discovery_interval} "
                    "second(s)."
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

                send_dev_alert(
                    source="MAIN / REMINDERS",
                    message=(
                        "Pre-race reminder check failed."
                    ),
                    error=error,
                    severity="ERROR",
                )

            # =================================================
            # PRICE MONITORING
            # =================================================

            for race in races:

                # -------------------------------------------------
                # PARSE RACE START
                # -------------------------------------------------

                try:
                    race_start = (
                        parse_race_start(
                            race
                        )
                    )

                except Exception as error:
                    print()
                    print(
                        f"ERROR parsing race start for "
                        f"{race.get('meeting_name')} "
                        f"R{race.get('race_number')}: "
                        f"{error}"
                    )

                    send_dev_alert(
                        source="MAIN / RACE DATA",
                        message=(
                            "Race start time could not "
                            "be parsed."
                        ),
                        error=error,
                        severity="ERROR",
                        details={
                            "Meeting":
                                race.get(
                                    "meeting_name"
                                ),
                            "Venue code":
                                race.get(
                                    "venue_code"
                                ),
                            "Race":
                                race.get(
                                    "race_number"
                                ),
                            "Race start":
                                race.get(
                                    "race_start"
                                ),
                            "Race URL":
                                race.get(
                                    "race_url"
                                ),
                        },
                    )

                    continue

                minutes_to_start = (
                    race_start - now
                ).total_seconds() / 60

                if minutes_to_start < -ODDS_POST_START_GRACE_MINUTES:
                    continue

                if minutes_to_start > ODDS_MONITOR_WINDOW_MINUTES:
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
                    last_checked_tab.get(
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

                    last_checked_tab[
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

                    send_dev_alert(
                        source="MAIN / RACE MONITOR",
                        message=(
                            "Race monitoring failed."
                        ),
                        error=error,
                        severity="ERROR",
                        details={
                            "Meeting":
                                race.get(
                                    "meeting_name"
                                ),
                            "Venue code":
                                race.get(
                                    "venue_code"
                                ),
                            "Race":
                                race.get(
                                    "race_number"
                                ),
                            "Race start":
                                race.get(
                                    "race_start"
                                ),
                            "Race URL":
                                race.get(
                                    "race_url"
                                ),
                        },
                    )

                finally:
                    try:
                        browser_session.close()

                    except Exception as error:
                        print(
                            "ERROR closing race monitor "
                            f"browser session: {error}"
                        )

                        send_dev_alert(
                            source=(
                                "MAIN / BROWSER SESSION"
                            ),
                            message=(
                                "Failed to close race "
                                "monitor browser session."
                            ),
                            error=error,
                            severity="WARNING",
                            details={
                                "Meeting":
                                    race.get(
                                        "meeting_name"
                                    ),
                                "Race":
                                    race.get(
                                        "race_number"
                                    ),
                            },
                        )

            # =================================================
            # SPORTSBET PRICE MONITORING
            # =================================================

            for race in sportsbet_races:

                try:
                    race_start = parse_race_start(
                        race
                    )

                except Exception as error:
                    print(
                        f"ERROR parsing Sportsbet race start for "
                        f"{race.get('meeting_name')} "
                        f"R{race.get('race_number')}: "
                        f"{error}"
                    )

                    send_dev_alert(
                        source="MAIN / SPORTSBET RACE DATA",
                        message=(
                            "Sportsbet race start time could not "
                            "be parsed."
                        ),
                        error=error,
                        severity="ERROR",
                        details={
                            "Meeting": race.get("meeting_name"),
                            "Venue code": race.get("venue_code"),
                            "Race": race.get("race_number"),
                            "Race start": race.get("race_start"),
                            "Race URL": race.get("race_url"),
                        },
                    )

                    continue

                minutes_to_start = (
                    race_start - now
                ).total_seconds() / 60

                if minutes_to_start < -ODDS_POST_START_GRACE_MINUTES:
                    continue

                if minutes_to_start > ODDS_MONITOR_WINDOW_MINUTES:
                    continue

                race_key = get_race_key(
                    race
                )

                poll_interval = get_poll_interval(
                    minutes_to_start
                )

                previous_check = (
                    last_checked_sportsbet.get(
                        race_key
                    )
                )

                if previous_check is not None:
                    seconds_since_check = (
                        now - previous_check
                    ).total_seconds()

                    if seconds_since_check < poll_interval:
                        continue

                if minutes_to_start >= 0:
                    timing_text = (
                        f"{minutes_to_start:.0f} min to start"
                    )

                else:
                    timing_text = (
                        f"{abs(minutes_to_start):.0f} "
                        f"min past scheduled start"
                    )

                print()
                print(
                    f"Monitoring Sportsbet "
                    f"{race['meeting_name']} "
                    f"R{race['race_number']} "
                    f"({timing_text})"
                )

                try:
                    monitor_sportsbet_race(
                        race_url=race["race_url"]
                    )

                    last_checked_sportsbet[
                        race_key
                    ] = datetime.now()

                    races_checked_this_cycle += 1

                except Exception as error:
                    print(
                        f"ERROR monitoring Sportsbet "
                        f"{race['meeting_name']} "
                        f"R{race['race_number']}: "
                        f"{error}"
                    )

                    send_dev_alert(
                        source="MAIN / SPORTSBET MONITOR",
                        message=(
                            "Sportsbet race monitoring failed."
                        ),
                        error=error,
                        severity="ERROR",
                        details={
                            "Meeting": race.get("meeting_name"),
                            "Venue code": race.get("venue_code"),
                            "Race": race.get("race_number"),
                            "Race start": race.get("race_start"),
                            "Race URL": race.get("race_url"),
                        },
                    )


            # =================================================
            # CLEAN OLD POLLING KEYS
            # =================================================

            try:
                active_race_keys = {
                    get_race_key(race)
                    for race in races
                }

                expired_keys = [
                    race_key
                    for race_key
                    in last_checked_tab
                    if race_key
                    not in active_race_keys
                ]

                for race_key in expired_keys:
                    del last_checked_tab[
                        race_key
                    ]

            except Exception as error:
                print(
                    "ERROR cleaning race polling "
                    f"history: {error}"
                )

                send_dev_alert(
                    source="MAIN / POLLING CACHE",
                    message=(
                        "Failed to clean expired "
                        "race polling keys."
                    ),
                    error=error,
                    severity="WARNING",
                )

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

                    send_dev_alert(
                        source="MAIN / RESULT MONITOR",
                        message=(
                            "Unprocessed race result "
                            "check failed."
                        ),
                        error=error,
                        severity="ERROR",
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

                    send_dev_alert(
                        source="MAIN / STATS REPORT",
                        message=(
                            "Scheduled 7-day statistics "
                            "report failed."
                        ),
                        error=error,
                        severity="ERROR",
                    )

                finally:
                    # Reset the timer even if the report
                    # failed so a fault does not trigger
                    # another attempt every 30 seconds.
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

                    send_dev_alert(
                        source="MAIN / STATUSCAKE",
                        message=(
                            "Scheduled StatusCake "
                            "heartbeat failed."
                        ),
                        error=error,
                        severity="WARNING",
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

            cycle_elapsed_seconds = time.monotonic() - cycle_started_at
            cycle_wait_seconds = max(
                0.0,
                MAIN_LOOP_SECONDS - cycle_elapsed_seconds,
            )

            print(
                f"Cycle took "
                f"{cycle_elapsed_seconds:.1f} seconds. "
                f"Waiting "
                f"{cycle_wait_seconds:.1f} seconds..."
            )

            if cycle_wait_seconds > 0:
                time.sleep(
                    cycle_wait_seconds
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

            send_dev_alert(
                source="MAIN / MONITOR LOOP",
                message=(
                    "Unhandled exception in the "
                    "main monitor cycle."
                ),
                error=error,
                severity="ERROR",
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













