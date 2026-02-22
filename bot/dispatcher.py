from aiogram import Dispatcher

from bot.routers import admin_control, assistant


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(admin_control.router)
    dp.include_router(assistant.router)
    return dp
