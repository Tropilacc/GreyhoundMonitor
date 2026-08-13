from datetime import datetime

from playwright.sync_api import Page

from alerts import ALERTS
from database import (
    connect_database,
    create_tables,
    get_alert_ids_for_runner,
    get_runner,
    has_alert_been_sent,
    has_scratch_alert_been_sent,
    mark_alert_as_sent,
    mark_runner_as_scratched,
    mark_scratch_alert_as_sent,
    save_runner,
)
from dev_alerts import send_dev_alert
from models import Runner
from notifications import (
    get_all_alerts_role_id,
    get_role_id,
    send_discord_message,
)
from scraper import get_race_prices


# ============================================================
# ALERT TIMING
# ============================================================

ALERT_CUTOFF_MINUTES_AFTER_START = 1


# ============================================================
# RESULT CODES
# ============================================================

SCRATCHED_POSITION = 100


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
# ALERT LOOKUP
# ============================================================

def get_alert_by_id(
    alert_id: str
):
    """
    Find an alert definition from alerts.py by ID.

    Historical ALERT_HISTORY rows may refer to alerts
    that have since been removed or renamed.

    In that case, return None.
    """

    for alert in ALERTS:

        if alert.id == alert_id:
            return alert

    return None


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

    Price monitoring itself continues through +5 minutes,
    controlled separately by main.py.
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
# PRICE ALERT MESSAGE
# ============================================================

