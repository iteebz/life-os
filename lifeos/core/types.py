"""Core type definitions."""

from enum import Enum
from typing import Any, Literal, Protocol


class _Unset(Enum):
    UNSET = "UNSET"


UNSET: Literal[_Unset.UNSET] = _Unset.UNSET
Unset = Literal[_Unset.UNSET]


class Conn(Protocol):
    """Portable database connection."""

    def execute(self, sql: str, params: Any = (), /) -> Any: ...

    def __enter__(self) -> "Conn": ...

    def __exit__(self, *args: object) -> bool | None: ...
