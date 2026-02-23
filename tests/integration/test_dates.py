from tests.conftest import FnCLIRunner


def test_list_empty(tmp_life_dir):
    runner = FnCLIRunner()
    result = runner.invoke(["dates", "ls"])

    assert result.exit_code == 0
    assert "no dates" in result.stdout


def test_add(tmp_life_dir):
    runner = FnCLIRunner()
    result = runner.invoke(["dates", "add", "vacation", "25-12"])

    assert result.exit_code == 0
    assert "added" in result.stdout


def test_list_shows_added(tmp_life_dir):
    runner = FnCLIRunner()
    runner.invoke(["dates", "add", "launch", "01-06"])

    result = runner.invoke(["dates", "ls"])

    assert result.exit_code == 0
    assert "launch" in result.stdout


def test_list_shows_type(tmp_life_dir):
    runner = FnCLIRunner()
    runner.invoke(["dates", "add", "tyson birthday", "22-08", "--type", "birthday"])

    result = runner.invoke(["dates", "ls"])

    assert result.exit_code == 0
    assert "tyson birthday" in result.stdout
    assert "birthday" in result.stdout


def test_remove(tmp_life_dir):
    runner = FnCLIRunner()
    runner.invoke(["dates", "add", "test", "15-03"])

    result = runner.invoke(["dates", "rm", "test"])

    assert result.exit_code == 0
    assert "removed" in result.stdout


def test_add_missing_args_fails(tmp_life_dir):
    runner = FnCLIRunner()
    result = runner.invoke(["dates", "add", "name_only"])

    assert result.exit_code != 0


def test_invalid_action_fails(tmp_life_dir):
    runner = FnCLIRunner()
    result = runner.invoke(["dates", "invalid"])

    assert result.exit_code != 0


def test_invalid_date_format_fails(tmp_life_dir):
    runner = FnCLIRunner()
    result = runner.invoke(["dates", "add", "test", "2025-12-25"])

    assert result.exit_code != 0
