from dataclasses import dataclass
from typing import Callable

from models import Runner


@dataclass(frozen=True)
class AlertRule:
    """
    Definition of one greyhound price alert.

    id:
        Permanent unique identifier used internally
        and stored in ALERT_HISTORY.

    name:
        Human-readable alert name.

    emoji:
        Emoji used in Discord messages.

    parameters:
        Human-readable conditions describing the alert.

    role_env_name:
        Name of the .env variable containing the
        Discord role ID for subscribers to this alert.

    condition:
        Function that determines whether a runner
        currently satisfies this alert.
    """

    id: str
    name: str
    emoji: str
    parameters: tuple[str, ...]
    role_env_name: str
    condition: Callable[[Runner], bool]


# ============================================================
# ALERT 1 — PRICE DRIFT
#
# Initial price < $5.00
# Current price > $10.00
# ============================================================

PRICE_DRIFT_INITIAL_MAX = 5.00
PRICE_DRIFT_CURRENT_MIN = 10.00


def price_drift_condition(
    runner: Runner
) -> bool:
    """
    Trigger when:

    - Initial price is below $5.00
    - Current price is above $10.00
    """

    return (
        runner.initial_price
        < PRICE_DRIFT_INITIAL_MAX
        and runner.current_price
        > PRICE_DRIFT_CURRENT_MIN
    )


# ============================================================
# ALERT 2 — PRICE SHORTENING
#
# Initial price > $10.00
# Price drop >= $5.00
# Current price <= $10.00
# ============================================================

PRICE_SHORTENING_INITIAL_MIN = 10.00
PRICE_SHORTENING_DROP_MIN = 5.00
PRICE_SHORTENING_CURRENT_MAX = 10.00


def price_shortening_condition(
    runner: Runner
) -> bool:
    """
    Trigger when ALL conditions are met:

    - Initial price is above $10.00
    - Price has shortened by at least $5.00
    - Current price is $10.00 or less
    """

    price_drop = (
        runner.initial_price
        - runner.current_price
    )

    return (
        runner.initial_price
        > PRICE_SHORTENING_INITIAL_MIN

        and price_drop
        >= PRICE_SHORTENING_DROP_MIN

        and runner.current_price
        <= PRICE_SHORTENING_CURRENT_MAX
    )


# ============================================================
# ALERT 3 — HEAVY SHORTENING
#
# Initial price >= $5.00
# Current price <= $2.00
# ============================================================

HEAVY_SHORTENING_INITIAL_MIN = 5.00
HEAVY_SHORTENING_CURRENT_MAX = 2.00


def heavy_shortening_condition(
    runner: Runner
) -> bool:
    """
    Trigger when ALL conditions are met:

    - Initial price is $5.00 or greater
    - Current price is $2.00 or less
    """

    return (
        runner.initial_price
        >= HEAVY_SHORTENING_INITIAL_MIN

        and runner.current_price
        <= HEAVY_SHORTENING_CURRENT_MAX
    )


# ============================================================
# ALERT 4 — EXTREME PRICE MOVE
#
# Initial price < $30.00
# Absolute price movement > $20.00
#
# Movement may be either:
# - Up / drifting
# - Down / shortening
# ============================================================

EXTREME_PRICE_MOVE_INITIAL_MAX = 30.00
EXTREME_PRICE_MOVE_MIN = 20.00


def extreme_price_move_condition(
    runner: Runner
) -> bool:
    """
    Trigger when ALL conditions are met:

    - Initial price is below $30.00
    - Price has moved by MORE than $20.00
    - Movement can be either up or down
    """

    price_movement = abs(
        runner.current_price
        - runner.initial_price
    )

    return (
        runner.initial_price
        < EXTREME_PRICE_MOVE_INITIAL_MAX

        and price_movement
        > EXTREME_PRICE_MOVE_MIN
    )


# ============================================================
# ACTIVE ALERTS
#
# This is the central list of active alert rules.
#
# Each alert also defines the .env variable containing
# the Discord role ID for subscribers to that alert.
# ============================================================

ALERTS = (
    AlertRule(
        id="price_drift",
        name="Price Drift",
        emoji="🚨",
        parameters=(
            (
                f"Initial Price: "
                f"Below ${PRICE_DRIFT_INITIAL_MAX:.2f}"
            ),
            (
                f"Current Price: "
                f"Above ${PRICE_DRIFT_CURRENT_MIN:.2f}"
            ),
        ),
        role_env_name=(
            "DISCORD_PRICE_DRIFT_ROLE_ID"
        ),
        condition=price_drift_condition,
    ),

    AlertRule(
        id="price_shortening",
        name="Price Shortening",
        emoji="🔥",
        parameters=(
            (
                f"Initial Price: "
                f"Above ${PRICE_SHORTENING_INITIAL_MIN:.2f}"
            ),
            (
                f"Price Drop: "
                f"At least ${PRICE_SHORTENING_DROP_MIN:.2f}"
            ),
            (
                f"Current Price: "
                f"${PRICE_SHORTENING_CURRENT_MAX:.2f} or less"
            ),
        ),
        role_env_name=(
            "DISCORD_PRICE_SHORTENING_ROLE_ID"
        ),
        condition=price_shortening_condition,
    ),

    AlertRule(
        id="heavy_shortening",
        name="Heavy Shortening",
        emoji="⚡",
        parameters=(
            (
                f"Initial Price: "
                f"${HEAVY_SHORTENING_INITIAL_MIN:.2f} "
                f"or greater"
            ),
            (
                f"Current Price: "
                f"${HEAVY_SHORTENING_CURRENT_MAX:.2f} "
                f"or less"
            ),
        ),
        role_env_name=(
            "DISCORD_HEAVY_SHORTENING_ROLE_ID"
        ),
        condition=heavy_shortening_condition,
    ),

    AlertRule(
        id="extreme_price_move",
        name="Extreme Price Move",
        emoji="💥",
        parameters=(
            (
                f"Initial Price: "
                f"Below ${EXTREME_PRICE_MOVE_INITIAL_MAX:.2f}"
            ),
            (
                f"Price Movement: "
                f"More than ${EXTREME_PRICE_MOVE_MIN:.2f}"
            ),
            (
                "Direction: Either up or down"
            ),
        ),
        role_env_name=(
            "DISCORD_EXTREME_PRICE_MOVE_ROLE_ID"
        ),
        condition=extreme_price_move_condition,
    ),
)


def get_alert_by_id(
    alert_id: str
) -> AlertRule | None:
    """
    Return the alert rule matching an internal ID.
    """

    for alert in ALERTS:
        if alert.id == alert_id:
            return alert

    return None


def get_triggered_alerts(
    runner: Runner
) -> list[AlertRule]:
    """
    Return all active alert rules whose price
    conditions are currently satisfied.

    Whether an alert has already been sent is handled
    separately by ALERT_HISTORY in the database.
    """

    return [
        alert
        for alert in ALERTS
        if alert.condition(runner)
    ]