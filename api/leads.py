import logging
from html import escape

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from core.config import settings
from db.models import Lead
from db.session import async_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/leads", tags=["leads"])


class LeadCreate(BaseModel):
    source: str = Field(default="telegram", min_length=2, max_length=30)
    name: str = Field(min_length=2, max_length=100)
    company: str = Field(min_length=2, max_length=150)
    service: str = Field(min_length=2, max_length=100)
    budget: str = Field(min_length=1, max_length=50)
    contact: str = Field(min_length=2, max_length=100)
    details: str = Field(min_length=10, max_length=1200)

    model_config = ConfigDict(extra="forbid")


def format_lead(lead: Lead) -> str:
    return (
        f"🧾 <b>Новая заявка</b> (#{lead.id})\n"
        f"Источник: <b>{escape(lead.source)}</b>\n"
        f"Имя: <b>{escape(lead.name)}</b>\n"
        f"Компания: <b>{escape(lead.company)}</b>\n"
        f"Услуга: <b>{escape(lead.service)}</b>\n"
        f"Бюджет: <b>{escape(lead.budget)}</b>\n"
        f"Контакт: <b>{escape(lead.contact)}</b>\n"
        f"Детали: {escape(lead.details)}"
    )


@router.post("/")
async def create_lead(data: LeadCreate) -> dict[str, int | str]:
    try:
        async with async_session() as session:
            lead = Lead(**data.model_dump())
            session.add(lead)
            await session.commit()
            await session.refresh(lead)
    except SQLAlchemyError as exc:
        logger.exception("Failed to save lead")
        raise HTTPException(status_code=500, detail="Failed to save lead") from exc

    try:
        bot = Bot(
            settings.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode="HTML"),
        )
        for chat_id in settings.notification_chat_ids():
            try:
                await bot.send_message(chat_id, format_lead(lead))
            except Exception:
                logger.exception("Failed to notify chat_id=%s", chat_id)
        await bot.session.close()
    except Exception:
        # Лид уже сохранен, не ломаем ответ клиенту из-за проблем с уведомлением.
        logger.exception("Failed to send lead notification")

    return {"status": "ok", "lead_id": lead.id}
