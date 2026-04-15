# api/app/routers/contacts.py — Gestión de contactos de WhatsApp

import uuid
import logging
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.schemas.contact import ContactCheck, ContactCheckResult, ContactList, ContactResponse
from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_channel_access
from api.app.database import get_db, get_redis
from api.app.services.contact_service import ContactService

logger = logging.getLogger("platform.contacts")

router = APIRouter(
    prefix="/api/{channel_id}/contacts",
    tags=["Contactos"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        403: {"model": ErrorResponse, "description": "Sin acceso al canal"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


@router.get(
    "",
    summary="Listar contactos",
    description="Retorna los contactos sincronizados del canal.",
)
async def list_contacts(
    channel_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    search: Optional[str] = Query(None, description="Buscar por nombre o número"),
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Lista contactos con búsqueda y paginación opcionales."""
    try:
        result = await ContactService.get_contacts(
            db,
            channel_id=channel_id,
            page=page,
            limit=limit,
        )
        return api_response(result)
    except Exception as e:
        logger.error("Error al listar contactos del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al listar contactos.",
        )


@router.get(
    "/{contact_id}",
    summary="Obtener contacto",
    description="Retorna los datos de un contacto específico.",
)
async def get_contact(
    channel_id: uuid.UUID,
    contact_id: str,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Obtiene un contacto por su ID de WhatsApp."""
    try:
        contact = await ContactService.get_contact(db, channel_id, contact_id)
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contacto '{contact_id}' no encontrado.",
            )
        return api_response(contact)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener contacto %s: %s", contact_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener el contacto.",
        )


@router.post(
    "/check",
    summary="Verificar números",
    description="Verifica si una lista de números de teléfono tienen WhatsApp registrado.",
)
async def check_contacts(
    channel_id: uuid.UUID,
    payload: ContactCheck,
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Verifica la existencia de números en WhatsApp."""
    try:
        results = await ContactService.check_phones(redis, channel_id, payload.phones)
        return api_response(results)
    except Exception as e:
        logger.error("Error al verificar contactos en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al verificar los números.",
        )


@router.get(
    "/{contact_id}/profile-pic",
    summary="Foto de perfil",
    description="Obtiene la URL de la foto de perfil del contacto.",
)
async def get_profile_pic(
    channel_id: uuid.UUID,
    contact_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Retorna la URL de la foto de perfil del contacto."""
    try:
        pic_url = await ContactService.get_profile(redis, channel_id, contact_id)
        return api_response({"profile_pic_url": pic_url})
    except Exception as e:
        logger.error("Error al obtener foto de %s: %s", contact_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener la foto de perfil.",
        )


@router.post(
    "/{contact_id}/block",
    summary="Bloquear contacto",
    description="Bloquea un contacto para que no pueda enviar mensajes.",
)
async def block_contact(
    channel_id: uuid.UUID,
    contact_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Bloquea al contacto indicado."""
    try:
        result = await ContactService.block_contact(redis, channel_id, contact_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contacto '{contact_id}' no encontrado.",
            )
        return api_response({"message": "Contacto bloqueado correctamente."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al bloquear contacto %s: %s", contact_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al bloquear el contacto.",
        )


@router.post(
    "/{contact_id}/unblock",
    summary="Desbloquear contacto",
    description="Desbloquea un contacto previamente bloqueado.",
)
async def unblock_contact(
    channel_id: uuid.UUID,
    contact_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Desbloquea al contacto indicado."""
    try:
        result = await ContactService.unblock_contact(redis, channel_id, contact_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contacto '{contact_id}' no encontrado.",
            )
        return api_response({"message": "Contacto desbloqueado correctamente."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al desbloquear contacto %s: %s", contact_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al desbloquear el contacto.",
        )