def build_alert_message(
    runner: Runner,
    alert
) -> str:
    """
    Build the Discord message for a price alert.
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
        f"— Box {runner.runner_number}\n\n"
        f"Initial Price: "
        f"**${runner.initial_price:.2f}**\n"
        f"Current Price: "
        f"**${runner.current_price:.2f}**\n"
        f"{movement_text}"
    )


# ============================================================
# SCRATCH MESSAGE
# ============================================================

def build_scratch_message(
    meeting_name: str,
    venue_code: str,
    race_number: int,
    runner_number: int,
    runner_name: str,
    alert_ids: list[str]
) -> str:
    """
    Build one Discord notification when a previously
    alerted runner becomes scratched.
    """

    alert_names = []

    for alert_id in alert_ids:

        alert = get_alert_by_id(
            alert_id
        )

        if alert is not None:
            alert_name = (
                alert.name
            )

        else:
            alert_name = (
                alert_id
                .replace("_", " ")
                .title()
            )

        if alert_name not in alert_names:
            alert_names.append(
                alert_name
            )

    if alert_names:

        alert_lines = "\n".join(
            f"• {alert_name}"
            for alert_name in alert_names
        )

    else:

        alert_lines = (
            "• Previous Greyhound Tracker alert"
        )

    return (
        "🚫 **GREYHOUND SCRATCHED** 🚫\n\n"
        f"**{runner_name}**\n"
        f"{meeting_name} "
        f"({venue_code}) "
        f"R{race_number} "
        f"— Box {runner_number}\n\n"
        f"This runner previously triggered:\n"
        f"{alert_lines}\n\n"
        f"TAB is now showing this runner as "
        f"**SCRATCHED (SCR)**.\n\n"
        f"The runner will not participate in the race."
    )


# ============================================================
# SCRATCH ROLE IDS
# ============================================================

def get_scratch_role_ids(
    alert_ids: list[str]
) -> list[str]:
    """
    Return Discord role IDs for a scratch notification.

    Includes:

        1. ALL Alerts role
        2. Specific role for every previous alert type

    Duplicate roles are removed.
    """

    role_ids = []

    all_alerts_role_id = (
        get_all_alerts_role_id()
    )

    if all_alerts_role_id:
        role_ids.append(
            all_alerts_role_id
        )

    for alert_id in alert_ids:

        alert = get_alert_by_id(
            alert_id
        )

        if alert is None:
            continue

        role_id = get_role_id(
            alert.role_env_name
        )

        if not role_id:
            continue

        if role_id in role_ids:
            continue

        role_ids.append(
            role_id
        )

    return role_ids


# ============================================================
# PROCESS LIVE SCRATCH
# ============================================================

def process_live_scratch(
    connection,
    meeting_date: str,
    meeting_name: str,
    venue_code: str,
    race_number: int,
    runner_number: int,
    runner_name: str,
    race_url: str
) -> bool:
    """
    Process one runner explicitly marked scratched by
    scraper.py.

    Returns True if the runner had at least one previous
    alert.

    Returns False if the runner was never alerted.

    For an alerted scratched runner:

        FINISHPOSITION = 100
        RESULTCHECKED = 1

    are saved immediately.

    Discord scratch history is recorded only after Discord
    successfully accepts the notification.
    """

    runner_id = build_runner_id(
        meeting_date=meeting_date,
        venue_code=venue_code,
        race_number=race_number,
        runner_number=runner_number
    )

    alert_ids = get_alert_ids_for_runner(
        connection,
        runner_id
    )

    # --------------------------------------------------------
    # NOT PREVIOUSLY ALERTED
    #
    # Still print the scratch so terminal output confirms
    # that the scraper detected it correctly.
    # --------------------------------------------------------

    if not alert_ids:

        print(
            f"SCRATCHED: "
            f"{venue_code} "
            f"R{race_number} "
            f"#{runner_number} "
            f"{runner_name} | "
            f"No previous alerts."
        )

        return False

    # --------------------------------------------------------
    # RESOLVE RESULT AS SCR
    # --------------------------------------------------------

    mark_runner_as_scratched(
        connection,
        runner_id
    )

    print(
        f"SCRATCHED: "
        f"{venue_code} "
        f"R{race_number} "
        f"#{runner_number} "
        f"{runner_name} | "
        f"FINISHPOSITION = "
        f"{SCRATCHED_POSITION}"
    )

    # --------------------------------------------------------
    # ALREADY NOTIFIED
    # --------------------------------------------------------

    if has_scratch_alert_been_sent(
        connection,
        runner_id
    ):
        print(
            f"Scratch notification already sent for "
            f"{venue_code} "
            f"R{race_number} "
            f"#{runner_number} "
            f"{runner_name}."
        )

        return True

    # --------------------------------------------------------
    # SEND SCRATCH NOTIFICATION
    # --------------------------------------------------------

    try:
        message = build_scratch_message(
            meeting_name=meeting_name,
            venue_code=venue_code,
            race_number=race_number,
            runner_number=runner_number,
            runner_name=runner_name,
            alert_ids=alert_ids
        )

        role_ids = get_scratch_role_ids(
            alert_ids
        )

        send_discord_message(
            message,
            role_ids=role_ids
        )

        mark_scratch_alert_as_sent(
            connection,
            runner_id
        )

        print(
            f"Discord scratch notification sent "
            f"successfully for "
            f"{venue_code} "
            f"R{race_number} "
            f"#{runner_number} "
            f"{runner_name}."
        )

    except Exception as error:
        print(
            f"ERROR sending scratch notification for "
            f"{meeting_name} "
            f"R{race_number} "
            f"#{runner_number} "
            f"{runner_name}: "
            f"{error}"
        )

        send_dev_alert(
            source="RACE MONITOR / SCRATCH ALERT",
            message=(
                "A previously alerted runner was "
                "scratched, but its Discord scratch "
                "notification could not be sent."
            ),
            error=error,
            severity="ERROR",
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
                    runner_name,
                "Previous alert IDs":
                    ", ".join(
                        alert_ids
                    ),
                "Race URL":
                    race_url,
            },
        )

    return True


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
    Scrape and process one TAB greyhound race.

    scraper.py provides the authoritative runner market state:

        current_price
        scratched

    LIVE SCRATCH FLOW:

        scratched=True
            ↓
        check ALERT_HISTORY
            ↓
        if previously alerted:
            FINISHPOSITION = 100
            RESULTCHECKED = 1
            send one Discord scratch notification
            record SCRATCH_HISTORY

    A runner with:

        current_price=None
        scratched=False

    is treated as an unavailable market, NOT as scratched.
    """

    # ========================================================
    # SCRAPE CURRENT RUNNER MARKET STATE
    # ========================================================

    scraped_runners = get_race_prices(
        page=page,
        race_url=race_url
    )

    if not scraped_runners:
        print(
            "No runner prices found."
        )

        return

    # ========================================================
    # ALERT CUTOFF
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
        # PROCESS RUNNERS
        # ====================================================

        for scraped_runner in scraped_runners:

            runner_number = scraped_runner[
                "runner_number"
            ]

            runner_name = scraped_runner[
                "runner_name"
            ]

            scratched = scraped_runner.get(
                "scratched",
                False
            )

            # =================================================
            # SCRATCHED RUNNER
            #
            # This MUST occur before current_price is checked.
            #
            # Scratched runners normally have:
            #
            #     current_price = None
            # =================================================

            if scratched:

                process_live_scratch(
                    connection=database,
                    meeting_date=meeting_date,
                    meeting_name=meeting_name,
                    venue_code=venue_code,
                    race_number=race_number,
                    runner_number=runner_number,
                    runner_name=runner_name,
                    race_url=race_url
                )

                continue

            # =================================================
            # ACTIVE RUNNER PRICE
            # =================================================

            current_price = scraped_runner[
                "current_price"
            ]

            # ------------------------------------------------
            # MISSING PRICE, BUT NOT SCRATCHED
            # ------------------------------------------------

            if current_price is None:
                continue

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
                runner_name=runner_name,
                initial_price=current_price,
                current_price=current_price
            )

            # =================================================
            # SAVE LATEST PRICE
            # =================================================

            save_runner(
                database,
                runner
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
                            runner_name,
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
            # PRICE ALERT CUTOFF
            # =================================================

            if not alerts_allowed:
                continue

            # =================================================
            # GENERIC ALERT ENGINE
            # =================================================

            for alert in ALERTS:

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
                # SEND PRICE ALERT
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