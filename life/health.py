import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from fncli import cli

from life import config
from life.db import get_db, load_migrations

__all__ = ["cli", "score"]

FTS_TABLES = ("tasks_fts", "habits_fts", "tags_fts")
MIGRATIONS_TABLE = "_migrations"


def _core_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return sorted(name for (name,) in rows if "_fts" not in name and name != MIGRATIONS_TABLE)


def _check_fk_violations(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    violations: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        violations[(row[0], row[2])] += 1
    return {f"{t}→{p}": n for (t, p), n in violations.items()}


def _check_fts_integrity(conn: sqlite3.Connection) -> list[str]:
    corrupted = []
    for table in FTS_TABLES:
        try:
            conn.execute(f"SELECT * FROM {table} LIMIT 1")  # noqa: S608
        except sqlite3.DatabaseError:
            corrupted.append(table)
    return corrupted


def _expected_schema(migrations_path: Path) -> dict[str, set[str]] | None:
    mem = sqlite3.connect(":memory:")
    try:
        for _name, migration in load_migrations():
            if callable(migration):
                migration(mem)
            else:
                mem.executescript(migration)
        rows = mem.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        schema: dict[str, set[str]] = {}
        for (table,) in rows:
            if "_fts" in table or table == MIGRATIONS_TABLE:
                continue
            cols = mem.execute(f"PRAGMA table_info('{table}')").fetchall()
            schema[table] = {col[1] for col in cols}
        return schema
    except Exception:
        return None
    finally:
        mem.close()


def _check_schema_drift(conn: sqlite3.Connection) -> list[str]:
    expected = _expected_schema(Path(__file__).parent / "migrations")
    if expected is None:
        return ["could not build expected schema"]

    drift: list[str] = []
    live_rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    live_tables: dict[str, set[str]] = {}
    for (table,) in live_rows:
        if "_fts" in table or table == MIGRATIONS_TABLE:
            continue
        cols = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
        live_tables[table] = {col[1] for col in cols}

    for table, expected_cols in expected.items():
        if table not in live_tables:
            drift.append(f"missing table: {table}")
            continue
        drift.extend(f"{table}.{col}: missing column" for col in expected_cols - live_tables[table])

    drift.extend(f"extra table: {table}" for table in live_tables if table not in expected)

    return drift


def score() -> dict[str, Any]:
    if not config.DB_PATH.exists():
        return {"ok": False, "detail": "db not initialized", "issues": []}

    issues: list[str] = []
    fk_violations: dict[str, int] = {}
    schema_drift: list[str] = []
    fts_corrupted: list[str] = []
    table_counts: dict[str, int] = {}

    try:
        with get_db() as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                issues.append(f"integrity: {result[0] if result else 'unknown'}")

            fk_violations = _check_fk_violations(conn)
            if fk_violations:
                issues.append(f"FK violations: {len(fk_violations)} relation(s)")

            schema_drift = _check_schema_drift(conn)
            if schema_drift:
                issues.append(f"schema drift: {len(schema_drift)} issue(s)")

            fts_corrupted = _check_fts_integrity(conn)
            if fts_corrupted:
                issues.append(f"FTS corrupted: {', '.join(fts_corrupted)}")

            for table in _core_tables(conn):
                table_counts[table] = conn.execute(
                    f'SELECT COUNT(*) FROM "{table}"'  # noqa: S608
                ).fetchone()[0]

    except Exception as e:
        return {"ok": False, "detail": f"db error: {e}", "issues": [str(e)]}

    ok = not issues
    detail = "db healthy" if ok else "; ".join(issues)
    return {
        "ok": ok,
        "detail": detail,
        "issues": issues,
        "fk_violations": fk_violations,
        "schema_drift": schema_drift,
        "fts_corrupted": fts_corrupted,
        "table_counts": table_counts,
    }


def _render() -> None:
    result = score()
    status = "✓" if result["ok"] else "✗"
    print(f"db: {status} {result['detail']}")

    if result.get("table_counts"):
        total = sum(result["table_counts"].values())
        print(f"rows: {total} across {len(result['table_counts'])} tables")
        for table, count in sorted(result["table_counts"].items(), key=lambda x: -x[1]):
            print(f"  {table}: {count}")

    if result.get("fk_violations"):
        print("\nFK violations:")
        for rel, count in result["fk_violations"].items():
            print(f"  {rel}: {count}")

    if result.get("schema_drift"):
        print("\nSchema drift:")
        for item in result["schema_drift"]:
            print(f"  {item}")

    if not result["ok"]:
        raise SystemExit(1)


@cli("life", name="health")
def health_cmd() -> None:
    """Check database integrity"""
    _render()


if __name__ == "__main__":
    _render()
