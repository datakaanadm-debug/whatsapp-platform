# api/app/database.py — Conexiones asíncronas a PostgreSQL y Redis
# SQLAlchemy 2.0 async + Redis con pool de conexiones

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.app.config import get_settings

settings = get_settings()

# ── Motor asíncrono de SQLAlchemy ─────────────────────────────────
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# ── Fábrica de sesiones asíncronas ────────────────────────────────
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ── Pool de conexiones Redis ──────────────────────────────────────
redis_pool: aioredis.Redis = aioredis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    max_connections=50,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependencia FastAPI: provee una sesión de base de datos por request."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """Dependencia FastAPI: provee una conexión Redis del pool."""
    try:
        yield redis_pool
    finally:
        pass


async def close_connections() -> None:
    """Cierra todas las conexiones al apagar la aplicación."""
    await engine.dispose()
    await redis_pool.aclose()
