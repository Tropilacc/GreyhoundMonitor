import json
import re
from urllib.parse import urlparse

import requests


DEFAULT_TIMEOUT = 20

SPORTSBET_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-AU,en;q=0.9",
}


def fractional_to_decimal(price):
    """
    Convert Sportsbet fractional price format:

        {"num": 9, "den": 1}

    into decimal odds:

        10.00

    Returns None if the price is unavailable or invalid.
    """

    if not price:
        return None

    try:
        numerator = float(
            price["num"]
        )

        denominator = float(
            price["den"]
        )

        if denominator == 0:
            return None

        return round(
            (numerator / denominator) + 1,
            4
        )

    except (
        KeyError,
        TypeError,
        ValueError
    ):
        return None


def extract_event_id(url):
    """
    Extract the Sportsbet event ID from a race URL.

    Example:

        https://www.sportsbet.com.au/.../race-1-10812878

    returns:

        10812878
    """

    parsed = urlparse(
        url
    )

    path = parsed.path.rstrip(
        "/"
    )

    match = re.search(
        r"race-\d+-(\d+)$",
        path,
        re.IGNORECASE
    )

    if not match:
        raise ValueError(
            f"Could not determine Sportsbet event ID "
            f"from URL: {url}"
        )

    return match.group(
        1
    )


def fetch_preloaded_state(
    url,
    timeout=DEFAULT_TIMEOUT
):
    """
    Download a Sportsbet race page and parse
    window.__PRELOADED_STATE__.

    Returns the complete Sportsbet preloaded-state
    dictionary.
    """

    response = requests.get(
        url,
        headers=SPORTSBET_HEADERS,
        timeout=timeout,
    )

    response.raise_for_status()

    html = response.text

    marker = (
        "window.__PRELOADED_STATE__ = "
    )

    start = html.find(
        marker
    )

    if start == -1:
        raise RuntimeError(
            "Sportsbet __PRELOADED_STATE__ "
            "marker was not found."
        )

    end = html.find(
        "window.__APOLLO_STATE__",
        start
    )

    if end == -1:
        raise RuntimeError(
            "Sportsbet __APOLLO_STATE__ "
            "marker was not found."
        )

    raw_json = html[
        start + len(marker):end
    ].strip()

    raw_json = (
        raw_json
        .rstrip(";")
        .strip()
    )

    try:
        return json.loads(
            raw_json
        )

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Could not parse Sportsbet "
            f"__PRELOADED_STATE__: {exc}"
        ) from exc


def get_sportsbook_state(
    preloaded_state
):
    """
    Return Sportsbet's sportsbook entity state.
    """

    try:
        return (
            preloaded_state[
                "entities"
            ][
                "sportsbook"
            ]
        )

    except KeyError as exc:
        raise RuntimeError(
            "Sportsbet sportsbook state "
            "was not found."
        ) from exc


def get_meeting_for_event(
    sportsbook,
    event_id
):
    """
    Find the Sportsbet meeting record that contains
    the supplied event ID.

    Some meeting records have:

        eventIds = None

    so those records are safely skipped.
    """

    meetings = sportsbook.get(
        "meetings",
        {}
    )

    event_id_int = int(
        event_id
    )

    for meeting_id, meeting in meetings.items():

        event_ids = (
            meeting.get(
                "eventIds"
            )
            or []
        )

        if event_id_int in event_ids:

            result = dict(
                meeting
            )

            result[
                "id"
            ] = meeting_id

            return result

    return None


def get_competition_for_meeting(
    sportsbook,
    meeting
):
    """
    Return the competition record attached to a
    Sportsbet meeting.

    Sportsbet stores the actual meeting name in the
    competition record rather than the meeting record.
    """

    competition_id = meeting.get(
        "competitionId"
    )

    if competition_id is None:
        return None

    competitions = sportsbook.get(
        "competitions",
        {}
    )

    competition = competitions.get(
        str(
            competition_id
        )
    )

    if competition is None:
        return None

    result = dict(
        competition
    )

    result[
        "id"
    ] = competition_id

    return result


