Entry: `life/cli.py`. Domain: `life/tasks.py`, `life/habits.py`, etc. Infrastructure: `life/lib/`. Output via `echo()`, errors via `exit_error()` — `life/lib/errors.py`.

Resolve refs at CLI boundary via `lib/resolve.py`. `resolve_task(ref)` / `resolve_item(ref)` — domain functions only receive IDs. Fuzzy match: UUID prefix → substring → fuzzy (0.8 cutoff). Fuzzy hits print `→ matched: <content>`.

## Structure

```
life/
  cli.py        — dispatch entry point
  add.py        — life add subcommands (t, h, o, p, l, a)
  dash.py       — dashboard, status, ls, momentum, stats, view
  tasks.py      — task CRUD, find_task*, schedule
  habits.py     — habit CRUD + check tracking
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

- `life add t "<name>" -t <tag>` — add task
- `life add h "<name>" -t <tag>` — add habit
- `life defer <task> --reason <why>` — defer, logs to task_mutations. Does not reschedule.
- `life schedule <HH:MM> <task>` — set time only
- `life now <task>` — due=today, time=now
- `life due <when> <task>` — set deadline
- `life ls [--tag <tag>] [--overdue]` — filtered task list

Outstanding debt: `~/life/brr/IMPROVEMENTS.md`
