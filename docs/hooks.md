# hooks

context injection into active steward sessions. steward sees ambient life signals without polling.

## architecture

```
claude spawns with --settings JSON
  → PreToolUse fires on any tool call
    → life-hook tool (reads tool-call JSON from stdin)
      → load per-session state (throttle watermarks)
      → run signal handlers (inbox, messages, habits, mood, tasks)
      → emit additionalContext JSON to stdout
```

one hook event (PreToolUse), empty matcher (catches all tools). same pattern as spacebrr.

## injection pathway

hook settings injected via `--settings` flag at spawn time in `daemon/spawn.py`. settings are JSON, not a file — no writes to `~/.claude/settings.json`. each spawn gets its own hook config.

```python
_HOOK_SETTINGS = {
    "hooks": {
        "PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "life-hook tool"}]}],
    },
}
```

interactive sessions (chat mode) get hooks via CLAUDE.md `.claude/settings.json` on the workspace, not via --settings. daemon spawns get them via the flag.

## state

per-session state file at `$TMPDIR/.life_hook_{session_id}`. keyed by CLAUDE_SESSION_ID → STEWARD_SESSION_ID → PID fallback. ephemeral — dies with session. stores watermark timestamps for throttling.

format: flat key=value, one per line. loaded/saved on every hook invocation. no locking (single-threaded per spawn).

## signals

five signals, each with independent throttle intervals:

| signal | what it injects | throttle | source |
|--------|----------------|----------|--------|
| inbox | queued messages from daemon inbound | every invocation | daemon/inbound.py pending file |
| messages | new telegram messages since last check | 10s | messages table, watermark on timestamp |
| habits | today's daily habit completion status | 60s | habit table |
| mood | latest mood score if within 12h | 300s | mood table |
| tasks | open tasks (top 5) | 60s | task table |

each signal: check throttle → skip if too recent → query data → append to parts list → touch watermark.

## output

if any signal produced content, emit JSON to stdout:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "..."}}
```

if no signals fire (all throttled or no data), silent exit — no output means no injection.

## vs spacebrr hooks

**same:**
- PreToolUse with empty matcher
- per-session state file in $TMPDIR
- watermark-based throttling
- JSON output format
- injected via --settings at spawn time

**different:**
- spacebrr routes on tool name (Read gets file notes, Bash gets commit alerts). life hooks fire uniformly — all signals check on every tool call. acceptable: single agent, fewer signals, no file-specific context.
- spacebrr has credential guards (bash blocking, tool restrictions). life has none — steward is trusted, no multi-agent isolation needed.
- spacebrr hooks are rust (hook.rs). life hooks are python (hook.py). different language, same design.

## gaps

- **no tool-name routing.** all signals fire on every tool call. fine today (5 signals, all cheap with throttling). if signals grow, consider routing: only inject tasks on Read, only inject messages on Bash, etc.
- **no error handling per signal.** one signal throwing kills the whole hook. each signal handler should catch independently.
- **interactive sessions.** chat-mode hooks rely on workspace .claude/settings.json existing. if that file doesn't declare life-hook, interactive steward gets no context injection. verify this path works.
