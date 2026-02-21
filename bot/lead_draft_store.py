from sqlalchemy import delete, select

from db.models import LeadDraft
from db.session import async_session


async def get_lead_draft(chat_id: int) -> LeadDraft | None:
    async with async_session() as session:
        result = await session.execute(select(LeadDraft).where(LeadDraft.chat_id == chat_id))
        return result.scalar_one_or_none()


async def has_active_lead_draft(chat_id: int) -> bool:
    draft = await get_lead_draft(chat_id)
    return draft is not None


async def start_lead_draft(
    chat_id: int,
    source: str = "telegram",
    tg_user_id: int | None = None,
    tg_username: str | None = None,
) -> None:
    async with async_session() as session:
        await session.execute(delete(LeadDraft).where(LeadDraft.chat_id == chat_id))
        session.add(
            LeadDraft(
                chat_id=chat_id,
                source=source,
                tg_user_id=tg_user_id,
                tg_username=tg_username,
                step="name",
            )
        )
        await session.commit()


async def update_lead_draft(chat_id: int, **fields) -> LeadDraft | None:
    async with async_session() as session:
        result = await session.execute(select(LeadDraft).where(LeadDraft.chat_id == chat_id))
        draft = result.scalar_one_or_none()
        if draft is None:
            return None

        for key, value in fields.items():
            if hasattr(draft, key):
                setattr(draft, key, value)

        await session.commit()
        await session.refresh(draft)
        return draft


async def clear_lead_draft(chat_id: int) -> None:
    async with async_session() as session:
        await session.execute(delete(LeadDraft).where(LeadDraft.chat_id == chat_id))
        await session.commit()
