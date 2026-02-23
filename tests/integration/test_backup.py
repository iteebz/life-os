from tests.conftest import FnCLIRunner

runner = FnCLIRunner()


def test_backup_command_returns_path(tmp_life_dir):
    result = runner.invoke(["backup"])

    assert result.exit_code == 0
    assert "/" in result.stdout


def test_db_backup_still_works(tmp_life_dir):
    result = runner.invoke(["db", "backup"])

    assert result.exit_code == 0
    assert "/" in result.stdout


def test_backup_prune(tmp_life_dir):
    runner.invoke(["backup"])
    result = runner.invoke(["backup", "prune"])

    assert result.exit_code == 0
    assert "pruned" in result.stdout
