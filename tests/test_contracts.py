"""Contracts: interface agreements between separate data sources that can silently drift.

Each test guards a boundary where two subsystems must stay in sync but nothing
enforces it at write time. Violations here are silent runtime failures.
"""

import os
import re
import tomllib
from pathlib import Path

LIFE_ROOT = Path(__file__).parent.parent / "life"
MIGRATIONS_DIR = LIFE_ROOT / "store" / "migrations"

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
