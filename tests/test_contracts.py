"""Contracts: interface agreements between separate data sources that can silently drift.

Each test guards a boundary where two subsystems must stay in sync but nothing
enforces it at write time. Violations here are silent runtime failures.
"""

import ast
import os
import re
import sqlite3
import tomllib
from pathlib import Path

LIFE_ROOT = Path(__file__).parent.parent / "life"
LIFEOS_ROOT = Path(__file__).parent.parent / "lifeos"
CLI_ROOTS = [LIFE_ROOT, LIFEOS_ROOT]
MIGRATIONS_DIR = LIFE_ROOT / "store" / "migrations"
SCHEMA_PATH = LIFE_ROOT / "schema.sql"

_TAGS_PATH = Path(os.environ.get("LIFE_DIR", str(Path.home() / ".life"))) / "tags.toml"

_DESTRUCTIVE_RE = re.compile(r"\b(DROP\s+TABLE|ALTER\s+TABLE\s+\w+\s+RENAME)\b", re.IGNORECASE)
_SELECT_STAR_RE = re.compile(r"INSERT\s+INTO\s+\w+\s+SELECT\s+\*\s+FROM", re.IGNORECASE)


# ── migrations ────────────────────────────────────────────────────────────────


def _migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("[0-9]*.sql"))


def test_migration_sequence_has_no_gaps():
    """SQL migration files must be sequentially numbered without gaps.

    A gap means a migration was deleted post-apply — old DBs silently skip
    the replacement. Name them, never remove them.
    """
    files = _migration_files()
    numbers = []
    for f in files:
        m = re.match(r"^(\d+)_", f.name)
        assert m, f"migration filename doesn't start with NNN_: {f.name}"
        numbers.append(int(m.group(1)))

    if not numbers:
        return

    start = numbers[0]
    expected = list(range(start, start + len(numbers)))
    gaps = sorted(set(expected) - set(numbers))
    dups = [n for n in numbers if numbers.count(n) > 1]

    assert not gaps, (
        f"Migration sequence has gaps at: {gaps}\nNever delete a migration — rename it to a tombstone if needed."
    )
    assert not dups, (
        f"Duplicate migration numbers: {sorted(set(dups))}\nEach migration must have a unique sequence number."
    )


_DESTRUCTIVE_DDL_KNOWN = {
    "021_events_foundation.sql",
    "027_drop_spawns.sql",
    "028_rename_session_columns.sql",
    "029_events_fk_to_sessions.sql",
}


def test_migrations_no_destructive_ddl():
    """Migration files must not contain DROP TABLE or ALTER TABLE ... RENAME.

    These destroy data irreversibly. Use a new migration to copy+rename instead.
    Already enforced at runtime in migrations.py — static check catches it before apply.
    Known historical violations are grandfathered. No new ones.
    """
    violations = []
    for path in _migration_files():
        if path.name in _DESTRUCTIVE_DDL_KNOWN:
            continue
        sql = path.read_text()
        if _DESTRUCTIVE_RE.search(sql):
            violations.append(f"  {path.name}: contains DROP TABLE or RENAME TABLE")
    assert not violations, (
        "Destructive DDL in migration files:\n"
        + "\n".join(violations)
        + "\n\nUse CREATE TABLE ... AS SELECT + INSERT to migrate, never DROP."
    )


def test_migrations_no_select_star_insert():
    """INSERT INTO ... SELECT * FROM is forbidden in migrations.

    If the source table gains a column, the INSERT silently breaks on old schemas.
    Name every column explicitly.
    """
    violations = []
    for path in _migration_files():
        sql = path.read_text()
        for i, line in enumerate(sql.splitlines(), 1):
            if _SELECT_STAR_RE.search(line):
                violations.append(f"  {path.name}:{i}: {line.strip()}")
    assert not violations, (
        "INSERT ... SELECT * in migrations:\n" + "\n".join(violations) + "\n\nName every column explicitly."
    )


