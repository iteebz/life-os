# wake

every steward session starts cold. `life steward wake` emits the total context snapshot.
daemon captures this via `fetch_wake_context()` and injects it into the claude prompt.

## current shape (flat)

wake dumps everything in one function, no ordering, no truncation control:

```
STEWARD — day N  |  date time

STEWARD TASKS:        steward-assigned tasks
FEEDBACK HEADLINE:    closure rate, streak, momentum
LAST LIFE:            most recent session summary
CONTRACTS:            behavioral contracts with ratification status
OBSERVATIONS:         upcoming (by date) + recent (24h) + tag-matched (3d)
DATES:                upcoming dates within 30d
CONTACTS (overdue):   stale contacts past cadence
IMPROVEMENTS:         open self-improvement items (top 5)
MOOD:                 latest score + 24h count
COMMIT STATS (7d):    per-repo commit counts, authors, last commit
COMMS:                inbox count, starred emails, pending drafts
TELEGRAM:             recent messages since last inbound
INBOX:                queued daemon messages
```

~15 sections. no priority ordering. if context grows, model attention dilutes equally
across everything. no way to control what survives truncation.

## target shape (tiered)

steal spacebrr's tier model. truncation eats from the bottom — identity survives.

```
IDENTITY (never truncated)
  age, datetime
  steward tasks (self-assigned work)
  contracts (behavioral commitments)

LIFE (truncated last within this tier)
  feedback headline (closure rate, momentum)
  last session summary
  mood

STATE (truncated before LIFE)
  open tasks (human tasks, not steward tasks)
  habits status
  observations (upcoming → recent → tag-matched)
  dates (upcoming 30d)
  contacts (overdue)
  improvements

CONTEXT (truncated first)
  commit stats
  comms (email inbox, starred, drafts)
  telegram recent
  inbox (queued daemon messages)
```

**why this ordering:**
- steward's contracts and self-assigned tasks define what it should DO — this is identity
- life priorities (mood, momentum, last session) set the frame
- state is the working set — important but recoverable via `life` commands
- context is ambient — nice to have, steward can query it explicitly if needed

## truncation mechanism

not implemented yet. current wake has no size awareness. two options:

1. **char budget per tier.** each tier gets a max char allocation. sections within a tier
   truncate by dropping items (fewer tasks, fewer observations) before dropping whole sections.
2. **total budget with tier priority.** set a total wake budget (e.g. 8000 chars). fill from
   top tier down. stop when budget exhausted. simpler, matches spacebrr's approach.

option 2 is the right starting point. tier ordering is the real win — the budget enforcement
can be rough.

## spawn surfaces

wake is consumed differently per surface:

| surface | how wake is used |
|---------|-----------------|
| chat | `steward wake` runs as boot step 1 in CLAUDE.md. steward reads stdout directly |
| tg | `fetch_wake_context()` captures stdout, injects into prompt string |
| auto | same as tg — `run_autonomous()` builds prompt from wake context |
| morning | `_build_opener()` calls `fetch_wake_context()` + adds memory + nudges |

all surfaces go through the same `wake()` function. tier ordering benefits all of them.
