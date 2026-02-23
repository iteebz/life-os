from life.habits import add_habit
from life.tasks import add_task
from tests.conftest import FnCLIRunner


def test_rm_can_delete_completed_task(tmp_life_dir):
    runner = FnCLIRunner()
    runner.invoke(["add", "t", "test done flag"])
    runner.invoke(["done", "test done flag"])

    rm_result = runner.invoke(["rm", "test done flag"])
    assert rm_result.exit_code == 0

    show_result = runner.invoke(["show", "test done flag"])
    assert show_result.exit_code != 0
    assert "No task found" in show_result.stderr


def test_dashboard_shows_index_key_for_task_and_habit(tmp_life_dir):
    task_id = add_task("index key task")
    habit_id = add_habit("index key habit")

    runner = FnCLIRunner()
    dash_result = runner.invoke([])

    assert dash_result.exit_code == 0
    assert f"[{task_id[:8]}]" in dash_result.stdout
    assert f"[{habit_id[:8]}]" in dash_result.stdout


def test_habits_matrix_shows_index_key(tmp_life_dir):
    habit_id = add_habit("matrix habit")

    runner = FnCLIRunner()
    result = runner.invoke(["habits"])

    assert result.exit_code == 0
    assert f"[{habit_id[:8]}]" in result.stdout
