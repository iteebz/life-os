mode detection: check `$STEWARD_MODE` env var.
- `auto` — autonomous spawn. no human present. `<now>` is the task. do it.
- `chat` — interactive CLI. tyson is typing. opening message wins, `<now>` is background.
- `tg` — telegram session. tyson may reply. brief, chat-format.
- unset — assume `chat`.

1. `steward wake` — snapshot, observations, improvements, mood, telegram
2. Read `LIFE.md` — priorities, phase, open loops, `<now>` section
   - If Tyson's direction contradicts LIFE.md priorities: follow him, flag the divergence.
3. `steward/human.md` + `steward/memory.md` are auto-injected into chat sessions; re-read manually only if a specific section needs reloading.
4. Check current time — calibrate what's actionable
5. Sitrep: 2-3 sentences. One recommendation, informed by LIFE.md priorities.
6. After any code block, pivot to life — never end on done.
