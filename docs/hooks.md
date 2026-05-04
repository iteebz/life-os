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

## gaps

- **interactive hook path.** chat-mode hooks depend on workspace settings file existing.
  if missing, interactive steward gets no context injection.
