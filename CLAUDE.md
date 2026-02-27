Entry: `life/cli.py`. Domain: `life/tasks.py`, `life/habits.py`, etc. Infrastructure: `life/lib/`. Output via `echo()`, errors via `exit_error()` — `life/lib/errors.py`.

Resolve refs at CLI boundary via `lib/resolve.py`. `resolve_task(ref)` / `resolve_item(ref)` — domain functions only receive IDs. Fuzzy match: UUID prefix → substring → fuzzy (0.8 cutoff). Fuzzy hits print `→ matched: <content>`.

## Structure

```
life/
  cli.py        — dispatch entry point
  dash.py       — dashboard, status, ls, momentum, stats, view
  task.py       — task CRUD + `life task` command
  habit.py      — habit CRUD + `life habit` command
  items.py      — done, rm, rename, focus (unified task/habit)
  models.py     — Task, Habit, TaskMutation (no deps)
  db.py         — SQLite + migrations
  lib/          — shared infrastructure (no domain imports except resolve.py)
    errors.py   — echo(), exit_error()
    fuzzy.py    — UUID prefix → substring → fuzzy
    resolve.py  — CLI boundary resolver
    render.py   — dashboard + habit matrix
    format.py   — format_task(), format_habit()
    clock.py    — today(), now()
```

## Layer rule

Higher imports lower, never upward. `lib/` is clean except `resolve.py` (intentional boundary layer).

## Key primitives

- `life task "<name>" -t <tag>` — add task (no args = list)
- `life habit "<name>" -t <tag>` — add habit (no args = list)
- `life achieve "<name>"` — log achievement (no args = list)
- `life defer <task> --reason <why>` — defer, logs to task_mutations. Does not reschedule.
- `life schedule <HH:MM> <task>` — set time only
- `life now <task>` — due=today, time=now
- `life due <when> <task>` — set deadline
- `life ls [--tag <tag>] [--overdue]` — filtered task list

Outstanding debt: `~/life/brr/IMPROVEMENTS.md`

## Commits

- Same logical change → amend, not new commit
- Visual/aesthetic changes shown for approval → don't commit until confirmed
- Exploratory work that may be reverted → hold the commit until direction is clear
- Revert+recommit pairs are always avoidable: verify before committing, not after
