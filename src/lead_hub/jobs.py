"""Automation: new-lead notifications, SLA reminders and escalations, the daily digest.

Every job receives `now` explicitly, so tests can move time forward without waiting.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path

from sqlalchemy.orm import Session

from lead_hub.config import Settings
from lead_hub.db import as_utc
from lead_hub.export import export_leads
from lead_hub.models import Lead
from lead_hub.notify import Notifier, NotifyError
from lead_hub.services import add_event, list_leads, overdue_new_leads, stats

logger = logging.getLogger(__name__)


def lead_card(lead: Lead) -> str:
    contacts = " · ".join(escape(c) for c in (lead.phone, lead.email) if c)
    message = f"\n💬 {escape(lead.message[:500])}" if lead.message else ""
    return f"<b>#{lead.id} {escape(lead.name)}</b>\n📞 {contacts}\n🔗 {escape(lead.source)}{message}"


def _target(lead: Lead, settings: Settings) -> str:
    """The manager's chat, or the admin chat if the lead has no manager or the manager has no chat."""
    if lead.manager and lead.manager.telegram_chat_id:
        return lead.manager.telegram_chat_id
    return settings.admin_chat_id


def _send(notifier: Notifier, chat_id: str, text: str) -> bool:
    if not chat_id:
        return False
    try:
        notifier.send_message(chat_id, text)
        return True
    except NotifyError as exc:
        logger.warning("Notification failed: %s", exc)
        return False


def notify_new_lead(lead: Lead, notifier: Notifier, settings: Settings) -> bool:
    who = f"\n👤 Менеджер: {escape(lead.manager.name)}" if lead.manager else "\n👤 Менеджер не назначен"
    return _send(notifier, _target(lead, settings), f"🆕 Новая заявка\n{lead_card(lead)}{who}")


def check_sla(session: Session, notifier: Notifier, settings: Settings, now: datetime) -> tuple[int, int]:
    """Reminds about new leads not taken within the SLA; escalates to the admin after 2×SLA.

    Returns (reminders, escalations). A failed send is retried on the next run instead of being marked done.
    """
    sla = timedelta(minutes=settings.sla_minutes)
    reminders = escalations = 0
    for lead in overdue_new_leads(session, now, sla):
        waited = int((now - as_utc(lead.created_at)).total_seconds() // 60)
        if lead.reminded_at is None:
            text = f"⏰ Заявка ждёт уже {waited} мин — возьмите в работу\n{lead_card(lead)}"
            if _send(notifier, _target(lead, settings), text):
                lead.reminded_at = now
                add_event(lead, "reminder", f"напоминание через {waited} мин")
                reminders += 1
        elif lead.escalated_at is None and now - as_utc(lead.created_at) >= 2 * sla:
            manager = escape(lead.manager.name) if lead.manager else "не назначен"
            text = f"🚨 Заявку не взяли в работу за {waited} мин (менеджер: {manager})\n{lead_card(lead)}"
            if _send(notifier, settings.admin_chat_id, text):
                lead.escalated_at = now
                add_event(lead, "escalation", f"эскалация через {waited} мин")
                escalations += 1
    return reminders, escalations


def send_digest(session: Session, notifier: Notifier, settings: Settings, now: datetime, export_dir: Path) -> str:
    """Today's summary (local day) + Excel with today's leads, sent to the admin chat."""
    local = now.astimezone(settings.tz)
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    s = stats(session, now, timedelta(minutes=settings.sla_minutes), since=day_start)
    leads, _ = list_leads(session, created_from=day_start, limit=100_000)
    sources = ", ".join(f"{escape(k)}: {v}" for k, v in s.by_source.items()) or "—"
    text = (
        f"📊 <b>Заявки за {local:%d.%m.%Y}</b>\n"
        f"Всего: {s.total} · новые: {s.by_status['new']} · в работе: {s.by_status['in_progress']}\n"
        f"Успех: {s.by_status['won']} · отказ: {s.by_status['lost']} · просрочено: {s.overdue}\n"
        f"Источники: {sources}"
    )
    if settings.admin_chat_id:
        path = export_leads(leads, export_dir / f"leads_{local:%Y-%m-%d}.xlsx", settings.tz)
        try:
            notifier.send_document(settings.admin_chat_id, path, caption=text)
        except NotifyError as exc:
            logger.warning("Digest was not sent: %s", exc)
    return text
