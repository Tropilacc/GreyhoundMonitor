from datetime import datetime

from playwright.sync_api import Page

from alerts import ALERTS
from database import (
    connect_database,
    create_tables,
    get_runner,
    has_alert_been_sent,
    mark_alert_as_sent,
    save_runner,
    save_runner_price,
)
from dev_alerts import send_dev_alert
from models import Runner
from notifications import (
    get_all_alerts_role_id,
    get_role_id,
    send_discord_message,
)
from scraper_tab import get_race_prices
from time_utils import format_race_start_time


# ============================================================
# ALERT TIMING
#
# Odds continue to be monitored until +5 minutes after the
# scheduled race start. That window is controlled by main.py.
#
# New alerts are only allowed until +1 minute after the
# scheduled race start.
# ============================================================

ALERT_CUTOFF_MINUTES_AFTER_START = 1


# ============================================================
# RUNNER ID
# ============================================================

def build_runner_id(
    meeting_date: str,
    venue_code: str,
    race_number: int,
    runner_number: int
) -> str:
    """
    Create a unique ID for one runner in one race.
    """

    return (
        f"{meeting_date}|"
        f"{venue_code}|"
        f"{race_number}|"
        f"{runner_number}"
    )


# ============================================================
# ALERT CUTOFF
# ============================================================

def are_alerts_allowed(
    race_start: str
) -> bool:
    """
    Return True while new alerts are still allowed.

    Alerts are allowed:
        Before scheduled start
        At scheduled start
        Up to and including 1 minute after scheduled start

    Alerts are blocked:
        More than 1 minute after scheduled start

    Price monitoring itself continues through +5 minutes
    because that is controlled separately by main.py.

    If race_start cannot be parsed, alerts fail closed so
    an invalid race time cannot cause late alerts.
    """

    try:
        scheduled_start = datetime.strptime(
            race_start,
            "%Y-%m-%d %H:%M"
        )

    except ValueError as error:
        print(
            f"WARNING: Could not parse race start "
            f"'{race_start}'. New alerts blocked "
            f"for safety."
        )

        send_dev_alert(
            source="RACE MONITOR / ALERT TIMING",
            message=(
                "Race start could not be parsed. "
                "New alerts were blocked for safety."
            ),
            error=error,
            severity="WARNING",
            details={
                "Race start":
                    race_start,
            },
        )

        return False

    seconds_after_start = (
        datetime.now()
        - scheduled_start
    ).total_seconds()

    alert_cutoff_seconds = (
        ALERT_CUTOFF_MINUTES_AFTER_START
        * 60
    )

    return (
        seconds_after_start
        <= alert_cutoff_seconds
    )


# ============================================================
# ALERT MESSAGE
# ============================================================

def build_alert_message(
    runner: Runner,
    alert
) -> str:
    """
    Build the Discord message for any alert rule.
    """

    price_change = (
        runner.current_price
        - runner.initial_price
    )

    price_change_absolute = abs(
        price_change
    )

    if runner.initial_price > 0:
        price_change_percent = (
            price_change_absolute
            / runner.initial_price
        ) * 100
    else:
        price_change_percent = 0

    if price_change > 0:
        movement_text = (
            f"Price Drift: "
            f"**+${price_change_absolute:.2f} "
            f"({price_change_percent:.1f}%)**"
        )

    elif price_change < 0:
        movement_text = (
            f"Price Drop: "
            f"**${price_change_absolute:.2f} "
            f"({price_change_percent:.1f}%)**"
        )

    else:
        movement_text = (
            "Price Movement: **$0.00 (0.0%)**"
        )

    return (
        f"{alert.emoji} "
        f"**GREYHOUND {alert.name.upper()} ALERT** "
        f"{alert.emoji}\n\n"
        f"**{runner.runner_name}**\n"
        f"{runner.meeting_name} "
        f"({runner.venue_code}) "
        f"R{runner.race_number} "
        f"- Box {runner.runner_number}\n"
        f"Race Start: "
        f"**{format_race_start_time(runner.race_start)}**\n\n"
        f"Initial Price: "
        f"**${runner.initial_price:.2f}**\n"
        f"Current Price: "
        f"**${runner.current_price:.2f}**\n"
        f"{movement_text}"
    )


# ============================================================
# MONITOR ONE RACE
# ============================================================

