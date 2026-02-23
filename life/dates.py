import fncli
from fncli import cli

from .lib.dates import add_date, list_dates, remove_date
from .lib.errors import echo, exit_error


@cli("life dates", name="add")
def add(name: str, date: str, type_: str = "other"):
    """Add a recurring date (DD-MM)"""
    try:
        add_date(name, date, type_)
    except ValueError as e:
        exit_error(str(e))
        return
    echo(f"added: {name} on {date}")


@cli("life dates", name="rm")
def rm(name: str):
    """Remove a recurring date"""
    remove_date(name)
    echo(f"removed: {name}")


@cli("life dates", name="ls")
def ls():
    """List all recurring dates"""
    items = list_dates()
    if not items:
        echo("no dates set")
        return
    for d in items:
        type_label = f"  [{d['type']}]" if d["type"] != "other" else ""
        days = d["days_until"]
        days_str = "today" if days == 0 else f"in {days}d"
        echo(f"  {d['name']} — {d['day']:02d}-{d['month']:02d}{type_label}  ({days_str})")


fncli._REGISTRY["life dates"] = fncli._REGISTRY["life dates ls"]
