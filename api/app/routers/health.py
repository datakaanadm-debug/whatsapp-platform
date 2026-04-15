# api/app/routers/health.py — Endpoints de salud y disponibilidad del servicio

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

logger = logging.getLogger("platform.health")

router = APIRouter(tags=["Salud"])


@router.get(
    "/health",
    summary="Health check",
    description="Verifica que el servidor está respondiendo.",
    status_code=status.HTTP_200_OK,
)
async def health_check():
    """Endpoint básico de salud — siempre retorna 200 si el proceso está activo."""
    return {
        "status": "ok",
        "service": "whatsapp-platform",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/health/ready",
    summary="Readiness check",
    description="Verifica que el servidor y sus dependencias (DB, Redis) están listas.",
    status_code=status.HTTP_200_OK,
)
async def readiness_check():
    """
    Verifica conectividad con base de datos y Redis.
    Retorna 503 si alguna dependencia no está disponible.
    """
    checks = {
        "database": False,
        "redis": False,
    }

    # Verificar base de datos
    try:
        from sqlalchemy import text
        from api.app.services.database import get_async_session

        async for session in get_async_session():
            await session.execute(text("SELECT 1"))
            checks["database"] = True
            break
    except Exception as e:
        logger.error("Readiness check — fallo en base de datos: %s", e)

    # Verificar Redis
    try:
        import redis.asyncio as aioredis
        from api.app.config import get_settings

        settings = get_settings()
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.ping()
        await r.aclose()
        checks["redis"] = True
    except Exception as e:
        logger.error("Readiness check — fallo en Redis: %s", e)

    all_ready = all(checks.values())

    response_data = {
        "status": "ready" if all_ready else "degraded",
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if not all_ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response_data,
        )

    return response_data
