# BitX Bot

Telegram-бот (aiogram 3.25.0) + FastAPI API для лидов и webhook-режима.

## Стек

- Python 3.13 (локально)
- aiogram 3.25.0
- FastAPI
- SQLAlchemy (async)
- SQLite (по умолчанию) или Postgres

## Установка

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Настройки

Создайте `.env`:

```env
BOT_TOKEN=...
ADMIN_CHAT_ID=...
MANAGER_CHAT_IDS=123456789,987654321

# polling | webhook
BOT_MODE=polling
WEBHOOK_PATH=/telegram/webhook
WEBHOOK_SECRET_TOKEN=
PUBLIC_BASE_URL=
META_GRAPH_API_VERSION=v20.0
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
INSTAGRAM_ACCESS_TOKEN=
INSTAGRAM_PAGE_ID=
INSTAGRAM_SEND_API_URL=

# Для Postgres используй postgresql+asyncpg://...
# Если провайдер дает postgres://, код сам конвертирует в asyncpg.
DATABASE_URL=sqlite+aiosqlite:///./bitx.db
API_BASE=http://127.0.0.1:8000

ASSISTANT_ENABLED=true
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OPENAI_BASE_URL=https://api.openai.com/v1
ASSISTANT_HISTORY_MESSAGES=10
ASSISTANT_MAX_TOKENS=350
SALES_MAX_DISCOUNT_PCT=15
```

## Инициализация БД

```powershell
.\venv\Scripts\python init_db.py
```

## Одна команда (локально)

```powershell
.\venv\Scripts\python run.py
```

Поведение:
- `BOT_MODE=polling` -> поднимаются API + бот (polling) одной командой.
- `BOT_MODE=webhook` -> поднимается только API (для webhook-входа).

## Ручной запуск (опционально)

API:
```powershell
.\venv\Scripts\uvicorn api.main:app --reload
```

Бот:
```powershell
.\venv\Scripts\python -m bot.main
```

## Vercel

Важно: на Vercel нельзя держать долгий polling-процесс, поэтому нужен `BOT_MODE=webhook`.

1. В Vercel задайте env:
- `BOT_MODE=webhook`
- `PUBLIC_BASE_URL=https://<your-project>.vercel.app`
- `WEBHOOK_PATH=/telegram/webhook`
- `WEBHOOK_SECRET_TOKEN=<random-string>`
- остальные переменные (`BOT_TOKEN`, БД, OpenAI и т.д.)

2. Задеплойте проект (`vercel --prod`).

3. После деплоя установите webhook:
```bash
curl -X POST https://<your-project>.vercel.app/telegram/set-webhook
```

4. Проверка:
- `GET /health`
- Telegram должен слать обновления на `/telegram/webhook`.

## WhatsApp / Instagram (Meta)

Используются отдельные webhook-эндпоинты:
- `GET/POST /webhook/whatsapp`
- `GET/POST /webhook/instagram`

Проверка webhook от Meta:
- в качестве verify token используется `WEBHOOK_SECRET_TOKEN`.

После настройки приложения Meta:
1. Укажи callback URL:
   - `https://<domain>/webhook/whatsapp`
   - `https://<domain>/webhook/instagram`
2. Укажи verify token = `WEBHOOK_SECRET_TOKEN`.
3. Заполни в `.env`:
   - `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`
   - `INSTAGRAM_ACCESS_TOKEN` и (`INSTAGRAM_PAGE_ID` или `INSTAGRAM_SEND_API_URL`)

## Админ

- Для клиента команды не используются: бот работает как свободный AI-чат.
- При эскалации и новых лидах бот отправляет уведомления в `ADMIN_CHAT_ID` и `MANAGER_CHAT_IDS`.
- Админ-команды (только `ADMIN_CHAT_ID`):
  - `/admin` — справка.
  - `/scenario` — показать текущий доп. сценарий.
  - `/scenario set <текст>` — установить доп. сценарий для ассистента.
  - `/scenario reset` — сбросить доп. сценарий.
  - `/send <chat_id> <текст>` — отправить сообщение клиенту.
- Быстрая пересылка материалов: ответь в админ-чате на уведомление, где есть `Chat ID: ...`, и бот перешлет твое сообщение (текст/файл/медиа) в этот чат.
