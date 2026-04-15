# api/app/routers/groups.py — Gestión de grupos de WhatsApp

import uuid
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.schemas.group import (
    GroupCreate,
    GroupParticipantAction,
    GroupResponse,
    GroupUpdate,
)
from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_channel_access
from api.app.database import get_db, get_redis
from api.app.services.group_service import GroupService

logger = logging.getLogger("platform.groups")

router = APIRouter(
    prefix="/api/{channel_id}/groups",
    tags=["Grupos"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        403: {"model": ErrorResponse, "description": "Sin acceso al canal"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Crear grupo",
    description="Crea un nuevo grupo de WhatsApp con los participantes indicados.",
)
async def create_group(
    channel_id: uuid.UUID,
    payload: GroupCreate,
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Crea un grupo nuevo y agrega los participantes iniciales."""
    try:
        group = await GroupService.create_group(
            redis, channel_id, payload.name, payload.participants
        )
        return api_response(group)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al crear grupo en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear el grupo.",
        )


@router.get(
    "",
    summary="Listar grupos",
    description="Retorna todos los grupos en los que participa el canal.",
)
async def list_groups(
    channel_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Lista grupos con paginación."""
    try:
        groups = await GroupService.get_groups(db, channel_id)
        return api_response({"groups": groups, "total": len(groups), "page": page, "limit": limit})
    except Exception as e:
        logger.error("Error al listar grupos del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al listar grupos.",
        )


@router.get(
    "/{group_id}",
    summary="Obtener grupo",
    description="Retorna los detalles de un grupo incluyendo participantes.",
)
async def get_group(
    channel_id: uuid.UUID,
    group_id: str,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Obtiene la información completa de un grupo."""
    try:
        group = await GroupService.get_group(db, channel_id, group_id)
        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Grupo '{group_id}' no encontrado.",
            )
        return api_response(group)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener grupo %s: %s", group_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener el grupo.",
        )


@router.patch(
    "/{group_id}",
    summary="Actualizar grupo",
    description="Actualiza el nombre o descripción de un grupo.",
)
async def update_group(
    channel_id: uuid.UUID,
    group_id: str,
    payload: GroupUpdate,
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Actualiza los metadatos del grupo."""
    try:
        group = await GroupService.update_group(
            redis, channel_id, group_id, payload.model_dump(exclude_unset=True)
        )
        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Grupo '{group_id}' no encontrado.",
            )
        return api_response(group)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al actualizar grupo %s: %s", group_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al actualizar el grupo.",
        )


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Salir del grupo",
    description="Abandona un grupo de WhatsApp.",
)
async def leave_group(
    channel_id: uuid.UUID,
    group_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Sale del grupo indicado."""
    try:
        result = await GroupService.leave_group(redis, channel_id, group_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Grupo '{group_id}' no encontrado.",
            )
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al salir del grupo %s: %s", group_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al salir del grupo.",
        )


@router.post(
    "/{group_id}/participants",
    summary="Gestionar participantes",
    description="Agrega, remueve, promueve o degrada participantes de un grupo.",
)
async def manage_participants(
    channel_id: uuid.UUID,
    group_id: str,
    payload: GroupParticipantAction,
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Ejecuta la acción indicada sobre los participantes del grupo."""
    try:
        action_map = {
            "add": GroupService.add_participants,
            "remove": GroupService.remove_participants,
            "promote": GroupService.promote_admin,
            "demote": GroupService.demote_admin,
        }
        handler = action_map.get(payload.action)
        if not handler:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Acción '{payload.action}' no válida. Usa: add, remove, promote, demote.",
            )
        result = await handler(redis, channel_id, group_id, payload.participants)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Grupo '{group_id}' no encontrado.",
            )
        return api_response({"message": f"Acción '{payload.action}' ejecutada sobre {len(payload.participants)} participante(s)."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al gestionar participantes del grupo %s: %s", group_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al gestionar participantes.",
        )


@router.get(
    "/{group_id}/invite",
    summary="Obtener enlace de invitación",
    description="Retorna el enlace de invitación actual del grupo.",
)
async def get_invite_link(
    channel_id: uuid.UUID,
    group_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Obtiene el enlace de invitación del grupo."""
    try:
        link = await GroupService.get_invite(redis, channel_id, group_id)
        if not link:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Grupo '{group_id}' no encontrado.",
            )
        return api_response({"invite_link": link})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener invitación del grupo %s: %s", group_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener el enlace de invitación.",
        )


@router.post(
    "/{group_id}/invite/revoke",
    summary="Revocar enlace de invitación",
    description="Invalida el enlace de invitación actual y genera uno nuevo.",
)
async def revoke_invite_link(
    channel_id: uuid.UUID,
    group_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Revoca el enlace de invitación y genera uno nuevo."""
    try:
        result = await GroupService.revoke_invite(redis, channel_id, group_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Grupo '{group_id}' no encontrado.",
            )
        return api_response({"message": "Enlace de invitación revocado."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al revocar invitación del grupo %s: %s", group_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al revocar el enlace.",
        )


@router.post(
    "/{group_id}/pic",
    summary="Establecer foto del grupo",
    description="Sube y establece la foto de perfil del grupo.",
)
async def set_group_picture(
    channel_id: uuid.UUID,
    group_id: str,
    file: UploadFile = File(..., description="Imagen JPG/PNG para el grupo"),
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Sube una imagen como foto de perfil del grupo."""
    try:
        # Validar tipo de archivo
        allowed_types = {"image/jpeg", "image/png", "image/webp"}
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tipo de archivo no soportado: {file.content_type}. Usa JPG, PNG o WebP.",
            )

        import base64
        image_data = await file.read()
        image_b64 = base64.b64encode(image_data).decode()
        result = await GroupService.set_icon(redis, channel_id, group_id, image_b64)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Grupo '{group_id}' no encontrado.",
            )
        return api_response({"message": "Foto del grupo actualizada."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al establecer foto del grupo %s: %s", group_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al establecer la foto del grupo.",
        )
