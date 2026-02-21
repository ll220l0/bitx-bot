from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request

from api.leads import router as leads_router
from api.meta import router as meta_router
from bot.dispatcher import build_dispatcher
from core.config import settings

app = FastAPI(title="BitX API")

app.include_router(leads_router)
app.include_router(meta_router)

bot = Bot(
    settings.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML"),
)
dp = build_dispatcher()


@app.get("/health")
async def health():
    return {"status": "ok", "bot_mode": settings.BOT_MODE}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    secret_token: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    if settings.BOT_MODE != "webhook":
        raise HTTPException(status_code=409, detail="Bot is not configured in webhook mode")

    if settings.WEBHOOK_SECRET_TOKEN and secret_token != settings.WEBHOOK_SECRET_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}


@app.post("/telegram/set-webhook")
async def set_webhook():
    if not settings.PUBLIC_BASE_URL:
        raise HTTPException(status_code=400, detail="PUBLIC_BASE_URL is required")

    webhook_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}{settings.WEBHOOK_PATH}"
    await bot.set_webhook(
        url=webhook_url,
        secret_token=settings.WEBHOOK_SECRET_TOKEN,
    )
    return {"ok": True, "webhook_url": webhook_url}


@app.post("/telegram/delete-webhook")
async def delete_webhook():
    await bot.delete_webhook(drop_pending_updates=False)
    return {"ok": True}


@app.on_event("shutdown")
async def shutdown_event():
    await bot.session.close()
