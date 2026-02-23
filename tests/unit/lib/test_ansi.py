from life.lib.ansi import ANSI


def test_ansi_constants():
    assert ANSI.BOLD == "\033[1m"
    assert ANSI.RESET == "\033[0m"
    assert len(ANSI.POOL) == 8
