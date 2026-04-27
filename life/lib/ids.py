from collections.abc import Sequence
from typing import Protocol


class _HasId(Protocol):
    @property
    def id(self) -> str: ...


def short(prefix: str, full_id: str) -> str:
    """Display helper: short('t', 'a9b3c2d1-...') → 't/a9b3c2d1'"""
    return f"{prefix}/{full_id[:8]}"


def parse_ref(ref: str) -> tuple[str | None, str]:
    """Parse a prefixed reference: 't/a9b3' → ('t', 'a9b3'), 'a9b3' → (None, 'a9b3')"""
    if "/" in ref:
        prefix, fragment = ref.split("/", 1)
        return prefix, fragment
    return None, ref


def resolve_prefix[T: _HasId](prefix: str, pool: Sequence[T]) -> T | None:
    """Resolve any item by UUID prefix. Works on any sequence with .id attribute."""
    _, fragment = parse_ref(prefix)
    p = fragment.lower()
    matches = [item for item in pool if item.id.startswith(p)]
    return matches[0] if matches else None
