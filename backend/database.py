from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    f"sqlite+aiosqlite:///{settings.DB_PATH}",
    echo=settings.DEV_MODE,
    connect_args={"check_same_thread": False, "timeout": 30},
)


async def _set_wal_mode(conn):
    await conn.execute(__import__('sqlalchemy').text("PRAGMA journal_mode=WAL"))
    await conn.execute(__import__('sqlalchemy').text("PRAGMA busy_timeout=30000"))

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    from . import models  # noqa: F401 — ensures models are registered
    async with engine.begin() as conn:
        await _set_wal_mode(conn)
        await conn.run_sync(Base.metadata.create_all)
        # Migrations manuelles pour colonnes ajoutées après création initiale
        for sql in [
            "ALTER TABLE series ADD COLUMN hidden BOOLEAN NOT NULL DEFAULT 0",
            "ALTER TABLE tomes ADD COLUMN hidden BOOLEAN NOT NULL DEFAULT 0",
        ]:
            try:
                await conn.execute(__import__('sqlalchemy').text(sql))
            except Exception:
                pass  # Colonne déjà existante


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
