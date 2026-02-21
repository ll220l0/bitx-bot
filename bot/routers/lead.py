from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command
from aiogram.types import Message

from api.client import send_lead_to_api
from bot.lead_draft_store import (
    clear_lead_draft,
    get_lead_draft,
    has_active_lead_draft,
    start_lead_draft,
    update_lead_draft,
)
from bot.validators import validate_budget, validate_company, validate_details, validate_name

router = Router()


def _service_normalize(text: str) -> str:
    value = (text or "").strip()
    if len(value) < 2:
        return ""
    if len(value) > 100:
        return value[:100]
    return value


@router.message(Command("lead"), F.chat.type == "private")
async def lead_start(message: Message) -> None:
    await start_lead_draft(
        chat_id=message.chat.id,
        source="telegram",
        tg_user_id=message.from_user.id if message.from_user else None,
        tg_username=message.from_user.username if message.from_user else None,
    )
    await message.answer(
        "<b>Заявка в BitX</b>\n\n"
        "Как вас зовут?\n"
        "Команда для отмены: /cancel"
    )


@router.message(Command("cancel"), F.chat.type == "private")
async def lead_cancel(message: Message) -> None:
    if not await has_active_lead_draft(message.chat.id):
        return
    await clear_lead_draft(message.chat.id)
    await message.answer("Ок, заявку отменил. Если захотите снова - команда /lead")


@router.message(F.chat.type == "private")
async def lead_progress(message: Message) -> None:
    text = (message.text or "").strip()
    if text.startswith("/"):
        raise SkipHandler()

    draft = await get_lead_draft(message.chat.id)
    if draft is None:
        raise SkipHandler()

    if draft.step == "name":
        ok, val = validate_name(text)
        if not ok:
            await message.answer(f"{val}\n\nКак вас зовут?")
            return
        await update_lead_draft(message.chat.id, name=val, step="company")
        await message.answer("Компания или ниша? (можно: частный заказ)")
        return

    if draft.step == "company":
        ok, val = validate_company(text)
        if not ok:
            await message.answer(f"{val}\n\nКомпания или ниша?")
            return
        await update_lead_draft(message.chat.id, company=val, step="service")
        await message.answer("Какая услуга нужна? (например: сайт, бот, CRM, поддержка)")
        return

    if draft.step == "service":
        val = _service_normalize(text)
        if not val:
            await message.answer("Укажите услугу текстом (минимум 2 символа).")
            return
        await update_lead_draft(message.chat.id, service=val, step="budget")
        await message.answer("Ориентир по бюджету? (число или «обсудим»)")
        return

    if draft.step == "budget":
        ok, val = validate_budget(text)
        if not ok:
            await message.answer(f"{val}\n\nОриентир по бюджету?")
            return
        await update_lead_draft(message.chat.id, budget=val, step="details")
        await message.answer("Опишите задачу и сроки (1-2 абзаца):")
        return

    if draft.step == "details":
        ok, val = validate_details(text)
        if not ok:
            await message.answer(f"{val}\n\nОпишите задачу и сроки:")
            return
        await update_lead_draft(message.chat.id, details=val, step="contact")
        await message.answer("Оставьте контакт для связи (телефон, @username или email).")
        return

    if draft.step != "contact":
        await clear_lead_draft(message.chat.id)
        await message.answer("Сбросил заявку из-за ошибки состояния. Начните заново: /lead")
        return

    contact_value = text
    if message.contact and message.contact.phone_number:
        contact_value = (message.contact.phone_number or "").strip()
    if len(contact_value) < 3:
        await message.answer("Контакт слишком короткий. Напишите телефон, @username или email.")
        return

    payload = {
        "source": draft.source or "telegram",
        "name": draft.name or "",
        "company": draft.company or "",
        "service": draft.service or "Другое",
        "budget": draft.budget or "",
        "contact": contact_value,
        "details": draft.details or "",
    }

    ok = await send_lead_to_api(payload)
    if not ok:
        await message.answer(
            "⚠️ Не удалось отправить заявку. Попробуйте снова через пару минут или напишите нам: @bitx_kg"
        )
        return

    await clear_lead_draft(message.chat.id)
    await message.answer("✅ Заявка принята. Мы свяжемся с вами в ближайшее время.")
