# api/app/routers/blacklist.py — Gestión de lista negra de contactos de WhatsApp

import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_api_key
from api.app.database import get_redis
from api.app.services.blacklist_service import BlacklistService

logger = logging.getLogger("platform.blacklist")

router = APIRouter(
    prefix="/api/blacklist",
    tags=["Lista negra"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


# ── Helpers ──────────────────────────────────────────────────────


async def _get_channel_id(auth: dict = Depends(verify_api_key)) -> str:
    """Extrae el channel_id asociado a la API Key autenticada."""
    return auth["channel_id"]


# ── Operaciones de lista negra ───────────────────────────────────


@router.get(
    "",
    summary="Obtener lista negra",
    description="Retorna la lista completa de contactos bloqueados en el canal.",
)
async def get_blacklist(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=200, description="Elementos por página"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Lista todos los contactos bloqueados con paginación."""
    try:
        result = await BlacklistService.get_blacklist(redis, channel_id)
        return api_response(result)
    except Exception as e:
        logger.error("Error al obtener lista negra del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener la lista negra.",
        )


@router.put(
    "/{contact_id}",
    summary="Agregar a lista negra",
    description="Bloquea un contacto agregándolo a la lista negra del canal.",
)
async def add_to_blacklist(
    contact_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Agrega un contacto a la lista negra (bloquear)."""
    try:
        result = await BlacklistService.add_to_blacklist(redis, channel_id, contact_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se pudo bloquear al contacto '{contact_id}'. Puede que ya esté bloqueado.",
            )
        return api_response({"message": f"Contacto '{contact_id}' bloqueado correctamente."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al agregar %s a lista negra: %s", contact_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al agregar a la lista negra.",
        )


@router.delete(
    "/{contact_id}",
    summary="Remover de lista negra",
    description="Desbloquea un contacto removiéndolo de la lista negra del canal.",
)
async def remove_from_blacklist(
    contact_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Remueve un contacto de la lista negra (desbloquear)."""
    try:
        result = await BlacklistService.remove_from_blacklist(redis, channel_id, contact_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contacto '{contact_id}' no encontrado en la lista negra.",
            )
        return api_response({"message": f"Contacto '{contact_id}' desbloqueado correctamente."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al remover %s de lista negra: %s", contact_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al remover de la lista negra.",
        )
