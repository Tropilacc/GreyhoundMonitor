from playwright.sync_api import Page

from alerts import ALERTS
from database import (
    connect_database,
    create_tables,
    get_runner,
    has_alert_been_sent,
    mark_alert_as_sent,
    save_runner,
)
from models import Runner
from notifications import (
    get_all_alerts_role_id,
    get_role_id,
    send_discord_message,
)
from scraper import get_race_prices


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
        f"— Box {runner.runner_number}\n\n"
        f"Initial Price: "
        f"**${runner.initial_price:.2f}**\n"
        f"Current Price: "
        f"**${runner.current_price:.2f}**\n"
        f"{movement_text}"
    )


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
    - Evaluates every active alert rule.
    - Sends qualifying Discord alerts.
    - Pings ALL Alerts subscribers.
    - Pings the role subscribed to the specific alert.
    - Stores the exact price at which each alert fired.
    """

    scraped_runners = get_race_prices(
        page=page,
        race_url=race_url
    )

    if not scraped_runners:
        print(
            "No runner prices found."
        )
        return

    database = connect_database()

    try:
        create_tables(
            database
        )

        for scraped_runner in scraped_runners:
            current_price = scraped_runner[
                "current_price"
            ]

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

            save_runner(
                database,
                runner
            )

            stored_runner = get_runner(
                database,
                runner_id
            )

            if stored_runner is None:
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

            # ==================================================
            # GENERIC ALERT ENGINE
            #
            # Every active rule in alerts.py is evaluated.
            #
            # Every price alert pings:
            #
            # 1. ALL Alerts role
            # 2. The role assigned to this specific alert
            # ==================================================

            for alert in ALERTS:
                if not alert.condition(
                    stored_runner
                ):
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

                    # Record only after Discord accepts
                    # the notification.
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

                print(
                    "*****************************"
                )

                print()

    finally:
        database.close()

        print(
            "Database closed."
        )