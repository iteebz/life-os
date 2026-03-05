from datetime import datetime

from fncli import cli

from life.core.errors import NotFoundError
from life.lib import ansi
from life.lib.format import format_elapsed
from life.lib.ids import short


@cli("steward", flags={"body": []})
def improve(
    body: str | None = None,
    log: bool = False,
    done: str | None = None,
):
    """Log a system improvement or mark one done"""
    from life.improvements import add_improvement, get_improvements, mark_improvement_done

    if done is not None:
        target = mark_improvement_done(done)
        if target:
            print(f"✓ {target.body}")
        else:
            raise NotFoundError(f"no open improvement matching '{done}'")
        return

    if log or not body:
        improvements = get_improvements()
        if not improvements:
            print("no open improvements")
            return
        now = datetime.now()
        for i in improvements:
            rel = format_elapsed(i.logged_at, now)
            print(f"  {ansi.muted('[' + short('i', i.id) + ']')}  {rel:<10}  {i.body}")
        return

    add_improvement(body)
    print(f"→ {body}")
