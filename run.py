import asyncio
import os

import uvicorn

from api.main import app
from bot.main import run_polling, setup_logging
from core.config import settings


async def run_api_server(host: str, port: int) -> None:
    config = uvicorn.Config(app=app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def run_all() -> None:
    setup_logging()

    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "8000"))

    if settings.BOT_MODE == "webhook":
        await run_api_server(host=host, port=port)
        return

    api_task = asyncio.create_task(run_api_server(host=host, port=port))
    await asyncio.sleep(0.8)
    bot_task = asyncio.create_task(run_polling())

    done, pending = await asyncio.wait(
        {api_task, bot_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)

    for task in done:
        exc = task.exception()
        if exc:
            raise exc


if __name__ == "__main__":
    asyncio.run(run_all())
