from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from api.client import send_lead_to_api
from bot.states import LeadState
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
async def lead_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(
        source="telegram",
        tg_user_id=message.from_user.id,
        tg_username=message.from_user.username,
    )
    await state.set_state(LeadState.name)
    await message.answer(
        "<b>Заявка в BitX</b>\n\n"
        "Как вас зовут?\n"
        "Команда для отмены: /cancel"
    )


@router.message(Command("cancel"), F.chat.type == "private")
async def lead_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        return
    await state.clear()
    await message.answer("Ок, заявку отменил. Если захотите снова - команда /lead")


@router.message(LeadState.name)
async def lead_name(message: Message, state: FSMContext) -> None:
    ok, val = validate_name(message.text or "")
    if not ok:
        await message.answer(f"{val}\n\nКак вас зовут?")
        return

    await state.update_data(name=val)
    await state.set_state(LeadState.company)
    await message.answer("Компания или ниша? (можно: частный заказ)")


@router.message(LeadState.company)
async def lead_company(message: Message, state: FSMContext) -> None:
    ok, val = validate_company(message.text or "")
    if not ok:
        await message.answer(f"{val}\n\nКомпания или ниша?")
        return

    await state.update_data(company=val)
    await state.set_state(LeadState.service)
    await message.answer("Какая услуга нужна? (например: сайт, бот, CRM, поддержка)")


@router.message(LeadState.service)
async def lead_service(message: Message, state: FSMContext) -> None:
    val = _service_normalize(message.text or "")
    if not val:
        await message.answer("Укажите услугу текстом (минимум 2 символа).")
        return

    await state.update_data(service=val)
    await state.set_state(LeadState.budget)
    await message.answer("Ориентир по бюджету? (число или «обсудим»)")


@router.message(LeadState.budget)
async def lead_budget(message: Message, state: FSMContext) -> None:
    ok, val = validate_budget(message.text or "")
    if not ok:
        await message.answer(f"{val}\n\nОриентир по бюджету?")
        return

    await state.update_data(budget=val)
    await state.set_state(LeadState.details)
    await message.answer("Опишите задачу и сроки (1-2 абзаца):")


@router.message(LeadState.details)
async def lead_details(message: Message, state: FSMContext) -> None:
    ok, val = validate_details(message.text or "")
    if not ok:
        await message.answer(f"{val}\n\nОпишите задачу и сроки:")
        return

    await state.update_data(details=val)
    await state.set_state(LeadState.contact)
    await message.answer(
        "Оставьте контакт для связи (телефон, @username или email)."
    )


@router.message(LeadState.contact)
async def lead_contact(message: Message, state: FSMContext) -> None:
    contact_value = (message.text or "").strip()
    if message.contact and message.contact.phone_number:
        contact_value = (message.contact.phone_number or "").strip()

    if len(contact_value) < 3:
        await message.answer("Контакт слишком короткий. Напишите телефон, @username или email.")
        return

    data = await state.get_data()
    payload = {
        "source": data.get("source", "telegram"),
        "name": data.get("name"),
        "company": data.get("company"),
        "service": data.get("service", "Другое"),
        "budget": data.get("budget"),
        "contact": contact_value,
        "details": data.get("details"),
    }

    ok = await send_lead_to_api(payload)
    await state.clear()

    if not ok:
        await message.answer(
            "⚠️ Не удалось отправить заявку. Попробуйте снова через пару минут или напишите нам: @bitx_kg"
        )
        return

    await message.answer("✅ Заявка принята. Мы свяжемся с вами в ближайшее время.")
