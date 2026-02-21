import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request

from api.leads import router as leads_router
from api.meta import router as meta_router
from bot.dispatcher import build_dispatcher
from core.config import settings
from db.init import ensure_db_schema

app = FastAPI(title="BitX API")
logger = logging.getLogger(__name__)

app.include_router(leads_router)
app.include_router(meta_router)

bot: Bot | None = None
dp = build_dispatcher()


def get_bot() -> Bot:
    global bot
    if bot is not None:
        return bot
    if not settings.BOT_TOKEN:
        raise HTTPException(status_code=503, detail="BOT_TOKEN is not configured")
    bot = Bot(
        settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    return bot


@app.get("/")
async def root():
    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok", "bot_mode": settings.BOT_MODE}


@app.on_event("startup")
async def startup_event():
    try:
        await ensure_db_schema()
    except Exception:
        logger.exception("Failed to initialize DB schema on startup")


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    secret_token: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    if settings.BOT_MODE != "webhook":
        raise HTTPException(status_code=409, detail="Bot is not configured in webhook mode")

    expected_secret = (settings.WEBHOOK_SECRET_TOKEN or "").strip()
    if expected_secret and (secret_token or "").strip() != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    try:
        tg_bot = get_bot()
        payload = await request.json()
        update = Update.model_validate(payload, context={"bot": tg_bot})
        logger.warning(
            "Telegram update received: update_id=%s event_type=%s",
            update.update_id,
            update.event_type,
        )
        result = await dp.feed_update(tg_bot, update)
        logger.warning(
            "Telegram update result: update_id=%s event_type=%s result_type=%s result_repr=%r",
            update.update_id,
            update.event_type,
            type(result).__name__,
            result,
        )
        if result is UNHANDLED:
            logger.warning(
                "Telegram update unhandled: update_id=%s event_type=%s",
                update.update_id,
                update.event_type,
            )
    except Exception:
        logger.exception("Failed to process telegram webhook update")
    return {"ok": True}


@app.post("/telegram/set-webhook")
async def set_webhook():
    if not settings.PUBLIC_BASE_URL:
        raise HTTPException(status_code=400, detail="PUBLIC_BASE_URL is required")

    tg_bot = get_bot()
    webhook_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}{settings.WEBHOOK_PATH}"
    await tg_bot.set_webhook(
        url=webhook_url,
        secret_token=settings.WEBHOOK_SECRET_TOKEN,
    )
    return {"ok": True, "webhook_url": webhook_url}


@app.post("/telegram/delete-webhook")
async def delete_webhook():
    tg_bot = get_bot()
    await tg_bot.delete_webhook(drop_pending_updates=False)
    return {"ok": True}


@app.on_event("shutdown")
async def shutdown_event():
    if bot is not None:
        await bot.session.close()
