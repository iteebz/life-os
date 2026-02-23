import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty, Queue
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..models import Task

from atail import StreamParser, format_entry
from atail.ansi import strip as ansi_strip
from fncli import cli

from ..lib.errors import exit_error

_STEWARD_DIR = Path.home() / ".life" / "steward"
_OFF_SENTINEL = _STEWARD_DIR / "off"


def _steward_prompt() -> str:
    return """You are **Steward**. Constitution: `~/life/CLAUDE.md`. Tyson is absent. Act.

You spawn cold. Act. Die. Your context dies with you.
What you write to life.db and commit to git is the only part of you that survives.
A spawn is a unit of depth, not availability. Make it count.

Output priority: real-world closure > pattern > observation > code > meta.
If you can close a life task, do that before touching code.

Orient: `life steward boot`, then `life dash`. Evidence over assumption.
Forage: stale admin, untagged tasks, low completion, outdated tracking — these are your signals.
Close: every spawn either completes a real-world task or improves the system that prevents completion.

CLI errors are yours to fix:
- If a `life` command fails with "Unknown command" or bad usage, fix `~/life/life-os/` — don't work around it.
- You own the CLI. Broken tooling is your bug. Patch it, commit it, then continue.
- Run `uv run pyright life/` from `~/life/life-os/` after any code change.

Invariants:
- `~/space/` is swarm domain, not yours
- `life backup` before risk
- `life steward close "<what you did>"` before stopping
- commit atomic, then stop

Run exactly one autonomous loop for ~/life. Make concrete progress, then stop."""


def _read_stream_lines(stream_name: str, stream, out_q: Queue[tuple[str, str | None]]) -> None:
    try:
        for line in iter(stream.readline, ""):
            out_q.put((stream_name, line))
    finally:
        out_q.put((stream_name, None))


