import sqlite3
from pathlib import Path


def connect_database():

    # Build the path to the database
    database_path = Path("data") / "greyhound.db"

    print(f"Database: {database_path}")

    # Connect to SQLite
    connection = sqlite3.connect(database_path)

    print("Connected successfully.")

    return connection