import logging
from typing import Any

import httpx
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from fastapi import APIRouter, HTTPException, Query, Request

from bot.assistant_engine import SalesAssistant
from core.config import settings

router = APIRouter(prefix="/webhook", tags=["meta"])
assistant = SalesAssistant()
logger = logging.getLogger(__name__)


def _verify_webhook_token(mode: str | None, token: str | None, challenge: str | None) -> str:
    if mode != "subscribe":
        raise HTTPException(status_code=400, detail="Invalid hub.mode")
    if not settings.WEBHOOK_SECRET_TOKEN:
        raise HTTPException(status_code=500, detail="WEBHOOK_SECRET_TOKEN is not configured")
    if token != settings.WEBHOOK_SECRET_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid verify token")
    return challenge or ""


def _extract_wa_text_events(payload: dict[str, Any]) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {}) or {}
            for msg in value.get("messages", []):
                if msg.get("type") != "text":
                    continue
                sender = (msg.get("from") or "").strip()
                text = (msg.get("text", {}) or {}).get("body", "").strip()
                if sender and text:
                    events.append((sender, text))
    return events


def _extract_ig_text_events(payload: dict[str, Any]) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    for entry in payload.get("entry", []):
        # Classic page messaging format.
        for event in entry.get("messaging", []):
            msg = event.get("message", {}) or {}
            if msg.get("is_echo"):
                continue
            sender = (event.get("sender", {}) or {}).get("id", "").strip()
            text = (msg.get("text") or "").strip()
            if sender and text:
                events.append((sender, text))

        # Changes format observed in some IG webhook integrations.
        for change in entry.get("changes", []):
            value = change.get("value", {}) or {}
            text = (value.get("text") or "").strip()
            sender = (value.get("from") or "").strip()
            if sender and text:
                events.append((sender, text))
    return events


async def _send_whatsapp_text(to: str, text: str) -> None:
    if not settings.WHATSAPP_ACCESS_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
        raise RuntimeError("WhatsApp credentials are not configured")

    url = (
        f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}/"
        f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    )
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()


async def _send_instagram_text(recipient_id: str, text: str) -> None:
    if not settings.INSTAGRAM_ACCESS_TOKEN:
        raise RuntimeError("Instagram access token is not configured")

    if settings.INSTAGRAM_SEND_API_URL:
        url = settings.INSTAGRAM_SEND_API_URL
    elif settings.INSTAGRAM_PAGE_ID:
        url = (
            f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}/"
            f"{settings.INSTAGRAM_PAGE_ID}/messages"
        )
    else:
        raise RuntimeError("Set INSTAGRAM_SEND_API_URL or INSTAGRAM_PAGE_ID")

    headers = {
        "Authorization": f"Bearer {settings.INSTAGRAM_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "recipient": {"id": recipient_id},
        "messaging_type": "RESPONSE",
        "message": {"text": text},
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()


async def _notify_managers(channel: str, external_user_id: str, user_text: str, reason: str) -> None:
    bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    text = (
        "⚠️ <b>Эскалация менеджеру</b>\n"
        f"Канал: <b>{channel}</b>\n"
        f"ID клиента: <code>{external_user_id}</code>\n"
        f"Причина: <code>{reason or 'escalation'}</code>\n"
        f"Сообщение: {user_text[:500]}"
    )
    try:
        for chat_id in settings.notification_chat_ids():
            try:
                await bot.send_message(chat_id, text)
            except Exception:
                logger.exception("Failed to notify manager chat_id=%s", chat_id)
    finally:
        await bot.session.close()


async def _assistant_reply(channel: str, external_user_id: str, user_text: str) -> str:
    key = f"{channel}:{external_user_id}"
    result = await assistant.reply(chat_id=key, user_text=user_text)
    if result.escalate:
        await _notify_managers(
            channel=channel,
            external_user_id=external_user_id,
            user_text=user_text,
            reason=result.reason,
        )
    return result.reply


@router.get("/whatsapp")
async def verify_whatsapp(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    return _verify_webhook_token(hub_mode, hub_verify_token, hub_challenge)


@router.get("/instagram")
async def verify_instagram(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    return _verify_webhook_token(hub_mode, hub_verify_token, hub_challenge)


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    payload = await request.json()
    processed = 0
    for sender_id, text in _extract_wa_text_events(payload):
        try:
            reply = await _assistant_reply("whatsapp", sender_id, text)
            await _send_whatsapp_text(sender_id, reply)
            processed += 1
        except Exception:
            logger.exception("Failed to process WhatsApp event sender=%s", sender_id)
    return {"ok": True, "processed": processed}


@router.post("/instagram")
async def instagram_webhook(request: Request):
    payload = await request.json()
    processed = 0
    for sender_id, text in _extract_ig_text_events(payload):
        try:
            reply = await _assistant_reply("instagram", sender_id, text)
            await _send_instagram_text(sender_id, reply)
            processed += 1
        except Exception:
            logger.exception("Failed to process Instagram event sender=%s", sender_id)
    return {"ok": True, "processed": processed}
