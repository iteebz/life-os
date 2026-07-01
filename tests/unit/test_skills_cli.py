from life import skills


def test_skill_records_loaded_event(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(skills, "SKILLS_DIR", tmp_path)
    (tmp_path / "sell.md").write_text("---\nwhen: selling stuff\n---\n\n# sell\nbody\n")

    recorded = []
    monkeypatch.setattr(skills.events, "record", lambda kind, **kw: recorded.append((kind, kw)))

    skills.skill("sell")

    assert recorded == [("skill.loaded", {"payload": {"name": "sell"}})]
    assert "body" in capsys.readouterr().out
