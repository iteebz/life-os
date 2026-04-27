# daemon

persistent process. launchd KeepAlive. spawns claude for steward sessions.

## topology

```
launchd
  → supervisor (lock file, crash restart with backoff)
    → daemon process
      → telegram thread     inbound messages → claude spawns
      → morning thread      scheduled briefs (morning + nightly)
      → signal thread       signal messenger inbound
      → auto thread         periodic autonomous steward (opt-in)
```

## design decisions

**one daemon, many surfaces.** telegram, signal, morning briefs, and autonomous runs all live
in the same process. they share a shutdown signal and a chat mutex (one telegram session at a
time). this avoids the coordination problem of multiple processes competing for the same
messaging channels.

**supervisor wraps the daemon.** the supervisor owns the lock file and restarts the child on
crash with exponential backoff. it imports zero application code — immune to bad edits. the
daemon itself is the application layer.

**stateful via threads, not API.** unlike spacebrr (stateless daemon, all state in cloud API),
life daemon holds session history and rate counters in-thread. acceptable tradeoff: single
machine, single agent, sessions are short-lived. conversation history reloads from DB on restart.

**claimed_chat mutex.** only one thread can own the telegram poll loop at a time. morning brief
claims the chat, telegram thread backs off. prevents interleaved messages from competing sessions.

**quiet hours.** all threads respect quiet hours — no spawns, no messages during sleep window.
messages received during quiet hours queue to inbox for next session.

## spawn model

all daemon threads use the same spawn function: capture wake context, invoke claude as a
subprocess with hook settings injected, return response as string. the spawn is stateless —
no persistent process, no session ID. each message gets a fresh claude invocation.

sessions (multi-turn) are built on top: the daemon polls for replies and spawns claude
repeatedly with accumulated history until timeout.

## gaps

- **no spawn backoff.** a broken claude binary error-loops every poll interval. spacebrr
  delegates backoff to its API; life daemon needs its own.
- **no health signal.** daemon health is only visible in the log file. steward wake can't
  tell if the daemon is alive or healthy. worth adding a heartbeat file or status endpoint.
