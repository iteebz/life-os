from atail import StreamParser, format_entry
from atail.ansi import strip


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
    assert rendered is not None
    assert "read" in strip(rendered)


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
    from atail.normalize import normalize_event

    tool_map: dict[str, str] = {}
    result = normalize_event(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "content": [
                            {"type": "text", "text": "line1"},
                            {"type": "text", "text": "line2"},
                        ],
                    }
                ]
            },
        },
        tool_map=tool_map,
    )
    assert result[0]["result"] == "line1\nline2"


def test_tail_parser_assistant_usage_and_tool_use_both_emitted():
    parser = StreamParser()
    entries = parser.parse_line(
        '{"type":"assistant","message":{"usage":{"input_tokens":12,"output_tokens":3,"cache_read_input_tokens":4},"content":[{"type":"tool_use","id":"toolu_1","name":"Read","input":{"file":"x.md"}}]}}'
    )
    rendered = [format_entry(e) for e in entries]
    plain = [strip(r) for r in rendered if r]
    assert any("in=12 out=3 cache=4" in p for p in plain)
    flushed = parser.flush()
    flushed_plain = [strip(r) for r in [format_entry(e) for e in flushed] if r]
    assert any("read" in p for p in flushed_plain)


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
