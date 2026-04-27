import io
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, time
from pathlib import Path

import fncli
import pytest

import life.core.config as life_config
import life.lib.clock as clock
from life.core.errors import LifeError
from life.lib.store import configure as configure_store
from life.store.connection import reset_for_testing
from life.store.migrations import init as db_init

_discovered = False


def invoke(argv: list[str]) -> fncli.Result:
    """Invoke a life CLI command, returning captured Result.

    Handles autodiscovery once, then delegates to fncli.invoke with
    life-os-specific routing (dashboard fallback, prefix trial).
    """
    global _discovered

    if not _discovered:
        import life.cli  # noqa: PLC0415, F401 — side-effect: registers CLI commands; deferred to avoid circular
        fncli.autodiscover(Path(__file__).parent.parent / "life", "life")
        _discovered = True

    from life.dash import dashboard  # noqa: PLC0415 — same circular as above

    _dashboard = getattr(dashboard, "__wrapped__", dashboard)

    out_buf = io.StringIO()
    err_buf = io.StringIO()
    code = 0
    try:
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            if not argv or argv == ["-v"] or argv == ["--verbose"]:
                _dashboard()
                code = 0
            else:
                # Try "life <cmd>" first; fall back to bare argv for
                # commands not registered under the "life" namespace
                trial_err = io.StringIO()
                with redirect_stderr(trial_err):
                    prefixed_code = fncli.try_dispatch(["life", *argv])
                if prefixed_code == 1 and "Unknown command" in trial_err.getvalue():
                    code = fncli.dispatch(argv)
                elif prefixed_code is None:
                    code = fncli.dispatch(["life", *argv])
                else:
                    err_buf.write(trial_err.getvalue())
                    code = prefixed_code
    except SystemExit as e:
        code = int(e.code) if e.code is not None else 1
    except LifeError as e:
        err_buf.write(f"{e}\n")
        code = 1
    return fncli.Result(code, out_buf.getvalue(), err_buf.getvalue())


@pytest.fixture
def tmp_life_dir(monkeypatch, tmp_path):
    db_path = tmp_path / "store.db"
    cfg_path = tmp_path / "config.yaml"

    monkeypatch.setenv("LIFE_DIR", str(tmp_path))

    monkeypatch.setattr("life.core.config.LIFE_DIR", tmp_path)
    monkeypatch.setattr("life.core.config.DB_PATH", db_path)
    monkeypatch.setattr("life.core.config.CONFIG_PATH", cfg_path)
    monkeypatch.setattr("life.core.config.BACKUP_DIR", tmp_path / "backups")

    life_config.Config._instance = None
    monkeypatch.setattr("life.core.config._config", life_config.Config())

    configure_store(db_path)
    db_init(db_path=db_path)
    yield tmp_path
    reset_for_testing()


@pytest.fixture
def fixed_today(monkeypatch):
    fixed_date = date(2025, 10, 30)
    monkeypatch.setattr(clock, "today", lambda: fixed_date)
    monkeypatch.setattr(clock, "now", lambda: datetime.combine(fixed_date, time.min))
    return fixed_date
