import re
from datetime import datetime, timedelta

from bookmaker_venues import get_normal_venue_code
from scraper_sportsbet import (
    fetch_preloaded_state,
    get_sportsbook_state,
)


SPORTSBET_GREYHOUND_URL = (
    "https://www.sportsbet.com.au/greyhound-racing"
)

MONITOR_WINDOW_HOURS = 5
POST_START_GRACE_MINUTES = 5


# ============================================================
# URL SLUG
# ============================================================

def make_slug(
    value: str
) -> str:
    """
    Convert a Sportsbet meeting name into the slug used
    in Sportsbet race URLs.
    """

    value = (
        str(value)
        .strip()
        .lower()
    )

    value = re.sub(
        r"[^a-z0-9]+",
        "-",
        value
    )

    return value.strip(
        "-"
    )


# ============================================================
# SPORTSBET REGION
# ============================================================

def get_sportsbet_region_slug(
    competition: dict
) -> str:
    """
    Determine the Sportsbet URL region from the competition
    record.
    """

    region_id = (
        str(
            competition.get(
                "regionId",
                ""
            )
        )
        .strip()
        .lower()
    )

    region_type = (
        str(
            competition.get(
                "regionType",
                ""
            )
        )
        .strip()
        .upper()
    )

    if region_id in {
        "australia",
        "new-zealand",
        "new_zealand",
        "new zealand",
        "nz",
    }:
        return "australia-nz"

    if (
        region_type == "DOMESTIC"
        and region_id in {
            "australia",
            "new-zealand",
            "new_zealand",
            "new zealand",
            "nz",
        }
    ):
        return "australia-nz"

    return "international"


# ============================================================
# RACE URL
# ============================================================

def build_sportsbet_race_url(
    meeting_name: str,
    race_number: int,
    event_id: int,
    competition: dict
) -> str:
    """
    Build the Sportsbet race URL using the meeting name,
    race number, event ID and competition region.
    """

    meeting_slug = make_slug(
        meeting_name
    )

    region_slug = (
        get_sportsbet_region_slug(
            competition
        )
    )

    return (
        "https://www.sportsbet.com.au/"
        f"greyhound-racing/{region_slug}/"
        f"{meeting_slug}/"
        f"race-{race_number}-{event_id}"
    )


# ============================================================
# DISCOVER SPORTSBET SCHEDULE
# ============================================================

