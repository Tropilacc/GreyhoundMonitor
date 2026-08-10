import os

import requests
from dotenv import load_dotenv

from alerts import ALERTS
from models import Runner


load_dotenv()


def get_webhook_url() -> str:
    """
    Get the Discord webhook URL from the .env file.
    """

    webhook_url = os.getenv(
        "DISCORD_WEBHOOK_URL"
    )

    if not webhook_url:
        raise RuntimeError(
            "DISCORD_WEBHOOK_URL was not found "
            "in the .env file."
        )

    return webhook_url


def send_discord_message(
    message: str
) -> None:
    """
    Send a message to the configured Discord webhook.
    """

    webhook_url = get_webhook_url()

    response = requests.post(
        webhook_url,
        json={
            "content": message
        },
        timeout=15
    )

    response.raise_for_status()


def build_alert_parameters_text() -> str:
    """
    Build the alert-rule section of the startup
    notification automatically from ALERTS.

    This means the startup notification always reflects
    the active rules defined in alerts.py.
    """

    sections = []

    for index, alert in enumerate(
        ALERTS,
        start=1
    ):
        parameter_lines = "\n".join(
            f"**{parameter}**"
            for parameter in alert.parameters
        )

        section = (
            f"{alert.emoji} "
            f"**Alert {index} — {alert.name}**\n"
            f"{parameter_lines}"
        )

        sections.append(section)

    return "\n\n".join(
        sections
    )


def send_startup_notification() -> None:
    """
    Send one Discord notification when the tracker starts.

    Alert information is generated automatically from
    the active ALERTS configuration.
    """

    alert_parameters = (
        build_alert_parameters_text()
    )

    message = (
        "🚨 **GREYHOUND TRACKER STARTED** 🚨\n\n"

        "**Monitoring Parameters**\n"
        "**Window:** 3 hours before race\n"
        "**Late Race Allowance:** "
        "5 minutes after scheduled start\n\n"

        "**Active Price Alerts**\n"
        f"{alert_parameters}\n\n"

        "**Polling Frequency**\n"
        "**60–180 min before:** Every 10 mins\n"
        "**30–60 min before:** Every 5 mins\n"
        "**10–30 min before:** Every 2 mins\n"
        "**10 min before to 5 min after:** "
        "Every 1 min\n\n"

        f"**Active Alerts:** {len(ALERTS)}\n"
        "**Discord Alerts:** Enabled"
    )

    send_discord_message(
        message
    )


def send_test_notification() -> None:
    """
    Send a test notification to Discord.
    """

    message = (
        "🧪 **GREYHOUND TRACKER TEST** 🧪\n\n"
        "Discord notifications are working!"
    )

    send_discord_message(
        message
    )

    print(
        "Discord test notification "
        "sent successfully."
    )


def send_discord_alert(
    runner: Runner
) -> None:
    """
    Legacy Alert 1 notification function.

    Kept temporarily for compatibility with any older
    code, although the generic monitor now builds its
    own alert messages.
    """

    if runner.initial_price > 0:
        drift_percent = (
            (
                runner.current_price
                - runner.initial_price
            )
            / runner.initial_price
        ) * 100
    else:
        drift_percent = 0

    message = (
        "🚨 **GREYHOUND PRICE ALERT** 🚨\n\n"
        f"**{runner.runner_name}**\n"
        f"{runner.venue_code} "
        f"R{runner.race_number} "
        f"— Box {runner.runner_number}\n\n"
        f"Initial Price: "
        f"**${runner.initial_price:.2f}**\n"
        f"Current Price: "
        f"**${runner.current_price:.2f}**\n"
        f"Price Drift: "
        f"**{drift_percent:+.1f}%**"
    )

    send_discord_message(
        message
    )