from collections.abc import Sequence
from difflib import get_close_matches
from typing import TypeVar

from life.core.errors import AmbiguousError
from life.models import Habit, Task

__all__ = ["find_in_pool", "find_in_pool_exact"]

FUZZY_MATCH_CUTOFF = 0.8

T = TypeVar("T", Task, Habit)


def _match_uuid_prefix[T: (Task, Habit)](ref: str, pool: Sequence[T]) -> T | None:
    ref_lower = ref.lower()
    matches = [item for item in pool if item.id[:8].startswith(ref_lower)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        exact = next((item for item in matches if item.id == ref), None)
        if exact:
            return exact

        sample = [item.id[:8] for item in matches[:3]]
        raise AmbiguousError(ref, count=len(matches), sample=sample)
    return None


def _match_substring[T: (Task, Habit)](ref: str, pool: Sequence[T]) -> T | None:
    ref_lower = ref.lower()
    exact = next((item for item in pool if item.content.lower() == ref_lower), None)
    if exact:
        return exact
    matches = [item for item in pool if ref_lower in item.content.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        sample = [item.content for item in matches[:3]]
        raise AmbiguousError(ref, count=len(matches), sample=sample)
    return None


def _match_fuzzy[T: (Task, Habit)](ref: str, pool: Sequence[T]) -> T | None:
    ref_lower = ref.lower()
    contents = [item.content for item in pool]
    matches = get_close_matches(
        ref_lower, [c.lower() for c in contents], n=1, cutoff=FUZZY_MATCH_CUTOFF
    )
    if matches:
        match_content = matches[0]
        for item in pool:
            if item.content.lower() == match_content:
                return item
    return None


def find_in_pool[T: (Task, Habit)](ref: str, pool: Sequence[T]) -> T | None:
    if not pool:
        return None
    return _match_uuid_prefix(ref, pool) or _match_substring(ref, pool) or _match_fuzzy(ref, pool)


def find_in_pool_exact[T: (Task, Habit)](ref: str, pool: Sequence[T]) -> T | None:
    if not pool:
        return None
    return _match_uuid_prefix(ref, pool) or _match_substring(ref, pool)
