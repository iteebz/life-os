---
description: daily dashboard layout — sections, tag groups, rendering pipeline
---
# dashboard

`life` renders the daily dashboard. layout is fixed sections top-down, with a config-driven
backlog at the bottom.

## layout

```
header (date, time, counts)
DONE (completed today)
OVERDUE (past scheduled date)
TODAY (scheduled today)
habit categories (care, connect, admin, input, chores)
WEEKLY
VICES
scheduled future days (tomorrow → +14d)
backlog groups (config-driven)
```

## habit categories

habits are grouped by tag into fixed sections. a habit appears in exactly one:

| tag | section | color |
|-----|---------|-------|
| care | CARE | purple |
| connect | CONNECT | pink |
| admin | ADMIN | yellow |
| input | INPUT | green |
| chore | CHORES | cyan |
| vice | VICES | red (inverted: checked = bad) |

habits with none of these tags fall into a generic HABITS section. weekly cadence habits
render separately under WEEKLY regardless of tags.

## backlog groups

tasks without a scheduled date render in the backlog, grouped by primary tag. grouping
order and display labels are driven by `~/.life/tags.toml`:

```toml
# tag color overrides (top-level key = tag, value = color name)
janice = "yellow"
sell = "cyan"

# backlog section ordering and labels
[groups]
finance = "FINANCE"
legal = "LEGAL"
sell = "SELL LIST"
health = "HEALTH"
```

tags listed in `[groups]` render as sections in that order. tasks with tags not in the
config sort alphabetically after. tasks with no tags fall into BACKLOG.

a task's "primary tag" determines its section. auxiliary tags (currently just `comms`)
are deprioritized — a task tagged `#comms #finance` groups under FINANCE.

## tag colors

each tag gets a deterministic color from a hash-based pool. `tags.toml` top-level
entries override this with named colors (yellow, cyan, etc). available names match
the ANSI theme palette — run `life colors` to see them.
