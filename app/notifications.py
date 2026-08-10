import os

import requests
from dotenv import load_dotenv


load_dotenv()


def get_webhook_url() -> str:
    """
    Return the Discord webhook URL stored in .env.
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


def get_active_role_id() -> str:
    """
    Return the Discord Active role ID stored in .env.
    """

    role_id = os.getenv(
        "DISCORD_ACTIVE_ROLE_ID"
    )

    if not role_id:
        raise RuntimeError(
            "DISCORD_ACTIVE_ROLE_ID was not found "
            "in the .env file."
        )

    return role_id


def send_discord_message(
    message: str
) -> None:
    """
    Send an alert to Discord and mention the Active role.

    Every message sent through this function automatically
    pings members subscribed to the Active role.
    """

    role_id = get_active_role_id()

    content = (
        f"<@&{role_id}>\n\n"
        f"{message}"
    )

    response = requests.post(
        get_webhook_url(),
        json={
            "content": content,
            "allowed_mentions": {
                "roles": [
                    role_id
                ]
            }
        },
        timeout=15
    )

    response.raise_for_status()