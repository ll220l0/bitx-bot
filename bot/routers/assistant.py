import logging

from aiogram import Router
from aiogram.types import Message

from bot.assistant_engine import SalesAssistant
from bot.lead_draft_store import has_active_lead_draft
from core.config import settings

router = Router()
assistant = SalesAssistant()
logger = logging.getLogger(__name__)


def _extract_text(message: Message) -> str:
    return (message.text or message.caption or "").strip()


def _chat_type(message: Message) -> str:
    chat = getattr(message, "chat", None)
    return getattr(chat, "type", "") or ""


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


async def _handle_message(message: Message) -> None:
    if not settings.ASSISTANT_ENABLED:
        return
    if message.from_user and message.from_user.is_bot:
        return
    chat = getattr(message, "chat", None)
    if not chat:
        return
    if _chat_type(message) in {"group", "supergroup", "channel"}:
        return
    if await has_active_lead_draft(chat.id):
        return

    text = _extract_text(message)
    if not text or text.startswith("/"):
        return

    result = await assistant.reply(chat_id=chat.id, user_text=text)
    await message.answer(result.reply)
    if result.escalate:
        await _notify_managers(message, reason=result.reason)


@router.message()
async def handle_message(message: Message) -> None:
    await _handle_message(message)


@router.business_message()
async def handle_business_message(message: Message) -> None:
    await _handle_message(message)


@router.edited_message()
async def handle_edited_message(message: Message) -> None:
    await _handle_message(message)


@router.edited_business_message()
async def handle_edited_business_message(message: Message) -> None:
    await _handle_message(message)


@router.channel_post()
async def handle_channel_post(message: Message) -> None:
    await _handle_message(message)
