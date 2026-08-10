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


def send_discord_message(
    message: str
) -> None:
    """
    Send a message to the configured Discord webhook.
    """

    response = requests.post(
        get_webhook_url(),
        json={
            "content": message
        },
        timeout=15
    )

    response.raise_for_status()