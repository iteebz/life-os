# initiatives

multi-step steward projects. canonical source of truth — no parallel TODO files.

## where

`~/life/steward/initiatives/<slug>.md` — one file per initiative.

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

## wake surface

`render_initiatives()` in `ctx/sections.py` reads all files via `initiative_index()` (in `steward/initiatives.py`), filters out done/closed, and emits title + first paragraph of body (or `description` frontmatter field) for each. steward sees the full list and rationale on every spawn.

## improvements vs initiatives

- **improvement** (`life improve "..."`) — single discrete thing to fix or build. DB-backed. shows in `── STEWARD ──` on wake (top 5).
- **initiative** — multi-step project with design doc, rationale, and tracked status. file-backed.

an improvement can graduate to an initiative when it needs a design doc.

## cli

```bash
life initiatives                    # list open
life steward initiatives new "name" # scaffold new file
life improve "..."                  # log a single improvement
life improve list                   # show open improvements
life improve --done i/abcd1234      # mark done
```
