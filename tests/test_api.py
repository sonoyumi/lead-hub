import pytest
from conftest import make_settings
from fastapi.testclient import TestClient

from lead_hub.api import create_app

SITE = {"X-Api-Key": "site-key"}
ADMIN = {"X-Api-Key": "admin-key"}
LEAD = {"name": "Mario", "phone": "+39 333 123 4567", "message": "Нужна консультация", "source": "landing"}


@pytest.fixture
def client(settings, factory, notifier, managers):
    with TestClient(create_app(settings, factory, notifier, run_scheduler=False)) as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_intake_requires_a_valid_key(client):
    assert client.post("/api/leads", json=LEAD).status_code == 401
    assert client.post("/api/leads", json=LEAD, headers={"X-Api-Key": "wrong"}).status_code == 401
    assert client.post("/api/leads", json=LEAD, headers=ADMIN).status_code == 401  # admin key is not an intake key


def test_intake_validation(client):
    response = client.post("/api/leads", json={"name": "Mario"}, headers=SITE)
    assert response.status_code == 422
    assert "phone or email is required" in response.text


def test_intake_creates_then_merges_and_notifies(client, notifier):
    first = client.post("/api/leads", json=LEAD, headers=SITE)
    assert first.status_code == 201 and first.json()["duplicate"] is False
    assert notifier.messages and notifier.messages[0][0] == "111"  # background task ran

    again = client.post("/api/leads", json={**LEAD, "message": "Ещё раз"}, headers=SITE)
    assert again.status_code == 200
    assert again.json() == {"id": first.json()["id"], "duplicate": True}
    assert len(notifier.messages) == 1  # duplicates do not notify again


def test_admin_api_requires_admin_key(client):
    assert client.get("/api/leads").status_code == 401
    assert client.get("/api/leads", headers=SITE).status_code == 401


def test_admin_api_disabled_without_key(factory, notifier):
    app = create_app(make_settings(admin_key=""), factory, notifier, run_scheduler=False)
    with TestClient(app) as c:
        assert c.get("/api/leads", headers=ADMIN).status_code == 403


def test_list_detail_update_flow(client):
    lead_id = client.post("/api/leads", json=LEAD, headers=SITE).json()["id"]
    client.post("/api/leads", json={**LEAD, "phone": "+39 333 999 0000", "source": "ads"}, headers=SITE)

    page = client.get("/api/leads", params={"source": "ads"}, headers=ADMIN).json()
    assert page["total"] == 1 and page["items"][0]["source"] == "ads"

    conflict = client.patch(f"/api/leads/{lead_id}", json={"status": "won"}, headers=ADMIN)
    assert conflict.status_code == 409  # new -> won is not allowed

    ok = client.patch(f"/api/leads/{lead_id}", json={"status": "in_progress", "note": "Позвонил"}, headers=ADMIN)
    assert ok.status_code == 200 and ok.json()["status"] == "in_progress"

    detail = client.get(f"/api/leads/{lead_id}", headers=ADMIN).json()
    assert [e["kind"] for e in detail["events"]] == ["created", "assigned", "status", "note"]

    assert client.get("/api/leads", params={"status": "in_progress"}, headers=ADMIN).json()["total"] == 1
    assert client.get("/api/leads/9999", headers=ADMIN).status_code == 404


def test_stats_and_managers(client):
    client.post("/api/leads", json=LEAD, headers=SITE)
    s = client.get("/api/stats", headers=ADMIN).json()
    assert s["total"] == 1 and s["by_status"]["new"] == 1

    managers = client.get("/api/managers", headers=ADMIN).json()
    assert [m["name"] for m in managers] == ["Ann", "Bob", "Off"]
    new = client.post("/api/managers", json={"name": "Carla", "telegram_chat_id": "444"}, headers=ADMIN).json()
    off = client.patch(f"/api/managers/{new['id']}", json={"active": False}, headers=ADMIN).json()
    assert off["active"] is False
