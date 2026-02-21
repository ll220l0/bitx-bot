import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.assistant_engine import SalesAssistant
from core.config import settings

router = Router()
assistant = SalesAssistant()
logger = logging.getLogger(__name__)


def _extract_text(message: Message) -> str:
    return (message.text or message.caption or "").strip()


async def _notify_managers(message: Message, reason: str) -> None:
    target_chat_ids = settings.notification_chat_ids()
    if message.chat.id in target_chat_ids:
        return
    user = message.from_user
    username = f"@{user.username}" if user and user.username else "no_username"
    full_name = user.full_name if user else "unknown"
    text = (
        "⚠️ <b>Требуется менеджер</b>\n"
        f"Причина: <code>{reason or 'escalation'}</code>\n"
        f"Клиент: <b>{full_name}</b> ({username})\n"
        f"Chat ID: <code>{message.chat.id}</code>\n"
        f"Сообщение: {(_extract_text(message) or '[non-text]')[:500]}"
    )
    try:
        for chat_id in target_chat_ids:
            try:
                await message.bot.send_message(chat_id, text)
            except Exception:
                logger.exception("Failed to notify manager chat_id=%s", chat_id)
    except Exception:
        logger.exception("Failed to notify managers about escalation")


async def _handle_message(message: Message, state: FSMContext) -> None:
    if not settings.ASSISTANT_ENABLED:
        return
    if message.from_user and message.from_user.is_bot:
        return
    if await state.get_state() is not None:
        return

    text = _extract_text(message)
    if not text or text.startswith("/"):
        return

    result = await assistant.reply(chat_id=message.chat.id, user_text=text)
    await message.answer(result.reply)
    if result.escalate:
        await _notify_managers(message, reason=result.reason)


@router.message(F.chat.type == "private")
async def handle_private_message(message: Message, state: FSMContext) -> None:
    await _handle_message(message, state)


@router.business_message()
async def handle_business_message(message: Message, state: FSMContext) -> None:
    await _handle_message(message, state)
