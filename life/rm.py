"""Unified `life rm` — dispatches across task, habit, observation, improvement.

Lives at root (above the layer DAG) so it can import freely from any package.
"""

from fncli import UsageError, cli

from life.core.errors import NotFoundError
from life.habit import delete_habit
from life.improvements import delete_improvement, get_improvements
from life.lib import ansi
from life.lib.ids import resolve_prefix
from life.resolve import resolve_item_any
from life.steward import delete_observation, get_observations
from life.task import delete_task


@cli("life", name="rm")
def rm(ref: list[str], hard: bool = False) -> None:
    """Delete item"""
    item_ref = " ".join(ref) if ref else ""
    if not item_ref:
        raise UsageError("Usage: life rm <item>")
    task, habit = resolve_item_any(item_ref)
    if task:
        delete_task(task.id, hard=hard)
        print(ansi.strikethrough(task.content))
        return
    if habit:
        delete_habit(habit.id)
        print(ansi.strikethrough(habit.content))
        return
    obs = resolve_prefix(item_ref, get_observations(limit=200))
    if obs:
        delete_observation(obs.id, hard=hard)
        print(ansi.strikethrough(obs.body[:80]))
        return
    imp = resolve_prefix(item_ref, get_improvements())
    if imp:
        delete_improvement(imp.id, hard=hard)
        print(ansi.strikethrough(imp.body[:80]))
        return
    raise NotFoundError(f"no item matching '{item_ref}'")
