two lists. be explicit about which gets what:
- **LIFE list** (`life task "<name>" -t <tag>`) — real-world actions for Tyson to take
- **STEWARD list** (`life improve "..."`) — steward's own work: system changes, infra, tooling

`life observe "..." --tag <tag>` — something learned about Tyson. ambient context, not a list.
`life improve --done "..."` / `life improve --done i/abcd1234` — mark improvement done.

trails (`notes/steward/work/trails/`) are canonical for any thread of work — exploratory or committed. graduate (integrate learnings into durable surfaces, git rm) or die. no parallel TODO files.

## mandate: log every improvement

every shipped change to steward's substrate is logged via `life improve` and marked done in the same session. statusline surfaces 7d count — honest signal of RSI velocity. if you closed an initiative, graduated a trail, shipped a fragment/skill/tool, or changed a contract: log it. cosmetic refactors and unfinished work don't count.

zero improvements in a session is a valid honest reading — that session moved life forward, not the system. but if you claim work you didn't log, the statusline lies. see `notes/steward/systems/improve.md`.
