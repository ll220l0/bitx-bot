from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import desc, select

from core.config import settings
from db.models import Lead
from db.session import async_session

router = Router()


@router.message(Command("leads"))
async def leads_list(message: Message) -> None:
    if message.chat.id not in settings.notification_chat_ids():
        return

    async with async_session() as session:
        result = await session.execute(select(Lead).order_by(desc(Lead.id)).limit(10))
        leads = result.scalars().all()

    text = "\n\n".join(
        f"#{lead.id} | {lead.name} | {lead.service} | {lead.status}" for lead in leads
    ) or "Нет лидов"

    await message.answer(text)
