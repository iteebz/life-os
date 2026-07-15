---
description: how hooks keep steward oriented and stop bad state from landing
---
# hooks

hooks are the small bits of code that fire around steward's session and around
every commit. they do two things: feed steward ambient context so it isn't blind
between tool calls, and guard the repo so broken state can't slip in unnoticed.

## why bother

without hooks, steward only knows what it explicitly checks. telegram comes in,
tasks change, a mood gets logged — none of it surfaces unless someone asks. with
hooks, that context arrives the moment a tool fires. same idea applies at commit:
without a guard, malformed files land and rot quietly.

## the session side

four events wrap a steward session. each does one job:

| event | what it does |
|-------|-------------|
| UserPromptSubmit | logs the human turn, drains the inbox, surfaces session size |
| PreToolUse | injects ambient signals — dirty repo, new commits, habits, mood, tasks |
| Stop | logs steward's response |
| SessionEnd | auto-sleeps the session and pushes every repo |

settings are injected at spawn time via `--settings`. nothing is written to
`.claude/settings.*` — hooks live in the launcher, not in any config file.

state is throttled per session in a tmp file. high-frequency signals (inbox,
tasks) check often, low-frequency ones (mood, dirty state) check rarely or once
per spawn. the file dies with the session — no cleanup, no leakage.

## the signals

seven ambient signals, each independently throttled. they fire on every tool
call. if the count ever grows beyond what's cheap, add routing by tool name.

| signal | what steward sees | when |
|--------|------------------|------|
| dirty_state | uncommitted ~/life changes | once per spawn |
| life_os_commits | new life-os commits since last seen HEAD | when HEAD advances |
| inbox | queued messages from when steward was busy | drained on read |
| habits | today's completion status | every 60s |
| mood | latest mood score | every 5min |
| tasks | open task summary | every 60s |
| session-meta | size/age of the current session | at every prompt |

## the commit side

two guards run on every commit. both can block.

**commit-msg** enforces `type(scope): verb object` — atomic, no commas, no
trailing periods, em-dashes auto-sanitized to `-`. subject capped at 72 chars.

**pre-commit** runs two things in order: the **frontmatter guard** (below), then
ruff format-check + lint on staged python.

## frontmatter guarding

stolen from spacebrr. the idea: certain directories own a frontmatter contract,
and the commit hook refuses to land files that break it. cheap to check, catches
typos and drift before they pollute steward's reads.

today there's one schema:

| glob | required field | valid values |
|------|----------------|--------------|
| `steward/work/trails/` | `description` | any non-empty |

adding a new schema is one line in `_FRONTMATTER_SCHEMAS` (life/hooks/git.py). set
`valid_values` to `None` if any non-empty value is acceptable. keep the schema
table small — every entry is a contract you're promising to maintain.

what it doesn't do: parse full YAML, enforce field ordering, check the body, or
warn on extra fields. it's a guard, not a linter. if a stricter shape matters,
write a dedicated check rather than expand this one.

## differences from spacebrr

same skeleton, smaller surface. no tool-name routing because steward is one
agent. no credential isolation because there's no multi-agent trust boundary.
python rather than rust because the rest of life-os is python and the perf
budget here is irrelevant.
