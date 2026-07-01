from life.hooks import signals, skills


def _isolate_state(tmp_path, monkeypatch):
    monkeypatch.setattr(signals, "_state_path", lambda: tmp_path / "state")


def test_no_match_returns_empty(tmp_path, monkeypatch):
    _isolate_state(tmp_path, monkeypatch)
    monkeypatch.setattr(skills, "_SKILLS_DIR", tmp_path)
    assert skills.inject_matching_skills("what's the weather", "sess1") == []


def test_keyword_match_injects_body(tmp_path, monkeypatch):
    _isolate_state(tmp_path, monkeypatch)
    monkeypatch.setattr(skills, "_SKILLS_DIR", tmp_path)
    (tmp_path / "sell.md").write_text("---\nkeywords: [sell, marketplace]\n---\n\n# sell\nlist an item.\n")

    result = skills.inject_matching_skills("help me sell my old chair", "sess1")

    assert len(result) == 1
    assert "[skill: sell]" in result[0]
    assert "list an item" in result[0]


def test_dedupes_within_same_session(tmp_path, monkeypatch):
    _isolate_state(tmp_path, monkeypatch)
    monkeypatch.setattr(skills, "_SKILLS_DIR", tmp_path)
    (tmp_path / "sell.md").write_text("---\nkeywords: [sell]\n---\n\n# sell\n")

    first = skills.inject_matching_skills("sell this", "sessA")
    second = skills.inject_matching_skills("sell this again", "sessA")

    assert len(first) == 1
    assert second == []


def test_reinjects_for_different_session(tmp_path, monkeypatch):
    _isolate_state(tmp_path, monkeypatch)
    monkeypatch.setattr(skills, "_SKILLS_DIR", tmp_path)
    (tmp_path / "sell.md").write_text("---\nkeywords: [sell]\n---\n\n# sell\n")

    first = skills.inject_matching_skills("sell this", "sessA")
    second = skills.inject_matching_skills("sell this", "sessB")

    assert len(first) == 1
    assert len(second) == 1


def test_skills_without_keywords_are_unaffected(tmp_path, monkeypatch):
    _isolate_state(tmp_path, monkeypatch)
    monkeypatch.setattr(skills, "_SKILLS_DIR", tmp_path)
    (tmp_path / "close.md").write_text("---\nwhen: ending a session\n---\n\n# close\n")

    assert skills.inject_matching_skills("sell close ending", "sess1") == []
