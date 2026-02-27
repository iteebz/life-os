from datetime import datetime

from fncli import cli

from ..lib import ansi
from ..lib.errors import exit_error
from . import _rel


@cli("steward", flags={"body": []})
def improve(
    body: str | None = None,
    log: bool = False,
    done: str | None = None,
):
    """Log a system improvement or mark one done"""
    from ..improvements import (
        add_improvement,
        get_improvements,
        mark_improvement_done,
    )

    if done is not None:
        target = mark_improvement_done(done)
        if target:
            print(f"✓ {target.body}")
        else:
            exit_error(f"no open improvement matching '{done}'")
        return

    if log or not body:
        improvements = get_improvements()
        if not improvements:
            print("no open improvements")
            return
        now = datetime.now()
        for i in improvements:
            rel = _rel((now - i.logged_at).total_seconds())
            print(f"  {ansi.muted('[' + i.uuid[:8] + ']')}  {rel:<10}  {i.body}")
        return

    add_improvement(body)
    print(f"→ {body}")
