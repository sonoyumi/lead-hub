# 📥 Lead Hub

<p>
  <a href="https://github.com/sonoyumi/lead-hub/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/sonoyumi/lead-hub/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white">
  <img alt="SQLAlchemy" src="https://img.shields.io/badge/SQLAlchemy-2.0-D71F00">
  <img alt="Alembic" src="https://img.shields.io/badge/migrations-Alembic-6BA81E">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
</p>

**🇬🇧 [English](#en)** · **🇷🇺 [Русский](#ru)**

---

<a name="en"></a>

## 🇬🇧 English

A small lead-management backend for businesses that get requests from websites and landing pages.
Forms send leads to a REST API; the service removes duplicates, assigns each lead to a manager,
notifies them in Telegram, reminds and escalates if nobody picks the lead up, and sends a daily
digest with an Excel file. A management API gives the lead list, statuses and conversion stats.

### What it automates

```
website form ──POST /api/leads──► validate & normalize phone/email
                                       │
                     same person within 24 h? ──yes──► merge into the existing lead (no new notification)
                                       │ no
                                       ▼
                      assign a manager (round-robin, active only) ──► 🆕 Telegram to the manager
                                       │
             not taken in SLA minutes ─► ⏰ reminder to the manager
             not taken in 2×SLA        ─► 🚨 escalation to the admin
                                       │
                    every day at 19:00 ─► 📊 digest + Excel of today's leads to the admin
```

### Features

- **REST API (FastAPI):** intake endpoint for forms (per-site keys), admin endpoints for leads, statuses,
  managers and statistics; interactive docs at `/docs`.
- **Database (SQLAlchemy 2.0):** SQLite by default, PostgreSQL by changing one setting;
  **Alembic migrations** — a test checks that the migrations match the models exactly.
- **Duplicates:** the same phone or email within 24 h (configurable) is merged into the first lead;
  phones are normalized (`+39 (333) 123-45-67` = `393331234567`).
- **Status pipeline** with allowed transitions (`new → in_progress → won/lost`, reopen allowed)
  and a full **audit trail** (created, duplicate, assigned, status, note, reminder, escalation).
- **Automation (APScheduler):** SLA check every minute, daily digest at a configured local hour.
  A failed Telegram send is retried on the next run instead of being lost.
- **Security:** API keys compared in constant time, admin API off until `ADMIN_KEY` is set,
  secrets never printed (`SecretStr`), user input HTML-escaped in Telegram and kept as text in Excel.
- **CLI:** `lead-hub db upgrade`, `serve`, `managers add/list/enable/disable`, `export`, `digest`, `sla`.

### API

| Method | Path | Key | What it does |
|---|---|---|---|
| `POST` | `/api/leads` | intake | New lead → `201`, duplicate → `200` with `"duplicate": true` |
| `GET` | `/api/leads?status=&source=&manager_id=&date_from=&date_to=&limit=&offset=` | admin | Filtered, paginated list |
| `GET` | `/api/leads/{id}` | admin | Lead with its history |
| `PATCH` | `/api/leads/{id}` | admin | `{"status": "in_progress", "manager_id": 2, "note": "…"}`; illegal transition → `409` |
| `GET` | `/api/stats?days=30` | admin | Counts by status and source, conversion, overdue |
| `GET/POST/PATCH` | `/api/managers[/{id}]` | admin | List, add, enable/disable managers |
| `GET` | `/health` | — | Service and database check |

Keys go in the `X-Api-Key` header.

```bash
curl -X POST http://localhost:8000/api/leads \
  -H "X-Api-Key: <intake key>" -H "Content-Type: application/json" \
  -d '{"name": "Mario Rossi", "phone": "+39 333 123 4567", "message": "Need a quote", "source": "landing"}'
# {"id": 1, "duplicate": false}
```

### Quick start

```bash
git clone https://github.com/sonoyumi/lead-hub.git
cd lead-hub
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env              # set INTAKE_KEYS, ADMIN_KEY, optionally BOT_TOKEN and ADMIN_CHAT_ID
lead-hub db upgrade               # create the tables (Alembic migrations)
lead-hub managers add "Anna" --chat 123456789
lead-hub serve                    # API on http://127.0.0.1:8000, docs on /docs
```

PostgreSQL: `pip install -e ".[postgres]"` and `DATABASE_URL=postgresql+psycopg://user:pass@host/leads`.

Tests: `pytest` (30 tests: services, automation with a controllable clock, API via TestClient,
migrations vs models, CLI).

### Project structure

```
src/lead_hub/
├── models.py    # SQLAlchemy models: managers, leads, lead_events; allowed status transitions
├── schemas.py   # Pydantic validation: phone/email normalization, API models
├── services.py  # intake + de-duplication, round-robin assignment, updates, stats (no commits inside)
├── jobs.py      # automation: new-lead notification, SLA reminders/escalations, daily digest
├── api.py       # FastAPI app, API-key auth, scheduler lifecycle
├── notify.py    # Telegram (or log-only when no token)
├── export.py    # Excel export
├── db.py        # engine/sessions (SQLite pragmas, PostgreSQL pool)
├── config.py    # settings from .env (pydantic-settings)
└── cli.py       # command line
migrations/      # Alembic
```

### Author

**Vladyslav Shokun** ([@sonoyumi](https://github.com/sonoyumi)), Python developer: Telegram bots, web scraping, automation.

[![Telegram](https://img.shields.io/badge/Telegram-write%20me-2CA5E0?logo=telegram&logoColor=white)](https://t.me/sonoyumiii)
[![Email](https://img.shields.io/badge/Email-contact-EA4335?logo=gmail&logoColor=white)](mailto:sonoyumiii@gmail.com)

> 💼 Losing leads between the website and your managers? Get in touch.

### License

MIT, see [LICENSE](LICENSE).

---

<a name="ru"></a>

## 🇷🇺 Русский

**[🇬🇧 English](#en)** · **🇷🇺 Русский**

Небольшой бэкенд для работы с заявками для бизнеса, который получает запросы с сайтов и лендингов.
Формы отправляют заявки в REST API; сервис убирает дубли, назначает менеджера, уведомляет его в Telegram,
напоминает и эскалирует, если заявку никто не взял, и присылает ежедневную сводку с Excel-файлом.
Админ-API даёт список заявок, статусы и статистику конверсии.

### Что автоматизирует

Схема — в английском разделе выше. Коротко: форма → проверка и нормализация телефона/почты →
склейка повторной заявки того же человека за 24 часа → назначение менеджера по кругу → 🆕 уведомление ему →
⏰ напоминание, если не взял за SLA → 🚨 эскалация руководителю после 2×SLA → 📊 ежедневная сводка с Excel.

### Возможности

- **REST API (FastAPI):** приём заявок с форм (свой ключ на каждый сайт), админ-API для заявок, статусов,
  менеджеров и статистики; интерактивная документация на `/docs`.
- **База данных (SQLAlchemy 2.0):** SQLite по умолчанию, PostgreSQL — сменой одной настройки;
  **миграции Alembic** — тест проверяет, что миграции в точности совпадают с моделями.
- **Дубли:** тот же телефон или email за 24 часа (настраивается) склеивается с первой заявкой;
  телефоны нормализуются (`+39 (333) 123-45-67` = `393331234567`).
- **Статусы** с допустимыми переходами (`new → in_progress → won/lost`, можно переоткрыть)
  и полная **история** (создана, повтор, назначена, статус, заметка, напоминание, эскалация).
- **Автоматизация (APScheduler):** проверка SLA каждую минуту, сводка в заданный час по местному времени.
  Неудачная отправка в Telegram повторяется при следующем запуске, а не теряется.
- **Безопасность:** ключи сравниваются за постоянное время, админ-API выключен без `ADMIN_KEY`,
  секреты не печатаются (`SecretStr`), текст из форм экранируется в Telegram и остаётся текстом в Excel.
- **CLI:** `lead-hub db upgrade`, `serve`, `managers add/list/enable/disable`, `export`, `digest`, `sla`.

### API

Таблица эндпоинтов и пример запроса — в английском разделе. Ключ передаётся в заголовке `X-Api-Key`.

### Быстрый старт

```bash
git clone https://github.com/sonoyumi/lead-hub.git
cd lead-hub
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env              # INTAKE_KEYS, ADMIN_KEY, по желанию BOT_TOKEN и ADMIN_CHAT_ID
lead-hub db upgrade               # создать таблицы (миграции Alembic)
lead-hub managers add "Анна" --chat 123456789
lead-hub serve                    # API на http://127.0.0.1:8000, документация на /docs
```

PostgreSQL: `pip install -e ".[postgres]"` и `DATABASE_URL=postgresql+psycopg://user:pass@host/leads`.

Тесты: `pytest` (30 тестов: бизнес-логика, автоматизация с управляемыми часами, API через TestClient,
соответствие миграций моделям, CLI).

### Структура проекта

См. английский раздел.

### Автор

**Vladyslav Shokun** ([@sonoyumi](https://github.com/sonoyumi)) — Python-разработчик: Telegram-боты, парсинг, автоматизация.

[![Telegram](https://img.shields.io/badge/Telegram-write%20me-2CA5E0?logo=telegram&logoColor=white)](https://t.me/sonoyumiii)
[![Email](https://img.shields.io/badge/Email-contact-EA4335?logo=gmail&logoColor=white)](mailto:sonoyumiii@gmail.com)

> 💼 Заявки теряются между сайтом и менеджерами? Напишите мне.

### Лицензия

MIT — см. [LICENSE](LICENSE).
