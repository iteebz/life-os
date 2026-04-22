"""Single DB access layer. All domain code imports get_db from here.

Migration path: get_db() now delegates to store.connection.ensure().
New code should import ensure/transaction from life.store.connection directly.
"""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from life.store.connection import (
    close_all,
    ensure,
    set_test_db_path,
    transaction,
)


def configure(path: Path) -> None:
    """Set DB path. Called once at startup and in test fixtures."""
    set_test_db_path(path)


@contextmanager
def get_db() -> Generator:
    """Legacy interface. Wraps ensure() in a transaction for backward compat."""
    with transaction() as conn:
        yield conn
