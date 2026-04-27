from datetime import date, datetime, timedelta

import life.config
from life.lib.store import get_db
from tests.conftest import invoke


def test_status_shows_feedback_metrics(tmp_life_dir):
    invoke(["task", "call bank", "--tag", "finance", "--due", "today"])
    invoke(["task", "wedding vids", "--tag", "janice"])

    result = invoke(["status"])

    assert result.exit_code == 0
    assert "HEALTH:" in result.stdout
    assert "FLAGS:" in result.stdout
    assert "HOT LIST:" in result.stdout


def test_status_flags_relationship_and_stuck_task(tmp_life_dir):
    life.config._config._data["partner_tag"] = "janice"
    invoke(["task", "wedding vids", "--tag", "janice"])
    invoke(["task", "call bank", "--tag", "finance"])

    today = date.today()
    with get_db() as conn:
        conn.execute(
            "UPDATE tasks SET created = ? WHERE content = ?",
            ((today - timedelta(days=4)).isoformat(), "call bank"),
        )

    result = invoke(["status"])

    assert result.exit_code == 0
    assert "FLAGS:" in result.stdout
    assert "partner_at_risk" in result.stdout
    assert "stuck" in result.stdout


def test_stats_closure_weighted_by_tag(tmp_life_dir):
    today = date.today()
    invoke(["task", "invoice jeff", "--tag", "finance", "--due", "today"])
    invoke(["done", "invoice jeff"])

    yesterday = datetime.combine(today - timedelta(days=1), datetime.min.time())
    with get_db() as conn:
        conn.execute(
            "UPDATE tasks SET scheduled_date = ?, created = ?, completed_at = ? WHERE content = ?",
            (
                (today - timedelta(days=1)).isoformat(),
                yesterday.isoformat(),
                datetime.combine(today, datetime.min.time()).isoformat(),
                "invoice jeff",
            ),
        )

    result = invoke(["stats"])

    assert result.exit_code == 0
    assert "STATS (7d):" in result.stdout
    assert "tasks:    100%" in result.stdout
    assert "pts)" in result.stdout
