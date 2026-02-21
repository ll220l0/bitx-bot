from aiogram import Dispatcher

from bot.routers import admin, assistant, lead, start


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(lead.router)
    dp.include_router(admin.router)
    dp.include_router(assistant.router)
    return dp
