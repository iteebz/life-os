# sessions

one steward, many entry points, one session model.

## the primitive

a **session** is one resumable thread of steward execution. it has an identity
(claude_session_id), a lifecycle (active → idle → closed), and a source (who rang
the doorbell: cli, tg, daemon).

previously this was split across two tables: `sessions` (logged after close) and
`spawns` (live process tracking with mode=auto|chat). the split was accidental —
two representations of one thing tied by FK. unified into `sessions`.

## lifecycle

```
[new message / cli launch / daemon timer]
         ↓
    ┌─────────┐
    │  active  │ ← turn executing
    └────┬────┘
         ↓ turn completes
    ┌─────────┐
    │  idle    │ ← awaiting next message, resumable
    └────┬────┘
         ↓ sleep called (explicit or reaper at 55m)
    ┌─────────┐
    │  closed  │ ← terminal, summary written
    └─────────┘
```

- **active**: a turn is executing. claude subprocess is running.
- **idle**: session alive between turns. no process running (tg/daemon) or process
  waiting for input (cli). resumable via `claude --resume <session_id>`.
- **closed**: sleep was called. summary persisted. next message = fresh session.

active ↔ idle freely between turns. sleep is the only exit, one-way.
reply after sleep = fresh session, no exceptions.

## routing

when a message arrives (tg, daemon timer, etc):

1. is there a hookable session? (pid alive = cli window open) → write inbox, hook surfaces it
2. else: find resumable session (`state IN ('active','idle')`, ordered by last_active_at) → resume
3. else: spawn fresh session

"current steward" = most recently active session. if multiple sessions exist in
parallel (power-user: two cli windows), most recent wins for tg routing.

## source

`source` records who triggered the session: `cli`, `tg`, `daemon`. it's metadata
for telemetry and tone calibration, not a routing axis. no code branches on source
for lifecycle decisions.

wake prompt density varies by source (tg=brief, cli=full, daemon=focused) but
the session model is identical.

## sleep

three triggers, same terminal state:
1. steward decides conversation is done (close ritual, writes summary)
2. reaper auto-sleeps after 55m idle (marks closed, no summary — just closes)
3. manual `life sleep "..."`

## divergence from spacebrr

both systems have the same primitive: an agent execution thread. the difference
is lifecycle:

- **spacebrr**: stateless, one-shot. each spawn loads context fresh from cloud API.
  agent identity is durable across infrastructure, individual invocations are not.
  works because spacebrr agents are autonomous workers doing discrete tasks.
- **life-os**: resumable, multi-turn. sessions live in idle state between turns.
  identity == the session itself. `claude --resume` keeps conversation cached (~60m TTL).

why:
- steward is in dialogue with a human. 30 messages reloaded 30 times vs cached once.
- single agent, single machine. no multi-agent coordination to force stateless.
- continuity is the research thesis. deep persistent context → better stewardship.
- no auth boundary. spacebrr's stateless model is partly security. steward IS trusted.
