from datetime import timedelta

import pytest
from conftest import NOW
from pydantic import ValidationError

from lead_hub.models import LeadStatus
from lead_hub.schemas import LeadIn, normalize_phone
from lead_hub.services import ServiceError, intake, list_leads, stats, update_lead

DAY = timedelta(hours=24)


def lead(**kwargs) -> LeadIn:
    data = {"name": "Mario", "phone": "+39 333 123 4567", "message": "Нужна консультация", "source": "landing"}
    data.update(kwargs)
    return LeadIn(**data)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+39 (333) 123-45-67", "+393331234567"),
        ("8 (999) 123-45-67", "+89991234567"),
        ("123 45 67", "1234567"),
        ("12-34", None),
        ("+1234567890123456", None),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_lead_validation():
    assert lead(name="  Mario   Rossi ").name == "Mario Rossi"
    assert lead(phone=None, email="  Mario@Example.COM ").email == "mario@example.com"
    with pytest.raises(ValidationError, match="phone or email is required"):
        lead(phone=None, email=None)
    with pytest.raises(ValidationError, match="invalid email"):
        lead(email="not-an-email")
    with pytest.raises(ValidationError, match="7-15 digits"):
        lead(phone="12")


def test_round_robin_skips_inactive_managers(session, managers):
    ann, bob, _ = managers
    assigned = [intake(session, lead(phone=f"+3933300000{i}"), NOW, DAY).lead.manager.name for i in range(4)]
    assert assigned == ["Ann", "Bob", "Ann", "Bob"]


def test_lead_without_managers_is_unassigned(session):
    created = intake(session, lead(), NOW, DAY).lead
    assert created.manager is None
    assert [e.kind for e in created.events] == ["created"]


def test_duplicate_within_window_is_merged(session, managers):
    first = intake(session, lead(), NOW, DAY)
    again = intake(session, lead(message="Перезвоните", source="instagram"), NOW + timedelta(hours=2), DAY)
    assert again.duplicate and again.lead.id == first.lead.id
    assert again.lead.duplicates == 1
    assert "Перезвоните" in again.lead.events[-1].detail

    by_email = intake(session, lead(phone=None, email="m@x.it"), NOW, DAY)
    same_email = intake(session, lead(phone=None, email="M@X.IT"), NOW, DAY)
    assert same_email.duplicate and same_email.lead.id == by_email.lead.id


def test_same_person_after_window_is_a_new_lead(session):
    first = intake(session, lead(), NOW, DAY)
    later = intake(session, lead(), NOW + timedelta(hours=25), DAY)
    assert not later.duplicate and later.lead.id != first.lead.id


def test_status_transitions(session, managers):
    created = intake(session, lead(), NOW, DAY).lead
    with pytest.raises(ServiceError, match="new to won"):
        update_lead(session, created, status=LeadStatus.WON)
    update_lead(session, created, status=LeadStatus.IN_PROGRESS, note="Позвонил")
    update_lead(session, created, status=LeadStatus.WON)
    update_lead(session, created, status=LeadStatus.IN_PROGRESS)  # reopen is allowed
    kinds = [e.kind for e in created.events]
    assert kinds.count("status") == 3 and "note" in kinds


def test_reassign_only_to_active_manager(session, managers):
    ann, bob, off = managers
    created = intake(session, lead(), NOW, DAY).lead
    update_lead(session, created, manager_id=bob.id)
    assert created.manager_id == bob.id
    with pytest.raises(ServiceError, match="inactive"):
        update_lead(session, created, manager_id=off.id)


def test_list_filters_and_pagination(session, managers):
    for i in range(5):
        intake(
            session, lead(phone=f"+3933311111{i}", source="site" if i % 2 else "ads"), NOW + timedelta(minutes=i), DAY
        )
    session.flush()
    items, total = list_leads(session, source="ads", limit=2)
    assert total == 3 and len(items) == 2
    assert items[0].created_at >= items[1].created_at  # newest first
    items, total = list_leads(session, created_from=NOW + timedelta(minutes=3))
    assert total == 2


def test_stats_conversion_and_overdue(session, managers):
    leads = [intake(session, lead(phone=f"+3933322222{i}"), NOW, DAY).lead for i in range(4)]
    update_lead(session, leads[0], status=LeadStatus.IN_PROGRESS)
    update_lead(session, leads[0], status=LeadStatus.WON)
    update_lead(session, leads[1], status=LeadStatus.LOST)
    session.flush()
    s = stats(session, NOW + timedelta(hours=1), timedelta(minutes=30))
    assert s.total == 4
    assert s.by_status == {"new": 2, "in_progress": 0, "won": 1, "lost": 1}
    assert s.conversion == 0.5
    assert s.overdue == 2
    assert s.by_source == {"landing": 4}
