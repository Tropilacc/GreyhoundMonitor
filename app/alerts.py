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
        Human-readable conditions displayed in the
        startup Discord notification.

    condition:
        Function that determines whether a runner
        currently satisfies this alert.
    """

    id: str
    name: str
    emoji: str
    parameters: tuple[str, ...]
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
# ACTIVE ALERTS
#
# This is the central list of active alert rules.
#
# monitor.py reads this list to determine what alerts
# should fire.
#
# notifications.py reads this same list to build the
# startup Discord notification.
#
# ALERT_HISTORY uses each alert's ID to remember which
# alerts have already been sent.
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
        condition=price_shortening_condition,
    ),

    AlertRule(
        id="heavy_shortening",
        name="Heavy Shortening",
        emoji="⚡",
        parameters=(
            (
                f"Initial Price: "
                f"${HEAVY_SHORTENING_INITIAL_MIN:.2f} or greater"
            ),
            (
                f"Current Price: "
                f"${HEAVY_SHORTENING_CURRENT_MAX:.2f} or less"
            ),
        ),
        condition=heavy_shortening_condition,
    ),
)


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