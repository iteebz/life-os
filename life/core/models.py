import dataclasses
from datetime import date, datetime


@dataclasses.dataclass(frozen=True)
class Task:
    id: str
    content: str
    focus: bool
    scheduled_date: date | None
    created: datetime
    completed_at: datetime | None
    parent_id: str | None = None
    scheduled_time: str | None = None
    blocked_by: str | None = None
    is_deadline: bool = False
    description: str | None = None
    steward: bool = False
    source: str | None = None
    tags: list[str] = dataclasses.field(default_factory=list, hash=False)


@dataclasses.dataclass(frozen=True)
class Habit:
    id: str
    content: str
    created: datetime
    archived_at: datetime | None = None
    parent_id: str | None = None
    private: bool = False
    checks: list[datetime] = dataclasses.field(default_factory=list, hash=False)
    tags: list[str] = dataclasses.field(default_factory=list, hash=False)


@dataclasses.dataclass(frozen=True)
class Tag:
    tag: str
    task_id: str | None = None
    habit_id: str | None = None


@dataclasses.dataclass(frozen=True)
class TaskMutation:
    id: int
    task_id: str
    field: str
    old_value: str | None
    new_value: str | None
    mutated_at: datetime
    reason: str | None = None


@dataclasses.dataclass(frozen=True)
class Weekly:
    tasks_completed: int = 0
    tasks_total: int = 0
    habits_completed: int = 0
    habits_total: int = 0
