import sqlite3
from pathlib import Path

from models import Runner


DATABASE_PATH = Path("data") / "greyhound.db"


def connect_database() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    print(f"Database: {DATABASE_PATH}")

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    print("Connected successfully.")

    return connection


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
        column[1].upper() == column_name.upper()
        for column in columns
    )


def create_tables(
    connection: sqlite3.Connection
) -> None:
    """
    Create and upgrade all tracker database tables.

    RUNNERS:
        Stores runner details, race metadata and prices.

    ALERT_HISTORY:
        Stores each price alert that fired.

    REMINDER_HISTORY:
        Stores one pre-race reminder per race.
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

    connection.commit()

    # ========================================================
    # REMINDER HISTORY
    #
    # One record per RACE, not per runner.
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

    print("RUNNERS table ready.")
    print("ALERT_HISTORY table ready.")
    print("REMINDER_HISTORY table ready.")


def save_runner(
    connection: sqlite3.Connection,
    runner: Runner
) -> None:
    """
    Insert or update a runner.

    INITIALPRICE remains the first observed price.
    CURRENTPRICE is updated on later checks.
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

    return cursor.fetchone() is not None


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


def get_alerted_runners_for_race(
    connection: sqlite3.Connection,
    meeting_date: str,
    venue_code: str,
    race_number: int
) -> list[dict]:
    """
    Return every runner in this race that has triggered
    at least one alert.

    Also returns the alert IDs and alert prices that
    were recorded for the runner.
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
            runners[runner_id] = {
                "runner_id": row[0],
                "meeting_date": row[1],
                "meeting_name": row[2] or "",
                "venue_code": row[3],
                "race_number": row[4],
                "race_start": row[5] or "",
                "runner_number": row[6],
                "runner_name": row[7],
                "initial_price": row[8],
                "current_price": row[9],
                "alerts": []
            }

        runners[runner_id]["alerts"].append(
            {
                "alert_id": row[10],
                "alert_price": row[11]
            }
        )

    return list(
        runners.values()
    )


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

    return cursor.fetchone() is not None


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


def save_finish_position(
    connection: sqlite3.Connection,
    runner_id: str,
    finish_position: int
) -> None:
    """
    Save finishing position against every alert
    generated by this runner.
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

        WHERE A.RESULTCHECKED = 0

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
            "runner_id": row[0],
            "meeting_date": row[1],
            "meeting_name": row[2],
            "venue_code": row[3],
            "race_number": row[4],
            "race_start": row[5],
            "runner_number": row[6],
            "runner_name": row[7]
        }
        for row in rows
    ]