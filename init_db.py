import asyncio

from db.init import ensure_db_schema
from db.session import engine

async def init():
    await ensure_db_schema()
    await engine.dispose()

asyncio.run(init()) 