def get_sportsbet_race(
    url
):
    """
    Parse one Sportsbet race.

    Returns:

    {
        "event_id": ...,
        "meeting_id": ...,
        "meeting_name": ...,
        "competition_id": ...,
        "race_number": ...,
        "race_name": ...,
        "start_time_ms": ...,
        "track_status": ...,
        "distance": ...,
        "primary_market_id": ...,
        "primary_market_name": ...,
        "runners": [...]
    }
    """

    event_id = extract_event_id(
        url
    )

    preloaded_state = (
        fetch_preloaded_state(
            url
        )
    )

    sportsbook = (
        get_sportsbook_state(
            preloaded_state
        )
    )

    events = sportsbook.get(
        "events",
        {}
    )

    markets = sportsbook.get(
        "markets",
        {}
    )

    outcomes = sportsbook.get(
        "outcomes",
        {}
    )

    event = events.get(
        event_id
    )

    if event is None:
        raise RuntimeError(
            f"Sportsbet event {event_id} "
            "was not found in sportsbook state."
        )

    meeting = get_meeting_for_event(
        sportsbook=sportsbook,
        event_id=event_id
    )

    if meeting is None:
        raise RuntimeError(
            f"Sportsbet meeting for event "
            f"{event_id} was not found."
        )

    competition = (
        get_competition_for_meeting(
            sportsbook=sportsbook,
            meeting=meeting
        )
    )

    if competition is None:
        raise RuntimeError(
            f"Sportsbet competition for event "
            f"{event_id} was not found."
        )

    meeting_name = competition.get(
        "name"
    )

    if not meeting_name:
        raise RuntimeError(
            f"Sportsbet competition for event "
            f"{event_id} has no name."
        )

    primary_market_id = event.get(
        "primaryMarketId"
    )

    if primary_market_id is None:
        raise RuntimeError(
            f"Sportsbet event {event_id} "
            "has no primaryMarketId."
        )

    market = markets.get(
        str(
            primary_market_id
        )
    )

    if market is None:
        raise RuntimeError(
            f"Sportsbet primary market "
            f"{primary_market_id} "
            "was not found."
        )

    outcome_ids = market.get(
        "outcomeIds",
        []
    )

    runners = []

    for outcome_id in outcome_ids:

        outcome = outcomes.get(
            str(
                outcome_id
            )
        )

        if outcome is None:
            continue

        runner_number = outcome.get(
            "runnerNumber"
        )

        runner_name = outcome.get(
            "name"
        )

        if (
            runner_number is None
            or not runner_name
        ):
            continue

        active = outcome.get(
            "active",
            True
        )

        result_code = outcome.get(
            "result"
        )

        scratched = (
            result_code == "V"
        )

        open_price = outcome.get(
            "openPrice"
        )

        current_price = (
            fractional_to_decimal(
                outcome.get(
                    "winPrice"
                )
            )
        )

        place_price = (
            fractional_to_decimal(
                outcome.get(
                    "placePrice"
                )
            )
        )

        recent_fluctuations = (
            outcome.get(
                "recentOddsFluctuations",
                [],
            )
        )

        runner = {
            "runner_number":
                int(
                    runner_number
                ),

            "runner_name":
                str(
                    runner_name
                ).strip(),

            "active":
                bool(
                    active
                ),

            "result_code":
                result_code,

            "scratched":
                scratched,

            "open_price":
                (
                    float(
                        open_price
                    )
                    if open_price
                    is not None
                    else None
                ),

            "current_price":
                current_price,

            "place_price":
                place_price,

            "market_mover":
                bool(
                    outcome.get(
                        "marketMover",
                        False
                    )
                ),

            "recent_odds_fluctuations":
                recent_fluctuations,

            "sportsbet_outcome_id":
                outcome.get(
                    "id"
                ),

            "sportsbet_market_id":
                outcome.get(
                    "marketId"
                ),
        }

        runners.append(
            runner
        )

    runners.sort(
        key=lambda x: x[
            "runner_number"
        ]
    )

    start_time = (
        event.get(
            "startTime"
        )
        or {}
    )

    result = {
        "event_id":
            int(
                event_id
            ),

        "meeting_id":
            meeting.get(
                "id"
            ),

        "meeting_name":
            str(
                meeting_name
            ).strip(),

        "competition_id":
            competition.get(
                "id"
            ),

        "race_number":
            event.get(
                "raceNumber"
            ),

        "race_name":
            event.get(
                "name"
            ),

        "start_time_ms":
            start_time.get(
                "milliseconds"
            ),

        "track_status":
            event.get(
                "trackStatus"
            ),

        "distance":
            event.get(
                "distance"
            ),

        "primary_market_id":
            primary_market_id,

        "primary_market_name":
            market.get(
                "name"
            ),

        "runners":
            runners,
    }

    return result


def print_race(
    race
):
    """
    Diagnostic printer used while developing
    Sportsbet support.
    """

    print()
    print(
        "SPORTSBET RACE"
    )
    print(
        "--------------"
    )

    print(
        f"Event ID: "
        f"{race['event_id']}"
    )

    print(
        f"Meeting ID: "
        f"{race['meeting_id']}"
    )

    print(
        f"Meeting: "
        f"{race['meeting_name']}"
    )

    print(
        f"Competition ID: "
        f"{race['competition_id']}"
    )

    print(
        f"Race: "
        f"{race['race_name']}"
    )

    print(
        f"Race number: "
        f"{race['race_number']}"
    )

    print(
        f"Distance: "
        f"{race['distance']}"
    )

    print(
        f"Track status: "
        f"{race['track_status']}"
    )

    print(
        f"Primary market: "
        f"{race['primary_market_name']} "
        f"({race['primary_market_id']})"
    )

    print()
    print(
        f"Runners: "
        f"{len(race['runners'])}"
    )
    print()

    for runner in race[
        "runners"
    ]:

        number = runner[
            "runner_number"
        ]

        name = runner[
            "runner_name"
        ]

        if runner[
            "scratched"
        ]:
            print(
                f"#{number} "
                f"{name} | "
                f"SCRATCHED"
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
            if open_price
            is not None
            else "N/A"
        )

        current_text = (
            f"${current_price:.2f}"
            if current_price
            is not None
            else "N/A"
        )

        place_text = (
            f"${place_price:.2f}"
            if place_price
            is not None
            else "N/A"
        )

        print(
            f"#{number} "
            f"{name} | "
            f"Open: {open_text} | "
            f"Current: {current_text} | "
            f"Place: {place_text} | "
            f"MM: "
            f"{runner['market_mover']}"
        )


if __name__ == "__main__":

    TEST_URL = (
        "https://www.sportsbet.com.au/"
        "greyhound-racing/australia-nz/"
        "the-meadows/race-1-10812878"
    )

    race = get_sportsbet_race(
        TEST_URL
    )

    print_race(
        race
    )


