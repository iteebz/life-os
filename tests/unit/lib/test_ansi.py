from life.lib.ansi import DEFAULT, POOL, Theme, bold, dim, strip, strip_markdown


def test_theme_defaults():
    assert DEFAULT.bold == "\033[1m"
    assert DEFAULT.reset == "\033[0m"
    assert len(POOL) == 8


def test_theme_colors():
    t = Theme()
    assert t.red == "\033[38;5;203m"
    assert t.green == "\033[38;5;114m"
    assert t.muted == "\033[90m"


def test_bold():
    result = bold("hi")
    assert "\033[1m" in result
    assert "hi" in result
    assert "\033[0m" in result


def test_dim():
    result = dim("hi")
    assert "\033[2m" in result
    assert "hi" in result


def test_strip():
    assert strip("\033[1mhello\033[0m") == "hello"


def test_strip_markdown():
    assert strip_markdown("**bold**") == "bold"
    assert strip_markdown("`code`") == "code"
