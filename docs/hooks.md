# hooks

context injection into active steward sessions. steward sees ambient life signals without
polling or explicit commands.

## why hooks

agents are blind between tool calls. telegram messages arrive, tasks change, mood shifts —
none of this surfaces unless steward explicitly checks. hooks solve this by injecting context
at the moment a tool fires. steward stays oriented mid-flight.

## design

one hook event (PreToolUse), empty matcher (catches all tools). same pattern as spacebrr.

daemon spawns inject hook settings via `--settings` JSON at spawn time — no writes to global
claude settings. interactive sessions get hooks via workspace `.claude/settings.json`.

## state model

per-session state file in `$TMPDIR`. stores watermark timestamps for throttling. each signal
has its own throttle interval — high-frequency signals (new messages) check often, low-frequency
signals (mood) check rarely. state is ephemeral — dies with the session. no cleanup needed.

## signals

five ambient signals, each independently throttled:

| signal | what steward sees | why |
|--------|------------------|-----|
| inbox | queued messages from when steward was busy | don't lose async messages |
| messages | new telegram messages since last check | stay current on conversation |
| habits | today's completion status | awareness of daily rhythm |
| mood | latest mood score | calibrate tone and recommendations |
| tasks | open task summary | keep working set visible |

all signals fire on every tool call (no tool-name routing). acceptable for a single agent
with five cheap signals. if signal count grows, add routing.

## vs spacebrr hooks

same pattern (PreToolUse, watermarks, --settings injection, JSON output). differences:
- no tool-name routing (spacebrr routes Read→file notes, Bash→commit alerts)
- no credential guards (steward is trusted, no multi-agent isolation)
- python not rust

## gaps

- **no per-signal error isolation.** one signal throwing kills the entire hook invocation.
  each handler should catch independently.
- **interactive hook path.** chat-mode hooks depend on workspace settings file existing.
  if missing, interactive steward gets no context injection.
