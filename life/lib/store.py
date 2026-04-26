"""Single DB access layer. All domain code imports get_db from here.

Migration path: get_db() now delegates to store.connection.ensure().
New code should import ensure/transaction from life.store.connection directly.
"""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from life.store.connection import (
    set_test_db_path,
    transaction,
)


def configure(path: Path) -> None:
    """Set DB path. Called once at startup and in test fixtures."""
    set_test_db_path(path)


@contextmanager
def get_db() -> Generator[Any, None, None]:
    """Legacy interface. Wraps ensure() in a transaction for backward compat."""
    with transaction() as conn:
        yield conn