# ── tags.toml ─────────────────────────────────────────────────────────────────


def _load_tags() -> dict:
    if not _TAGS_PATH.exists():
        return {}
    with _TAGS_PATH.open("rb") as f:
        return tomllib.load(f)


def test_tags_groups_subset_of_valid():
    """Every tag in tags.toml [groups] must appear in the valid list.

    An unknown group tag is silently dropped from the dashboard backlog.
    Add it to valid[] or remove it from [groups].
    """
    data = _load_tags()
    valid = data.get("valid")
    if not isinstance(valid, list):
        return  # open tag set — no constraint to enforce
    valid_set = frozenset(str(t).lower() for t in valid)
    groups = data.get("groups")
    if not isinstance(groups, dict):
        return
    unknown = [k for k in groups if k.lower() not in valid_set]
    assert not unknown, (
        f"tags.toml [groups] references tags not in valid[]: {unknown}\nAdd them to valid[] or remove from [groups]."
    )


def test_tags_color_overrides_subset_of_valid():
    """Top-level string values in tags.toml (color overrides) must be in valid[].

    A color override for a removed tag is dead config that masks typos.
    """
    data = _load_tags()
    valid = data.get("valid")
    if not isinstance(valid, list):
        return
    valid_set = frozenset(str(t).lower() for t in valid)
    overrides = [k for k, v in data.items() if isinstance(v, str) and k != "valid"]
    unknown = [k for k in overrides if k.lower() not in valid_set]
    assert not unknown, (
        f"tags.toml color overrides reference tags not in valid[]: {unknown}\n"
        "Remove the override or add the tag to valid[]."
    )


def test_tags_valid_list_has_no_duplicates():
    """tags.toml valid[] must not contain duplicate entries.

    Duplicates are silent no-ops but indicate copy-paste drift.
    """
    data = _load_tags()
    valid = data.get("valid")
    if not isinstance(valid, list):
        return
    tags = [str(t).lower() for t in valid]
    seen: set[str] = set()
    dups = [t for t in tags if t in seen or seen.add(t)]  # type: ignore[func-returns-value]
    assert not dups, f"Duplicate tags in tags.toml valid[]: {sorted(set(dups))}\nRemove the duplicates."


# ── schema integrity ─────────────────────────────────────────────────────────


_REQUIRED_TABLES = {
    "tasks",
    "habits",
    "habit_checks",
    "tags",
    "sessions",
    "observations",
    "moods",
    "improvements",
    "achievements",
    "contacts",
    "events",
    "notes",
}

# Columns whose removal/rename would silently corrupt soft-delete, completion,
# scheduling, or session-tracking semantics. Tyson-visible state lives here.
_REQUIRED_COLUMNS = {
    "tasks": {"id", "content", "completed_at", "deleted_at", "scheduled_date", "parent_id"},
    "habits": {"id", "content", "deleted_at", "archived_at", "cadence"},
    "habit_checks": {"habit_id", "check_date", "completed_at"},
    "tags": {"task_id", "habit_id", "tag"},
    "sessions": {"id"},
    "observations": {"id", "body", "deleted_at"},
    "events": {"id"},
}


def _fresh_schema_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


def test_schema_has_required_tables():
    """schema.sql must declare every table the app reads from at boot."""
    conn = _fresh_schema_conn()
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing = _REQUIRED_TABLES - have
    assert not missing, f"schema.sql missing required tables: {sorted(missing)}"


def test_schema_has_required_columns():
    """Critical columns must exist — renames silently break queries that filter on them."""
    conn = _fresh_schema_conn()
    violations = []
    for table, cols in _REQUIRED_COLUMNS.items():
        actual = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        missing = cols - actual
        if missing:
            violations.append(f"  {table}: missing {sorted(missing)}")
    assert not violations, "schema.sql is missing required columns:\n" + "\n".join(violations)


