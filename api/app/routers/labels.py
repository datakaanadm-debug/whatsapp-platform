# api/app/routers/labels.py — Gestión de etiquetas de WhatsApp (Labels)

import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_api_key
from api.app.database import get_redis
from api.app.services.label_service import LabelService

logger = logging.getLogger("platform.labels")

router = APIRouter(
    prefix="/api/labels",
    tags=["Etiquetas"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


# ── Helpers ──────────────────────────────────────────────────────


async def _get_channel_id(auth: dict = Depends(verify_api_key)) -> str:
    """Extrae el channel_id asociado a la API Key autenticada."""
    return auth["channel_id"]


# ── CRUD de etiquetas ────────────────────────────────────────────


@router.get(
    "",
    summary="Listar etiquetas",
    description="Retorna todas las etiquetas de WhatsApp del canal autenticado.",
)
async def list_labels(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=200, description="Elementos por página"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Lista todas las etiquetas con paginación."""
    try:
        result = await LabelService.get_labels(redis, channel_id)
        return api_response(result)
    except Exception as e:
        logger.error("Error al listar etiquetas del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al listar etiquetas.",
        )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Crear etiqueta",
    description="Crea una nueva etiqueta de WhatsApp para organizar chats y contactos.",
)
async def create_label(
    name: str = Body(..., embed=True, description="Nombre de la etiqueta"),
    color: int = Body(0, embed=True, description="Índice de color (0-19)"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Crea una nueva etiqueta con el nombre y color indicados."""
    try:
        result = await LabelService.create_label(redis, channel_id, {"name": name, "color": color})
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al crear etiqueta en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear la etiqueta.",
        )


# ── Operaciones por etiqueta ────────────────────────────────────


@router.get(
    "/{label_id}",
    summary="Obtener objetos con etiqueta",
    description="Retorna la lista de chats, contactos o mensajes asociados a una etiqueta específica.",
)
async def get_label_associations(
    label_id: str,
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=200, description="Elementos por página"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Obtiene todos los objetos (chats, contactos) asociados a una etiqueta."""
    try:
        result = await LabelService.get_label_objects(redis, channel_id, label_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Etiqueta '{label_id}' no encontrada.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener asociaciones de etiqueta %s: %s", label_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener los objetos de la etiqueta.",
        )


@router.post(
    "/{label_id}/{assoc_id}",
    summary="Agregar asociación a etiqueta",
    description="Asocia un chat, contacto o mensaje a la etiqueta indicada.",
)
async def add_label_association(
    label_id: str,
    assoc_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Agrega una asociación (chat/contacto/mensaje) a una etiqueta."""
    try:
        result = await LabelService.add_association(redis, channel_id, label_id, assoc_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Etiqueta '{label_id}' no encontrada.",
            )
        return api_response({"message": f"Asociación '{assoc_id}' agregada a la etiqueta."})
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al agregar asociación %s a etiqueta %s: %s", assoc_id, label_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al agregar la asociación.",
        )


@router.delete(
    "/{label_id}/{assoc_id}",
    summary="Remover asociación de etiqueta",
    description="Remueve la asociación de un chat, contacto o mensaje de la etiqueta indicada.",
)
async def remove_label_association(
    label_id: str,
    assoc_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Remueve una asociación de una etiqueta."""
    try:
        result = await LabelService.delete_association(redis, channel_id, label_id, assoc_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asociación '{assoc_id}' no encontrada en la etiqueta '{label_id}'.",
            )
        return api_response({"message": f"Asociación '{assoc_id}' removida de la etiqueta."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al remover asociación %s de etiqueta %s: %s", assoc_id, label_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al remover la asociación.",
        )
