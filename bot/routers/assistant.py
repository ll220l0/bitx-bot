import logging

from aiogram import Router
from aiogram.types import Message

from bot.assistant_engine import SalesAssistant
from bot.lead_capture import process_lead_capture
from core.config import settings
from core.security import is_admin_message

router = Router()
assistant = SalesAssistant()
logger = logging.getLogger(__name__)


def _extract_text(message: Message) -> str:
    return (message.text or message.caption or "").strip()


def _chat_type(message: Message) -> str:
    chat = getattr(message, "chat", None)
    return getattr(chat, "type", "") or ""


def _safe_reply_text(text: str) -> str:
    clean = (text or "").strip()
    if not clean:
        return "Могу помочь с консультацией. Опиши задачу в 1-2 предложениях."
    return clean[:3500]


async def _reply_user(message: Message, text: str) -> None:
    # Force plain text to avoid Telegram HTML parse errors from model output.
    await message.answer(_safe_reply_text(text), parse_mode=None)


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
        logger.warning("Assistant skip: disabled")
        return
    if message.from_user and message.from_user.is_bot:
        logger.warning("Assistant skip: from_bot chat_id=%s", getattr(message.chat, "id", None))
        return
    chat = getattr(message, "chat", None)
    if not chat:
        logger.warning("Assistant skip: no_chat")
        return
    if is_admin_message(message):
        logger.warning("Assistant skip: admin_identity chat_id=%s", chat.id)
        return

    chat_type = _chat_type(message)
    if chat_type in {"group", "supergroup", "channel"}:
        logger.warning("Assistant skip: chat_type=%s chat_id=%s", chat_type, chat.id)
        return

    text = _extract_text(message)
    if not text:
        logger.warning(
            "Assistant skip: empty_text chat_id=%s chat_type=%s",
            chat.id,
            chat_type,
        )
        return

    logger.warning(
        "Assistant process: chat_id=%s chat_type=%s text_len=%s",
        chat.id,
        chat_type,
        len(text),
    )
    result = await assistant.reply(chat_id=chat.id, user_text=text)
    extra_note = ""

    try:
        capture = await process_lead_capture(
            chat_id=chat.id,
            user_id=message.from_user.id if message.from_user else None,
            username=message.from_user.username if message.from_user else None,
            full_name=message.from_user.full_name if message.from_user else None,
            user_text=text,
            bot=message.bot,
        )
        if capture.sent:
            extra_note = "Спасибо, собрал вашу заявку и передал менеджеру. Скоро с вами свяжемся."
        elif capture.follow_up_question:
            extra_note = capture.follow_up_question
    except Exception:
        logger.exception("Lead auto-capture failed for chat_id=%s", chat.id)

    final_reply = result.reply
    if extra_note:
        final_reply = f"{final_reply}\n\n{extra_note}"

    await _reply_user(message, final_reply)
    logger.warning("Assistant replied: chat_id=%s reply_len=%s", chat.id, len(final_reply or ""))

    if result.escalate:
        await _notify_managers(message, reason=result.reason)


@router.message()
async def handle_message(message: Message) -> None:
    try:
        await _handle_message(message)
    except Exception:
        logger.exception("Assistant handler failed for chat_id=%s", getattr(message.chat, "id", None))


@router.business_message()
async def handle_business_message(message: Message) -> None:
    try:
        await _handle_message(message)
    except Exception:
        logger.exception("Assistant business handler failed for chat_id=%s", getattr(message.chat, "id", None))


@router.edited_message()
async def handle_edited_message(message: Message) -> None:
    try:
        await _handle_message(message)
    except Exception:
        logger.exception("Assistant edited handler failed for chat_id=%s", getattr(message.chat, "id", None))


@router.edited_business_message()
async def handle_edited_business_message(message: Message) -> None:
    try:
        await _handle_message(message)
    except Exception:
        logger.exception("Assistant edited business handler failed for chat_id=%s", getattr(message.chat, "id", None))


@router.channel_post()
async def handle_channel_post(message: Message) -> None:
    try:
        await _handle_message(message)
    except Exception:
        logger.exception("Assistant channel handler failed for chat_id=%s", getattr(message.chat, "id", None))