def test_schema_enables_foreign_keys():
    """schema.sql must enable foreign_keys — without it, ON DELETE CASCADE is a no-op."""
    sql = SCHEMA_PATH.read_text()
    assert re.search(r"PRAGMA\s+foreign_keys\s*=\s*ON", sql, re.IGNORECASE), (
        "schema.sql must declare PRAGMA foreign_keys = ON — cascades silently no-op without it."
    )


# ── hard-delete confinement ──────────────────────────────────────────────────


# Tables holding user-visible state that must only be soft-deleted.
# DELETE FROM <table> is only allowed in the listed file (the rm path).
_HARD_DELETE_ALLOWED = {
    "tasks": {"life/task/domain.py"},
    "habits": set(),  # habits never hard-delete; archive only
    "observations": {"life/rm.py", "life/note.py"},
}


def test_hard_delete_confined_to_rm_path():
    """`DELETE FROM <user_state_table>` must only appear in the soft/hard-delete module.

    A stray DELETE elsewhere bypasses the deleted_at convention and irrecoverably
    drops Tyson's data. Every new hard-delete site = explicit allowlist entry.
    """
    pattern = re.compile(r"DELETE\s+FROM\s+(\w+)", re.IGNORECASE)
    violations = []
    for path in sorted(LIFE_ROOT.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        rel = str(path.relative_to(LIFE_ROOT.parent))
        text = path.read_text()
        for match in pattern.finditer(text):
            table = match.group(1).lower()
            if table not in _HARD_DELETE_ALLOWED:
                continue
            if rel not in _HARD_DELETE_ALLOWED[table]:
                line = text[: match.start()].count("\n") + 1
                violations.append(f"  {rel}:{line}  DELETE FROM {table} (not allowed here)")
    assert not violations, (
        "Hard-delete on user-state tables outside the rm path:\n"
        + "\n".join(violations)
        + "\n\nUse UPDATE ... SET deleted_at = ... instead, or extend the allowlist."
    )


# ── CLI surface stability ────────────────────────────────────────────────────


# Verbs tyson types daily. Renaming or losing any of these breaks muscle memory
# and silently degrades the loop — `life done` is the closure ritual itself.
_CRITICAL_CLI = {
    "done",  # life done <ref>  — mark task complete
    "task",  # life task "..."  — create task
    "habit",  # life habit "..." — create/list habit
    "rm",  # life rm <ref>    — soft delete
    "show",  # life show <ref>  — inspect
    "set",  # life set ...     — edit
    "mood",  # life mood log    — energy state
    "observe",  # life observe ... — capture context
    "improve",  # life improve ... — steward backlog
    "sleep",  # life sleep "..." — close ritual
    "backup",  # life backup      — pre-risk safety
    "skill",  # life skill <name>— load skill
}


def _registered_cli_commands() -> set[str]:
    """Walk @cli(...) decorators in life/ and collect every command token reachable.

    Includes both the terminal command name (name= kwarg or function name) and
    each segment of the namespace after `life ` — so `@cli("life mood", name="log")`
    contributes both `mood` and `log`.
    """
    names: set[str] = set()
    paths = [p for root in CLI_ROOTS if root.exists() for p in sorted(root.rglob("*.py"))]
    for path in paths:
        if "__pycache__" in str(path):
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                func = dec.func
                func_name = (
                    func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else None)
                )
                if func_name != "cli":
                    continue
                if dec.args and isinstance(dec.args[0], ast.Constant):
                    ns = str(dec.args[0].value).split()
                    if ns and ns[0] == "life":
                        names.update(ns[1:])
                explicit = None
                for kw in dec.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                        explicit = kw.value.value
                names.add(explicit or node.name)
    return names


def test_critical_cli_commands_exist():
    """Every verb in Tyson's muscle memory must remain a registered command."""
    registered = _registered_cli_commands()
    missing = _CRITICAL_CLI - registered
    assert not missing, (
        f"Critical CLI commands missing or renamed: {sorted(missing)}\n"
        f"These are in Tyson's muscle memory — re-add the alias or restore the name."
    )