def _discover_todays_sportsbet_schedule() -> dict:
    """
    Discover today's Sportsbet greyhound schedule.

    Returns:
        {
            "eligible_races": [...],
            "next_future_race": {...} | None
        }

    Eligible races are:
        - No more than 3 hours before scheduled start.
        - No more than 5 minutes after scheduled start.

    next_future_race is the earliest mapped greyhound race
    that is more than 3 hours away.

    Only meetings with an existing mapping in:

        data/bookmaker_venues.csv

    are considered.
    """

    now = datetime.now()

    monitor_until = now + timedelta(
        hours=MONITOR_WINDOW_HOURS
    )

    monitor_from = now - timedelta(
        minutes=POST_START_GRACE_MINUTES
    )

    # ========================================================
    # LOAD SPORTSBET STATE
    # ========================================================

    preloaded_state = (
        fetch_preloaded_state(
            SPORTSBET_GREYHOUND_URL
        )
    )

    sportsbook = (
        get_sportsbook_state(
            preloaded_state
        )
    )

    meetings = sportsbook.get(
        "meetings",
        {}
    )

    competitions = sportsbook.get(
        "competitions",
        {}
    )

    events = sportsbook.get(
        "events",
        {}
    )

    eligible_races = []
    next_future_race = None

    mapped_meetings = 0
    unmapped_meetings = 0

    # ========================================================
    # PROCESS MEETINGS
    # ========================================================

    for meeting_id, meeting in meetings.items():

        event_ids = (
            meeting.get(
                "eventIds"
            )
            or []
        )

        if not event_ids:
            continue

        competition_id = meeting.get(
            "competitionId"
        )

        if competition_id is None:
            continue

        competition = competitions.get(
            str(
                competition_id
            )
        )

        if competition is None:
            continue

        meeting_name = competition.get(
            "name"
        )

        if not meeting_name:
            continue

        # Sportsbet racing class IDs:
        #
        #     4 = Greyhounds
        #
        # Other racing codes can appear in the general
        # Sportsbet racing state even when loading the
        # greyhound landing page.

        if competition.get("classId") != 4:
            continue

        # ====================================================
        # CANONICAL TAB VENUE CODE
        # ====================================================

        venue_code = get_normal_venue_code(
            bookmaker="SPORTSBET",
            bookmaker_meeting_name=meeting_name
        )

        if venue_code is None:
            unmapped_meetings += 1
            continue

        mapped_meetings += 1

        # ====================================================
        # PROCESS RACES
        # ====================================================

        for event_id in event_ids:

            event = events.get(
                str(
                    event_id
                )
            )

            if event is None:
                continue

            race_number = event.get(
                "raceNumber"
            )

            start_time = (
                event.get(
                    "startTime"
                )
                or {}
            )

            start_time_ms = start_time.get(
                "milliseconds"
            )

            if (
                race_number is None
                or start_time_ms is None
            ):
                continue

            # =================================================
            # RACE START
            # =================================================

            race_start = (
                datetime
                .fromtimestamp(
                    start_time_ms / 1000
                )
                .astimezone()
                .replace(
                    tzinfo=None
                )
            )

            meeting_date = (
                race_start.strftime(
                    "%Y-%m-%d"
                )
            )

            # =================================================
            # SPORTSBET RACE URL
            # =================================================

            race_url = (
                build_sportsbet_race_url(
                    meeting_name=meeting_name,
                    race_number=int(
                        race_number
                    ),
                    event_id=int(
                        event_id
                    ),
                    competition=competition
                )
            )

            race_data = {
                "bookmaker":
                    "SPORTSBET",

                "event_id":
                    int(
                        event_id
                    ),

                "meeting_id":
                    str(
                        meeting_id
                    ),

                "competition_id":
                    competition_id,

                "meeting_date":
                    meeting_date,

                "meeting_name":
                    meeting_name,

                "venue_code":
                    venue_code,

                "race_number":
                    int(
                        race_number
                    ),

                "race_start":
                    race_start.strftime(
                        "%Y-%m-%d %H:%M"
                    ),

                "race_url":
                    race_url,

                "region_id":
                    competition.get(
                        "regionId"
                    ),

                "region_type":
                    competition.get(
                        "regionType"
                    ),
            }

            # -------------------------------------------------
            # FUTURE RACE OUTSIDE MONITOR WINDOW
            # -------------------------------------------------

            if race_start > monitor_until:
                if next_future_race is None:
                    next_future_race = (
                        race_data
                    )

                else:
                    current_next_start = (
                        datetime.strptime(
                            next_future_race[
                                "race_start"
                            ],
                            "%Y-%m-%d %H:%M"
                        )
                    )

                    if (
                        race_start
                        < current_next_start
                    ):
                        next_future_race = (
                            race_data
                        )

                continue

            # -------------------------------------------------
            # MORE THAN 5 MINUTES PAST START
            # -------------------------------------------------

            if race_start < monitor_from:
                continue

            eligible_races.append(
                race_data
            )

    # ========================================================
    # SORT
    # ========================================================

    eligible_races.sort(
        key=lambda race: (
            race[
                "race_start"
            ],
            race[
                "venue_code"
            ],
            race[
                "race_number"
            ],
        )
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    print(
        f"Sportsbet mapped meetings: "
        f"{mapped_meetings}"
    )

    print(
        f"Sportsbet unmapped meetings skipped: "
        f"{unmapped_meetings}"
    )

    print(
        f"Sportsbet eligible races: "
        f"{len(eligible_races)}"
    )

    if next_future_race is not None:
        print(
            "Sportsbet next future race outside "
            f"monitor window: "
            f"{next_future_race['meeting_name']} "
            f"R{next_future_race['race_number']} "
            f"at {next_future_race['race_start']}"
        )

    return {
        "eligible_races": eligible_races,
        "next_future_race": next_future_race,
    }


# ============================================================
# PUBLIC SCHEDULE
# ============================================================

def get_todays_sportsbet_greyhound_schedule() -> dict:
    """
    Return today's Sportsbet monitoring schedule including:

    - Eligible races inside the monitoring window.
    - The next future race outside the window.
    """

    return _discover_todays_sportsbet_schedule()


# ============================================================
# PUBLIC ELIGIBLE RACES
# ============================================================

def get_todays_sportsbet_greyhound_races() -> list[dict]:
    """
    Return today's Sportsbet greyhound races currently
    eligible for bookmaker-price monitoring.

    This preserves the original public function used by
    main.py.
    """

    schedule = (
        _discover_todays_sportsbet_schedule()
    )

    return schedule[
        "eligible_races"
    ]


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    schedule = (
        get_todays_sportsbet_greyhound_schedule()
    )

    races = schedule[
        "eligible_races"
    ]

    print()

    for race in races:

        print(
            f"{race['race_start']} | "
            f"{race['meeting_name']} "
            f"({race['venue_code']}) "
            f"R{race['race_number']} | "
            f"{race['region_id']} / "
            f"{race['region_type']} | "
            f"{race['race_url']}"
        )

    next_future_race = schedule[
        "next_future_race"
    ]

    if next_future_race is not None:
        print()
        print(
            "Next future race outside monitor window:"
        )
        print(
            f"{next_future_race['race_start']} | "
            f"{next_future_race['meeting_name']} "
            f"({next_future_race['venue_code']}) "
            f"R{next_future_race['race_number']}"
        )
