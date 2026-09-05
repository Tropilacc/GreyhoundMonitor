import sqlite3
from pathlib import Path

from models import Runner


DATABASE_PATH = (
    Path("data")
    / "greyhound.db"
)


# ============================================================
# RESULT CODES
# ============================================================

SCRATCHED_POSITION = 100


# ============================================================
# DATABASE CONNECTION
# ============================================================

def connect_database() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    print(
        f"Database: "
        f"{DATABASE_PATH}"
    )

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    print(
        "Connected successfully."
    )

    return connection


# ============================================================
# SCHEMA HELPERS
# ============================================================

def column_exists(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str
) -> bool:
    """
    Return True if a column already exists
    in a SQLite table.
    """

    cursor = connection.cursor()

    cursor.execute(
        f"PRAGMA table_info({table_name});"
    )

    columns = cursor.fetchall()

    return any(
        column[1].upper()
        == column_name.upper()
        for column in columns
    )


# ============================================================
# CREATE / UPGRADE TABLES
# ============================================================

def create_tables(
    connection: sqlite3.Connection
) -> None:
    """
    Create and upgrade all tracker database tables.

    RUNNERS:
        Stores the core runner identity, race metadata and
        the existing TAB price fields.

        INITIALPRICE and CURRENTPRICE remain in this table
        for backwards compatibility with the existing TAB
        alert engine.

    RUNNER_PRICES:
        Stores bookmaker-specific pricing for each runner.

        One runner can therefore have separate rows for:

            TAB
            SPORTSBET
            LADBROKES
            etc.

        The primary key is:

            RUNNERID + BOOKMAKER

        OPENING_PRICE:
            The bookmaker's genuine published opening price,
            when available.

        INITIAL_OBSERVED_PRICE:
            The first price GreyhoundMonitor personally
            observed from that bookmaker.

        CURRENT_PRICE:
            The latest Win price observed.

    ALERT_HISTORY:
        Stores each price alert that fired.

        WINALERTSENT tracks the secondary Discord
        notification for a winning alerted runner.

        This is stored per RUNNERID + ALERTID so a runner
        that triggered multiple alert categories receives
        one independent win notification for each category.

    REMINDER_HISTORY:
        Stores one pre-race reminder per race.

    SCRATCH_HISTORY:
        Stores one successful scratched-runner Discord
        notification per runner.

        This prevents a scratched alerted runner from
        generating the same notification every monitoring
        cycle.
    """

    cursor = connection.cursor()

    # ========================================================
    # RUNNERS
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS RUNNERS (
            RUNNERID TEXT PRIMARY KEY,
            MEETINGDATE TEXT NOT NULL,
            MEETINGNAME TEXT,
            VENUECODE TEXT NOT NULL,
            RACENUMBER INTEGER NOT NULL,
            RACESTART TEXT,
            RUNNERNUMBER INTEGER NOT NULL,
            RUNNERNAME TEXT NOT NULL,
            INITIALPRICE REAL NOT NULL,
            CURRENTPRICE REAL NOT NULL
        );
        """
    )

    connection.commit()

    if not column_exists(
        connection,
        "RUNNERS",
        "MEETINGNAME"
    ):
        cursor.execute(
            """
            ALTER TABLE RUNNERS
            ADD COLUMN MEETINGNAME TEXT;
            """
        )

    if not column_exists(
        connection,
        "RUNNERS",
        "RACESTART"
    ):
        cursor.execute(
            """
            ALTER TABLE RUNNERS
            ADD COLUMN RACESTART TEXT;
            """
        )

    connection.commit()

    # ========================================================
    # RUNNER PRICES
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS RUNNER_PRICES (
            RUNNERID TEXT NOT NULL,
            BOOKMAKER TEXT NOT NULL,

            SOURCE_RUNNER_ID TEXT,

            OPENING_PRICE REAL,
            INITIAL_OBSERVED_PRICE REAL,
            CURRENT_PRICE REAL,
            PLACE_PRICE REAL,

            SCRATCHED INTEGER NOT NULL DEFAULT 0,
            MARKET_MOVER INTEGER NOT NULL DEFAULT 0,

            LAST_SEEN TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (
                RUNNERID,
                BOOKMAKER
            )
        );
        """
    )

    connection.commit()

    # ========================================================
    # ALERT HISTORY
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ALERT_HISTORY (
            RUNNERID TEXT NOT NULL,
            ALERTID TEXT NOT NULL,
            ALERTPRICE REAL,
            FINISHPOSITION INTEGER,
            RESULTCHECKED INTEGER NOT NULL DEFAULT 0,
            WINALERTSENT INTEGER NOT NULL DEFAULT 0,
            SENTAT TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (
                RUNNERID,
                ALERTID
            )
        );
        """
    )

    connection.commit()

    if not column_exists(
        connection,
        "ALERT_HISTORY",
        "ALERTPRICE"
    ):
        cursor.execute(
            """
            ALTER TABLE ALERT_HISTORY
            ADD COLUMN ALERTPRICE REAL;
            """
        )

    if not column_exists(
        connection,
        "ALERT_HISTORY",
        "FINISHPOSITION"
    ):
        cursor.execute(
            """
            ALTER TABLE ALERT_HISTORY
            ADD COLUMN FINISHPOSITION INTEGER;
            """
        )

    if not column_exists(
        connection,
        "ALERT_HISTORY",
        "RESULTCHECKED"
    ):
        cursor.execute(
            """
            ALTER TABLE ALERT_HISTORY
            ADD COLUMN RESULTCHECKED
            INTEGER NOT NULL DEFAULT 0;
            """
        )

    # --------------------------------------------------------
    # WIN ALERT MIGRATION
    #
    # Existing historical wins must NOT generate retroactive
    # Discord notifications when this feature is first added.
    #
    # Therefore:
    #
    #     1. Add WINALERTSENT with default 0.
    #     2. Mark existing completed wins as already sent.
    #
    # This UPDATE runs only during the one-time migration.
    # New alert rows created afterwards remain at 0.
    # --------------------------------------------------------

    if not column_exists(
        connection,
        "ALERT_HISTORY",
        "WINALERTSENT"
    ):
        cursor.execute(
            """
            ALTER TABLE ALERT_HISTORY
            ADD COLUMN WINALERTSENT
            INTEGER NOT NULL DEFAULT 0;
            """
        )

        cursor.execute(
            """
            UPDATE ALERT_HISTORY
            SET WINALERTSENT = 1
            WHERE
                RESULTCHECKED = 1
                AND FINISHPOSITION = 1;
            """
        )

    connection.commit()

    # ========================================================
    # REMINDER HISTORY
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS REMINDER_HISTORY (
            RACEID TEXT PRIMARY KEY,
            SENTAT TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    connection.commit()

    # ========================================================
    # SCRATCH HISTORY
    # ========================================================

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS SCRATCH_HISTORY (
            RUNNERID TEXT PRIMARY KEY,
            SENTAT TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    connection.commit()

    print(
        "RUNNERS table ready."
    )

    print(
        "RUNNER_PRICES table ready."
    )

    print(
        "ALERT_HISTORY table ready."
    )

    print(
        "REMINDER_HISTORY table ready."
    )

    print(
        "SCRATCH_HISTORY table ready."
    )


# ============================================================
# RUNNERS
# ============================================================

def save_runner(
    connection: sqlite3.Connection,
    runner: Runner
) -> None:
    """
    Insert or update a runner.

    INITIALPRICE remains the first observed price.

    CURRENTPRICE is updated on later checks.

    These fields currently represent the existing TAB
    monitoring architecture.

    Multi-bookmaker prices are stored separately in
    RUNNER_PRICES.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO RUNNERS (
            RUNNERID,
            MEETINGDATE,
            MEETINGNAME,
            VENUECODE,
            RACENUMBER,
            RACESTART,
            RUNNERNUMBER,
            RUNNERNAME,
            INITIALPRICE,
            CURRENTPRICE
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(RUNNERID) DO UPDATE SET
            MEETINGDATE = excluded.MEETINGDATE,
            MEETINGNAME = excluded.MEETINGNAME,
            VENUECODE = excluded.VENUECODE,
            RACENUMBER = excluded.RACENUMBER,
            RACESTART = excluded.RACESTART,
            RUNNERNUMBER = excluded.RUNNERNUMBER,
            RUNNERNAME = excluded.RUNNERNAME,
            CURRENTPRICE = excluded.CURRENTPRICE;
        """,
        (
            runner.runner_id,
            runner.meeting_date,
            runner.meeting_name,
            runner.venue_code,
            runner.race_number,
            runner.race_start,
            runner.runner_number,
            runner.runner_name,
            runner.initial_price,
            runner.current_price
        )
    )

    connection.commit()


def get_runner(
    connection: sqlite3.Connection,
    runner_id: str
) -> Runner | None:
    """
    Load one runner from SQLite.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            RUNNERID,
            MEETINGDATE,
            MEETINGNAME,
            VENUECODE,
            RACENUMBER,
            RACESTART,
            RUNNERNUMBER,
            RUNNERNAME,
            INITIALPRICE,
            CURRENTPRICE
        FROM RUNNERS
        WHERE RUNNERID = ?;
        """,
        (
            runner_id,
        )
    )

    row = cursor.fetchone()

    if row is None:
        return None

    return Runner(
        runner_id=row[0],
        meeting_date=row[1],
        meeting_name=row[2] or "",
        venue_code=row[3],
        race_number=row[4],
        race_start=row[5] or "",
        runner_number=row[6],
        runner_name=row[7],
        initial_price=row[8],
        current_price=row[9]
    )


# ============================================================
# RUNNER PRICES
# ============================================================

def save_runner_price(
    connection: sqlite3.Connection,
    runner_id: str,
    bookmaker: str,
    current_price: float | None,
    opening_price: float | None = None,
    place_price: float | None = None,
    source_runner_id: str | int | None = None,
    scratched: bool = False,
    market_mover: bool = False
) -> None:
    """
    Insert or update one bookmaker-specific runner price.
    """

    bookmaker_name = (
        bookmaker
        .strip()
        .upper()
    )

    if not bookmaker_name:
        raise ValueError(
            "Bookmaker cannot be blank."
        )

    source_runner_id_text = None

    if source_runner_id is not None:
        source_runner_id_text = str(
            source_runner_id
        )

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO RUNNER_PRICES (
            RUNNERID,
            BOOKMAKER,
            SOURCE_RUNNER_ID,
            OPENING_PRICE,
            INITIAL_OBSERVED_PRICE,
            CURRENT_PRICE,
            PLACE_PRICE,
            SCRATCHED,
            MARKET_MOVER,
            LAST_SEEN
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?,
            CURRENT_TIMESTAMP
        )

        ON CONFLICT(
            RUNNERID,
            BOOKMAKER
        )
        DO UPDATE SET

            SOURCE_RUNNER_ID =
                COALESCE(
                    excluded.SOURCE_RUNNER_ID,
                    RUNNER_PRICES.SOURCE_RUNNER_ID
                ),

            OPENING_PRICE =
                COALESCE(
                    excluded.OPENING_PRICE,
                    RUNNER_PRICES.OPENING_PRICE
                ),

            CURRENT_PRICE =
                excluded.CURRENT_PRICE,

            PLACE_PRICE =
                excluded.PLACE_PRICE,

            SCRATCHED =
                excluded.SCRATCHED,

            MARKET_MOVER =
                excluded.MARKET_MOVER,

            LAST_SEEN =
                CURRENT_TIMESTAMP;
        """,
        (
            runner_id,
            bookmaker_name,
            source_runner_id_text,
            opening_price,
            current_price,
            current_price,
            place_price,
            int(scratched),
            int(market_mover)
        )
    )

    connection.commit()


