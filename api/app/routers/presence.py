# api/app/routers/presence.py — Presencia y estado en línea de contactos

import uuid
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_channel_access
from api.app.database import get_redis
from api.app.services.presence_service import PresenceService

logger = logging.getLogger("platform.presence")

router = APIRouter(
    prefix="/api/{channel_id}/presence",
    tags=["Presencia"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        403: {"model": ErrorResponse, "description": "Sin acceso al canal"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


# ── Esquemas auxiliares (específicos de este router) ─────────────


class PresenceResponse(BaseModel):
    """Estado de presencia de un contacto."""

    contact_id: str
    is_online: bool
    last_seen: str | None = Field(None, description="Última conexión en formato ISO 8601")


class PresenceSubscribeRequest(BaseModel):
    """Solicitud para suscribirse a actualizaciones de presencia."""

    contacts: list[str] = Field(
        ..., min_length=1, max_length=50,
        description="IDs de WhatsApp de los contactos a monitorear",
    )


# ── Endpoints ────────────────────────────────────────────────────


@router.get(
    "/{contact_id}",
    summary="Obtener presencia",
    description="Consulta si un contacto está en línea y su última conexión.",
)
async def get_presence(
    channel_id: uuid.UUID,
    contact_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Retorna el estado de presencia del contacto."""
    try:
        presence = await PresenceService.get_presence(redis, channel_id, contact_id)
        if not presence:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se pudo obtener la presencia de '{contact_id}'.",
            )
        return api_response(presence)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener presencia de %s: %s", contact_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener la presencia.",
        )


@router.post(
    "/subscribe",
    summary="Suscribirse a presencia",
    description="Se suscribe a actualizaciones de presencia de una lista de contactos.",
)
async def subscribe_presence(
    channel_id: uuid.UUID,
    payload: PresenceSubscribeRequest,
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Activa las notificaciones de presencia para los contactos indicados."""
    try:
        results = []
        for contact_id in payload.contacts:
            result = await PresenceService.subscribe_presence(redis, channel_id, contact_id)
            results.append(result)
        return api_response({"message": f"Suscrito a presencia de {len(payload.contacts)} contacto(s).", "subscribed": results})
    except Exception as e:
        logger.error("Error al suscribir presencia en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al suscribir presencia.",
        )


@router.post(
    "/available",
    summary="Establecer disponible",
    description="Marca el canal como disponible / en línea.",
)
async def set_available(
    channel_id: uuid.UUID,
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Establece el estado del canal como en línea."""
    try:
        await PresenceService.set_my_presence(redis, channel_id, "online")
        return api_response({"message": "Estado establecido como disponible."})
    except Exception as e:
        logger.error("Error al establecer disponible en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al cambiar el estado de presencia.",
        )


@router.post(
    "/unavailable",
    summary="Establecer no disponible",
    description="Marca el canal como no disponible / fuera de línea.",
)
async def set_unavailable(
    channel_id: uuid.UUID,
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Establece el estado del canal como fuera de línea."""
    try:
        await PresenceService.set_my_presence(redis, channel_id, "offline")
        return api_response({"message": "Estado establecido como no disponible."})
    except Exception as e:
        logger.error("Error al establecer no disponible en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al cambiar el estado de presencia.",
        )
