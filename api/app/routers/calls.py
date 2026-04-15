# api/app/routers/calls.py — Gestión de llamadas de WhatsApp

import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Body, Depends, HTTPException, status

from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_api_key
from api.app.database import get_redis
from api.app.services.call_service import CallService

logger = logging.getLogger("platform.calls")

router = APIRouter(
    prefix="/api/calls",
    tags=["Llamadas"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


# ── Helpers ──────────────────────────────────────────────────────


async def _get_channel_id(auth: dict = Depends(verify_api_key)) -> str:
    """Extrae el channel_id asociado a la API Key autenticada."""
    return auth["channel_id"]


# ── Crear llamada ────────────────────────────────────────────────


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Crear evento de llamada",
    description="Inicia una nueva llamada de voz o video de WhatsApp.",
)
async def create_call(
    payload: dict = Body(..., description="Datos de la llamada (to, type: voice|video)"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Crea un evento de llamada de WhatsApp (voz o video)."""
    try:
        result = await CallService.create_call(redis, channel_id, payload)
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al crear llamada en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear la llamada.",
        )


# ── Rechazar llamada ─────────────────────────────────────────────


@router.delete(
    "/{call_id}",
    summary="Rechazar llamada",
    description="Rechaza una llamada entrante de WhatsApp.",
)
async def reject_call(
    call_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Rechaza una llamada entrante por su ID."""
    try:
        result = await CallService.reject_call(redis, channel_id, call_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Llamada '{call_id}' no encontrada.",
            )
        return api_response({"message": "Llamada rechazada correctamente."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al rechazar llamada %s: %s", call_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al rechazar la llamada.",
        )


@router.post(
    "/{call_id}/reject",
    summary="Rechazar llamada (alias)",
    description="Alias POST para rechazar una llamada entrante de WhatsApp.",
)
async def reject_call_alias(
    call_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Rechaza una llamada entrante (endpoint alternativo con POST)."""
    try:
        result = await CallService.reject_call(redis, channel_id, call_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Llamada '{call_id}' no encontrada.",
            )
        return api_response({"message": "Llamada rechazada correctamente."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al rechazar llamada %s: %s", call_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al rechazar la llamada.",
        )


# ── Enlace de videollamada grupal ────────────────────────────────


@router.post(
    "/group_link",
    status_code=status.HTTP_201_CREATED,
    summary="Crear enlace de videollamada grupal",
    description="Genera un enlace para iniciar una videollamada grupal de WhatsApp.",
)
async def create_group_call_link(
    payload: dict = Body(
        default={},
        description="Datos opcionales (group_id para vincular a un grupo específico)",
    ),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Genera un enlace de videollamada grupal."""
    try:
        result = await CallService.create_group_call_link(redis, channel_id)
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al crear enlace de videollamada en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear el enlace de videollamada grupal.",
        )
