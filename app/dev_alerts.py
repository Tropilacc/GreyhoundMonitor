import os
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

ENV_PATH = (
    PROJECT_ROOT
    / ".env"
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv(
    ENV_PATH,
    override=True
)

DISCORD_DEV_WEBHOOK_URL = os.getenv(
    "DISCORD_DEV_WEBHOOK_URL"
)


# ============================================================
# SETTINGS
# ============================================================

DEV_WEBHOOK_TIMEOUT_SECONDS = 15

VALID_SEVERITIES = {
    "WARNING",
    "ERROR",
}


# ============================================================
# FORMAT SEVERITY
# ============================================================

def get_severity_heading(
    severity: str
) -> str:
    """
    Return a Discord heading for the requested severity.
    """

    severity = (
        severity
        .strip()
        .upper()
    )

    if severity == "ERROR":
        return "🚨 GREYHOUND TRACKER — ERROR"

    if severity == "WARNING":
        return "⚠️ GREYHOUND TRACKER — WARNING"

    return "⚠️ GREYHOUND TRACKER — WARNING"


# ============================================================
# SEND DEV ALERT
# ============================================================

def send_dev_alert(
    source: str,
    message: str,
    error: Exception | str | None = None,
    severity: str = "ERROR",
    details: dict | None = None,
) -> bool:
    """
    Send an error or warning to the dedicated DEV Discord
    webhook.

    Parameters:

        source:
            Component that generated the fault.

            Examples:
                MAIN
                RESULT MONITOR
                RESULT SCRAPER
                RACE FINDER
                DATABASE
                STATS REPORT

        message:
            Human-readable description of what failed.

        error:
            Optional Exception or string containing the
            underlying error.

        severity:
            WARNING or ERROR.

        details:
            Optional dictionary containing extra context.

            Example:

                {
                    "Meeting": "BULLI",
                    "Race": "2",
                    "URL": "https://..."
                }

    Returns:

        True
            Discord notification sent successfully.

        False
            Notification could not be sent.

    IMPORTANT:

    This function must NEVER raise an exception back into
    Greyhound Tracker.

    DEV notification failures are printed locally only.
    """

    try:
        severity = (
            severity
            .strip()
            .upper()
        )

        if severity not in VALID_SEVERITIES:
            severity = "ERROR"

        if not DISCORD_DEV_WEBHOOK_URL:
            print(
                "DEV ALERT NOT SENT: "
                f"DISCORD_DEV_WEBHOOK_URL is missing "
                f"from {ENV_PATH}"
            )

            return False

        heading = get_severity_heading(
            severity
        )

        now = datetime.now()

        content_lines = [
            f"**{heading}**",
            "",
            f"**Source:** {source}",
            f"**Message:** {message}",
        ]

        if error is not None:

            if isinstance(
                error,
                Exception
            ):
                error_type = (
                    type(error).__name__
                )

                error_text = str(
                    error
                )

                content_lines.append(
                    f"**Error type:** {error_type}"
                )

                if error_text:
                    content_lines.append(
                        f"**Error:** {error_text}"
                    )

            else:
                content_lines.append(
                    f"**Error:** {error}"
                )

        if details:

            content_lines.append(
                ""
            )

            content_lines.append(
                "**Details:**"
            )

            for (
                key,
                value
            ) in details.items():

                if value is None:
                    continue

                content_lines.append(
                    f"- **{key}:** {value}"
                )

        content_lines.append(
            ""
        )

        content_lines.append(
            f"**Time:** "
            f"{now.strftime('%d/%m/%Y %I:%M %p')}"
        )

        content = "\n".join(
            content_lines
        )

        response = requests.post(
            DISCORD_DEV_WEBHOOK_URL,
            json={
                "content": content
            },
            timeout=(
                DEV_WEBHOOK_TIMEOUT_SECONDS
            ),
        )

        response.raise_for_status()

        return True

    except Exception as notification_error:
        print(
            "ERROR sending DEV Discord alert: "
            f"{notification_error}"
        )

        return False


# ============================================================
# DIRECT TEST
# ============================================================

def main():
    """
    Send a test message when this file is run directly.
    """

    print(
        "Testing DEV Discord webhook..."
    )

    print(
        f"Environment file: "
        f"{ENV_PATH}"
    )

    print(
        "DISCORD_DEV_WEBHOOK_URL loaded:",
        bool(
            DISCORD_DEV_WEBHOOK_URL
        )
    )

    success = send_dev_alert(
        source="DEV ALERT TEST",
        message=(
            "Greyhound Tracker DEV webhook "
            "test message."
        ),
        severity="WARNING",
        details={
            "Status":
                "Webhook test",
            "Expected result":
                "This message should appear "
                "in the DEV Discord channel",
        },
    )

    if success:
        print(
            "DEV Discord test message "
            "sent successfully."
        )

    else:
        print(
            "DEV Discord test message "
            "was not sent."
        )


if __name__ == "__main__":
    main()