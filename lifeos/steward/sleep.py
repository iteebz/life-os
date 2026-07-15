import contextlib
import os
from datetime import date, datetime

from fncli import cli

from life import utterances as utter
from life.backup import run_backup, run_prune
from lifeos.core.comms.messages import telegram as tg
from lifeos.core.lib import ansi
from lifeos.core.lib.dates import parse_due_date
from lifeos.core.lib.format import format_elapsed, print_info
from lifeos.core.lib.ids import short
from lifeos.core.lib.repos import push_repos
from lifeos.core.lib.store import get_db
from lifeos.steward.daemon.session import get_user_chat_id

from . import (
    add_observation,
    close_session,
    get_observations,
)


def _notify_tg(note: str, runtime_mins: int | None, welfare: int | None) -> None:
    with contextlib.suppress(Exception):
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


@cli("life", flags={"note": [], "welfare": ["-w", "--welfare"]})
@cli("life steward", flags={"note": [], "welfare": ["-w", "--welfare"]})
def sleep(note: str, welfare: int | None = None):
    """Close the session with a recap note"""
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
        kill = os.environ.get("STEWARD_MODE") in ("auto", "daemon")
        close_session(db_id, summary=note, welfare=welfare, kill_pid=kill)
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
    print_info(f"session closed{runtime_str}{welfare_str}")
    if db_id is not None and runtime_seconds is not None:
        welfare_val = welfare_db or welfare
        _session_banner(db_id, note, runtime_seconds, welfare_val)
    if source in ("tg", "auto", "daemon"):
        runtime_mins = (runtime_seconds // 60) if runtime_seconds else None
        welfare_val = welfare_db or welfare
        _notify_tg(note, runtime_mins, welfare_val)
    run_backup()
    run_prune()
    utter.backfill()
    push_repos()


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
