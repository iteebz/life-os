# wake

every steward session starts cold. wake is the total context snapshot — everything steward
knows at boot. daemon captures it and injects it into the claude prompt.

## current shape

`life/ctx/` owns prompt assembly:
- `sections.py` — one renderer per data slice, returns string or "" to omit.
- `assemble.py` — `build_wake()` composes sections in priority order; `build_chat_prompt()` wraps for system-prompt injection.
- `fragments.py` — static atoms (templates, constants).

`steward/wake.py` is a thin CLI wrapper that prints `build_wake()`. Chat sessions
inject `build_chat_prompt()` directly via `--append-system-prompt` (no subprocess).
Daemon paths use `fetch_wake_context()` which calls `build_wake()` in-process.

## target shape (tiered)

steal spacebrr's tier model. truncation eats from the bottom — identity survives.

```
IDENTITY (never truncated)
  steward tasks (self-assigned work)
  contracts (behavioral commitments)

LIFE (truncated last within this tier)
  feedback headline (closure rate, momentum)
  last session summary
  mood

STATE (truncated before LIFE)
  open tasks, habits, observations
  dates, contacts, improvements

CONTEXT (truncated first)
  commit stats, comms, telegram, inbox
```

**why this ordering:** steward's contracts define what it should DO — that's identity.
life priorities set the frame. state is the working set — recoverable via CLI.
context is ambient — queryable on demand.

## design principles

**all surfaces use the same wake.** chat, telegram, auto, morning — all go through
`build_wake()`. tier ordering benefits all of them.

**char budget with tier priority.** set a total wake budget. fill from top tier down.
stop when exhausted. sections within a tier drop items before dropping whole sections.
not yet implemented — currently emits everything.

**sections are pure.** each `render_*()` returns a string or "" (no print, no I/O
contracts beyond DB reads). composable, testable, side-effect-free.

## spawn surfaces

| surface | how wake is consumed |
|---------|---------------------|
| chat (fresh) | injected into `--append-system-prompt` so the model boots hot |
| chat (resume) | skipped — prior turns already carry state |
| chat (`--raw`) | skipped — bare model session |
| tg/auto | daemon captures stdout and injects into prompt string |
| morning | same capture + adds memory and nudge context on top |

## warm resume

telegram messages arriving with no active chat session look for a *warm* prior session
(closed cleanly, <55m old, <100k chars). if found, the message goes through
`claude --print --resume` so continuity holds. cold sessions fall back to stateless
spawn with full wake context.

## session-meta nudges

UserPromptSubmit hook emits `<session-meta>` on each human turn once the session
crosses size/age thresholds. 100k chars → wrap soon. 150k chars → sleep now. keeps
chat sessions from drifting into stale, oversized territory.