def monitor_race(
    page: Page,
    race_url: str,
    meeting_date: str,
    meeting_name: str,
    venue_code: str,
    race_number: int,
    race_start: str
) -> None:
    """
    Scrape one TAB greyhound race.

    The monitor:

    - Updates runner prices.
    - Stores meeting information.
    - Stores the scheduled race start.
    - Continues recording prices through +5 minutes,
      as controlled by main.py.
    - Allows new alerts only through +1 minute after
      the scheduled race start.
    - Evaluates every active alert rule while alerts
      are permitted.
    - Sends qualifying Discord alerts.
    - Pings ALL Alerts subscribers.
    - Pings the role subscribed to the specific alert.
    - Stores the exact price at which each alert fired.

    DEV FAULT REPORTING:

    - Scraper failures are handled by scraper_tab.py.
    - Invalid alert timing is reported here.
    - Discord alert failures are reported here.
    - Database / unexpected failures are allowed to
      propagate to main.py, where they are reported by
      the MAIN / RACE MONITOR DEV handler.
    """

    # ========================================================
    # SCRAPE CURRENT PRICES
    # ========================================================

    scraped_runners = get_race_prices(
        page=page,
        race_url=race_url
    )

    if not scraped_runners:
        print(
            "No runner prices found."
        )

        # scraper_tab.py already sends the detailed DEV warning
        # for a zero-runner scrape, so do not send a duplicate
        # notification here.

        return

    # ========================================================
    # DETERMINE WHETHER NEW ALERTS ARE STILL ALLOWED
    #
    # This is calculated after the scrape so that the actual
    # time at which prices are being processed is used.
    #
    # Even when False, runner prices are still saved below.
    # ========================================================

    alerts_allowed = are_alerts_allowed(
        race_start
    )

    if not alerts_allowed:
        print(
            f"Alert cutoff passed for "
            f"{meeting_name} R{race_number}. "
            f"Prices will still be updated, "
            f"but no new alerts will trigger."
        )

    # ========================================================
    # DATABASE
    # ========================================================

    database = connect_database()

    try:
        create_tables(
            database
        )

        # ====================================================
        # PROCESS SCRAPED RUNNERS
        # ====================================================

        for scraped_runner in scraped_runners:

            current_price = scraped_runner[
                "current_price"
            ]

            # ------------------------------------------------
            # RUNNER HAS NO CURRENT FIXED WIN PRICE
            #
            # This can be normal for scratchings or unavailable
            # Fixed Odds markets, so it is not a DEV fault.
            # ------------------------------------------------

            if current_price is None:
                continue

            runner_number = scraped_runner[
                "runner_number"
            ]

            runner_id = build_runner_id(
                meeting_date=meeting_date,
                venue_code=venue_code,
                race_number=race_number,
                runner_number=runner_number
            )

            runner = Runner(
                runner_id=runner_id,
                meeting_date=meeting_date,
                meeting_name=meeting_name,
                venue_code=venue_code,
                race_number=race_number,
                race_start=race_start,
                runner_number=runner_number,
                runner_name=scraped_runner[
                    "runner_name"
                ],
                initial_price=current_price,
                current_price=current_price
            )

            # =================================================
            # ALWAYS SAVE THE LATEST PRICE
            #
            # This continues even after the alert cutoff.
            #
            # INITIALPRICE remains preserved by save_runner().
            # =================================================

            save_runner(
                database,
                runner
            )

            # Store TAB pricing in the generic bookmaker table.
            #
            # TAB currently has no reliable published opening
            # price, so OPENING_PRICE remains NULL.
            #
            # INITIAL_OBSERVED_PRICE is automatically preserved
            # by save_runner_price() from the first TAB observation.

            save_runner_price(
                connection=database,
                runner_id=runner_id,
                bookmaker="TAB",
                current_price=current_price,
                opening_price=None,
                place_price=None,
                source_runner_id=None,
                scratched=False,
                market_mover=False,
            )

            stored_runner = get_runner(
                database,
                runner_id
            )

            if stored_runner is None:
                print(
                    f"WARNING: Runner was saved but "
                    f"could not be read back from database: "
                    f"{runner_id}"
                )

                send_dev_alert(
                    source="RACE MONITOR / DATABASE",
                    message=(
                        "Runner was saved but could not "
                        "be read back from the database."
                    ),
                    severity="WARNING",
                    details={
                        "Runner ID":
                            runner_id,
                        "Meeting":
                            meeting_name,
                        "Venue code":
                            venue_code,
                        "Race":
                            race_number,
                        "Runner":
                            runner_number,
                        "Runner name":
                            scraped_runner[
                                "runner_name"
                            ],
                    },
                )

                continue

            print(
                f"{stored_runner.venue_code} "
                f"R{stored_runner.race_number} "
                f"#{stored_runner.runner_number} "
                f"{stored_runner.runner_name} | "
                f"Initial: "
                f"${stored_runner.initial_price:.2f} | "
                f"Current: "
                f"${stored_runner.current_price:.2f}"
            )

            # =================================================
            # ALERT CUTOFF
            #
            # After scheduled start +1 minute:
            #
            # - Price is still saved.
            # - CURRENTPRICE is still updated.
            # - No alert rules are evaluated.
            # - No Discord alerts are sent.
            # - No ALERT_HISTORY rows are created.
            # =================================================

            if not alerts_allowed:
                continue

            # =================================================
            # GENERIC ALERT ENGINE
            #
            # Every active rule in alerts.py is evaluated.
            #
            # Every price alert pings:
            #
            # 1. ALL Alerts role
            # 2. The role assigned to this specific alert
            # =================================================

            for alert in ALERTS:

                # ------------------------------------------------
                # EVALUATE ALERT RULE
                #
                # If an alert condition itself throws an exception,
                # report it to DEV but continue processing other
                # alert rules / runners.
                # ------------------------------------------------

                try:
                    alert_triggered = (
                        alert.condition(
                            stored_runner
                        )
                    )

                except Exception as error:
                    print(
                        f"ERROR evaluating "
                        f"{alert.name} alert for "
                        f"{stored_runner.runner_name}: "
                        f"{error}"
                    )

                    send_dev_alert(
                        source="RACE MONITOR / ALERT ENGINE",
                        message=(
                            "Alert condition raised "
                            "an exception."
                        ),
                        error=error,
                        severity="ERROR",
                        details={
                            "Alert ID":
                                alert.id,
                            "Alert name":
                                alert.name,
                            "Meeting":
                                stored_runner.meeting_name,
                            "Venue code":
                                stored_runner.venue_code,
                            "Race":
                                stored_runner.race_number,
                            "Runner":
                                stored_runner.runner_number,
                            "Runner name":
                                stored_runner.runner_name,
                            "Initial price":
                                stored_runner.initial_price,
                            "Current price":
                                stored_runner.current_price,
                        },
                    )

                    continue

                if not alert_triggered:
                    continue

                # ------------------------------------------------
                # ALREADY SENT CHECK
                # ------------------------------------------------

                if has_alert_been_sent(
                    database,
                    stored_runner.runner_id,
                    alert.id
                ):
                    continue

                print()
                print(
                    f"***** "
                    f"{alert.name.upper()} ALERT "
                    f"*****"
                )

                print(
                    f"{stored_runner.meeting_name} "
                    f"({stored_runner.venue_code}) "
                    f"R{stored_runner.race_number}"
                )

                print(
                    f"#{stored_runner.runner_number} "
                    f"{stored_runner.runner_name}"
                )

                print(
                    f"Initial: "
                    f"${stored_runner.initial_price:.2f}"
                )

                print(
                    f"Current: "
                    f"${stored_runner.current_price:.2f}"
                )

                # =================================================
                # SEND DISCORD PRICE ALERT
                #
                # ALERT_HISTORY is written ONLY after Discord
                # successfully accepts the alert.
                # =================================================

                try:
                    message = build_alert_message(
                        stored_runner,
                        alert
                    )

                    all_alerts_role_id = (
                        get_all_alerts_role_id()
                    )

                    specific_alert_role_id = (
                        get_role_id(
                            alert.role_env_name
                        )
                    )

                    send_discord_message(
                        message,
                        role_ids=[
                            all_alerts_role_id,
                            specific_alert_role_id
                        ]
                    )

                    # ---------------------------------------------
                    # RECORD ONLY AFTER DISCORD ACCEPTS
                    # THE NOTIFICATION
                    # ---------------------------------------------

                    mark_alert_as_sent(
                        database,
                        stored_runner.runner_id,
                        alert.id,
                        stored_runner.current_price
                    )

                    print(
                        f"Discord {alert.name} "
                        f"alert sent successfully."
                    )

                except Exception as error:
                    print(
                        f"ERROR sending "
                        f"{alert.name} alert: "
                        f"{error}"
                    )

                    send_dev_alert(
                        source="RACE MONITOR / DISCORD ALERT",
                        message=(
                            "A qualifying greyhound alert "
                            "could not be sent or recorded."
                        ),
                        error=error,
                        severity="ERROR",
                        details={
                            "Alert ID":
                                alert.id,
                            "Alert name":
                                alert.name,
                            "Role env":
                                alert.role_env_name,
                            "Runner ID":
                                stored_runner.runner_id,
                            "Meeting":
                                stored_runner.meeting_name,
                            "Venue code":
                                stored_runner.venue_code,
                            "Race":
                                stored_runner.race_number,
                            "Runner":
                                stored_runner.runner_number,
                            "Runner name":
                                stored_runner.runner_name,
                            "Initial price":
                                (
                                    f"${stored_runner.initial_price:.2f}"
                                ),
                            "Current price":
                                (
                                    f"${stored_runner.current_price:.2f}"
                                ),
                            "Race URL":
                                race_url,
                        },
                    )

                print(
                    "*****************************"
                )

                print()

    finally:
        database.close()

        print(
            "Database closed."
        )
