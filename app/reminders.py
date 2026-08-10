from datetime import datetime

from alerts import ALERTS
from database import (
    connect_database,
    create_tables,
    get_alerted_runners_for_race,
    has_race_reminder_been_sent,
    mark_race_reminder_as_sent,
)
from notifications import send_discord_message


REMINDER_WINDOW_MINUTES = 2


def build_race_id(
    meeting_date: str,
    venue_code: str,
    race_number: int
) -> str:
    """
    Create a unique ID for one race.
    """

    return (
        f"{meeting_date}|"
        f"{venue_code}|"
        f"{race_number}"
    )


def get_alert_display(
    alert_id: str
) -> str:
    """
    Convert an internal alert ID into its
    configured emoji and display name.
    """

    for alert in ALERTS:
        if alert.id == alert_id:
            return (
                f"{alert.emoji} "
                f"{alert.name}"
            )

    return alert_id


def format_start_time(
    race_start: str
) -> str:
    """
    Convert stored scheduled start into a
    friendly 12-hour clock time.

    Example:
        2026-08-10 15:42
        becomes
        3:42 PM
    """

    try:
        start = datetime.strptime(
            race_start,
            "%Y-%m-%d %H:%M"
        )

        return start.strftime(
            "%I:%M %p"
        ).lstrip("0")

    except ValueError:
        return race_start


def build_reminder_message(
    race: dict,
    alerted_runners: list[dict],
    minutes_to_start: float
) -> str:
    """
    Build one Discord reminder containing
    every alerted runner in the race.
    """

    start_time_text = format_start_time(
        race["race_start"]
    )

    runner_sections = []

    for runner in alerted_runners:
        alert_lines = []

        for alert_data in runner["alerts"]:
            alert_name = get_alert_display(
                alert_data["alert_id"]
            )

            alert_price = alert_data[
                "alert_price"
            ]

            if alert_price is not None:
                alert_lines.append(
                    f"{alert_name} "
                    f"@ ${alert_price:.2f}"
                )
            else:
                alert_lines.append(
                    alert_name
                )

        triggered_text = "\n".join(
            f"• {line}"
            for line in alert_lines
        )

        runner_section = (
            f"**#{runner['runner_number']} "
            f"{runner['runner_name']}**\n"
            f"Initial: "
            f"**${runner['initial_price']:.2f}** | "
            f"Current: "
            f"**${runner['current_price']:.2f}**\n"
            f"{triggered_text}"
        )

        runner_sections.append(
            runner_section
        )

    runners_text = "\n\n".join(
        runner_sections
    )

    return (
        "⏰ **GREYHOUND RACE STARTING SOON** ⏰\n\n"
        f"**{race['meeting_name']} "
        f"R{race['race_number']}**\n"
        f"Scheduled Start: "
        f"**{start_time_text}**\n"
        f"Starts in approximately "
        f"**{max(1, round(minutes_to_start))} minute(s)**\n\n"
        f"**Alerted Runners**\n\n"
        f"{runners_text}"
    )


def check_race_reminders(
    races: list[dict]
) -> None:
    """
    Check the currently eligible races.

    If a race is 2 minutes or less from scheduled start,
    and at least one runner has previously generated an
    alert, send ONE Discord reminder containing all
    alerted runners.

    Only one reminder is sent per race.
    """

    now = datetime.now()

    database = connect_database()

    try:
        create_tables(
            database
        )

        for race in races:
            try:
                race_start = datetime.strptime(
                    race["race_start"],
                    "%Y-%m-%d %H:%M"
                )

            except ValueError:
                continue

            minutes_to_start = (
                race_start - now
            ).total_seconds() / 60

            # Only trigger while the scheduled start
            # is still in the future.
            if minutes_to_start <= 0:
                continue

            # Only trigger inside the 2-minute window.
            if (
                minutes_to_start
                > REMINDER_WINDOW_MINUTES
            ):
                continue

            race_id = build_race_id(
                meeting_date=race[
                    "meeting_date"
                ],
                venue_code=race[
                    "venue_code"
                ],
                race_number=race[
                    "race_number"
                ]
            )

            if has_race_reminder_been_sent(
                database,
                race_id
            ):
                continue

            alerted_runners = (
                get_alerted_runners_for_race(
                    database,
                    meeting_date=race[
                        "meeting_date"
                    ],
                    venue_code=race[
                        "venue_code"
                    ],
                    race_number=race[
                        "race_number"
                    ]
                )
            )

            if not alerted_runners:
                continue

            message = build_reminder_message(
                race=race,
                alerted_runners=alerted_runners,
                minutes_to_start=minutes_to_start
            )

            try:
                send_discord_message(
                    message
                )

                mark_race_reminder_as_sent(
                    database,
                    race_id
                )

                print(
                    f"Race reminder sent: "
                    f"{race['meeting_name']} "
                    f"R{race['race_number']} "
                    f"with "
                    f"{len(alerted_runners)} "
                    f"alerted runner(s)."
                )

            except Exception as error:
                print(
                    f"ERROR sending race reminder "
                    f"for "
                    f"{race['meeting_name']} "
                    f"R{race['race_number']}: "
                    f"{error}"
                )

    finally:
        database.close()