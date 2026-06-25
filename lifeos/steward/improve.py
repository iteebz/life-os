from datetime import datetime

from fncli import cli

from life.improvements import Improvement, add_improvement, get_improvements, mark_improvement_done, promote_improvement
from lifeos.core.errors import NotFoundError
from lifeos.core.lib import ansi
from lifeos.core.lib.format import format_elapsed, print_info, print_ok
from lifeos.core.lib.ids import short


def _print_improvements(items: list[Improvement], show_done: bool = False) -> None:
    now = datetime.now()
    for i in items:
        ts = i.done_at if (show_done and i.done_at) else i.logged_at
        rel = format_elapsed(ts, now)
        tag = short("i", i.id)
        if show_done and i.done_at:
            label = ansi.muted(f"[{tag}]")
            marker = ansi.green("✓")
            print(f"  {label}  {rel:<12}  {marker}  {ansi.muted(i.body)}")
        elif i.promoted_at:
            label = ansi.muted(f"[{tag}]")
            initiative_str = f"  → {i.initiative}" if i.initiative else ""
            print(f"  {label}  {rel:<12}  {ansi.muted('↑')}  {ansi.muted(i.body)}{ansi.muted(initiative_str)}")
        else:
            label = ansi.muted(f"[{tag}]")
            print(f"  {label}  {rel:<12}  {i.body}")


@cli("life", flags={"body": []})
@cli("life steward", flags={"body": []})
def improve(
    body: str | None = None,
    log: bool = False,
    done: str | None = None,
    promote: str | None = None,
    to: str | None = None,
):
    """Log a system improvement, promote to initiative, or mark one done"""
    if done is not None:
        target = mark_improvement_done(done)
        if target:
            print_ok(target.body)
        else:
            raise NotFoundError(f"no open improvement matching '{done}'")
        return

    if promote is not None:
        initiative = to or ""
        target = promote_improvement(promote, initiative)
        if target:
            suffix = f" → {initiative}" if initiative else ""
            print_ok(f"promoted: {target.body}{suffix}")
        else:
            raise NotFoundError(f"no improvement matching '{promote}'")
        return

    if log or not body or body == "list":
        improvements = get_improvements()
        if not improvements:
            print_info("no open improvements")
            return
        _print_improvements(improvements)
        return

    add_improvement(body)
    print_info(body)


@cli("life steward improve", flags={"id": []})
def close(id: str) -> None:
    """Close an improvement by id or prefix"""
    target = mark_improvement_done(id)
    if target:
        print_ok(target.body)
    else:
        raise NotFoundError(f"no open improvement matching '{id}'")


@cli("life")
@cli("life steward")
def improvements(done: bool = False, promoted: bool = False) -> None:
    """Show outstanding (or completed/promoted) improvements"""
    if done:
        items = [i for i in get_improvements(done=True) if i.done_at]
        if not items:
            print("no completed improvements")
            return
        print(ansi.muted(f"  completed ({len(items)})\n"))
        _print_improvements(items, show_done=True)
    elif promoted:
        items = [i for i in get_improvements(include_promoted=True) if i.promoted_at]
        if not items:
            print("no promoted improvements")
            return
        print(ansi.muted(f"  promoted ({len(items)})\n"))
        _print_improvements(items)
    else:
        items = get_improvements(done=False)
        if not items:
            print("nothing outstanding")
            return
        print(ansi.muted(f"  outstanding ({len(items)})\n"))
        _print_improvements(items)
