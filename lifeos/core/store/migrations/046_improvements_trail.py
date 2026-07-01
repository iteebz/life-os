import sqlite3


def up(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE improvements RENAME COLUMN initiative TO trail")
