from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright


MONITOR_WINDOW_HOURS = 3
POST_START_GRACE_MINUTES = 5


def _discover_todays_greyhound_schedule() -> dict:
    """
    Discover today's TAB greyhound schedule.

    Returns:
        {
            "eligible_races": [...],
            "next_future_race": {...} | None
        }

    Eligible races are:
    - No more than 3 hours before scheduled start.
    - No more than 5 minutes after scheduled start.

    next_future_race is the earliest race that is
    more than 3 hours away.

    TAB requires a headed Chromium browser, so the
    browser is launched far off-screen to prevent it
    interrupting normal desktop use.
    """

    now = datetime.now()

    monitor_until = now + timedelta(
        hours=MONITOR_WINDOW_HOURS
    )

    monitor_from = now - timedelta(
        minutes=POST_START_GRACE_MINUTES
    )

    today_text = now.strftime("%Y-%m-%d")

    meetings_page_url = (
        "https://www.tab.com.au/racing/meetings/today/G"
    )

    api_url = (
        "https://api.beta.tab.com.au/"
        "v1/tab-info-service/racing/"
        f"dates/{today_text}/meetings"
        "?returnOffers=true"
        "&returnPromo=true"
        "&jurisdiction=NSW"
    )

    eligible_races = []
    next_future_race = None

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=False,
            args=[
                "--window-position=-32000,-32000",
                "--window-size=1600,1200",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding"
            ]
        )

        context = browser.new_context(
            permissions=[
                "local-network-access"
            ],
            viewport={
                "width": 1600,
                "height": 1200
            }
        )

        page = context.new_page()

        try:
            page.goto(
                meetings_page_url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_timeout(5000)

            meetings_data = page.evaluate(
                """
                async (apiUrl) => {
                    const response = await fetch(
                        apiUrl,
                        {
                            method: "GET",
                            credentials: "include",
                            headers: {
                                "Accept": "application/json"
                            }
                        }
                    );

                    if (!response.ok) {
                        throw new Error(
                            `TAB API returned ${response.status}`
                        );
                    }

                    return await response.json();
                }
                """,
                api_url
            )

            meetings = meetings_data.get(
                "meetings",
                meetings_data
            )

            if isinstance(meetings, dict):
                meetings = meetings.get(
                    "meetings",
                    []
                )

            for meeting in meetings:
                if meeting.get("raceType") != "G":
                    continue

                meeting_name = meeting.get(
                    "meetingName",
                    ""
                )

                venue_code = meeting.get(
                    "venueMnemonic",
                    ""
                )

                meeting_date = meeting.get(
                    "meetingDate",
                    today_text
                )

                if not meeting_name or not venue_code:
                    continue

                meeting_slug = (
                    meeting_name
                    .upper()
                    .replace(" ", "-")
                )

                for race in meeting.get(
                    "races",
                    []
                ):
                    race_number = race.get(
                        "raceNumber"
                    )

                    race_start_text = race.get(
                        "raceStartTime"
                    )

                    if (
                        race_number is None
                        or not race_start_text
                    ):
                        continue

                    race_start = (
                        datetime.fromisoformat(
                            race_start_text.replace(
                                "Z",
                                "+00:00"
                            )
                        )
                    )

                    race_start_local = (
                        race_start
                        .astimezone()
                        .replace(tzinfo=None)
                    )

                    race_url = (
                        "https://www.tab.com.au/racing/"
                        f"{meeting_date}/"
                        f"{meeting_slug}/"
                        f"{venue_code}/G/"
                        f"{race_number}"
                    )

                    race_data = {
                        "race_url": race_url,
                        "meeting_date": meeting_date,
                        "meeting_name": meeting_name,
                        "venue_code": venue_code,
                        "race_number": race_number,
                        "race_start": (
                            race_start_local.strftime(
                                "%Y-%m-%d %H:%M"
                            )
                        )
                    }

                    # -----------------------------------------
                    # FUTURE RACE OUTSIDE MONITOR WINDOW
                    # -----------------------------------------

                    if race_start_local > monitor_until:
                        if next_future_race is None:
                            next_future_race = race_data

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
                                race_start_local
                                < current_next_start
                            ):
                                next_future_race = (
                                    race_data
                                )

                        continue

                    # -----------------------------------------
                    # TOO FAR PAST START
                    # -----------------------------------------

                    if race_start_local < monitor_from:
                        continue

                    eligible_races.append(
                        race_data
                    )

        finally:
            context.close()
            browser.close()

    eligible_races.sort(
        key=lambda race: race["race_start"]
    )

    return {
        "eligible_races": eligible_races,
        "next_future_race": next_future_race,
    }


def get_todays_greyhound_schedule() -> dict:
    """
    Return today's monitoring schedule including:

    - Eligible races inside the monitoring window.
    - The next future race outside the window.
    """

    return _discover_todays_greyhound_schedule()


def get_todays_greyhound_races() -> list[dict]:
    """
    Return today's TAB greyhound races that are
    currently eligible for price monitoring.

    This preserves the original public function
    used by main.py.
    """

    schedule = (
        _discover_todays_greyhound_schedule()
    )

    return schedule[
        "eligible_races"
    ]