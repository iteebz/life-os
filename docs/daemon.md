# daemon

persistent process. launchd KeepAlive. spawns claude for steward sessions.

## topology

```
launchd (com.life.daemon)
  → life daemon run
    → telegram thread     polls telegram, spawns claude per message
    → morning thread      8am brief + 8pm nightly (if tyson active)
    → signal thread       polls signal, spawns claude per message
    → auto thread         periodic autonomous steward (opt-in, --auto-every)
```

all threads share a `stop` event (shutdown) and `claimed_chat` mutex (one telegram session at a time).

## spawn path

`daemon/spawn.py` — single spawning function for all daemon threads.

1. resolve claude binary (PATH → nvm fallback)
2. `life steward wake` → capture stdout as context
3. `claude --print --no-session-persistence --dangerously-skip-permissions`
4. inject hook settings via `--settings` JSON (PreToolUse → `life-hook tool`)
5. prompt on stdin, response on stdout
6. truncate to 4000 chars

env built by `lib/env.py:build_base_env(mode)` — sets STEWARD_MODE for hook/wake to detect surface.

## threads

**telegram** — main interaction surface. polls every 10s. rate limited (12 spawns/hour). slash commands (`/status`, etc) handled inline without spawning. quiet hours respected. each message either spawns a one-shot claude or enters a session (multi-turn with history).

**morning** — fires once at 8am (unconditional) and 8pm (conditional on tyson activity). builds opener from wake context + memory + nudges. runs a full telegram session with reply polling.

**signal** — polls signal accounts. same inbound handling as telegram. less developed.

**auto** — opt-in (`--auto-every N`). runs `steward/auto.py:run_autonomous()` on interval. currently disabled by default (auto_every=0).

## session model

`daemon/session.py` — shared session loop for all telegram interactions.

1. send opener (claude response to initial prompt)
2. poll telegram for replies (5s interval)
3. build reply prompt with conversation history (trimmed to 8000 chars)
4. spawn claude for each reply
5. timeout after 55 min
6. log transcript to `steward/sessions/`

history survives daemon restarts via DB (messages table).

## properties

**always running.** launchd KeepAlive=true. same as spacebrr.

**stateful via threads.** unlike spacebrr daemon (stateless, all state in API), life daemon holds thread-local state: session history, spawn rate counters, claimed_chat mutex. state resets on restart — acceptable because sessions are short-lived and history reloads from DB.

**single pathway.** one daemon, all surfaces. no mode gates in core behavior.

**lock file.** `~/.life/daemon.lock` with PID. checked before manual triggers (nightly.py:trigger_now) to prevent poll fights.

## known issues

- `nightly.py` duplicates logic already in `morning.py`. morning_thread handles both 8am and 8pm. nightly_thread is never started in run(). nightly.py is dead code except for `trigger_now()` manual trigger.
- no backoff on spawn failures. spacebrr daemon delegates backoff to API; life daemon has no equivalent — a broken claude binary loops errors every poll interval.
- no health signal. spacebrr exposes daemon.status for `brr watch`. life daemon logs to file only — no way for steward wake to know if daemon is healthy.
