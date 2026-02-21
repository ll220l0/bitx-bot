from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings

engine_kwargs = {"echo": False}
if settings.DATABASE_URL.startswith("sqlite+aiosqlite://"):
    # Fail faster when SQLite file is locked instead of hanging.
    engine_kwargs["connect_args"] = {"timeout": 10}

engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)

async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
