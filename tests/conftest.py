from datetime import UTC, datetime
from pathlib import Path

import pytest

from lead_hub.config import Settings
from lead_hub.db import make_engine, make_session_factory
from lead_hub.models import Base, Manager
from lead_hub.notify import NotifyError

NOW = datetime(2026, 9, 25, 10, 0, tzinfo=UTC)


class RecordingNotifier:
    def __init__(self, fail: bool = False) -> None:
        self.messages: list[tuple[str, str]] = []
        self.documents: list[tuple[str, Path, str]] = []
        self.fail = fail

    def send_message(self, chat_id: str, text: str) -> None:
        if self.fail:
            raise NotifyError("down")
        self.messages.append((chat_id, text))

    def send_document(self, chat_id: str, path: Path, caption: str = "") -> None:
        if self.fail:
            raise NotifyError("down")
        self.documents.append((chat_id, path, caption))


def make_settings(**overrides) -> Settings:
    values = dict(
        database_url="sqlite:///:memory:",
        intake_keys=["site-key"],
        admin_key="admin-key",
        admin_chat_id="999",
        sla_minutes=30,
        duplicate_window_hours=24,
        timezone="Europe/Rome",
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def factory(settings):
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    yield make_session_factory(engine)
    engine.dispose()


@pytest.fixture
def session(factory):
    with factory() as s:
        yield s


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture
def managers(session):
    ann = Manager(name="Ann", telegram_chat_id="111", active=True)
    bob = Manager(name="Bob", telegram_chat_id="222", active=True)
    off = Manager(name="Off", telegram_chat_id="333", active=False)
    session.add_all([ann, bob, off])
    session.commit()
    return ann, bob, off