def get_runner_price(
    connection: sqlite3.Connection,
    runner_id: str,
    bookmaker: str
) -> dict | None:
    """
    Return one bookmaker-specific pricing row.
    """

    bookmaker_name = (
        bookmaker
        .strip()
        .upper()
    )

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            RUNNERID,
            BOOKMAKER,
            SOURCE_RUNNER_ID,
            OPENING_PRICE,
            INITIAL_OBSERVED_PRICE,
            CURRENT_PRICE,
            PLACE_PRICE,
            SCRATCHED,
            MARKET_MOVER,
            LAST_SEEN
        FROM RUNNER_PRICES

        WHERE
            RUNNERID = ?
            AND BOOKMAKER = ?;
        """,
        (
            runner_id,
            bookmaker_name
        )
    )

    row = cursor.fetchone()

    if row is None:
        return None

    return {
        "runner_id":
            row[0],

        "bookmaker":
            row[1],

        "source_runner_id":
            row[2],

        "opening_price":
            row[3],

        "initial_observed_price":
            row[4],

        "current_price":
            row[5],

        "place_price":
            row[6],

        "scratched":
            bool(row[7]),

        "market_mover":
            bool(row[8]),

        "last_seen":
            row[9]
    }


def get_runner_prices(
    connection: sqlite3.Connection,
    runner_id: str
) -> list[dict]:
    """
    Return all bookmaker pricing rows for one runner.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            RUNNERID,
            BOOKMAKER,
            SOURCE_RUNNER_ID,
            OPENING_PRICE,
            INITIAL_OBSERVED_PRICE,
            CURRENT_PRICE,
            PLACE_PRICE,
            SCRATCHED,
            MARKET_MOVER,
            LAST_SEEN
        FROM RUNNER_PRICES

        WHERE RUNNERID = ?

        ORDER BY BOOKMAKER;
        """,
        (
            runner_id,
        )
    )

    rows = cursor.fetchall()

    return [
        {
            "runner_id":
                row[0],

            "bookmaker":
                row[1],

            "source_runner_id":
                row[2],

            "opening_price":
                row[3],

            "initial_observed_price":
                row[4],

            "current_price":
                row[5],

            "place_price":
                row[6],

            "scratched":
                bool(row[7]),

            "market_mover":
                bool(row[8]),

            "last_seen":
                row[9]
        }
        for row in rows
    ]


# ============================================================
# ALERT HISTORY
# ============================================================

def has_alert_been_sent(
    connection: sqlite3.Connection,
    runner_id: str,
    alert_id: str
) -> bool:
    """
    Return True if this alert has already
    been sent for this runner.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT 1
        FROM ALERT_HISTORY
        WHERE RUNNERID = ?
        AND ALERTID = ?
        LIMIT 1;
        """,
        (
            runner_id,
            alert_id
        )
    )

    return (
        cursor.fetchone()
        is not None
    )


def mark_alert_as_sent(
    connection: sqlite3.Connection,
    runner_id: str,
    alert_id: str,
    alert_price: float
) -> None:
    """
    Record a successfully sent price alert.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO ALERT_HISTORY (
            RUNNERID,
            ALERTID,
            ALERTPRICE
        )
        VALUES (?, ?, ?);
        """,
        (
            runner_id,
            alert_id,
            alert_price
        )
    )

    connection.commit()


def get_alert_ids_for_runner(
    connection: sqlite3.Connection,
    runner_id: str
) -> list[str]:
    """
    Return every alert ID that has fired for a runner.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT ALERTID
        FROM ALERT_HISTORY
        WHERE RUNNERID = ?
        ORDER BY SENTAT, ALERTID;
        """,
        (
            runner_id,
        )
    )

    rows = cursor.fetchall()

    alert_ids = []

    for row in rows:

        alert_id = row[0]

        if not alert_id:
            continue

        if alert_id in alert_ids:
            continue

        alert_ids.append(
            alert_id
        )

    return alert_ids


def runner_has_any_alert(
    connection: sqlite3.Connection,
    runner_id: str
) -> bool:
    """
    Return True if this runner has triggered at least
    one price alert.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT 1
        FROM ALERT_HISTORY
        WHERE RUNNERID = ?
        LIMIT 1;
        """,
        (
            runner_id,
        )
    )

    return (
        cursor.fetchone()
        is not None
    )


def get_alerted_runners_for_race(
    connection: sqlite3.Connection,
    meeting_date: str,
    venue_code: str,
    race_number: int
) -> list[dict]:
    """
    Return every runner in this race that has triggered
    at least one alert.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            R.RUNNERID,
            R.MEETINGDATE,
            R.MEETINGNAME,
            R.VENUECODE,
            R.RACENUMBER,
            R.RACESTART,
            R.RUNNERNUMBER,
            R.RUNNERNAME,
            R.INITIALPRICE,
            R.CURRENTPRICE,
            A.ALERTID,
            A.ALERTPRICE
        FROM RUNNERS R

        INNER JOIN ALERT_HISTORY A
            ON A.RUNNERID = R.RUNNERID

        WHERE
            R.MEETINGDATE = ?
            AND R.VENUECODE = ?
            AND R.RACENUMBER = ?

        ORDER BY
            R.RUNNERNUMBER,
            A.SENTAT;
        """,
        (
            meeting_date,
            venue_code,
            race_number
        )
    )

    rows = cursor.fetchall()

    runners = {}

    for row in rows:

        runner_id = row[0]

        if runner_id not in runners:
            runners[
                runner_id
            ] = {
                "runner_id":
                    row[0],
                "meeting_date":
                    row[1],
                "meeting_name":
                    row[2] or "",
                "venue_code":
                    row[3],
                "race_number":
                    row[4],
                "race_start":
                    row[5] or "",
                "runner_number":
                    row[6],
                "runner_name":
                    row[7],
                "initial_price":
                    row[8],
                "current_price":
                    row[9],
                "alerts":
                    []
            }

        runners[
            runner_id
        ][
            "alerts"
        ].append(
            {
                "alert_id":
                    row[10],
                "alert_price":
                    row[11]
            }
        )

    return list(
        runners.values()
    )


# ============================================================
# WIN ALERT HISTORY
# ============================================================

def get_pending_win_alerts(
    connection: sqlite3.Connection
) -> list[dict]:
    """
    Return every winning alert row whose secondary
    Discord win notification has not yet been sent.

    One result is returned per RUNNERID + ALERTID.

    Therefore, if one runner triggered two separate alert
    categories before winning, two independent win
    notifications are returned.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            A.RUNNERID,
            A.ALERTID,
            A.ALERTPRICE,
            R.MEETINGDATE,
            R.MEETINGNAME,
            R.VENUECODE,
            R.RACENUMBER,
            R.RACESTART,
            R.RUNNERNUMBER,
            R.RUNNERNAME,
            R.INITIALPRICE,
            R.CURRENTPRICE
        FROM ALERT_HISTORY A

        INNER JOIN RUNNERS R
            ON R.RUNNERID = A.RUNNERID

        WHERE
            A.RESULTCHECKED = 1
            AND A.FINISHPOSITION = 1
            AND A.WINALERTSENT = 0

        ORDER BY
            A.SENTAT,
            A.RUNNERID,
            A.ALERTID;
        """
    )

    rows = cursor.fetchall()

    return [
        {
            "runner_id":
                row[0],

            "alert_id":
                row[1],

            "alert_price":
                row[2],

            "meeting_date":
                row[3],

            "meeting_name":
                row[4] or "",

            "venue_code":
                row[5],

            "race_number":
                row[6],

            "race_start":
                row[7] or "",

            "runner_number":
                row[8],

            "runner_name":
                row[9],

            "initial_price":
                row[10],

            "current_price":
                row[11],
        }
        for row in rows
    ]


def mark_win_alert_as_sent(
    connection: sqlite3.Connection,
    runner_id: str,
    alert_id: str
) -> None:
    """
    Mark one specific secondary winning-alert
    notification as successfully sent.

    This must only be called after Discord accepts the
    corresponding notification.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE ALERT_HISTORY
        SET WINALERTSENT = 1
        WHERE
            RUNNERID = ?
            AND ALERTID = ?;
        """,
        (
            runner_id,
            alert_id
        )
    )

    connection.commit()


# ============================================================
# SCRATCH HISTORY
# ============================================================

def has_scratch_alert_been_sent(
    connection: sqlite3.Connection,
    runner_id: str
) -> bool:
    """
    Return True if a scratched-runner notification has
    already been successfully sent for this runner.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT 1
        FROM SCRATCH_HISTORY
        WHERE RUNNERID = ?
        LIMIT 1;
        """,
        (
            runner_id,
        )
    )

    return (
        cursor.fetchone()
        is not None
    )


def mark_scratch_alert_as_sent(
    connection: sqlite3.Connection,
    runner_id: str
) -> None:
    """
    Record that the scratched-runner Discord notification
    was successfully sent.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO SCRATCH_HISTORY (
            RUNNERID
        )
        VALUES (?);
        """,
        (
            runner_id,
        )
    )

    connection.commit()


def mark_runner_as_scratched(
    connection: sqlite3.Connection,
    runner_id: str
) -> None:
    """
    Resolve all alerts for this runner as scratched.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE ALERT_HISTORY
        SET
            FINISHPOSITION = ?,
            RESULTCHECKED = 1
        WHERE RUNNERID = ?;
        """,
        (
            SCRATCHED_POSITION,
            runner_id
        )
    )

    connection.commit()


# ============================================================
# REMINDER HISTORY
# ============================================================

def has_race_reminder_been_sent(
    connection: sqlite3.Connection,
    race_id: str
) -> bool:
    """
    Return True if this race has already received
    its pre-race Discord reminder.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT 1
        FROM REMINDER_HISTORY
        WHERE RACEID = ?
        LIMIT 1;
        """,
        (
            race_id,
        )
    )

    return (
        cursor.fetchone()
        is not None
    )


def mark_race_reminder_as_sent(
    connection: sqlite3.Connection,
    race_id: str
) -> None:
    """
    Record that the race reminder was successfully sent.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO REMINDER_HISTORY (
            RACEID
        )
        VALUES (?);
        """,
        (
            race_id,
        )
    )

    connection.commit()


# ============================================================
# RESULT PROCESSING
# ============================================================

def save_finish_position(
    connection: sqlite3.Connection,
    runner_id: str,
    finish_position: int
) -> None:
    """
    Save finishing position against every alert
    generated by this runner.

    Known result codes:

        1
            Win

        2-98
            Exact placing

        99
            Did not Place

        100
            Scratched
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE ALERT_HISTORY
        SET
            FINISHPOSITION = ?,
            RESULTCHECKED = 1
        WHERE RUNNERID = ?;
        """,
        (
            finish_position,
            runner_id
        )
    )

    connection.commit()


def mark_result_checked(
    connection: sqlite3.Connection,
    runner_id: str
) -> None:
    """
    Mark an alerted runner's result as processed.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE ALERT_HISTORY
        SET RESULTCHECKED = 1
        WHERE RUNNERID = ?;
        """,
        (
            runner_id,
        )
    )

    connection.commit()


def get_unchecked_alert_runners(
    connection: sqlite3.Connection
) -> list[dict]:
    """
    Return alerted runners whose result has not
    yet been processed.

    A runner marked as scratched receives:

        RESULTCHECKED = 1

    and therefore no longer appears here.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT DISTINCT
            R.RUNNERID,
            R.MEETINGDATE,
            R.MEETINGNAME,
            R.VENUECODE,
            R.RACENUMBER,
            R.RACESTART,
            R.RUNNERNUMBER,
            R.RUNNERNAME
        FROM RUNNERS R

        INNER JOIN ALERT_HISTORY A
            ON A.RUNNERID = R.RUNNERID

        WHERE
            A.RESULTCHECKED = 0

        ORDER BY
            R.MEETINGDATE,
            R.VENUECODE,
            R.RACENUMBER,
            R.RUNNERNUMBER;
        """
    )

    rows = cursor.fetchall()

    return [
        {
            "runner_id":
                row[0],
            "meeting_date":
                row[1],
            "meeting_name":
                row[2],
            "venue_code":
                row[3],
            "race_number":
                row[4],
            "race_start":
                row[5],
            "runner_number":
                row[6],
            "runner_name":
                row[7]
        }
        for row in rows
    ]