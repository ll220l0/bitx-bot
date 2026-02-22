import logging

from db.models import AssistantConfig
from db.session import async_session

logger = logging.getLogger(__name__)

_CONFIG_ID = 1


async def get_custom_prompt() -> str | None:
    try:
        async with async_session() as session:
            config = await session.get(AssistantConfig, _CONFIG_ID)
            value = (config.custom_prompt if config else "") or ""
            cleaned = value.strip()
            return cleaned or None
    except Exception:
        logger.exception("Failed to load assistant custom prompt")
        return None


async def set_custom_prompt(prompt: str | None) -> None:
    value = (prompt or "").strip()
    if len(value) > 8000:
        value = value[:8000]
    stored = value or None

    async with async_session() as session:
        config = await session.get(AssistantConfig, _CONFIG_ID)
        if config is None:
            config = AssistantConfig(id=_CONFIG_ID, custom_prompt=stored)
            session.add(config)
        else:
            config.custom_prompt = stored
        await session.commit()

