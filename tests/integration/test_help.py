from tests.conftest import invoke


def test_dash_h_shows_help(tmp_life_dir):
    result = invoke(["-h"])

    assert result.exit_code == 0
    assert "usage:" in result.stdout
