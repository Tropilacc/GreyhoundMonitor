from datetime import datetime

from alerts import (
    ALERTS,
    get_alert_by_id,
)
from database import (
    connect_database,
    create_tables,
    get_alerted_runners_for_race,
    has_race_reminder_been_sent,
    mark_race_reminder_as_sent,
)
from notifications import (
    get_all_alerts_role_id,
    get_role_id,
    send_discord_message,
)


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

    alert = get_alert_by_id(
        alert_id
    )

    if alert is None:
        return alert_id

    return (
        f"{alert.emoji} "
        f"{alert.name}"
    )


def format_start_time(
    race_start: str
) -> str:
    """
    Convert the stored race start into a
    friendly 12-hour clock time.

    Example:
        2026-08-10 16:30
        becomes
        4:30 PM
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


def format_minutes_to_start(
    minutes_to_start: float
) -> str:
    """
    Format the approximate time remaining.

    Examples:
        1 minute
        2 minutes
    """

    rounded_minutes = max(
        1,
        round(minutes_to_start)
    )

    if rounded_minutes == 1:
        return "1 minute"

    return (
        f"{rounded_minutes} minutes"
    )


def get_reminder_role_ids(
    alerted_runners: list[dict]
) -> list[str]:
    """
    Build the Discord role list for one race reminder.

    Every reminder pings:
        - ALL Alerts

    It also pings each specific alert role represented
    by at least one alerted runner in the race.

    Duplicate roles are removed.
    """

    role_ids = [
        get_all_alerts_role_id()
    ]

    for runner in alerted_runners:
        for alert_data in runner[
            "alerts"
        ]:
            alert = get_alert_by_id(
                alert_data[
                    "alert_id"
                ]
            )

            if alert is None:
                continue

            role_id = get_role_id(
                alert.role_env_name
            )

            if role_id not in role_ids:
                role_ids.append(
                    role_id
                )

    return role_ids


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

    time_remaining_text = (
        format_minutes_to_start(
            minutes_to_start
        )
    )

    runner_sections = []

    for runner in alerted_runners:
        alert_lines = []

        for alert_data in runner[
            "alerts"
        ]:
            alert_name = get_alert_display(
                alert_data[
                    "alert_id"
                ]
            )

            alert_price = alert_data[
                "alert_price"
            ]

            if alert_price is not None:
                alert_lines.append(
                    f"• {alert_name} — "
                    f"Triggered at "
                    f"**${alert_price:.2f}**"
                )

            else:
                alert_lines.append(
                    f"• {alert_name}"
                )

        triggered_text = "\n".join(
            alert_lines
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
        f"**{time_remaining_text}**\n\n"
        f"**Alerted Runners**\n\n"
        f"{runners_text}"
    )


def check_race_reminders(
    races: list[dict]
) -> None:
    """
    Check currently eligible races.

    If a race is two minutes or less from its
    scheduled start and at least one runner has
    previously generated an alert, send one
    Discord reminder containing all alerted runners.

    The reminder pings:
        - ALL Alerts
        - Each specific alert role represented
          in the race

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
                    race[
                        "race_start"
                    ],
                    "%Y-%m-%d %H:%M"
                )

            except ValueError:
                continue

            minutes_to_start = (
                race_start - now
            ).total_seconds() / 60

            if minutes_to_start <= 0:
                continue

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

            role_ids = get_reminder_role_ids(
                alerted_runners
            )

            try:
                send_discord_message(
                    message,
                    role_ids=role_ids
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