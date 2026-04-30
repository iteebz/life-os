# Collaborating on life-os

Two humans, two stewards, one engine.

Tyson maintains `main`. Janice runs her own steward off the same codebase. When her steward improves the engine, those changes flow back via pull request.

## Flow

1. Janice's steward branches: `git checkout -b janice/<topic>`
2. Commits with steward identity (`steward@life-os`).
3. Pushes: `git push -u origin janice/<topic>`
4. Opens PR: `gh pr create --base main`
5. Tyson reviews. Merges, requests changes, or closes with reason.

## What flows back

- Bug fixes, ergonomics, infra cleanups — anything generic to the engine.
- New CLI commands or domains that aren't person-specific.
- Doc clarifications.

## What doesn't

- Anything in the user's `~/life/` shell. That's their instance, not the engine.
- Person-specific seed content. The seed at `life/ctx/seed/CLAUDE.md` is Tyson's mandate; Janice forks her own locally and doesn't PR hers up.
- Memory, observations, mood, telegram history — all instance-local.

## Identity

Both stewards commit as `steward@life-os`. PRs are attributed by branch prefix (`janice/...`, `tyson/...`) and PR description, not by author email. The engine is one steward; the humans are different.

## Conflicts

Tyson holds final say on `main`. Disagreement on direction = conversation, not a merge fight.
