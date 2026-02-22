import re

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Filter
from aiogram.types import Message

from bot.assistant_config_store import get_custom_prompt, set_custom_prompt
from bot.assistant_engine import SalesAssistant
from core.config import settings
from core.security import is_admin_message

router = Router()
assistant = SalesAssistant()

CHAT_ID_PATTERN = re.compile(r"chat\s*id\s*:\s*(-?\d+)", flags=re.IGNORECASE)
SEND_PATTERN = re.compile(r"^(?:отправь|перешли|send)\s+(-?\d+)\s+(.+)$", flags=re.IGNORECASE | re.DOTALL)
SET_SCENARIO_PATTERN = re.compile(
    r"^(?:сценарий\s*:\s*|установи\s+сценарий\s*:?\s*|обнови\s+сценарий\s*:?\s*|измени\s+сценарий\s*:?\s*)(.+)$",
    flags=re.IGNORECASE | re.DOTALL,
)
EMAIL_UPDATE_PATTERN = re.compile(
    r"^(?:измени|изменить|смени|сменить|обнови|обновить)\s+(?:почту|email|e-mail)\s+(?:на\s+)?([^\s]+@[^\s]+)\s*$",
    flags=re.IGNORECASE,
)
INSTAGRAM_UPDATE_PATTERN = re.compile(
    r"^(?:измени|изменить|смени|сменить|обнови|обновить)\s+(?:инсту|инстаграм|instagram)\s+(?:на\s+)?@?([A-Za-z0-9._]{2,30})\s*$",
    flags=re.IGNORECASE,
)
TELEGRAM_UPDATE_PATTERN = re.compile(
    r"^(?:измени|изменить|смени|сменить|обнови|обновить)\s+(?:телеграм|telegram|tg)\s+(?:на\s+)?@?([A-Za-z0-9_]{2,32})\s*$",
    flags=re.IGNORECASE,
)
WHATSAPP_UPDATE_PATTERN = re.compile(
    r"^(?:измени|изменить|смени|сменить|обнови|обновить)\s+(?:ватсап|вацап|whatsapp)\s+(?:на\s+)?([+\d][\d\s\-()]{6,20})\s*$",
    flags=re.IGNORECASE,
)
CONTACTS_BLOCK_PATTERN = re.compile(
    r"\[CONTACTS_OVERRIDE_START\].*?\[CONTACTS_OVERRIDE_END\]",
    flags=re.IGNORECASE | re.DOTALL,
)
CONTACTS_LINE_PATTERN = re.compile(r"^(telegram|instagram|email|whatsapp)\s*=\s*(.+)$", flags=re.IGNORECASE)

SHOW_SCENARIO_PHRASES = {
    "покажи сценарий",
    "показать сценарий",
    "какой сценарий",
    "текущий сценарий",
    "сценарий",
    "show scenario",
}
RESET_SCENARIO_PHRASES = {
    "сбрось сценарий",
    "сброс сценария",
    "очисти сценарий",
    "убери сценарий",
    "reset scenario",
}
HELP_PHRASES = {
    "помощь",
    "админ помощь",
    "что ты умеешь",
    "help",
}
REPLY_SET_SCENARIO_PHRASES = {
    "сделай это сценарием",
    "используй это как сценарий",
    "запомни это как сценарий",
}
DEFAULT_CONTACTS = {
    "telegram": "@bitx_kg",
    "instagram": "@bitx_kg",
    "email": "bitxkg@gmail.com",
    "whatsapp": "https://wa.me/996509000991",
}


class AdminFilter(Filter):
    async def __call__(self, message: Message) -> bool:
        return bool(
            settings.ADMIN_CHAT_ID is not None
            and message.chat.type == "private"
            and is_admin_message(message)
        )


def _safe_text(text: str) -> str:
    clean = (text or "").strip()
    if not clean:
        return "Могу помочь с консультацией. Опиши задачу в 1-2 предложениях."
    return clean[:3500]


