# life-os

steward's own tooling. python CLI + daemon + hooks.

## before acting

read `docs/` first. `docs/arch.md` is the map.

docs/ is architectural design rationale — why things are shaped this way. not implementation
details. no function names, line numbers, specific values, or anything that rots when code
changes. if you can read it from the code, it doesn't belong in docs/. keep docs/ updated
when architecture changes.

## structure

```
life/           python package
  cli.py        fncli entry point
  daemon/       launchd daemon, claude spawning
  steward/      agent logic: wake, auto, chat, close
  store/        sqlite persistence
  core/         errors, models, types
  comms/        email, telegram, contacts
  hook.py       PreToolUse context injection
  lib/          shared utilities
  task/         task domain
docs/           architecture and design rationale
scripts/        launchd plist
tests/          unit + integration
```

## commands

- `life` — dashboard
- `life steward wake` — load context for spawn
- `life daemon run` — start persistent daemon
- `life hook tool` — hook entry point (stdin JSON)

## conventions

- fncli: function signature IS the CLI. `@cli("namespace")` decorator.
- store: sqlite in `~/.life/life.db`. backup before risk.
- config: yaml in `~/.life/config.yaml`. singleton via `Config()`.
- commits: `type(scope): verb object`. steward identity.
