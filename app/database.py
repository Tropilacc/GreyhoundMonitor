import sqlite3
from pathlib import Path


def connect_database():

    database_path = Path("data") / "greyhound.db"

    print(f"Database: {database_path}")

    connection = sqlite3.connect(database_path)

    print("Connected successfully.")

    return connection


def create_tables(connection):

    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS RUNNERS (

            RUNNERID TEXT PRIMARY KEY,

            RUNNERNAME TEXT NOT NULL,

            INITIALPRICE REAL,

            CURRENTPRICE REAL,

            ALERTSENT INTEGER DEFAULT 0

        );
    """)

    connection.commit()

    print("RUNNERS table created.")