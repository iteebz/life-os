# life-os

personal life assistant. single agent (steward), not a swarm.

**new machine?** → [`docs/setup.md`](docs/setup.md)  
**collaborating?** → [`JANICE.md`](JANICE.md)

---

Live structure and conventions: see [`CLAUDE.md`](CLAUDE.md).

## Key primitives

- `life task "<name>" -t <tag>` — add task (no args = list)
- `life habit "<name>" -t <tag>` — add habit (no args = list)
- `life achieve "<name>"` — log achievement (no args = list)
- `life defer <task> --reason <why>` — defer, logs to task_mutations. Does not reschedule.
- `life schedule <HH:MM> <task>` — set time only
- `life now <task>` — due=today, time=now
- `life due <when> <task>` — set deadline
- `life ls [--tag <tag>] [--overdue]` — filtered task list
