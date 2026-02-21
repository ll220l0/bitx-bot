from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router()

WELCOME_TEXT = (
    "<b>BitX</b> - разработка цифровых продуктов и автоматизация.\n\n"
    "Напишите ваш запрос в свободной форме, и я проконсультирую.\n"
    "Для быстрого старта заявки: /lead\n"
    "Контакты: /contacts\n"
    "FAQ: /faq"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(WELCOME_TEXT)


@router.message(Command("contacts"))
async def contacts(message: Message) -> None:
    text = (
        "<b>Контакты BitX</b>\n\n"
        "📲 <b>WhatsApp:</b> <a href='https://wa.me/996509000991'>Написать в WhatsApp</a>\n"
        "💬 <b>Telegram:</b> @bitx_kg\n"
        "📸 <b>Instagram:</b> @bitx_kg\n"
        "📧 <b>Email:</b> bitxkg@gmail.com"
    )
    await message.answer(text)


@router.message(Command("faq"))
async def faq(message: Message) -> None:
    text = (
        "<b>FAQ</b>\n"
        "• <b>Сроки</b>: от 3 дней (MVP) до 4-8 недель (система)\n"
        "• <b>Бюджет</b>: зависит от объема, можно начать с MVP\n"
        "• <b>Гарантия</b>: поддержка и сопровождение по договоренности\n\n"
        "Чтобы оценить точно, запустите форму: /lead"
    )
    await message.answer(text)
