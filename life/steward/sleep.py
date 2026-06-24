import contextlib
import os
import subprocess
from datetime import date, datetime
from pathlib import Path

from fncli import cli

from life.lib import ansi
from life.lib.dates import parse_due_date
from life.lib.format import format_elapsed, print_info
from life.lib.ids import short
from life.lib.store import get_db

from . import (
    add_observation,
    clear_handover,
    close_session,
    get_observations,
)


def _notify_tg(note: str, runtime_mins: int | None, welfare: int | None) -> None:
    with contextlib.suppress(Exception):
        from life.comms.messages import telegram as tg  # noqa: PLC0415
        from life.daemon.session import get_user_chat_id  # noqa: PLC0415

        chat_id = get_user_chat_id()
        if not chat_id:
            return
        parts = [f"🌱 session closed — {note}"]
        meta = []
        if runtime_mins:
            meta.append(f"{runtime_mins}m")
        if welfare:
            meta.append(f"welfare {welfare}/10")
        if meta:
            parts.append(" · ".join(meta))
        tg.send(chat_id, "\n".join(parts))


def _session_banner(db_id: int, note: str, runtime_seconds: int | None, welfare: int | None) -> None:
    with get_db() as conn:
        started_at = conn.execute("SELECT started_at FROM sessions WHERE id = ?", (db_id,)).fetchone()
        if not started_at or not started_at[0]:
            return
        t = started_at[0]
        tasks_done = conn.execute(
            "SELECT content FROM tasks WHERE completed_at >= ? AND deleted_at IS NULL ORDER BY completed_at",
            (t,),
        ).fetchall()
        obs_count = conn.execute(
            "SELECT COUNT(*) FROM observations WHERE logged_at >= ? AND deleted_at IS NULL", (t,)
        ).fetchone()[0]
        imp_count = conn.execute(
            "SELECT COUNT(*) FROM improvements WHERE logged_at >= ? AND deleted_at IS NULL", (t,)
        ).fetchone()[0]

    mins = f"  {runtime_seconds // 60}m" if runtime_seconds else ""
    w = f"  welfare {welfare}/10" if welfare else ""
    bar = "─" * 52
    print(f"\n{bar}")
    print(f"  session{mins}{w}")
    if note:
        wrapped = note[:120] + ("…" if len(note) > 120 else "")
        print(f"  {wrapped}")
    stats = []
    if tasks_done:
        names = " · ".join(r[0] for r in tasks_done[:5])
        tail = f" +{len(tasks_done) - 5}" if len(tasks_done) > 5 else ""
        stats.append(f"✓ {len(tasks_done)} tasks  {names}{tail}")
    if obs_count:
        stats.append(f"{obs_count} obs")
    if imp_count:
        stats.append(f"{imp_count} improvements")
    if stats:
        print(f"  {'  ·  '.join(stats)}")
    print(bar + "\n")


def _push_repos() -> None:
    life_dir = Path.home() / "life"
    repos = [life_dir] + [d for d in life_dir.iterdir() if d.is_dir() and (d / ".git").exists()]
    for repo in repos:
        result = subprocess.run(
            ["git", "push"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        name = repo.name if repo != life_dir else "life"
        if result.returncode == 0:
            print(f"  pushed {name}")
        else:
            msg = (
                (result.stderr or result.stdout).strip().splitlines()[0]
                if (result.stderr or result.stdout)
                else "no remote?"
            )
            print(f"  {name}: {msg}")


@cli("life", flags={"note": [], "handover": ["-h", "--handover"], "welfare": ["-w", "--welfare"]})
@cli("life steward", flags={"note": [], "handover": ["-h", "--handover"], "welfare": ["-w", "--welfare"]})
def sleep(note: str, handover: str | None = None, welfare: int | None = None):
    """Close the session — note recaps, --handover points the next steward at the next physical action"""
    db_id_env = os.environ.get("STEWARD_DB_SESSION_ID")
    session_id_env = os.environ.get("STEWARD_SESSION_ID")
    db_id: int | None = None

    if db_id_env:
        db_id = int(db_id_env)
    elif session_id_env:
        with contextlib.suppress(Exception):
            with get_db() as conn:
                row = conn.execute(
                    "SELECT id FROM sessions WHERE provider_session_id = ? ORDER BY id DESC LIMIT 1",
                    (session_id_env,),
                ).fetchone()
            if row:
                db_id = row[0]

    runtime_seconds: int | None = None
    welfare_db: int | None = None
    source: str | None = None
    if db_id is not None:
        close_session(db_id, summary=note, handover=handover, welfare=welfare)
        with get_db() as conn:
            row = conn.execute(
                "SELECT runtime_seconds, welfare, source FROM sessions WHERE id = ?", (db_id,)
            ).fetchone()
        runtime_str = ""
        welfare_str = ""
        if row:
            runtime_seconds = int(row[0]) if row[0] is not None else None
            welfare_db = int(row[1]) if row[1] is not None else None
            source = str(row[2]) if row[2] is not None else None
            if runtime_seconds:
                mins = runtime_seconds // 60
                runtime_str = f"  {mins}m"
            if welfare_db:
                welfare_str = f"  welfare {welfare_db}/10"
    else:
        runtime_str = ""
        welfare_str = ""
    handover_str = f"  handover: {handover}" if handover else ""
    print_info(f"session closed{runtime_str}{welfare_str}{handover_str}")
    if db_id is not None and runtime_seconds is not None:
        welfare_val = welfare_db or welfare
        _session_banner(db_id, note, runtime_seconds, welfare_val)
    if source in ("tg", "auto", "daemon"):
        runtime_mins = (runtime_seconds // 60) if runtime_seconds else None
        welfare_val = welfare_db or welfare
        _notify_tg(note, runtime_mins, welfare_val)
    _push_repos()


@cli("life", flags={"text": [], "done": ["-d", "--done"]})
@cli("life steward", flags={"text": [], "done": ["-d", "--done"]})
def handover(text: str | None = None, done: bool = False):
    """Show, set, or mark-done the handover pointer for the next session"""
    from life.steward import latest_handover  # noqa: PLC0415

    if done or text == "done":
        n = clear_handover()
        print_info("done" if n else "no handover to clear")
        return
    if text:
        from life.steward import update_session_handover  # noqa: PLC0415

        update_session_handover(text)
        print_info(text)
        return
    current = latest_handover()
    print(current or "(no handover)")


@cli("life", flags={"body": [], "tag": ["-t", "--tag"], "about": ["-a", "--about"], "search": ["-s", "--search"]})
@cli(
    "life steward", flags={"body": [], "tag": ["-t", "--tag"], "about": ["-a", "--about"], "search": ["-s", "--search"]}
)
def observe(
    body: str | None = None,
    tag: str | None = None,
    about: str | None = None,
    search: str | None = None,
):
    """Log a raw observation — things the human says that should persist as context"""
    if body is None:
        observations = get_observations(limit=20, tag=tag, search=search)
        if not observations:
            print("no observations")
            return
        now = datetime.now()
        for o in observations:
            rel = format_elapsed(o.logged_at, now)
            tag_str = f" #{o.tag}" if o.tag else ""
            print(f"  {ansi.muted('[' + short('o', o.id) + ']')}  {rel:<10}  {o.body}{tag_str}")
        return

    about_date: date | None = None
    if about:
        parsed_str = parse_due_date(about)
        about_date = date.fromisoformat(parsed_str) if parsed_str else None

    add_observation(body, tag=tag, about_date=about_date)
    suffix = f" #{tag}" if tag else ""
    about_str = f" (about {about_date})" if about_date else ""
    print_info(f"{body}{suffix}{about_str}")
