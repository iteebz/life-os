"""Core type definitions."""

from enum import Enum
from typing import Literal


class _Unset(Enum):
    UNSET = "UNSET"


UNSET: Literal[_Unset.UNSET] = _Unset.UNSET
Unset = Literal[_Unset.UNSET]
