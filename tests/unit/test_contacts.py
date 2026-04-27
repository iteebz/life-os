from datetime import datetime, timedelta

from life.contacts import (
    add_contact,
    find_contact,
    get_contacts,
    get_stale_contacts,
    log_contact,
)
from life.lib.store import get_db


def test_add_and_list(tmp_life_dir):
    add_contact("Alice", cadence_days=14)
    contacts = get_contacts()
    assert len(contacts) == 1
    assert contacts[0].name == "Alice"
    assert contacts[0].cadence_days == 14
    assert contacts[0].last_contact_at is None


def test_log_updates_timestamp(tmp_life_dir):
    add_contact("Bob", cadence_days=30)
    result = log_contact("Bob")
    assert result is not None
    assert result.last_contact_at is not None


def test_log_case_insensitive(tmp_life_dir):
    add_contact("Charlie")
    result = log_contact("charlie")
    assert result is not None
    assert result.name == "Charlie"


def test_log_nonexistent_returns_none(tmp_life_dir):
    assert log_contact("nobody") is None


def test_find_exact(tmp_life_dir):
    add_contact("Dave")
    assert find_contact("Dave") is not None
    assert find_contact("dave") is not None


def test_find_substring(tmp_life_dir):
    add_contact("Elizabeth")
    assert find_contact("liza") is not None


def test_find_fuzzy(tmp_life_dir):
    add_contact("Francis")
    result = find_contact("Francs")
    assert result is not None
    assert result.name == "Francis"


def test_find_no_match(tmp_life_dir):
    add_contact("George")
    assert find_contact("zzzzz") is None


def test_stale_never_contacted(tmp_life_dir):
    add_contact("Helen", cadence_days=7)
    stale = get_stale_contacts()
    assert len(stale) == 1
    assert stale[0][0].name == "Helen"
    assert stale[0][1] is None  # never contacted


def test_stale_past_cadence(tmp_life_dir, fixed_today):
    add_contact("Ivan", cadence_days=7)
    # Backdate last_contact_at to 10 days before fixed_today
    old = datetime.combine(fixed_today - timedelta(days=10), datetime.min.time()).isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE contacts SET last_contact_at = ? WHERE name = 'Ivan'",
            (old,),
        )
    stale = get_stale_contacts()
    assert any(c.name == "Ivan" for c, _ in stale)


def test_not_stale_within_cadence(tmp_life_dir):
    add_contact("Jane", cadence_days=30)
    log_contact("Jane")
    stale = get_stale_contacts()
    assert not any(c.name == "Jane" for c, _ in stale)


def test_soft_delete_hides_contact(tmp_life_dir):
    add_contact("Kate")
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE contacts SET deleted_at = ? WHERE name = 'Kate'",
            (now,),
        )
    assert len(get_contacts()) == 0


def test_stale_sorted_by_staleness(tmp_life_dir, fixed_today):
    add_contact("Liam", cadence_days=7)
    add_contact("Mia", cadence_days=7)
    # Liam contacted 20d ago, Mia contacted 10d ago (relative to fixed_today)
    t = datetime.min.time()
    with get_db() as conn:
        conn.execute(
            "UPDATE contacts SET last_contact_at = ? WHERE name = 'Liam'",
            (datetime.combine(fixed_today - timedelta(days=20), t).isoformat(),),
        )
        conn.execute(
            "UPDATE contacts SET last_contact_at = ? WHERE name = 'Mia'",
            (datetime.combine(fixed_today - timedelta(days=10), t).isoformat(),),
        )
    stale = get_stale_contacts()
    names = [c.name for c, _ in stale]
    assert names.index("Liam") < names.index("Mia")
