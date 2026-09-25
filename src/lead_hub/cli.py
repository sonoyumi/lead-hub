"""Command line: lead-hub serve | db upgrade | managers … | export | digest | sla."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from lead_hub import __version__
from lead_hub.api import PROJECT_ROOT, build_notifier, create_app
from lead_hub.config import Settings
from lead_hub.db import make_engine, make_session_factory, session_scope
from lead_hub.export import export_leads
from lead_hub.jobs import check_sla, send_digest
from lead_hub.models import Manager
from lead_hub.services import list_leads


def upgrade_database(settings: Settings) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    make_engine(settings.database_url).dispose()  # creates the data/ folder for SQLite
    command.upgrade(cfg, "head")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lead-hub", description="Lead intake, assignment and automation service")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the API and the scheduler")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    db = sub.add_parser("db", help="database commands")
    db.add_argument("action", choices=["upgrade"], help="upgrade: apply migrations (create/update tables)")

    managers = sub.add_parser("managers", help="manage managers")
    msub = managers.add_subparsers(dest="action", required=True)
    add = msub.add_parser("add", help="add a manager")
    add.add_argument("name")
    add.add_argument("--chat", help="Telegram chat ID for notifications")
    msub.add_parser("list", help="list managers")
    for action in ("disable", "enable"):
        m = msub.add_parser(action, help=f"{action} a manager (disabled ones get no new leads)")
        m.add_argument("manager_id", type=int)

    export = sub.add_parser("export", help="export leads to Excel")
    export.add_argument("--days", type=int, default=7, help="leads of the last N days (7)")
    export.add_argument("-o", "--output", type=Path, default=Path("leads.xlsx"))

    sub.add_parser("digest", help="send the daily digest now")
    sub.add_parser("sla", help="run the SLA check once (reminders and escalations)")
    return parser


def run(argv: list[str] | None = None, settings: Settings | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = settings or Settings()

    if args.command == "serve":
        import uvicorn

        uvicorn.run(create_app(settings), host=args.host, port=args.port)
        return 0
    if args.command == "db":
        upgrade_database(settings)
        print("База обновлена до последней версии схемы.")
        return 0

    factory = make_session_factory(make_engine(settings.database_url))
    now = datetime.now(UTC)
    with session_scope(factory) as session:
        if args.command == "managers":
            if args.action == "add":
                manager = Manager(name=args.name, telegram_chat_id=args.chat, active=True)
                session.add(manager)
                session.flush()
                print(f"Добавлен менеджер #{manager.id}: {manager.name}")
            elif args.action == "list":
                for m in session.scalars(select(Manager).order_by(Manager.id)):
                    state = "активен" if m.active else "отключён"
                    print(f"#{m.id}  {m.name}  chat={m.telegram_chat_id or '—'}  {state}")
            else:
                manager = session.get(Manager, args.manager_id)
                if manager is None:
                    print(f"Нет менеджера #{args.manager_id}", file=sys.stderr)
                    return 2
                manager.active = args.action == "enable"
                print(f"Менеджер #{manager.id} {'включён' if manager.active else 'отключён'}")
        elif args.command == "export":
            leads, total = list_leads(session, created_from=now - timedelta(days=args.days), limit=1_000_000)
            export_leads(leads, args.output, settings.tz)
            print(f"Выгружено заявок: {total} → {args.output}")
        elif args.command == "digest":
            print(send_digest(session, build_notifier(settings), settings, now, PROJECT_ROOT / "data" / "exports"))
        elif args.command == "sla":
            reminders, escalations = check_sla(session, build_notifier(settings), settings, now)
            print(f"Напоминаний: {reminders}, эскалаций: {escalations}")
    return 0


def main() -> None:
    sys.exit(run())
