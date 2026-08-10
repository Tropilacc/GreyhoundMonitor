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
    Create and upgrade the database tables.

    RUNNERS:
        Stores runner details, scheduled race start,
        and price information.

    ALERT_HISTORY:
        Stores alert events, trigger prices,
        finishing positions, and result-check status.

    Existing databases are upgraded automatically.
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

    # Upgrade older RUNNERS tables without deleting data.

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

    # Upgrade older ALERT_HISTORY tables.

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

    print("RUNNERS table ready.")
    print("ALERT_HISTORY table ready.")


def save_runner(
    connection: sqlite3.Connection,
    runner: Runner
) -> None:
    """
    Insert or update a runner.

    When first seen:
        INITIALPRICE = first observed price.

    On subsequent checks:
        INITIALPRICE remains unchanged.
        CURRENTPRICE is updated.
        Race/runner metadata is refreshed.
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
    Load one runner from the database.
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
    Check whether this specific alert has already
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
    Record a successfully sent alert.

    ALERTPRICE stores the exact price observed
    when the alert triggered.
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
    Mark the runner's alert result as processed.

    FINISHPOSITION remains NULL when the runner
    was not in the published placing block.
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
    Return alerted runners whose race result
    has not yet been processed.

    DISTINCT prevents runners that triggered
    multiple alert types from appearing more than once.
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