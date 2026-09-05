import csv
from pathlib import Path


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

BOOKMAKER_VENUES_PATH = (
    PROJECT_ROOT
    / "data"
    / "bookmaker_venues.csv"
)


def normalise_text(value: str) -> str:
    """
    Normalise bookmaker names, track names and track codes
    for matching.
    """

    return (
        str(value)
        .strip()
        .upper()
    )


def load_bookmaker_venues() -> list[dict]:
    """
    Load bookmaker/source track mappings from:

        data/bookmaker_venues.csv

    Expected columns:

        BOOKMAKER
        TRACKNAME
        TRACKCODE
        COMMENTS

    TRACKCODE is specific to the BOOKMAKER/source.

    Examples:

        TAB,RICHMOND,RIC
        TABFORM,RICHMOND,S
        SPORTSBET,Richmond,RIC
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
            "TRACKNAME",
            "TRACKCODE",
            "COMMENTS",
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

        seen_keys = set()

        for row in reader:

            bookmaker = normalise_text(
                row.get(
                    "BOOKMAKER",
                    ""
                )
            )

            track_name = normalise_text(
                row.get(
                    "TRACKNAME",
                    ""
                )
            )

            track_code = normalise_text(
                row.get(
                    "TRACKCODE",
                    ""
                )
            )

            comments = (
                str(
                    row.get(
                        "COMMENTS",
                        ""
                    )
                    or ""
                )
                .strip()
            )

            if not bookmaker:
                continue

            if not track_name:
                continue

            key = (
                bookmaker,
                track_name,
            )

            if key in seen_keys:
                raise ValueError(
                    "Duplicate bookmaker track mapping "
                    f"found for "
                    f"{bookmaker} / {track_name}"
                )

            seen_keys.add(
                key
            )

            mappings.append(
                {
                    "bookmaker":
                        bookmaker,

                    "track_name":
                        track_name,

                    "track_code":
                        track_code,

                    "comments":
                        comments,
                }
            )

    return mappings


def get_track_mapping(
    bookmaker: str,
    track_name: str
) -> dict | None:
    """
    Return the mapping row for a bookmaker/source and
    track name.

    Returns None if the track is not configured.
    """

    bookmaker_normalised = normalise_text(
        bookmaker
    )

    track_name_normalised = normalise_text(
        track_name
    )

    mappings = load_bookmaker_venues()

    for mapping in mappings:

        if (
            mapping["bookmaker"]
            != bookmaker_normalised
        ):
            continue

        if (
            mapping["track_name"]
            != track_name_normalised
        ):
            continue

        return mapping

    return None


def get_track_code(
    bookmaker: str,
    track_name: str
) -> str | None:
    """
    Return the source-specific TRACKCODE for a track.

    Example:

        get_track_code(
            "TABFORM",
            "Richmond"
        )

    returns:

        S
    """

    mapping = get_track_mapping(
        bookmaker=bookmaker,
        track_name=track_name
    )

    if mapping is None:
        return None

    track_code = mapping[
        "track_code"
    ]

    if not track_code:
        return None

    return track_code


def require_track_code(
    bookmaker: str,
    track_name: str
) -> str:
    """
    Return the source-specific TRACKCODE.

    Raises an error if the mapping does not exist or the
    TRACKCODE is blank.
    """

    track_code = get_track_code(
        bookmaker=bookmaker,
        track_name=track_name
    )

    if track_code is None:
        raise ValueError(
            "No track code configured for "
            f"{bookmaker} / {track_name}"
        )

    return track_code


def get_normal_venue_code(
    bookmaker: str,
    bookmaker_meeting_name: str
) -> str | None:
    """
    Return the canonical TAB track code used in RUNNERID.

    The supplied bookmaker/source is first used to identify
    the common TRACKNAME. The matching TAB row is then used
    to obtain the canonical TAB TRACKCODE.

    This function is retained for compatibility with the
    existing Sportsbet integration.
    """

    source_mapping = get_track_mapping(
        bookmaker=bookmaker,
        track_name=bookmaker_meeting_name
    )

    if source_mapping is None:
        return None

    common_track_name = source_mapping[
        "track_name"
    ]

    tab_track_code = get_track_code(
        bookmaker="TAB",
        track_name=common_track_name
    )

    return tab_track_code


def require_normal_venue_code(
    bookmaker: str,
    bookmaker_meeting_name: str
) -> str:
    """
    Return the canonical TAB track code used in RUNNERID.

    Raises an error when the bookmaker track cannot be
    resolved to a configured TAB TRACKCODE.
    """

    venue_code = get_normal_venue_code(
        bookmaker=bookmaker,
        bookmaker_meeting_name=(
            bookmaker_meeting_name
        )
    )

    if venue_code is None:
        raise ValueError(
            "No canonical TAB track mapping found for "
            f"{bookmaker} / "
            f"{bookmaker_meeting_name}"
        )

    return venue_code


if __name__ == "__main__":

    tests = [
        (
            "SPORTSBET",
            "Wentworth Park",
        ),
        (
            "TAB",
            "Richmond",
        ),
        (
            "TABFORM",
            "Richmond",
        ),
    ]

    for bookmaker, track_name in tests:

        source_code = get_track_code(
            bookmaker=bookmaker,
            track_name=track_name
        )

        normal_code = get_normal_venue_code(
            bookmaker=bookmaker,
            bookmaker_meeting_name=track_name
        )

        print(
            f"{bookmaker} / "
            f"{track_name} -> "
            f"source={source_code}, "
            f"TAB={normal_code}"
        )