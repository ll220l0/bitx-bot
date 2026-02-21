from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings


def _normalize_database_url(raw_url: str) -> str:
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgresql+psycopg2://"):
        return raw_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    return raw_url


database_url = _normalize_database_url(settings.DATABASE_URL)

engine_kwargs = {"echo": False}
if database_url.startswith("sqlite+aiosqlite://"):
    # Fail faster when SQLite file is locked instead of hanging.
    engine_kwargs["connect_args"] = {"timeout": 10}

engine = create_async_engine(database_url, **engine_kwargs)

async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
