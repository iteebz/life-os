import sqlite3


def up(conn: sqlite3.Connection) -> None:
    # habit_checks.habit_id had ON DELETE CASCADE, so a hard delete of a habit
    # silently wipes its check history. no hard-delete path exists today, but
    # the schema shouldn't leave that trap loaded. rebuild without cascade.
    conn.execute("""
        CREATE TABLE habit_checks_new (
            habit_id TEXT NOT NULL,
            check_date TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            PRIMARY KEY (habit_id, check_date),
            FOREIGN KEY (habit_id) REFERENCES habits(id),
            CHECK (DATE(check_date) IS NOT NULL),
            CHECK (DATETIME(completed_at) IS NOT NULL)
        )
    """)
    conn.execute("INSERT INTO habit_checks_new SELECT * FROM habit_checks")
    conn.execute("DROP TABLE habit_checks")
    conn.execute("ALTER TABLE habit_checks_new RENAME TO habit_checks")
    conn.execute("CREATE INDEX idx_checks_date ON habit_checks(check_date)")
