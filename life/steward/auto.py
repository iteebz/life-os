import subprocess
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..models import Task

from fncli import cli

from ..lib.ansi import strip as ansi_strip
from ..lib.errors import echo, exit_error
from ..lib.tail import StreamParser, format_entry


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


def _run_tail_stream(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout: int,
    raw: bool,
    quiet_system: bool,
) -> int:
    parser = StreamParser()
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

    deadline = time.monotonic() + timeout
    stdout_done = False
    stderr_done = False
    stderr_lines: list[str] = []
    timed_out = False
    last_rendered: str | None = None

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

        if raw:
            echo(text)
            continue

        entries = parser.parse_line(text)
        for entry in entries:
            rendered = format_entry(entry, quiet_system=quiet_system)
            if not rendered:
                continue
            rendered_plain = ansi_strip(rendered).strip()
            if rendered == last_rendered and rendered_plain.startswith(("error.", "in=")):
                continue
            echo(rendered)
            last_rendered = rendered

    if timed_out:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        echo(f"[tail] timed out after {timeout}s", err=True)
        return 124

    rc = proc.wait()
    stdout_thread.join(timeout=0.2)
    stderr_thread.join(timeout=0.2)
    if rc != 0 and stderr_lines:
        echo(f"[tail] stderr: {stderr_lines[-1]}", err=True)
    return rc


def _select_required_real_world_task(tasks: list[Any]) -> "Task | None":
    from ..lib.clock import today
    from ..models import Task

    discomfort = {"finance", "legal", "janice"}
    candidates: list[Task] = [t for t in tasks if isinstance(t, Task) and set(t.tags or []).intersection(discomfort)]
    if not candidates:
        return None
    overdue = [t for t in candidates if t.scheduled_date and t.scheduled_date < today()]
    ranked = overdue or candidates
    return sorted(ranked, key=lambda t: t.created)[0]


def _run_autonomous() -> None:
    from ..lib.clock import today
    from ..lib.providers import glm
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
    today_date = today()
    snapshot_before = build_feedback_snapshot(
        all_tasks=all_before, pending_tasks=tasks_before, today=today_date
    )
    echo("\n".join(render_feedback_snapshot(snapshot_before)))

    state = load_loop_state()
    gate_required = require_real_world_closure(state)
    required_task = _select_required_real_world_task(tasks_before) if gate_required else None

    prompt = _steward_prompt()
    if required_task:
        prompt += (
            "\n\nHARD GATE: Before any meta/refactor work, close this real-world task in this run: "
            f"{required_task.content} ({required_task.id})."
        )
        echo(f"steward gate: close real-world loop first -> {required_task.content}")

    cmd = glm.build_command(prompt=prompt)
    env = glm.build_env()
    rc = _run_tail_stream(
        cmd,
        cwd=Path.home() / "life",
        env=env,
        timeout=1200,
        raw=False,
        quiet_system=False,
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
    snapshot_after = build_feedback_snapshot(
        all_tasks=all_after, pending_tasks=tasks_after, today=today_date
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

    echo("\n".join(render_feedback_snapshot(snapshot_after)))
    if gate_required and not shipped_life:
        exit_error("steward gate failed: no real-world task was closed")


def cmd_tail(
    cycles: int = 1,
    interval_seconds: int = 0,
    model: str = "glm-5",
    dry_run: bool = False,
    continue_on_error: bool = False,
    timeout_seconds: int = 1200,
    retries: int = 2,
    retry_delay_seconds: int = 2,
    raw: bool = False,
    quiet_system: bool = False,
) -> None:
    from ..lib.providers import glm

    if cycles < 1:
        exit_error("--cycles must be >= 1")
    if interval_seconds < 0:
        exit_error("--every must be >= 0")
    if timeout_seconds < 1:
        exit_error("--timeout must be >= 1")
    if retries < 0:
        exit_error("--retries must be >= 0")
    if retry_delay_seconds < 0:
        exit_error("--retry-delay must be >= 0")

    life_dir = Path.home() / "life"
    prompt = _steward_prompt()

    for i in range(1, cycles + 1):
        echo(f"[tail] cycle {i}/{cycles}")
        cmd = glm.build_command(prompt=prompt)
        env = glm.build_env()
        attempts = retries + 1
        if dry_run:
            echo(" ".join(cmd))
        else:
            ok = False
            last_rc = 1
            for attempt in range(1, attempts + 1):
                if attempt > 1:
                    echo(f"[tail] retry {attempt - 1}/{retries} after failure")
                try:
                    last_rc = _run_tail_stream(
                        cmd,
                        cwd=life_dir,
                        env=env,
                        timeout=timeout_seconds,
                        raw=raw,
                        quiet_system=quiet_system,
                    )
                except Exception as exc:
                    echo(f"[tail] execution error: {exc}", err=True)
                    last_rc = 1

                if last_rc == 0:
                    ok = True
                    break
                if attempt < attempts and retry_delay_seconds > 0:
                    time.sleep(retry_delay_seconds)

            if not ok:
                if continue_on_error:
                    echo(f"[tail] cycle {i} failed (exit {last_rc}), continuing")
                else:
                    exit_error(f"tail loop failed on cycle {i} (exit {last_rc})")
        if i < cycles and interval_seconds > 0:
            echo(f"[tail] sleeping {interval_seconds}s")
            time.sleep(interval_seconds)


@cli("life")
def auto(
    cycles: int = 1,
    every: int = 0,
    model: str = "glm-4",
    timeout: int = 1200,
    retries: int = 2,
    retry_delay: int = 2,
    dry_run: bool = False,
    raw: bool = False,
    quiet_system: bool = False,
    continue_on_error: bool = False,
) -> None:
    """Run unattended Steward loop through the glm connector"""
    cmd_tail(
        cycles=cycles,
        interval_seconds=every,
        model=model,
        timeout_seconds=timeout,
        retries=retries,
        retry_delay_seconds=retry_delay,
        dry_run=dry_run,
        raw=raw,
        quiet_system=quiet_system,
        continue_on_error=continue_on_error,
    )


@cli("life steward", name="run")
def steward_run() -> None:
    """Run autonomous steward loop"""
    _run_autonomous()
