from datetime import datetime

from bookmaker_venues import require_normal_venue_code
from database import (
    connect_database,
    create_tables,
    save_runner_price,
)
from scraper_sportsbet import get_sportsbet_race


BOOKMAKER = "SPORTSBET"


# ============================================================
# RUNNER ID
# ============================================================

def build_runner_id(
    meeting_date: str,
    venue_code: str,
    race_number: int,
    runner_number: int
) -> str:
    """
    Create the canonical GreyhoundMonitor RUNNERID.

    This must exactly match the RUNNERID format used by TAB:

        YYYY-MM-DD|VENUECODE|RACE|RUNNER

    Example:

        2026-08-15|MEA|1|4
    """

    return (
        f"{meeting_date}|"
        f"{venue_code}|"
        f"{race_number}|"
        f"{runner_number}"
    )


# ============================================================
# MEETING DATE
# ============================================================

def get_meeting_date(
    start_time_ms: int
) -> str:
    """
    Convert Sportsbet's race start timestamp into the
    local meeting date used by GreyhoundMonitor.

    Sportsbet supplies startTime as Unix milliseconds.
    """

    if start_time_ms is None:
        raise ValueError(
            "Sportsbet race has no start_time_ms."
        )

    race_start = datetime.fromtimestamp(
        start_time_ms / 1000
    ).astimezone()

    return race_start.strftime(
        "%Y-%m-%d"
    )


# ============================================================
# MONITOR SPORTSBET RACE
# ============================================================

