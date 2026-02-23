import sqlite3

from life.backup import _is_snapshot_dir, _validate_backup, run_backup, run_prune


def test_backup_creates_dir(tmp_life_dir):
    result = run_backup()
    assert result["path"].exists()
    assert result["path"].is_dir()


def test_backup_contains_db(tmp_life_dir):
    result = run_backup()
    assert (result["path"] / "life.db").exists()


def test_backup_timestamp_format(tmp_life_dir):
    result = run_backup()
    name = result["path"].name
    assert name[:8].isdigit()
    assert name[8] == "_"
    assert name[9:15].isdigit()
    assert name[15] == "_"
    assert name[16:].isdigit()


def test_backup_in_backup_dir(tmp_life_dir):
    result = run_backup()
    assert str(result["path"]).startswith(str(tmp_life_dir / "backups"))


def test_backup_excludes_backups_subdir(tmp_life_dir):
    result = run_backup()
    assert not (result["path"] / "backups").exists()


def test_backup_integrity_ok(tmp_life_dir):
    result = run_backup()
    assert result["integrity_ok"] is True


def test_backup_has_row_count(tmp_life_dir):
    result = run_backup()
    assert isinstance(result["rows"], int)
    assert result["rows"] >= 0


def test_backup_first_has_no_delta(tmp_life_dir):
    result = run_backup()
    assert result["delta_total"] is None


def test_backup_second_has_delta(tmp_life_dir):
    run_backup()
    result = run_backup()
    assert result["delta_total"] is not None


def test_backup_missing_source_returns_error(tmp_life_dir, monkeypatch):
    monkeypatch.setattr("life.config.DB_PATH", tmp_life_dir / "nonexistent.db")
    result = run_backup()
    assert result["path"] is None
    assert "source db missing" in result["error"]


def test_backup_validates_row_counts(tmp_life_dir):
    from life.tasks import add_task

    add_task("safety test 1")
    add_task("safety test 2")
    result = run_backup()
    assert result["path"] is not None
    assert result["rows"] > 0
    assert "error" not in result


def test_validate_backup_catches_empty(tmp_life_dir):
    from life import config
    from life.tasks import add_task

    add_task("data")
    empty = tmp_life_dir / "empty.db"
    conn = sqlite3.connect(empty)
    conn.close()
    ok, reason = _validate_backup(empty, config.DB_PATH)
    assert not ok
    assert "no rows" in reason


def test_validate_backup_catches_massive_loss(tmp_life_dir):
    from life import config
    from life.tasks import add_task

    for i in range(10):
        add_task(f"task {i}")

    partial = tmp_life_dir / "partial.db"
    conn = sqlite3.connect(partial)
    conn.execute(
        "CREATE TABLE tasks (id TEXT, content TEXT, focus INTEGER, scheduled_date TEXT, created TEXT, completed_at TEXT, parent_id TEXT, scheduled_time TEXT, blocked_by TEXT, description TEXT, steward INTEGER DEFAULT 0, source TEXT, is_deadline INTEGER DEFAULT 0)"
    )
    conn.execute("INSERT INTO tasks (id, content) VALUES ('x', 'only one')")
    conn.commit()
    conn.close()

    ok, _reason = _validate_backup(partial, config.DB_PATH)
    assert not ok


def test_is_snapshot_dir_filters_non_snapshots(tmp_life_dir):
    migrations_dir = tmp_life_dir / "backups" / "migrations"
    migrations_dir.mkdir(parents=True, exist_ok=True)
    assert not _is_snapshot_dir(migrations_dir)

    snap = tmp_life_dir / "backups" / "20260101_120000_123456"
    snap.mkdir(parents=True)
    assert _is_snapshot_dir(snap)


def test_prune_keeps_latest(tmp_life_dir):
    run_backup()
    run_backup()
    run_backup()
    removed = run_prune(keep_daily_days=0, keep_hourly_hours=0)
    assert removed >= 0
    result = run_backup()
    assert result["path"] is not None


def test_prune_empty_dir(tmp_life_dir):
    assert run_prune() == 0
