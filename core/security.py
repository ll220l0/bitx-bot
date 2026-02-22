from collections.abc import Mapping
from typing import Any

from aiogram.types import Message

from core.config import settings


def is_admin_identity(chat_id: int | None, user_id: int | None) -> bool:
    admin_id = settings.ADMIN_CHAT_ID
    if admin_id is None:
        return False
    return chat_id == admin_id or user_id == admin_id


def is_admin_message(message: Message) -> bool:
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    user_id = getattr(getattr(message, "from_user", None), "id", None)
    return is_admin_identity(chat_id=chat_id, user_id=user_id)


def is_admin_payload(payload: Mapping[str, Any]) -> bool:
    message = payload.get("message")
    if not isinstance(message, Mapping):
        return False

    chat = message.get("chat")
    from_user = message.get("from")
    chat_id = chat.get("id") if isinstance(chat, Mapping) else None
    user_id = from_user.get("id") if isinstance(from_user, Mapping) else None

    if not isinstance(chat_id, int):
        chat_id = None
    if not isinstance(user_id, int):
        user_id = None

    return is_admin_identity(chat_id=chat_id, user_id=user_id)
