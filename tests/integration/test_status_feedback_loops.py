from datetime import date, datetime, timedelta

from life import db
from tests.conftest import FnCLIRunner


def test_status_shows_feedback_metrics(tmp_life_dir):
    runner = FnCLIRunner()
    runner.invoke(["add", "call bank", "--tag", "finance", "--due", "today"])
    runner.invoke(["add", "wedding vids", "--tag", "janice"])

    result = runner.invoke(["status"])

    assert result.exit_code == 0
    assert "HEALTH:" in result.stdout
    assert "FLAGS:" in result.stdout
    assert "HOT LIST:" in result.stdout


def test_status_flags_relationship_and_stuck_task(tmp_life_dir):
    runner = FnCLIRunner()
    runner.invoke(["add", "wedding vids", "--tag", "janice"])
    runner.invoke(["add", "call bank", "--tag", "finance"])

    today = date.today()
    with db.get_db() as conn:
        conn.execute(
            "UPDATE tasks SET created = ? WHERE content = ?",
            ((today - timedelta(days=4)).isoformat(), "call bank"),
        )

    result = runner.invoke(["status"])

    assert result.exit_code == 0
    assert "FLAGS:" in result.stdout
    assert "partner_at_risk" in result.stdout
    assert "stuck" in result.stdout


def test_stats_admin_closure_rate_counts_recent_overdue_closures(tmp_life_dir):
    runner = FnCLIRunner()
    today = date.today()
    runner.invoke(["add", "invoice jeff", "--tag", "finance", "--due", "today"])
    runner.invoke(["done", "invoice jeff"])

    yesterday = datetime.combine(today - timedelta(days=1), datetime.min.time())
    with db.get_db() as conn:
        conn.execute(
            "UPDATE tasks SET scheduled_date = ?, created = ?, completed_at = ? WHERE content = ?",
            (
                (today - timedelta(days=1)).isoformat(),
                yesterday.isoformat(),
                datetime.combine(today, datetime.min.time()).isoformat(),
                "invoice jeff",
            ),
        )

    result = runner.invoke(["stats"])

    assert result.exit_code == 0
    assert "STATS (7d):" in result.stdout
    assert "closure:  100% (1/1)" in result.stdout
