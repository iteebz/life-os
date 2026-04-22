from life.task import add_task
from tests.conftest import invoke


def test_observe_write_retrieve_roundtrip(tmp_life_dir):
    result = invoke(["steward", "observe", "Janice seemed stressed about the wedding"])
    assert result.exit_code == 0

    result = invoke(["steward", "wake"])
    assert result.exit_code == 0
    assert "Janice seemed stressed" in result.stdout


def test_observe_tag_filters_on_boot(tmp_life_dir):
    invoke(["steward", "observe", "noise entry", "--tag", "finance"])
    invoke(["steward", "observe", "janice hens weekend", "--tag", "janice"])

    result = invoke(["steward", "wake"])
    assert result.exit_code == 0
    assert "janice hens weekend" in result.stdout


def test_steward_close_persists_session(tmp_life_dir):
    result = invoke(["steward", "summary", "closed tax loop, mood 3"])
    assert result.exit_code == 0

    result = invoke(["steward", "wake"])
    assert result.exit_code == 0
    assert "closed tax loop" in result.stdout


def test_pattern_write_retrieve_roundtrip(tmp_life_dir):
    result = invoke(["steward", "observe", "Decision fatigue disengages him"])
    assert result.exit_code == 0

    result = invoke(["steward", "observe"])
    assert result.exit_code == 0
    assert "Decision fatigue" in result.stdout


def test_mood_write_retrieve_rm_cycle(tmp_life_dir):
    result = invoke(["mood", "log", "3", "--label", "flat"])
    assert result.exit_code == 0

    result = invoke(["mood", "show"])
    assert result.exit_code == 0
    assert "3" in result.stdout

    result = invoke(["mood", "rm"])
    assert result.exit_code == 0

    result = invoke(["mood", "show"])
    assert result.exit_code == 0
    assert "3" not in result.stdout


def test_boot_exits_zero_on_empty_db(tmp_life_dir):
    result = invoke(["steward", "wake"])
    assert result.exit_code == 0


def test_steward_task_visible_in_boot(tmp_life_dir):
    add_task("build mood rm", steward=True, source="tyson", tags=["steward"])

    result = invoke(["steward", "wake"])
    assert result.exit_code == 0
    assert "build mood rm" in result.stdout
