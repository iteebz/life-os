import io
from pathlib import Path

from life.lib.ansi import strip
from life.lib.tail import StreamParser, format_entry
from life.steward.auto import cmd_tail


class _FakePopen:
    def __init__(self, stdout_text: str, stderr_text: str, returncode: int = 0):
        self.stdout = io.StringIO(stdout_text)
        self.stderr = io.StringIO(stderr_text)
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.returncode = 124

    def kill(self):
        self.returncode = 124


def test_tail_parser_text_block_formats_ai_line():
    parser = StreamParser()
    entries = parser.parse_line(
        '{"type":"assistant","message":{"content":[{"type":"text","text":"hello world"}]}}'
    )
    assert entries
    rendered = format_entry(entries[-1])
    assert rendered is not None
    plain = strip(rendered)
    assert "hm..." in plain
    assert "hello world" in plain


def test_tail_parser_tool_result_correlates_tool_name():
    parser = StreamParser()
    parser.parse_line(
        '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_1","name":"Read","input":{"file":"a.txt"}}]}}'
    )
    entries = parser.parse_line(
        '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"toolu_1","content":"ok"}]}}'
    )
    assert entries
    rendered = format_entry(entries[-1])
    assert rendered is None


def test_tail_parser_malformed_json_falls_back_to_raw():
    parser = StreamParser()
    entries = parser.parse_line("{not-json")
    assert entries
    assert format_entry(entries[0]) is None


def test_tail_usage_zero_is_suppressed():
    parser = StreamParser()
    entries = parser.parse_line(
        '{"type":"assistant","message":{"usage":{"input_tokens":0,"output_tokens":0,"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}}'
    )
    assert entries
    assert format_entry(entries[0]) is None


def test_tail_tool_result_structured_content_is_flattened():
    parser = StreamParser()
    entries = parser.parse_line(
        '{"type":"user","message":{"content":[{"type":"tool_result","tool_name":"Read","content":[{"type":"text","text":"line1"},{"type":"text","text":"line2"}]}]}}'
    )
    assert entries
    rendered = format_entry(entries[0])
    assert rendered is None


def test_tail_parser_assistant_usage_and_tool_use_both_emitted():
    parser = StreamParser()
    entries = parser.parse_line(
        '{"type":"assistant","message":{"usage":{"input_tokens":12,"output_tokens":3,"cache_read_input_tokens":4},"content":[{"type":"tool_use","id":"toolu_1","name":"Read","input":{"file":"x.md"}}]}}'
    )
    rendered = [format_entry(e) for e in entries]
    plain = [strip(r) for r in rendered if r]
    assert any("in=12 out=3 cache=4" in p for p in plain)
    assert any("read" in p for p in plain)


def test_tail_tool_result_diff_is_summarized():
    rendered = format_entry(
        {
            "type": "tool_result",
            "tool_name": "Edit",
            "is_error": False,
            "result": (
                "diff --git a/life/commands.py b/life/commands.py\n"
                "--- a/life/commands.py\n"
                "+++ b/life/commands.py\n"
                "@@\n"
                "-old\n"
                "+new\n"
                "+line2\n"
            ),
        }
    )
    assert rendered is None


def test_tail_tool_call_formats_key_args():
    rendered = format_entry(
        {
            "type": "tool_call",
            "tool_name": "Bash",
            "args": {
                "command": "uv run pytest tests/unit/test_tail.py -q",
                "description": "run tests",
            },
        }
    )
    assert rendered is not None
    plain = strip(rendered)
    assert "run" in plain
    assert "pytest" in plain


def test_cmd_tail_streams_pretty_output(monkeypatch, tmp_path):
    home = tmp_path
    life_dir = home / "life"
    life_dir.mkdir()
    monkeypatch.setenv("ZAI_API_KEY", "test-key")
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr("life.steward.auto.time.sleep", lambda _seconds: None)

    calls: list[tuple[list[str], Path, dict | None, int | None]] = []
    outputs: list[str] = []

    def fake_popen(cmd, cwd=None, env=None, stdout=None, stderr=None, text=None, bufsize=None):
        calls.append((cmd, cwd, env, bufsize))
        return _FakePopen(
            '{"type":"assistant","message":{"content":[{"type":"text","text":"hi"}]}}\n',
            "",
            0,
        )

    monkeypatch.setattr("life.steward.auto.subprocess.Popen", fake_popen)
    monkeypatch.setattr("life.steward.auto.echo", lambda msg="", err=False: outputs.append(msg))

    cmd_tail(cycles=1, interval_seconds=0, dry_run=False)

    assert len(calls) == 1
    assert calls[0][0][0:5] == ["claude", "--print", "--output-format", "stream-json", "--verbose"]
    assert calls[0][1] == life_dir
    assert calls[0][2] is not None
    assert "ANTHROPIC_AUTH_TOKEN" not in calls[0][2]
    plain_outputs = [strip(o) for o in outputs]
    assert any("hm..." in o and "hi" in o for o in plain_outputs)


