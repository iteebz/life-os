from __future__ import annotations

from fncli import UsageError, cli

from life.lib.ids import parse_ref


def _resolve_and_print(ref: str) -> bool:
    prefix, fragment = parse_ref(ref)

    if prefix in ("s", "session") or (prefix is None and fragment.isdigit()):
        return _try_session(fragment)

    if prefix in ("o", "obs"):
        return _try_obs(fragment)

    if prefix in ("i", "imp"):
        return _try_imp(fragment)

    # default: task first, then obs, then imp, then session
    if _try_task(ref):
        return True
    if _try_obs(fragment):
        return True
    if _try_imp(fragment):
        return True
    return fragment.isdigit() and _try_session(fragment)


def _try_task(ref: str) -> bool:
    from life.task.domain import get_mutations, get_subtasks, get_task  # noqa: PLC0415
    from life.task.render import render_task_detail  # noqa: PLC0415

    try:
        from life.resolve import resolve_task  # noqa: PLC0415

        t = resolve_task(ref)
    except Exception:
        return False

    if t.parent_id:
        parent = get_task(t.parent_id)
        parent_subtasks = get_subtasks(t.parent_id) if parent else []
        mutations = get_mutations(t.parent_id) if parent else []
        print(render_task_detail(t, [], mutations, parent=parent, parent_subtasks=parent_subtasks))
    else:
        subtasks = get_subtasks(t.id)
        mutations = get_mutations(t.id)
        print(render_task_detail(t, subtasks, mutations))
    return True


def _try_obs(fragment: str) -> bool:
    from life.lib.ids import resolve_prefix  # noqa: PLC0415
    from life.steward import get_observations  # noqa: PLC0415

    obs = resolve_prefix(fragment, get_observations(limit=500))
    if not obs:
        return False
    tag = f"  [{obs.tag}]" if obs.tag else ""
    date_str = obs.logged_at.strftime("%Y-%m-%d %H:%M")
    print(f"obs/{obs.id[:8]}{tag}  {date_str}")
    print(f"  {obs.body}")
    if obs.about_date:
        print(f"  about: {obs.about_date}")
    return True


def _try_imp(fragment: str) -> bool:
    from life.improvements import get_improvements  # noqa: PLC0415
    from life.lib.ids import resolve_prefix  # noqa: PLC0415

    imp = resolve_prefix(fragment, get_improvements(done=True))
    if not imp:
        return False
    status = "✓" if imp.done_at else "○"
    date_str = imp.logged_at.strftime("%Y-%m-%d")
    print(f"{status} imp/{imp.id[:8]}  {date_str}")
    print(f"  {imp.body}")
    return True


def _try_session(fragment: str) -> bool:
    from life.steward import get_sessions  # noqa: PLC0415

    sessions = get_sessions(limit=500)
    target = next((s for s in sessions if str(s.id) == fragment), None)
    if not target:
        return False
    started = target.started_at.strftime("%Y-%m-%d %H:%M") if target.started_at else "?"
    print(f"session/{target.id}  {started}  [{target.state}]")
    if target.name:
        print(f"  name: {target.name}")
    print(f"  {target.summary}")
    if target.follow_ups:
        print("  follow-ups:")
        for fu in target.follow_ups:
            print(f"    · {fu}")
    if target.handover:
        print(f"  handover: {target.handover}")
    if target.welfare is not None:
        print(f"  welfare: {target.welfare}/10")
    return True


@cli("life")
def r(ref: list[str]) -> None:
    """Resolve any ref — task, obs, imp, or session — and show full context"""
    if not ref:
        raise UsageError("Usage: life r <ref>")
    joined = " ".join(ref)
    if not _resolve_and_print(joined):
        raise UsageError(f"nothing found: '{joined}'")
