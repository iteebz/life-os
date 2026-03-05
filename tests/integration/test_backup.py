from tests.conftest import invoke


def test_backup_command_returns_path(tmp_life_dir):
    result = invoke(["backup"])

    assert result.exit_code == 0
    assert "/" in result.stdout


def test_db_backup_still_works(tmp_life_dir):
    result = invoke(["backup"])

    assert result.exit_code == 0
    assert "/" in result.stdout


def test_backup_prune(tmp_life_dir):
    invoke(["backup"])
    result = invoke(["backup", "prune"])

    assert result.exit_code == 0
    assert "pruned" in result.stdout
