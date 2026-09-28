# 📥 Lead Hub

<p>
  <a href="https://github.com/sonoyumi/lead-hub/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/sonoyumi/lead-hub/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white">
  <img alt="SQLAlchemy" src="https://img.shields.io/badge/SQLAlchemy-2.0-D71F00">
  <img alt="Alembic" src="https://img.shields.io/badge/migrations-Alembic-6BA81E">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
</p>

**🇬🇧 [English](#en)** · **🇮🇹 [Italiano](#it)** · **🇺🇦 [Українська](#uk)** · **🇷🇺 [Русский](#ru)**

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

Tests: `pytest` (32 tests: services, automation with a controllable clock, API via TestClient,
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

<a name="it"></a>

## 🇮🇹 Italiano

**[🇬🇧 English](#en)** · **🇮🇹 Italiano** · **[🇺🇦 Українська](#uk)** · **[🇷🇺 Русский](#ru)**

Un piccolo backend per la gestione dei contatti (lead) per le attività che ricevono richieste da siti web e landing page.
I moduli inviano i lead a una REST API; il servizio elimina i duplicati, assegna ogni lead a un commerciale,
lo avvisa su Telegram, invia un promemoria e un'escalation se nessuno prende in carico il lead e manda
un riepilogo giornaliero con un file Excel. Un'API di gestione fornisce l'elenco dei lead, gli stati e le statistiche di conversione.

### Cosa automatizza

Lo schema è nella sezione inglese qui sopra. In breve: modulo → controllo e normalizzazione di telefono/email →
unione di una nuova richiesta della stessa persona entro 24 ore → assegnazione a rotazione del commerciale → 🆕 notifica →
⏰ promemoria se non preso in carico entro lo SLA → 🚨 escalation al responsabile dopo 2×SLA → 📊 riepilogo giornaliero con Excel.

### Funzionalità

- **REST API (FastAPI):** ricezione dei lead dai moduli (una chiave per ogni sito), API di amministrazione per lead, stati,
  commerciali e statistiche; documentazione interattiva su `/docs`.
- **Database (SQLAlchemy 2.0):** SQLite di default, PostgreSQL cambiando una sola impostazione;
  **migrazioni Alembic**: un test verifica che le migrazioni corrispondano esattamente ai modelli.
- **Duplicati:** lo stesso telefono o email entro 24 ore (configurabile) viene unito al primo lead;
  i numeri di telefono vengono normalizzati (`+39 (333) 123-45-67` = `393331234567`).
- **Stati** con transizioni consentite (`new → in_progress → won/lost`, riapertura possibile)
  e **storico** completo (creato, duplicato, assegnato, stato, nota, promemoria, escalation).
- **Automazione (APScheduler):** controllo dello SLA ogni minuto, riepilogo all'ora locale impostata.
  Un invio Telegram fallito viene ritentato al giro successivo, non va perso.
- **Sicurezza:** chiavi confrontate in tempo costante, API di amministrazione disattivata senza `ADMIN_KEY`,
  segreti mai stampati (`SecretStr`), il testo dei moduli viene escapato in Telegram e resta testo in Excel.
- **CLI:** `lead-hub db upgrade`, `serve`, `managers add/list/enable/disable`, `export`, `digest`, `sla`.

### API

La tabella degli endpoint e un esempio di richiesta sono nella sezione inglese. La chiave va nell'header `X-Api-Key`.

### Avvio rapido

```bash
git clone https://github.com/sonoyumi/lead-hub.git
cd lead-hub
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env              # INTAKE_KEYS, ADMIN_KEY, facoltativi BOT_TOKEN e ADMIN_CHAT_ID
lead-hub db upgrade               # crea le tabelle (migrazioni Alembic)
lead-hub managers add "Anna" --chat 123456789
lead-hub serve                    # API su http://127.0.0.1:8000, documentazione su /docs
```

PostgreSQL: `pip install -e ".[postgres]"` e `DATABASE_URL=postgresql+psycopg://user:pass@host/leads`.

Test: `pytest` (32 test: logica di business, automazione con orologio controllabile, API tramite TestClient,
corrispondenza tra migrazioni e modelli, CLI).

### Struttura del progetto

Vedi la sezione inglese.

### Autore

**Vladyslav Shokun** ([@sonoyumi](https://github.com/sonoyumi)), sviluppatore Python: bot Telegram, web scraping, automazione.

[![Telegram](https://img.shields.io/badge/Telegram-write%20me-2CA5E0?logo=telegram&logoColor=white)](https://t.me/sonoyumiii)
[![Email](https://img.shields.io/badge/Email-contact-EA4335?logo=gmail&logoColor=white)](mailto:sonoyumiii@gmail.com)

> 💼 Perdi contatti tra il sito e i tuoi commerciali? Scrivimi.

### Licenza

MIT, vedi [LICENSE](LICENSE).

---

<a name="uk"></a>

## 🇺🇦 Українська

**[🇬🇧 English](#en)** · **[🇮🇹 Italiano](#it)** · **🇺🇦 Українська** · **[🇷🇺 Русский](#ru)**

Невеликий бекенд для роботи із заявками для бізнесу, який отримує запити із сайтів і лендингів.
Форми надсилають заявки в REST API; сервіс прибирає дублі, призначає менеджера, сповіщає його в Telegram,
нагадує та ескалює, якщо заявку ніхто не взяв, і надсилає щоденне зведення з Excel-файлом.
Адмін-API дає список заявок, статуси та статистику конверсії.

### Що автоматизує

Схема — в англійському розділі вище. Коротко: форма → перевірка й нормалізація телефону/пошти →
об'єднання повторної заявки тієї самої людини за 24 години → призначення менеджера по колу → 🆕 сповіщення йому →
⏰ нагадування, якщо не взяв за SLA → 🚨 ескалація керівнику після 2×SLA → 📊 щоденне зведення з Excel.

### Можливості

- **REST API (FastAPI):** прийом заявок із форм (свій ключ для кожного сайту), адмін-API для заявок, статусів,
  менеджерів і статистики; інтерактивна документація на `/docs`.
- **База даних (SQLAlchemy 2.0):** SQLite за замовчуванням, PostgreSQL — зміною одного налаштування;
  **міграції Alembic** — тест перевіряє, що міграції точно збігаються з моделями.
- **Дублі:** той самий телефон або email за 24 години (налаштовується) об'єднується з першою заявкою;
  телефони нормалізуються (`+39 (333) 123-45-67` = `393331234567`).
- **Статуси** з допустимими переходами (`new → in_progress → won/lost`, можна перевідкрити)
  і повна **історія** (створена, повтор, призначена, статус, нотатка, нагадування, ескалація).
- **Автоматизація (APScheduler):** перевірка SLA щохвилини, зведення в заданий час за місцевим часом.
  Невдале надсилання в Telegram повторюється під час наступного запуску, а не губиться.
- **Безпека:** ключі порівнюються за сталий час, адмін-API вимкнений без `ADMIN_KEY`,
  секрети не друкуються (`SecretStr`), текст із форм екранується в Telegram і залишається текстом в Excel.
- **CLI:** `lead-hub db upgrade`, `serve`, `managers add/list/enable/disable`, `export`, `digest`, `sla`.

### API

Таблиця ендпоінтів і приклад запиту — в англійському розділі. Ключ передається в заголовку `X-Api-Key`.

### Швидкий старт

```bash
git clone https://github.com/sonoyumi/lead-hub.git
cd lead-hub
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env              # INTAKE_KEYS, ADMIN_KEY, за бажанням BOT_TOKEN і ADMIN_CHAT_ID
lead-hub db upgrade               # створити таблиці (міграції Alembic)
lead-hub managers add "Анна" --chat 123456789
lead-hub serve                    # API на http://127.0.0.1:8000, документація на /docs
```

PostgreSQL: `pip install -e ".[postgres]"` і `DATABASE_URL=postgresql+psycopg://user:pass@host/leads`.

Тести: `pytest` (32 тестів: бізнес-логіка, автоматизація з керованим годинником, API через TestClient,
відповідність міграцій моделям, CLI).

### Структура проєкту

Див. англійський розділ.

### Автор

**Vladyslav Shokun** ([@sonoyumi](https://github.com/sonoyumi)) — Python-розробник: Telegram-боти, парсинг, автоматизація.

[![Telegram](https://img.shields.io/badge/Telegram-write%20me-2CA5E0?logo=telegram&logoColor=white)](https://t.me/sonoyumiii)
[![Email](https://img.shields.io/badge/Email-contact-EA4335?logo=gmail&logoColor=white)](mailto:sonoyumiii@gmail.com)

> 💼 Заявки губляться між сайтом і менеджерами? Напишіть мені.

### Ліцензія

MIT — див. [LICENSE](LICENSE).

---

<a name="ru"></a>

## 🇷🇺 Русский

**[🇬🇧 English](#en)** · **[🇮🇹 Italiano](#it)** · **[🇺🇦 Українська](#uk)** · **🇷🇺 Русский**

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

Тесты: `pytest` (32 тестов: бизнес-логика, автоматизация с управляемыми часами, API через TestClient,
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
