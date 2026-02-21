import asyncio
import logging
import os
import socket
import sys
from pathlib import Path

# Allow running as `python bot/main.py` from project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramConflictError

from bot.dispatcher import build_dispatcher
from core.config import settings


def acquire_instance_lock(port: int) -> socket.socket:
    lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock_socket.bind(("127.0.0.1", port))
        lock_socket.listen(1)
    except OSError as exc:
        lock_socket.close()
        raise RuntimeError(
            f"Bot instance lock is already held on 127.0.0.1:{port}. "
            "Another bot process is running."
        ) from exc
    return lock_socket


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


async def run_polling() -> None:
    setup_logging()

    lock_port = int(os.getenv("BOT_LOCK_PORT", "47291"))
    lock_socket = acquire_instance_lock(lock_port)

    if not settings.BOT_TOKEN:
        lock_socket.close()
        raise RuntimeError("BOT_TOKEN is not configured")

    bot = Bot(
        settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    dp: Dispatcher = build_dispatcher()

    try:
        try:
            await dp.start_polling(bot)
        except TelegramConflictError:
            raise RuntimeError(
                "TelegramConflictError: another getUpdates consumer is using this token. "
                "Stop duplicate bot instances (local or remote) and run one process only."
            )
    finally:
        await bot.session.close()
        lock_socket.close()


async def main() -> None:
    await run_polling()


if __name__ == "__main__":
    asyncio.run(main())
