import fncli
from fncli import cli


def _log_task(
    content: list[str], tag: list[str] | None = None, due: str | None = None, focus: bool = False
) -> None:
    from .items import add as _add

    _add(content, tag=tag, due=due, focus=focus)


def _log_observation(body: str, tag: str | None = None) -> None:
    from .steward import add_observation as _add

    _add(body, tag=tag)
    suffix = f" #{tag}" if tag else ""
    print(f"→ {body}{suffix}")


def _log_pattern(body: str, tag: str | None = None) -> None:
    from .patterns import add_pattern as _add

    _add(body, tag=tag)
    suffix = f" #{tag}" if tag else ""
    print(f"~ {body}{suffix}")


def _log_achievement(name: str, tags: str | None = None) -> None:
    from .achievements import add_achievement as _add

    _add(name, tags)
    print(f"★ {name}")


@cli("life add", name="h", flags={"tag": ["-t", "--tag"]})
def add_habit_cmd(content: list[str], tag: list[str] | None = None):
    """Add a habit"""
    from .habits import add_habit as _add

    name = " ".join(content)
    _add(name, tags=tag)
    suffix = " " + " ".join(f"#{t}" for t in tag) if tag else ""
    print(f"→ {name}{suffix}")


@cli("life add", name="t", flags={"tag": ["-t", "--tag"], "schedule": ["-s", "--schedule"]})
def add_task_cmd(
    content: list[str],
    tag: list[str] | None = None,
    due: str | None = None,
    focus: bool = False,
    schedule: str | None = None,
):
    """Add a task. Use -s HH:MM to schedule at a time today."""
    _log_task(content, tag=tag, due=due or schedule, focus=focus)


@cli("life add", name="o", flags={"tag": ["-t", "--tag"]})
def add_observation_sub(body: str, tag: str | None = None):
    """Log an observation"""
    _log_observation(body, tag)


@cli("life add", name="p", flags={"tag": ["-t", "--tag"]})
def add_pattern_sub(body: str, tag: str | None = None):
    """Log a pattern"""
    _log_pattern(body, tag)


@cli("life add", name="a", flags={"tags": ["-t", "--tags"]})
def add_achievement_sub(name: str, tags: str | None = None):
    """Log an achievement"""
    _log_achievement(name, tags)


fncli.alias_namespace("life add", "life log")