def monitor_sportsbet_race(
    race_url: str
) -> dict:
    """
    Scrape one Sportsbet race and save bookmaker-specific
    runner prices into RUNNER_PRICES.

    This function does NOT:

    - Create canonical RUNNERS rows.
    - Replace TAB pricing in RUNNERS.
    - Generate alerts.
    - Send Discord notifications.
    - Mark alert runners as scratched.

    TAB remains the canonical race/runner and alert source
    while the multi-bookmaker architecture is being built.

    Sportsbet contributes bookmaker-specific information:

    - Genuine opening price.
    - Initial observed price.
    - Current Win price.
    - Current Place price.
    - Scratch status.
    - Sportsbet market-mover status.
    - Sportsbet outcome ID.
    """

    # ========================================================
    # SCRAPE SPORTSBET
    # ========================================================

    race = get_sportsbet_race(
        race_url
    )

    meeting_name = race[
        "meeting_name"
    ]

    race_number = race[
        "race_number"
    ]

    start_time_ms = race[
        "start_time_ms"
    ]

    if race_number is None:
        raise ValueError(
            "Sportsbet race has no race number."
        )

    # ========================================================
    # CANONICAL MEETING IDENTITY
    # ========================================================

    meeting_date = get_meeting_date(
        start_time_ms
    )

    venue_code = require_normal_venue_code(
        bookmaker=BOOKMAKER,
        bookmaker_meeting_name=meeting_name
    )

    print()
    print(
        f"Sportsbet: "
        f"{meeting_name} "
        f"({venue_code}) "
        f"R{race_number}"
    )

    print(
        f"Meeting date: "
        f"{meeting_date}"
    )

    print(
        f"Sportsbet event ID: "
        f"{race['event_id']}"
    )

    print(
        f"Primary market: "
        f"{race['primary_market_name']} "
        f"({race['primary_market_id']})"
    )

    # ========================================================
    # DATABASE
    # ========================================================

    database = connect_database()

    saved_runners = 0
    active_runners = 0
    scratched_runners = 0
    canonical_matches = 0
    canonical_missing = 0

    try:
        create_tables(
            database
        )

        # ====================================================
        # PROCESS SPORTSBET RUNNERS
        # ====================================================

        for runner in race[
            "runners"
        ]:

            runner_number = runner[
                "runner_number"
            ]

            runner_name = runner[
                "runner_name"
            ]

            runner_id = build_runner_id(
                meeting_date=meeting_date,
                venue_code=venue_code,
                race_number=race_number,
                runner_number=runner_number
            )

            # ================================================
            # SAVE BOOKMAKER PRICE
            # ================================================

            save_runner_price(
                connection=database,
                runner_id=runner_id,
                bookmaker=BOOKMAKER,
                current_price=runner[
                    "current_price"
                ],
                opening_price=runner[
                    "open_price"
                ],
                place_price=runner[
                    "place_price"
                ],
                source_runner_id=runner[
                    "sportsbet_outcome_id"
                ],
                scratched=runner[
                    "scratched"
                ],
                market_mover=runner[
                    "market_mover"
                ]
            )

            saved_runners += 1

            if runner[
                "scratched"
            ]:
                scratched_runners += 1

            else:
                active_runners += 1

            # ================================================
            # CHECK WHETHER TAB HAS CREATED THE CANONICAL
            # RUNNER RECORD YET
            #
            # Sportsbet does not create RUNNERS rows itself.
            # ================================================

            canonical_runner = database.execute(
                """
                SELECT
                    RUNNERNAME
                FROM RUNNERS
                WHERE RUNNERID = ?;
                """,
                (
                    runner_id,
                )
            ).fetchone()

            if canonical_runner is None:
                canonical_missing += 1
                canonical_text = (
                    "TAB runner not yet stored"
                )

            else:
                canonical_matches += 1
                canonical_text = (
                    f"TAB: "
                    f"{canonical_runner[0]}"
                )

            # ================================================
            # TERMINAL OUTPUT
            # ================================================

            if runner[
                "scratched"
            ]:
                print(
                    f"{venue_code} "
                    f"R{race_number} "
                    f"#{runner_number} "
                    f"{runner_name} | "
                    f"SCRATCHED | "
                    f"{canonical_text}"
                )

                continue

            open_price = runner[
                "open_price"
            ]

            current_price = runner[
                "current_price"
            ]

            place_price = runner[
                "place_price"
            ]

            open_text = (
                f"${open_price:.2f}"
                if open_price is not None
                else "N/A"
            )

            current_text = (
                f"${current_price:.2f}"
                if current_price is not None
                else "N/A"
            )

            place_text = (
                f"${place_price:.2f}"
                if place_price is not None
                else "N/A"
            )

            print(
                f"{venue_code} "
                f"R{race_number} "
                f"#{runner_number} "
                f"{runner_name} | "
                f"Open: {open_text} | "
                f"Current: {current_text} | "
                f"Place: {place_text} | "
                f"MM: {runner['market_mover']} | "
                f"{canonical_text}"
            )

    finally:
        database.close()

        print(
            "Database closed."
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    summary = {
        "bookmaker":
            BOOKMAKER,

        "event_id":
            race["event_id"],

        "meeting_date":
            meeting_date,

        "meeting_name":
            meeting_name,

        "venue_code":
            venue_code,

        "race_number":
            race_number,

        "saved_runners":
            saved_runners,

        "active_runners":
            active_runners,

        "scratched_runners":
            scratched_runners,

        "canonical_matches":
            canonical_matches,

        "canonical_missing":
            canonical_missing,
    }

    print()
    print(
        "SPORTSBET MONITOR SUMMARY"
    )
    print(
        "--------------------------"
    )

    print(
        f"Saved runners: "
        f"{saved_runners}"
    )

    print(
        f"Active runners: "
        f"{active_runners}"
    )

    print(
        f"Scratched runners: "
        f"{scratched_runners}"
    )

    print(
        f"TAB canonical matches: "
        f"{canonical_matches}"
    )

    print(
        f"TAB canonical missing: "
        f"{canonical_missing}"
    )

    return summary


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    TEST_URL = (
        "https://www.sportsbet.com.au/"
        "greyhound-racing/australia-nz/"
        "the-meadows/race-1-10812878"
    )

    monitor_sportsbet_race(
        TEST_URL
    )
