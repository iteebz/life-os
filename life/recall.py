"""life recall — FTS search over Tyson's utterances."""

from datetime import UTC, datetime

from fncli import cli

from life import utterances as utter
from lifeos.core.lib.format import print_info


@cli("life", flags={"query": [], "limit": ["-n", "--limit"]})
def recall(query: list[str], limit: int = 10):
    """Search past messages by keyword"""
    q = " ".join(query) if query else ""
    if not q:
        print("usage: life recall <query>")
        return
    results = utter.search(q, limit=limit)
    if not results:
        print("no matches")
        return
    for r in results:
        ts = datetime.fromtimestamp(r["ts"], tz=UTC).strftime("%Y-%m-%d %H:%M")
        body = r["body"].replace("\n", " ").strip()
        if len(body) > 120:
            body = body[:117] + "..."
        print(f"  {ts}  {body}")


@cli("life recall", name="backfill")
def backfill():
    """Extract all inbound events into utterances table"""
    n = utter.backfill()
    total = utter.count()
    print_info(f"backfilled {n} utterances  ({total} total)")


@cli("life recall", name="count")
def count_cmd():
    """Show utterance corpus size"""
    n = utter.count()
    print(f"{n} utterances")
