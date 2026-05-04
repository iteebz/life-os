# hooks

context injection into active steward sessions. steward sees ambient life signals without
polling or explicit commands.

## why hooks

agents are blind between tool calls. telegram messages arrive, tasks change, mood shifts —
none of this surfaces unless steward explicitly checks. hooks solve this by injecting context
at the moment a tool fires. steward stays oriented mid-flight.

## design

four hook events (PreToolUse, UserPromptSubmit, Stop, SessionEnd). same pattern as spacebrr.

all sessions (chat and auto) inject hook settings via `--settings` JSON at spawn time.
no writes to `.claude/settings.*` — hooks live in launch architecture, not config.

## state model

per-session state file in `$TMPDIR`. stores watermark timestamps for throttling. each signal
has its own throttle interval — high-frequency signals (new messages) check often, low-frequency
signals (mood) check rarely. state is ephemeral — dies with the session. no cleanup needed.

## signals

seven ambient signals, each independently throttled:

| signal | what steward sees | throttle |
|--------|------------------|---------|
| dirty_state | uncommitted ~/life changes | once per spawn |
| life_os_commits | new life-os commits since last seen HEAD | watermark (HEAD hash) |
| inbox | queued messages from when steward was busy | drain (no throttle) |
| habits | today's completion status | 60s |
| mood | latest mood score | 300s |
| tasks | open task summary | 60s |

dirty_state fires once per spawn — presence of uncommitted changes is the signal, not frequency.
life_os_commits uses HEAD-hash watermarking (spacebrr pattern): fires only when HEAD advances, never on repeated calls.

all signals fire on every tool call (no tool-name routing). acceptable for a single agent
with seven cheap signals. if signal count grows, add routing.

## vs spacebrr hooks

same pattern (PreToolUse, watermarks, --settings injection, JSON output). differences:
- no tool-name routing (spacebrr routes Read→file notes, Bash→commit alerts)
- no credential guards (steward is trusted, no multi-agent isolation)
- python not rust

## session lifecycle

| event | handler | what it does |
|-------|---------|-------------|
| UserPromptSubmit | `hook prompt` | log human turn, drain inbox, surface session meta |
| PreToolUse | `hook tool` | inject ambient signals (habits, tasks, mood, commits, inbox) |
| Stop | `hook stop` | log steward response |
| SessionEnd | `hook session-end` | auto-close session record, push all repos |

SessionEnd auto-sleep generates a mechanical summary from the message log — no human required.
