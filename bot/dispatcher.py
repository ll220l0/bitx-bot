from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage

from bot.routers import admin, assistant, lead, start
from core.config import settings


def build_storage():
    if settings.FSM_STORAGE == "redis" and settings.REDIS_URL:
        return RedisStorage.from_url(settings.REDIS_URL)
    return MemoryStorage()


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=build_storage())
    dp.include_router(start.router)
    dp.include_router(lead.router)
    dp.include_router(admin.router)
    dp.include_router(assistant.router)
    return dp
