import pytest

from life.note import add_note, get_notes
from tests.conftest import invoke


def test_note_added_to_db(tmp_life_dir):
    note_id = add_note("observation", "abc-123", "this is a note")
    notes = get_notes("observation", "abc-123")
    assert len(notes) == 1
    assert notes[0].body == "this is a note"
    assert notes[0].entity_type == "observation"
    assert notes[0].entity_id == "abc-123"
    assert notes[0].id == note_id


def test_note_isolated_by_entity(tmp_life_dir):
    add_note("observation", "aaa", "obs note")
    add_note("improvement", "bbb", "imp note")

    obs_notes = get_notes("observation", "aaa")
    imp_notes = get_notes("improvement", "bbb")

    assert len(obs_notes) == 1
    assert obs_notes[0].body == "obs note"
    assert len(imp_notes) == 1
    assert imp_notes[0].body == "imp note"


def test_multiple_notes_ordered(tmp_life_dir):
    add_note("task", "t1", "first")
    add_note("task", "t1", "second")
    notes = get_notes("task", "t1")
    assert len(notes) == 2
    assert notes[0].body == "first"
    assert notes[1].body == "second"


def test_invalid_entity_type_raises(tmp_life_dir):
    with pytest.raises(ValueError, match="unknown entity type"):
        add_note("banana", "xyz", "some note")


def test_note_cli(tmp_life_dir):
    result = invoke(["note", "habit", "ce8f295e-0000-0000-0000-000000000000", "aligner #8"])
    assert result.exit_code == 0
    assert "noted" in result.stdout

    notes = get_notes("habit", "ce8f295e-0000-0000-0000-000000000000")
    assert len(notes) == 1
    assert notes[0].body == "aligner #8"
