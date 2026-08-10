import os

import requests
from dotenv import load_dotenv


load_dotenv()


def get_statuscake_push_url() -> str:
    """
    Read the StatusCake push URL from the .env file.
    """

    push_url = os.getenv(
        "STATUSCAKE_PUSH_URL"
    )

    if not push_url:
        raise RuntimeError(
            "STATUSCAKE_PUSH_URL was not found "
            "in the .env file."
        )

    return push_url


def send_heartbeat() -> None:
    """
    Send one heartbeat to StatusCake.

    A successful HTTP response means StatusCake
    received the heartbeat.
    """

    push_url = get_statuscake_push_url()

    response = requests.get(
        push_url,
        timeout=15
    )

    response.raise_for_status()