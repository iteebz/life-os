from fncli import cli

from .db import get_db


def add_learning(body: str, tags: str | None = None) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO learnings (body, tags) VALUES (?, ?)",
            (body, tags),
        )
        return cursor.lastrowid or 0


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


def _log_learning(body: str, tags: str | None = None) -> None:
    add_learning(body, tags)
    suffix = f" [{tags}]" if tags else ""
    print(f"◆ {body}{suffix}")


def _log_achievement(name: str, tags: str | None = None) -> None:
    from .achievements import add_achievement as _add

    _add(name, tags)
    print(f"★ {name}")


@cli("life add", name="t", flags={"tag": ["-t", "--tag"]})
def add_task_cmd(
    content: list[str], tag: list[str] | None = None, due: str | None = None, focus: bool = False
):
    """Add a task"""
    _log_task(content, tag=tag, due=due, focus=focus)


@cli("life add", name="o", flags={"tag": ["-t", "--tag"]})
def add_observation_sub(body: str, tag: str | None = None):
    """Log an observation"""
    _log_observation(body, tag)


@cli("life add", name="p", flags={"tag": ["-t", "--tag"]})
def add_pattern_sub(body: str, tag: str | None = None):
    """Log a pattern"""
    _log_pattern(body, tag)


@cli("life add", name="l", flags={"tags": ["-t", "--tags"]})
def add_learning_sub(body: str, tags: str | None = None):
    """Log a steward learning"""
    _log_learning(body, tags)


@cli("life add", name="a", flags={"tags": ["-t", "--tags"]})
def add_achievement_sub(name: str, tags: str | None = None):
    """Log an achievement"""
    _log_achievement(name, tags)


@cli("life log", name="a", flags={"tags": ["-t", "--tags"]})
def add_achievement(name: str, tags: str | None = None):
    """Log an achievement"""
    _log_achievement(name, tags)


@cli("life log", name="o", flags={"tag": ["-t", "--tag"]})
def add_observation(body: str, tag: str | None = None):
    """Log an observation"""
    _log_observation(body, tag)


@cli("life log", name="p", flags={"tag": ["-t", "--tag"]})
def add_pattern(body: str, tag: str | None = None):
    """Log a pattern"""
    _log_pattern(body, tag)


@cli("life log", name="l", flags={"tags": ["-t", "--tags"]})
def add_learning_cmd(body: str, tags: str | None = None):
    """Log a steward learning"""
    _log_learning(body, tags)
