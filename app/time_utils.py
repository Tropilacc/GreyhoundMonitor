from datetime import datetime


def format_race_start_time(
    race_start: str
) -> str:
    """
    Convert stored race start time into a friendly
    12-hour clock format.

    Example:
        2026-09-06 20:42 -> 8:42 PM

    If parsing fails, return the original value.
    """

    if not race_start:
        return "Unknown"

    try:
        start = datetime.strptime(
            race_start,
            "%Y-%m-%d %H:%M",
        )

        return start.strftime(
            "%I:%M %p"
        ).lstrip("0")

    except ValueError:
        return race_start
