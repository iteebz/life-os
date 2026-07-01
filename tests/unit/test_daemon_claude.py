"""Tests for the claude subprocess runner's heartbeat/timeout loop."""

import subprocess
from unittest.mock import MagicMock, patch

from lifeos.steward.daemon.claude import run_claude


def _mock_proc(side_effects):
    proc = MagicMock()
    proc.pid = 1234
    proc.communicate.side_effect = side_effects
    return proc


@patch("lifeos.steward.daemon.claude._claude_bin", return_value="/usr/bin/claude")
@patch("subprocess.Popen")
def test_run_claude_returns_output_immediately(mock_popen, _bin):
    mock_popen.return_value = _mock_proc([("hello", "")])
    result = run_claude("hi", timeout=600)
    assert result == "hello"


@patch("lifeos.steward.daemon.claude._claude_bin", return_value="/usr/bin/claude")
@patch("subprocess.Popen")
def test_run_claude_fires_heartbeat_before_completing(mock_popen, _bin):
    mock_popen.return_value = _mock_proc(
        [
            subprocess.TimeoutExpired(cmd="claude", timeout=120),
            subprocess.TimeoutExpired(cmd="claude", timeout=120),
            ("done", ""),
        ]
    )
    heartbeats = []
    result = run_claude("hi", timeout=600, on_heartbeat=heartbeats.append)
    assert result == "done"
    assert heartbeats == [120, 240]


@patch("lifeos.steward.daemon.claude._claude_bin", return_value="/usr/bin/claude")
@patch("subprocess.Popen")
def test_run_claude_times_out_after_exhausting_heartbeats(mock_popen, _bin):
    proc = _mock_proc([subprocess.TimeoutExpired(cmd="claude", timeout=120)] * 2 + [("", "")])
    mock_popen.return_value = proc
    result = run_claude("hi", timeout=240)
    assert result == "[steward: timed out (240s)]"
    proc.kill.assert_called_once()