def test_cmd_tail_raw_mode_prints_raw_lines(monkeypatch, tmp_path):
    home = tmp_path
    life_dir = home / "life"
    life_dir.mkdir()
    monkeypatch.setenv("ZAI_API_KEY", "test-key")
    monkeypatch.setattr(Path, "home", lambda: home)

    outputs: list[str] = []

    def fake_popen(cmd, cwd=None, env=None, stdout=None, stderr=None, text=None, bufsize=None):
        return _FakePopen('{"type":"assistant"}\n', "", 0)

    monkeypatch.setattr("life.steward.auto.subprocess.Popen", fake_popen)
    monkeypatch.setattr("life.steward.auto.echo", lambda msg="", err=False: outputs.append(msg))

    cmd_tail(cycles=1, raw=True)
    assert '{"type":"assistant"}' in outputs


def test_cmd_tail_retries_then_succeeds(monkeypatch, tmp_path):
    home = tmp_path
    life_dir = home / "life"
    life_dir.mkdir()
    monkeypatch.setenv("ZAI_API_KEY", "test-key")
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr("life.steward.auto.time.sleep", lambda _seconds: None)

    calls = {"n": 0}

    def fake_popen(cmd, cwd=None, env=None, stdout=None, stderr=None, text=None, bufsize=None):
        calls["n"] += 1
        return _FakePopen("", "boom\n", 1 if calls["n"] == 1 else 0)

    monkeypatch.setattr("life.steward.auto.subprocess.Popen", fake_popen)
    cmd_tail(cycles=1, retries=2, retry_delay_seconds=0)
    assert calls["n"] == 2


def test_cmd_tail_suppresses_duplicate_usage_and_errors(monkeypatch, tmp_path):
    home = tmp_path
    life_dir = home / "life"
    life_dir.mkdir()
    monkeypatch.setenv("ZAI_API_KEY", "test-key")
    monkeypatch.setattr(Path, "home", lambda: home)

    outputs: list[str] = []

    def fake_popen(cmd, cwd=None, env=None, stdout=None, stderr=None, text=None, bufsize=None):
        return _FakePopen(
            '{"type":"error","message":"permission denied"}\n'
            '{"type":"error","message":"permission denied"}\n'
            '{"type":"assistant","message":{"usage":{"input_tokens":1,"output_tokens":2,"cache_read_input_tokens":3,"cache_creation_input_tokens":0}}}\n'
            '{"type":"assistant","message":{"usage":{"input_tokens":1,"output_tokens":2,"cache_read_input_tokens":3,"cache_creation_input_tokens":0}}}\n',
            "",
            0,
        )

    monkeypatch.setattr("life.steward.auto.subprocess.Popen", fake_popen)
    monkeypatch.setattr("life.steward.auto.echo", lambda msg="", err=False: outputs.append(msg))

    cmd_tail(cycles=1)
    plain = [strip(o) for o in outputs]
    assert plain.count("  error. permission denied") == 1
    assert plain.count("  in=1 out=2 cache=3") == 1


def test_cmd_tail_dry_run_does_not_execute(monkeypatch, tmp_path):
    home = tmp_path
    life_dir = home / "life"
    life_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)

    called = {"popen": 0}

    def fake_popen(cmd, cwd=None, env=None, stdout=None, stderr=None, text=None, bufsize=None):
        called["popen"] += 1
        raise AssertionError("subprocess.Popen should not be called in dry-run")

    monkeypatch.setattr("life.steward.auto.subprocess.Popen", fake_popen)

    cmd_tail(cycles=1, dry_run=True)
    assert called["popen"] == 0
