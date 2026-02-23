from life.tasks import add_task
from tests.conftest import FnCLIRunner

runner = FnCLIRunner()


def test_observe_write_retrieve_roundtrip(tmp_life_dir):
    result = runner.invoke(["steward", "observe", "Janice seemed stressed about the wedding"])
    assert result.exit_code == 0

    result = runner.invoke(["steward", "boot"])
    assert result.exit_code == 0
    assert "Janice seemed stressed" in result.stdout


def test_observe_tag_filters_on_boot(tmp_life_dir):
    runner.invoke(["steward", "observe", "noise entry", "--tag", "finance"])
    runner.invoke(["steward", "observe", "janice hens weekend", "--tag", "janice"])

    result = runner.invoke(["steward", "boot"])
    assert result.exit_code == 0
    assert "janice hens weekend" in result.stdout


def test_steward_close_persists_session(tmp_life_dir):
    result = runner.invoke(["steward", "close", "closed tax loop, mood 3"])
    assert result.exit_code == 0

    result = runner.invoke(["steward", "boot"])
    assert result.exit_code == 0
    assert "closed tax loop" in result.stdout


def test_pattern_write_retrieve_roundtrip(tmp_life_dir):
    result = runner.invoke(["pattern", "add", "Decision fatigue disengages him"])
    assert result.exit_code == 0

    result = runner.invoke(["pattern", "log"])
    assert result.exit_code == 0
    assert "Decision fatigue" in result.stdout


def test_mood_write_retrieve_rm_cycle(tmp_life_dir):
    result = runner.invoke(["mood", "log", "3", "--label", "flat"])
    assert result.exit_code == 0

    result = runner.invoke(["mood", "show"])
    assert result.exit_code == 0
    assert "3" in result.stdout

    result = runner.invoke(["mood", "rm"])
    assert result.exit_code == 0

    result = runner.invoke(["mood", "show"])
    assert result.exit_code == 0
    assert "3" not in result.stdout


def test_boot_exits_zero_on_empty_db(tmp_life_dir):
    result = runner.invoke(["steward", "boot"])
    assert result.exit_code == 0


def test_steward_task_visible_in_boot(tmp_life_dir):
    add_task("build mood rm", steward=True, source="tyson", tags=["steward"])

    result = runner.invoke(["steward", "boot"])
    assert result.exit_code == 0
    assert "build mood rm" in result.stdout