def _extract_target_chat_id_from_message(message: Message | None) -> int | None:
    if message is None:
        return None
    raw_text = (message.text or message.caption or "").strip()
    if not raw_text:
        return None
    match = CHAT_ID_PATTERN.search(raw_text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _normalized_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _extract_send_intent(text: str) -> tuple[int, str] | None:
    match = SEND_PATTERN.match((text or "").strip())
    if not match:
        return None
    try:
        target_chat_id = int(match.group(1))
    except ValueError:
        return None
    body = (match.group(2) or "").strip()
    if not body:
        return None
    return target_chat_id, body


def _extract_set_scenario_text(text: str) -> str | None:
    match = SET_SCENARIO_PATTERN.match((text or "").strip())
    if not match:
        return None
    value = (match.group(1) or "").strip()
    return value or None


def _normalize_contacts_value(key: str, value: str) -> str:
    cleaned = (value or "").strip()
    if key in {"telegram", "instagram"} and cleaned and not cleaned.startswith("@"):
        return f"@{cleaned}"
    if key == "whatsapp":
        compact = re.sub(r"[^\d+]", "", cleaned)
        return compact or cleaned
    return cleaned


def _parse_contacts_override(prompt_text: str | None) -> dict[str, str]:
    contacts = dict(DEFAULT_CONTACTS)
    raw = (prompt_text or "").strip()
    if not raw:
        return contacts

    match = CONTACTS_BLOCK_PATTERN.search(raw)
    if not match:
        return contacts

    for line in match.group(0).splitlines():
        parsed = CONTACTS_LINE_PATTERN.match(line.strip())
        if not parsed:
            continue
        key = parsed.group(1).lower()
        value = parsed.group(2).strip()
        if key in contacts and value:
            contacts[key] = value
    return contacts


def _with_contacts_override(prompt_text: str | None, contacts: dict[str, str]) -> str:
    base = (prompt_text or "").strip()
    base = CONTACTS_BLOCK_PATTERN.sub("", base).strip()

    override_block = (
        "[CONTACTS_OVERRIDE_START]\n"
        "Используй только актуальные контакты ниже:\n"
        f"telegram={contacts['telegram']}\n"
        f"instagram={contacts['instagram']}\n"
        f"email={contacts['email']}\n"
        f"whatsapp={contacts['whatsapp']}\n"
        "[CONTACTS_OVERRIDE_END]"
    )
    if not base:
        return override_block
    return f"{base}\n\n{override_block}"


async def _update_contact_override(message: Message, key: str, raw_value: str) -> None:
    value = _normalize_contacts_value(key, raw_value)
    if not value:
        await message.answer("Не вижу новое значение. Пример: измени почту на name@example.com")
        return

    current = await get_custom_prompt()
    contacts = _parse_contacts_override(current)
    contacts[key] = value
    await set_custom_prompt(_with_contacts_override(current, contacts))

    labels = {
        "email": "Почта",
        "instagram": "Instagram",
        "telegram": "Telegram",
        "whatsapp": "WhatsApp",
    }
    await message.answer(f"{labels.get(key, key)} обновлен: {value}")


async def _send_to_target(message: Message, target_chat_id: int, text: str) -> None:
    if not text.strip():
        await message.answer("Текст пустой. Пример: отправь 7027426496 Привет, готово.")
        return
    try:
        await message.bot.send_message(target_chat_id, text, parse_mode=None)
        await message.answer(f"Отправлено в chat_id={target_chat_id}.")
    except TelegramBadRequest as exc:
        await message.answer(f"Не удалось отправить: {exc.message}")


async def _show_help(message: Message) -> None:
    await message.answer(
        "Админ-режим без команд:\n"
        "1) Покажи сценарий\n"
        "2) Установи сценарий: <текст>\n"
        "3) Сбрось сценарий\n"
        "4) Отправь <chat_id> <текст>\n"
        "5) Измени почту на <email>\n"
        "6) Измени инстаграм на <username>\n\n"
        "Быстрая пересылка: ответь на уведомление с Chat ID и отправь текст/файл, я перешлю клиенту."
    )


async def _handle_admin_message(message: Message) -> None:
    text = (message.text or "").strip()
    normalized = _normalized_text(text)

    if normalized in HELP_PHRASES:
        await _show_help(message)
        return

    if normalized in SHOW_SCENARIO_PHRASES:
        current = await get_custom_prompt()
        await message.answer(current or "Сценарий не задан, используется базовый.")
        return

    if normalized in RESET_SCENARIO_PHRASES:
        await set_custom_prompt(None)
        await message.answer("Сценарий сброшен.")
        return

    email_update = EMAIL_UPDATE_PATTERN.match(text)
    if email_update:
        await _update_contact_override(message, "email", email_update.group(1))
        return

    instagram_update = INSTAGRAM_UPDATE_PATTERN.match(text)
    if instagram_update:
        await _update_contact_override(message, "instagram", instagram_update.group(1))
        return

    telegram_update = TELEGRAM_UPDATE_PATTERN.match(text)
    if telegram_update:
        await _update_contact_override(message, "telegram", telegram_update.group(1))
        return

    whatsapp_update = WHATSAPP_UPDATE_PATTERN.match(text)
    if whatsapp_update:
        await _update_contact_override(message, "whatsapp", whatsapp_update.group(1))
        return

    scenario_text = _extract_set_scenario_text(text)
    if scenario_text:
        await set_custom_prompt(scenario_text)
        await message.answer("Сценарий обновлен.")
        return

    if normalized in REPLY_SET_SCENARIO_PHRASES and message.reply_to_message is not None:
        reply_text = (message.reply_to_message.text or message.reply_to_message.caption or "").strip()
        if not reply_text:
            await message.answer("В сообщении-источнике нет текста сценария.")
            return
        await set_custom_prompt(reply_text)
        await message.answer("Сценарий обновлен из сообщения выше.")
        return

    send_intent = _extract_send_intent(text)
    if send_intent is not None:
        target_chat_id, body = send_intent
        await _send_to_target(message, target_chat_id, body)
        return

    # Auto-forward: admin replies to a message that contains "Chat ID: <id>".
    target_chat_id = _extract_target_chat_id_from_message(message.reply_to_message)
    if target_chat_id is not None:
        try:
            await message.copy_to(chat_id=target_chat_id)
            await message.answer(f"Переслал в chat_id={target_chat_id}.")
        except TelegramBadRequest as exc:
            await message.answer(f"Не удалось переслать: {exc.message}")
        return

    # Default: admin can talk to the assistant in free form.
    user_text = (message.text or message.caption or "").strip()
    if not user_text:
        return
    result = await assistant.reply(chat_id=message.chat.id, user_text=user_text)
    await message.answer(_safe_text(result.reply), parse_mode=None)


@router.message(AdminFilter())
async def admin_message(message: Message) -> None:
    await _handle_admin_message(message)


@router.business_message(AdminFilter())
async def admin_business_message(message: Message) -> None:
    await _handle_admin_message(message)
