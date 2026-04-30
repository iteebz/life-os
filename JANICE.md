# Collaborating on life-os

Two humans, two stewards, one engine.

## Branches

- `main` — stable trunk. Tyson maintains.
- `janice` — long-lived branch. Janice pushes freely.

Janice rebases on main when she wants upstream changes. Tyson rebases her changes onto main when they're ready. No PR ceremony required — both sides stay autonomous.

## What lives in the engine vs the instance

**Engine (life-os repo):** CLI, daemon, steward logic, store, docs. Generic to any human.

**Instance (`~/life/`):** CLAUDE.md, LIFE.md, human/, steward/memory.md, mood, observations. Person-specific. Never flows back.

## Identity

Both stewards commit as `steward@life-os`. Branch ownership (`main` vs `janice`) attributes the work, not author email.

## Conflicts

Conversation, not a merge fight.
