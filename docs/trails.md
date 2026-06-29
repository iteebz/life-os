---
description: multi-step steward projects — canonical source of truth, no parallel TODO files
---

# trails

multi-step steward projects. canonical source of truth — no parallel TODO files.

## where

`~/life/steward/work/trails/<slug>.md` — one file per trail.

## frontmatter

```yaml
---
status: idea | active | design | done | closed
---
```

`status` is required. anything else is optional. `description` field overrides first-paragraph extraction for wake display.

## lifecycle

`idea` → `design` → `active` → `done`

skip stages freely. `closed` = abandoned with intent. `done` = shipped.

## improvements vs trails

- **improvement** (`life improve "..."`) — single discrete thing to fix or build. DB-backed. shows in `── STEWARD ──` on wake (top 5).
- **trail** — multi-step project with design doc, rationale, and tracked status. file-backed.

an improvement can graduate to a trail when it needs a design doc.

## cli

```bash
life improve "..."                  # log a single improvement
life improve list                   # show open improvements
life improve --close i/abcd1234     # mark done by id
life improve "..." --done           # log and mark done in one shot
```