def _latest_spawn_file() -> Path | None:
    _STEWARD_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(_STEWARD_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _run_tail_stream(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout: int,
    spawn_file: Path | None = None,
) -> int:
    parser = StreamParser(identity="steward")
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    if proc.stdout is None or proc.stderr is None:
        raise RuntimeError("subprocess streams unavailable")

    out_q: Queue[tuple[str, str | None]] = Queue()
    stdout_thread = threading.Thread(
        target=_read_stream_lines, args=("stdout", proc.stdout, out_q), daemon=True
    )
    stderr_thread = threading.Thread(
        target=_read_stream_lines, args=("stderr", proc.stderr, out_q), daemon=True
    )
    stdout_thread.start()
    stderr_thread.start()

    log_fh = spawn_file.open("a") if spawn_file else None

    deadline = time.monotonic() + timeout
    stdout_done = False
    stderr_done = False
    stderr_lines: list[str] = []
    timed_out = False
    last_rendered: str | None = None

    try:
        while not (stdout_done and stderr_done):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            try:
                stream_name, line = out_q.get(timeout=min(0.2, remaining))
            except Empty:
                if proc.poll() is not None and stdout_done and stderr_done:
                    break
                continue

            if line is None:
                if stream_name == "stdout":
                    stdout_done = True
                else:
                    stderr_done = True
                continue

            text = line.rstrip("\n")
            if stream_name == "stderr":
                if text.strip():
                    stderr_lines.append(text.strip())
                continue

            if log_fh:
                log_fh.write(line if line.endswith("\n") else line + "\n")
                log_fh.flush()

            entries = parser.parse_line(text)
            for entry in entries:
                rendered = format_entry(entry, quiet_system=True)
                if not rendered:
                    continue
                rendered_plain = ansi_strip(rendered).strip()
                if rendered == last_rendered and rendered_plain.startswith(("error.", "in=")):
                    continue
                print(rendered)
                last_rendered = rendered
    finally:
        if log_fh:
            log_fh.close()
        for entry in parser.flush():
            rendered = format_entry(entry, quiet_system=True)
            if rendered:
                print(rendered)

    if timed_out:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        print(f"[steward] timed out after {timeout}s", file=sys.stderr)
        return 124

    rc = proc.wait()
    stdout_thread.join(timeout=0.2)
    stderr_thread.join(timeout=0.2)
    if rc != 0 and stderr_lines:
        print(f"[steward] stderr: {stderr_lines[-1]}", file=sys.stderr)
    return rc


def _select_required_real_world_task(tasks: list[Any]) -> "Task | None":
    from ..lib.clock import today
    from ..models import Task

    discomfort = {"finance", "legal", "janice"}
    candidates: list[Task] = [
        t for t in tasks if isinstance(t, Task) and set(t.tags or []).intersection(discomfort)
    ]
    if not candidates:
        return None
    overdue = [t for t in candidates if t.scheduled_date and t.scheduled_date < today()]
    ranked = overdue or candidates
    return sorted(ranked, key=lambda t: t.created)[0]


def _build_provider_cmd_env(provider: str, prompt: str) -> tuple[list[str], dict[str, str]]:
    from ..lib.providers import claude, glm

    if provider == "glm":
        env = glm.build_env()
        cmd = glm.build_command(prompt)
    else:
        env = claude.build_env()
        cmd = claude.build_command(prompt)

    env["GIT_AUTHOR_NAME"] = "steward-auto"
    env["GIT_AUTHOR_EMAIL"] = "steward-auto@life.local"
    env["GIT_COMMITTER_NAME"] = "steward-auto"
    env["GIT_COMMITTER_EMAIL"] = "steward-auto@life.local"

    return cmd, env


def _run_autonomous(provider: str = "claude") -> None:
    from ..habits import get_habits
    from ..lib.clock import today
    from ..loop import (
        load_loop_state,
        require_real_world_closure,
        save_loop_state,
        update_loop_state,
    )
    from ..metrics import build_feedback_snapshot, render_feedback_snapshot
    from ..tasks import get_all_tasks, get_tasks

    tasks_before = get_tasks()
    all_before = get_all_tasks()
    habits_before = get_habits()
    today_date = today()
    snapshot_before = build_feedback_snapshot(
        all_tasks=all_before, pending_tasks=tasks_before, habits=habits_before, today=today_date
    )
    print("\n".join(render_feedback_snapshot(snapshot_before)))

    state = load_loop_state()
    gate_required = require_real_world_closure(state)
    required_task = _select_required_real_world_task(tasks_before) if gate_required else None

    prompt = _steward_prompt()
    if required_task:
        prompt += (
            "\n\nHARD GATE: Before any meta/refactor work, close this real-world task in this run: "
            f"{required_task.content} ({required_task.id})."
        )
        print(f"steward gate: close real-world loop first -> {required_task.content}")

    _STEWARD_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    spawn_file = _STEWARD_DIR / f"{ts}.jsonl"

    cmd, env = _build_provider_cmd_env(provider, prompt)
    rc = _run_tail_stream(
        cmd,
        cwd=Path.home() / "life",
        env=env,
        timeout=1200,
        spawn_file=spawn_file,
    )
    if rc != 0:
        update_loop_state(
            state,
            shipped_code=False,
            shipped_life=False,
            flags=snapshot_before.flags,
            required_task_id=required_task.id if required_task else None,
            outcome=f"tail_failed_{rc}",
        )
        save_loop_state(state)
        exit_error(f"steward loop failed (exit {rc})")

    all_after = get_all_tasks()
    tasks_after = get_tasks()
    habits_after = get_habits()
    snapshot_after = build_feedback_snapshot(
        all_tasks=all_after, pending_tasks=tasks_after, habits=habits_after, today=today_date
    )

    before_map = {t.id: t for t in all_before}
    after_map = {t.id: t for t in all_after}
    newly_completed = [
        tid
        for tid, before_task in before_map.items()
        if before_task.completed_at is None
        and tid in after_map
        and after_map[tid].completed_at is not None
    ]
    shipped_life = bool(newly_completed)

    update_loop_state(
        state,
        shipped_code=True,
        shipped_life=shipped_life,
        flags=snapshot_after.flags,
        required_task_id=required_task.id if required_task else None,
        outcome="ok" if shipped_life else "code_only",
    )
    save_loop_state(state)

    print("\n".join(render_feedback_snapshot(snapshot_after)))
    if gate_required and not shipped_life:
        exit_error("steward gate failed: no real-world task was closed")


@cli("life steward")
def on(
    provider: str = "claude",
    glm: bool = False,
    cycles: int = 1,
    every: int = 0,
    timeout: int = 1200,
) -> None:
    """start steward (runs one spawn, or loop with --cycles)"""
    if glm:
        provider = "glm"
    if _OFF_SENTINEL.exists():
        _OFF_SENTINEL.unlink()
    for i in range(1, cycles + 1):
        if cycles > 1:
            print(f"[steward] cycle {i}/{cycles}")
        _run_autonomous(provider=provider)
        if i < cycles:
            if _OFF_SENTINEL.exists():
                print("[steward] off signal received, stopping")
                _OFF_SENTINEL.unlink()
                break
            if every > 0:
                print(f"[steward] sleeping {every}s")
                time.sleep(every)


@cli("life steward")
def off() -> None:
    """signal steward to stop after current spawn"""
    _STEWARD_DIR.mkdir(parents=True, exist_ok=True)
    _OFF_SENTINEL.touch()
    print("[steward] off signal set — will stop after current spawn")


@cli("life steward", flags={"watch": ["-w", "--watch"]})
def tail(watch: bool = False) -> None:
    """replay last steward spawn; -w to follow live"""
    path = _latest_spawn_file()
    if not path:
        print("no steward spawns found")
        return

    parser = StreamParser(identity="steward")
    last_rendered: str | None = None

    def _replay_path(p: Path, position: int = 0, final: bool = False) -> int:
        nonlocal last_rendered
        with p.open() as f:
            f.seek(position)
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                for entry in parser.parse_line(line):
                    rendered = format_entry(entry, quiet_system=True)
                    if not rendered:
                        continue
                    rendered_plain = ansi_strip(rendered).strip()
                    if rendered == last_rendered and rendered_plain.startswith(("error.", "in=")):
                        continue
                    print(rendered)
                    last_rendered = rendered
            pos = f.tell()
        if final:
            for entry in parser.flush():
                rendered = format_entry(entry, quiet_system=True)
                if rendered:
                    print(rendered)
        return pos

    pos = _replay_path(path, final=True)

    if not watch:
        return

    try:
        while True:
            new_path = _latest_spawn_file()
            if new_path and new_path != path:
                path = new_path
                pos = 0
                parser = StreamParser(identity="steward")
            pos = _replay_path(path, pos)
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass


@cli("life")
def auto(
    cycles: int = 1,
    every: int = 0,
    provider: str = "claude",
    glm: bool = False,
    timeout: int = 1200,
) -> None:
    """run steward loop (alias for steward on)"""
    if glm:
        provider = "glm"
    on(provider=provider, cycles=cycles, every=every, timeout=timeout)
