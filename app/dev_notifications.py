import os

import requests
from dotenv import load_dotenv


load_dotenv()


# ============================================================
# IN-MEMORY DUPLICATE SUPPRESSION
#
# If result checking retries the same missing venue every
# minute, Discord should only receive one warning for that
# venue during the current tracker session.
#
# If the tracker is restarted, the warning may be sent again.
# ============================================================

_sent_missing_venue_alerts: set[str] = set()


def get_dev_webhook_url() -> str | None:
    """
    Return the private Discord development webhook URL.

    Returns None if it has not been configured.
    """

    webhook_url = os.getenv(
        "DISCORD_DEV_WEBHOOK_URL"
    )

    if not webhook_url:
        return None

    return webhook_url


def send_missing_form_venue_alert(
    meeting_name: str,
    normal_venue_code: str,
    meeting_date: str
) -> bool:
    """
    Notify the private Discord development channel that
    no TAB Form venue code has been configured.

    The message uses @everyone so every member who can
    access the private Dev channel receives the notification.

    Duplicate warnings for the same meeting are suppressed
    for the lifetime of the current tracker process.

    Returns:
        True
            Alert was sent, or had already been sent.

        False
            Alert could not be sent.
    """

    alert_key = (
        meeting_name
        .strip()
        .upper()
    )

    # Already reported during this tracker session.
    if alert_key in _sent_missing_venue_alerts:
        return True

    webhook_url = get_dev_webhook_url()

    if not webhook_url:
        print(
            "WARNING: DISCORD_DEV_WEBHOOK_URL is not "
            "configured. Dev alert could not be sent."
        )

        return False

    message = (
        "@everyone\n\n"
        "⚠️ **GREYHOUND TRACKER DEV ALERT** ⚠️\n\n"
        "**Missing TAB Form Venue Code**\n\n"
        f"Meeting: **{meeting_name}**\n"
        f"Normal Venue Code: **{normal_venue_code}**\n"
        f"Meeting Date: **{meeting_date}**\n\n"
        "No TAB Form venue code is configured for this "
        "meeting.\n\n"
        "Historical result recovery cannot proceed until "
        "the venue is added to "
        "`TAB_FORM_VENUE_CODES` in "
        "`app/result_scraper.py`."
    )

    try:
        response = requests.post(
            webhook_url,
            json={
                "username": "⚠️ Developer Alert ⚠️",
                "content": message,
                "allowed_mentions": {
                    "parse": [
                        "everyone"
                    ]
                }
            },
            timeout=15
        )

        response.raise_for_status()

    except Exception as error:
        print(
            f"ERROR sending missing venue dev alert: "
            f"{error}"
        )

        return False

    _sent_missing_venue_alerts.add(
        alert_key
    )

    print(
        f"Dev alert sent for missing TAB Form "
        f"venue code: {meeting_name}"
    )

    return True