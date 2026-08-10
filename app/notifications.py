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


def get_role_id(
    env_name: str
) -> str:
    """
    Return a Discord role ID from an environment
    variable.

    Example:
        DISCORD_PRICE_DRIFT_ROLE_ID
    """

    role_id = os.getenv(
        env_name
    )

    if not role_id:
        raise RuntimeError(
            f"{env_name} was not found "
            f"in the .env file."
        )

    return role_id


def get_all_alerts_role_id() -> str:
    """
    Return the role ID for users subscribed
    to every Greyhound Tracker alert.
    """

    return get_role_id(
        "DISCORD_ALL_ALERTS_ROLE_ID"
    )


def send_discord_message(
    message: str,
    role_ids: list[str] | tuple[str, ...] | None = None
) -> None:
    """
    Send a Discord message.

    role_ids:
        Optional Discord role IDs to mention.

    The function removes duplicate role IDs so a role
    is never mentioned twice in the same message.
    """

    unique_role_ids = []

    for role_id in role_ids or []:
        if (
            role_id
            and role_id not in unique_role_ids
        ):
            unique_role_ids.append(
                role_id
            )

    if unique_role_ids:
        mentions = " ".join(
            f"<@&{role_id}>"
            for role_id in unique_role_ids
        )

        content = (
            f"{mentions}\n\n"
            f"{message}"
        )

    else:
        content = message

    payload = {
        "content": content
    }

    if unique_role_ids:
        payload[
            "allowed_mentions"
        ] = {
            "roles": unique_role_ids
        }

    response = requests.post(
        get_webhook_url(),
        json=payload,
        timeout=15
    )

    response.raise_for_status()