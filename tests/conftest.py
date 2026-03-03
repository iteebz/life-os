import io
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, time

import pytest

import life.config
import life.lib.clock as clock
from life import db
from life.lib.store import configure as configure_store


class _Result:
    def __init__(self, exit_code: int, stdout: str, stderr: str):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class FnCLIRunner:
    def invoke(self, argv: list[str]) -> _Result:
        from fncli import dispatch

        import life.cli  # noqa: F401 — registers fncli commands
        from life.dash import dashboard

        out_buf = io.StringIO()
        err_buf = io.StringIO()
        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                if not argv or argv == ["-v"] or argv == ["--verbose"]:
                    dashboard(verbose="--verbose" in argv or "-v" in argv)
                    code = 0
                else:
                    code = dispatch(["life", *argv])
        except SystemExit as e:
            code = int(e.code) if e.code is not None else 1
        return _Result(code, out_buf.getvalue(), err_buf.getvalue())


@pytest.fixture
def tmp_life_dir(monkeypatch, tmp_path):
    db_path = tmp_path / "store.db"
    cfg_path = tmp_path / "config.yaml"

    monkeypatch.setenv("LIFE_DIR", str(tmp_path))

    monkeypatch.setattr("life.config.LIFE_DIR", tmp_path)
    monkeypatch.setattr("life.config.DB_PATH", db_path)
    monkeypatch.setattr("life.config.CONFIG_PATH", cfg_path)
    monkeypatch.setattr("life.config.BACKUP_DIR", tmp_path / "backups")

    life.config.Config._instance = None
    life.config.Config._data = None
    monkeypatch.setattr("life.config._config", life.config.Config())

    configure_store(db_path)
    db.init(db_path=db_path)
    yield tmp_path


@pytest.fixture
def fixed_today(monkeypatch):
    fixed_date = date(2025, 10, 30)
    monkeypatch.setattr(clock, "today", lambda: fixed_date)
    monkeypatch.setattr(clock, "now", lambda: datetime.combine(fixed_date, time.min))
    return fixed_date
