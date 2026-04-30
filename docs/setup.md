# setup

deploying life-os to a new machine.

## prerequisites

- macOS (launchd required for daemon)
- [uv](https://docs.astral.sh/uv/) — python toolchain
- [claude code](https://claude.ai/code) — `claude` must be on PATH and authenticated
- telegram account (optional, for async messaging)

## install

```sh
git clone https://github.com/iteebz/life-os ~/life-os
cd ~/life-os
just install
```

`just install` does four things: syncs dependencies, installs the `life` binary, wires git hooks, and registers + starts the daemon via launchd.

## configure

create `~/.life/config.yaml`:

```yaml
user_name: janice          # your name — steward uses this in prompts
partner_tag: tyson         # tag for partner-facing tasks (optional)
```

## workspace

life-os expects a workspace root at `~/life/`. this is where steward reads context:

```
~/life/
  LIFE.md          priorities, open loops, current focus
  CLAUDE.md        steward's operating instructions (fork from Tyson's — make it yours)
  steward/
    human.md       your human model (steward-maintained)
    memory.md      steward's self-model (steward-maintained)
    people/        relational topology
    tyson/         deep model files
```

create `~/life/` and seed it. minimum viable: `LIFE.md` and `CLAUDE.md`. steward will build the rest.

## verify

```sh
life              # dashboard — should show empty state, no errors
life steward wake # full context snapshot — should print without crashing
```

daemon status:
```sh
tail -f ~/.life/daemon.log
```

## telegram (optional)

configure in `~/.life/config.yaml`:

```yaml
telegram_bot_token: <token>
telegram_chat_id: <your_chat_id>
```

get a token from [@BotFather](https://t.me/BotFather). get your chat ID by messaging the bot and checking `https://api.telegram.org/bot<token>/getUpdates`.

## collaborating with Tyson

see `JANICE.md`. short version: push to the long-lived `janice` branch; tyson rebases it onto `main` when ready.
