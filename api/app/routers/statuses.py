# api/app/routers/statuses.py — Consulta de estados de visualización (ACK / confirmaciones de lectura)

import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status

from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_api_key
from api.app.database import get_redis
from api.app.services.status_service import StatusService

logger = logging.getLogger("platform.statuses")

router = APIRouter(
    prefix="/api/statuses",
    tags=["Estados de visualización"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


# ── Helpers ──────────────────────────────────────────────────────


async def _get_channel_id(auth: dict = Depends(verify_api_key)) -> str:
    """Extrae el channel_id asociado a la API Key autenticada."""
    return auth["channel_id"]


# ── Consulta de estados de visualización ─────────────────────────


@router.get(
    "/{message_id}",
    summary="Obtener estados de visualización de un mensaje/historia",
    description=(
        "Retorna la lista de estados de visualización (ACK/confirmaciones de lectura) "
        "de un mensaje o historia específica. Incluye quién lo vio, cuándo, y el estado "
        "de entrega (enviado, entregado, leído, reproducido)."
    ),
)
async def get_view_statuses(
    message_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Obtiene los estados de visualización de un mensaje o historia por su ID."""
    try:
        statuses = await StatusService.get_view_statuses(redis, channel_id, message_id)
        if statuses is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Mensaje o historia '{message_id}' no encontrado.",
            )
        return api_response(statuses)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener estados del mensaje %s: %s", message_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener los estados de visualización.",
        )
