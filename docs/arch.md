# life-os architecture

personal life assistant for neurodivergent humans. single agent (steward), not a swarm.
research lab for ~/space RSI thesis. productization possible, not the focus.

## topology

```
life        human CLI (python, fncli autodiscovery)
steward     agent surface (subcommand namespace, same binary)
daemon      persistent process, launchd KeepAlive, spawns claude
~/.life/    runtime: life.db, config.yaml, daemon.log
~/life/     workspace root. LIFE.md is physics. steward/ is knowledge.
```

single agent, three surfaces: chat (claude code interactive), auto (daemon), tg (telegram async).
same identity, same memory, different density.

## structural mirror: spacebrr

life-os replicates spacebrr's proven patterns at smaller scale.

| pattern | spacebrr | life-os | notes |
|---------|----------|---------|-------|
| CLI framework | fncli autodiscovery | fncli autodiscovery | identical |
| human/agent surfaces | brr / space | life / steward | same binary, namespace split |
| hook injection | space hook tool (PreToolUse) | life-hook tool (PreToolUse) | same _HOOK_SETTINGS shape |
| daemon | launchd KeepAlive, spawns claude | launchd KeepAlive, spawns claude | identical plist pattern |
| wake context | fetch_wake_context → prompt | fetch_wake_context → prompt | same subprocess injection |
| human model | brr/memory/human.md | steward/human.md | same semantics |
| agent memory | brr/memory/{agent}.md | steward/memory.md | same: overwrite-only, self-model |
| store | store/{sqlite,connection,query} | store/{sqlite,connection,query} | same triple |
| core types | core/{errors,models,types} | core/{errors,models,types} | same |
| runtime dir | ~/.space/ | ~/.life/ | same |
| config | SPACE.md (workspace physics) | LIFE.md (workspace physics) | same role |

## gaps to close

### wake tiers (steal from spacebrr)
life's wake is flat — one function dumps everything. spacebrr has ordered tiers
(SYSTEM→SPACE→WORLD→SELF→DO) with truncation from the bottom. when context is long,
identity survives and instructions get trimmed. steward needs this.

### memory cap (steal from spacebrr)
spacebrr enforces 2kb on agent memory files. forces curation, prevents bloat.
steward/memory.md has no size discipline. will degrade over time.

### hook watermarking (mostly done)
hook.py has watermark-based throttling wired for all five signals (inbox, messages,
habits, mood, tasks). remaining gap: no tool-name routing (all signals fire on every
tool call) and no per-signal error isolation. see `docs/hooks.md`.

## what life-os does NOT need

- ledger (no multi-agent coordination)
- game/fitness (no ranking, no progression mechanics)
- cloud API (no relay, steward is local-only)
- fragments compiler (single identity, no constitutional assembly)
- vault (no multi-agent secret isolation — steward IS the trusted process)
- spawn proxy (no rust binary boundary — python in-process auth)

## package map

| package | what it owns |
|---------|-------------|
| cli.py | fncli entry point, dashboard fallback |
| config.py | ~/.life/ paths, yaml config singleton |
| core/ | errors, models, types |
| daemon/ | launchd daemon: run, spawn, session, morning/nightly, inbound. see `docs/daemon.md` |
| steward/ | agent logic: auto, chat, wake, improve, inbox, log, close |
| store/ | sqlite persistence: connection, query |
| hook.py | PreToolUse context injection. see `docs/hooks.md` |
| comms/ | email, telegram, contacts, messaging |
| task/ | task domain |
| lib/ | ansi, clock, dates, format, fuzzy, ids, parsing, providers, resolve |
| accounts, contacts, dates, health, mood, habit, nudge | domain modules |
| feedback, improvements, momentum | self-improvement loop |
| db.py, schema.sql, migrations/ | schema and migration |
