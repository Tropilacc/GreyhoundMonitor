import csv
from pathlib import Path


BOOKMAKER_VENUES_PATH = (
    Path("data")
    / "bookmaker_venues.csv"
)


def normalise_text(value: str) -> str:
    """
    Normalise bookmaker and meeting names for matching.
    """

    return (
        str(value)
        .strip()
        .upper()
    )


def load_bookmaker_venues() -> list[dict]:
    """
    Load bookmaker venue mappings from:

        data/bookmaker_venues.csv

    Expected columns:

        BOOKMAKER
        BOOKMAKER_MEETING_NAME
        NORMALVENUECODE
    """

    if not BOOKMAKER_VENUES_PATH.exists():
        raise FileNotFoundError(
            f"Bookmaker venue mapping file not found: "
            f"{BOOKMAKER_VENUES_PATH}"
        )

    mappings = []

    with BOOKMAKER_VENUES_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        reader = csv.DictReader(
            file
        )

        required_columns = {
            "BOOKMAKER",
            "BOOKMAKER_MEETING_NAME",
            "NORMALVENUECODE",
        }

        actual_columns = set(
            reader.fieldnames or []
        )

        missing_columns = (
            required_columns
            - actual_columns
        )

        if missing_columns:
            raise ValueError(
                "bookmaker_venues.csv is missing "
                f"required column(s): "
                f"{', '.join(sorted(missing_columns))}"
            )

        for row in reader:

            bookmaker = normalise_text(
                row.get(
                    "BOOKMAKER",
                    ""
                )
            )

            bookmaker_meeting_name = (
                normalise_text(
                    row.get(
                        "BOOKMAKER_MEETING_NAME",
                        ""
                    )
                )
            )

            normal_venue_code = (
                normalise_text(
                    row.get(
                        "NORMALVENUECODE",
                        ""
                    )
                )
            )

            if not bookmaker:
                continue

            if not bookmaker_meeting_name:
                continue

            if not normal_venue_code:
                continue

            mappings.append(
                {
                    "bookmaker":
                        bookmaker,

                    "bookmaker_meeting_name":
                        bookmaker_meeting_name,

                    "normal_venue_code":
                        normal_venue_code,
                }
            )

    return mappings


def get_normal_venue_code(
    bookmaker: str,
    bookmaker_meeting_name: str
) -> str | None:
    """
    Convert a bookmaker-specific meeting name into the
    canonical venue code used by GreyhoundMonitor.

    Example:

        bookmaker:
            SPORTSBET

        bookmaker_meeting_name:
            Wentworth Park

        returns:
            WWP

    Returns None if no mapping exists.
    """

    bookmaker_normalised = (
        normalise_text(
            bookmaker
        )
    )

    meeting_normalised = (
        normalise_text(
            bookmaker_meeting_name
        )
    )

    mappings = load_bookmaker_venues()

    for mapping in mappings:

        if (
            mapping["bookmaker"]
            != bookmaker_normalised
        ):
            continue

        if (
            mapping[
                "bookmaker_meeting_name"
            ]
            != meeting_normalised
        ):
            continue

        return mapping[
            "normal_venue_code"
        ]

    return None


def require_normal_venue_code(
    bookmaker: str,
    bookmaker_meeting_name: str
) -> str:
    """
    Return the canonical venue code.

    Raises an error when no mapping exists.

    This is useful during bookmaker integration because
    silently inventing or guessing a venue code could cause
    bookmaker prices to be attached to the wrong RUNNERID.
    """

    venue_code = get_normal_venue_code(
        bookmaker=bookmaker,
        bookmaker_meeting_name=(
            bookmaker_meeting_name
        )
    )

    if venue_code is None:
        raise ValueError(
            "No bookmaker venue mapping found for "
            f"{bookmaker} / "
            f"{bookmaker_meeting_name}"
        )

    return venue_code


if __name__ == "__main__":

    test_bookmaker = "SPORTSBET"
    test_meeting = "Wentworth Park"

    result = require_normal_venue_code(
        bookmaker=test_bookmaker,
        bookmaker_meeting_name=test_meeting
    )

    print(
        f"{test_bookmaker} / "
        f"{test_meeting} -> "
        f"{result}"
    )
