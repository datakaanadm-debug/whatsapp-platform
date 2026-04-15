# api/app/routers/communities.py — Gestión de comunidades de WhatsApp

import logging
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_api_key
from api.app.database import get_redis
from api.app.services.community_service import CommunityService

logger = logging.getLogger("platform.communities")

router = APIRouter(
    prefix="/api/communities",
    tags=["Comunidades"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


# ── Helpers ──────────────────────────────────────────────────────


async def _get_channel_id(auth: dict = Depends(verify_api_key)) -> str:
    """Extrae el channel_id asociado a la API Key autenticada."""
    return auth["channel_id"]


# ── CRUD de comunidades ──────────────────────────────────────────


@router.get(
    "",
    summary="Listar comunidades",
    description="Retorna las comunidades de WhatsApp en las que participa el canal.",
)
async def list_communities(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=200, description="Elementos por página"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Lista todas las comunidades con paginación."""
    try:
        result = await CommunityService.get_communities(redis, channel_id)
        return api_response(result)
    except Exception as e:
        logger.error("Error al listar comunidades del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al listar comunidades.",
        )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Crear comunidad",
    description="Crea una nueva comunidad de WhatsApp.",
)
async def create_community(
    payload: dict = Body(..., description="Datos de la comunidad (name, description, participants)"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Crea una nueva comunidad con los datos proporcionados."""
    try:
        result = await CommunityService.create_community(redis, channel_id, payload)
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al crear comunidad en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear la comunidad.",
        )


@router.get(
    "/{community_id}",
    summary="Obtener comunidad",
    description="Retorna los detalles de una comunidad específica.",
)
async def get_community(
    community_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Obtiene los detalles de una comunidad por su ID."""
    try:
        community = await CommunityService.get_community(redis, channel_id, community_id)
        if not community:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comunidad '{community_id}' no encontrada.",
            )
        return api_response(community)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener comunidad %s: %s", community_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener la comunidad.",
        )


@router.post(
    "/{community_id}",
    status_code=status.HTTP_201_CREATED,
    summary="Crear grupo en comunidad",
    description="Crea un nuevo grupo dentro de una comunidad existente.",
)
async def create_group_in_community(
    community_id: str,
    payload: dict = Body(..., description="Datos del grupo (name, participants)"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Crea un grupo dentro de la comunidad indicada."""
    try:
        result = await CommunityService.create_group_in_community(redis, channel_id, community_id, payload)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comunidad '{community_id}' no encontrada.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al crear grupo en comunidad %s: %s", community_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear el grupo en la comunidad.",
        )


@router.delete(
    "/{community_id}",
    summary="Desactivar comunidad",
    description="Desactiva una comunidad de WhatsApp. Los grupos vinculados permanecen activos.",
)
async def deactivate_community(
    community_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Desactiva la comunidad sin eliminar los grupos vinculados."""
    try:
        result = await CommunityService.deactivate_community(redis, channel_id, community_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comunidad '{community_id}' no encontrada.",
            )
        return api_response({"message": "Comunidad desactivada correctamente."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al desactivar comunidad %s: %s", community_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al desactivar la comunidad.",
        )


# ── Enlace de invitación ─────────────────────────────────────────


@router.delete(
    "/{community_id}/link",
    summary="Revocar código de invitación",
    description="Revoca el código de invitación actual de la comunidad y genera uno nuevo.",
)
async def revoke_invite_code(
    community_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Revoca el enlace de invitación de la comunidad."""
    try:
        result = await CommunityService.revoke_invite(redis, channel_id, community_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comunidad '{community_id}' no encontrada.",
            )
        return api_response({"message": "Código de invitación revocado."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al revocar invitación de comunidad %s: %s", community_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al revocar el código de invitación.",
        )


# ── Vincular/desvincular grupos ──────────────────────────────────


@router.put(
    "/{community_id}/{group_id}",
    summary="Vincular grupo a comunidad",
    description="Vincula un grupo existente a la comunidad.",
)
async def link_group(
    community_id: str,
    group_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Vincula un grupo existente a la comunidad indicada."""
    try:
        result = await CommunityService.link_group(redis, channel_id, community_id, group_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comunidad '{community_id}' o grupo '{group_id}' no encontrado.",
            )
        return api_response({"message": f"Grupo '{group_id}' vinculado a la comunidad."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al vincular grupo %s a comunidad %s: %s", group_id, community_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al vincular el grupo.",
        )


@router.delete(
    "/{community_id}/{group_id}",
    summary="Desvincular grupo de comunidad",
    description="Desvincula un grupo de la comunidad. El grupo sigue existiendo de forma independiente.",
)
async def unlink_group(
    community_id: str,
    group_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Desvincula un grupo de la comunidad."""
    try:
        result = await CommunityService.unlink_group(redis, channel_id, community_id, group_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Grupo '{group_id}' no encontrado en la comunidad '{community_id}'.",
            )
        return api_response({"message": f"Grupo '{group_id}' desvinculado de la comunidad."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al desvincular grupo %s de comunidad %s: %s", group_id, community_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al desvincular el grupo.",
        )


# ── Unirse a grupo de comunidad ──────────────────────────────────


@router.post(
    "/{community_id}/{group_id}/join",
    summary="Unirse a grupo de comunidad",
    description="Se une a un grupo específico dentro de una comunidad.",
)
async def join_community_group(
    community_id: str,
    group_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Se une al grupo indicado dentro de la comunidad."""
    try:
        result = await CommunityService.join_group(redis, channel_id, community_id, group_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comunidad '{community_id}' o grupo '{group_id}' no encontrado.",
            )
        return api_response({"message": f"Te has unido al grupo '{group_id}'."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al unirse al grupo %s de comunidad %s: %s", group_id, community_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al unirse al grupo.",
        )


# ── Configuración de comunidad ───────────────────────────────────


@router.patch(
    "/{community_id}/settings",
    summary="Cambiar configuración de comunidad",
    description="Actualiza la configuración de una comunidad (nombre, descripción, permisos, etc.).",
)
async def change_community_settings(
    community_id: str,
    payload: dict = Body(..., description="Campos de configuración a actualizar"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Actualiza la configuración de la comunidad."""
    try:
        result = await CommunityService.change_settings(redis, channel_id, community_id, payload)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comunidad '{community_id}' no encontrada.",
            )
        return api_response({"message": "Configuración actualizada."})
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al cambiar configuración de comunidad %s: %s", community_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al cambiar la configuración.",
        )


# ── Gestión de participantes ─────────────────────────────────────


@router.post(
    "/{community_id}/participants",
    summary="Agregar participantes a comunidad",
    description="Agrega uno o más participantes a la comunidad.",
)
async def add_participants(
    community_id: str,
    participants: list[str] = Body(..., embed=True, description="Lista de números de teléfono o contact_ids"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Agrega participantes a la comunidad."""
    try:
        result = await CommunityService.add_participants(redis, channel_id, community_id, participants)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comunidad '{community_id}' no encontrada.",
            )
        return api_response({"message": f"{len(participants)} participante(s) agregado(s) a la comunidad."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al agregar participantes a comunidad %s: %s", community_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al agregar participantes.",
        )


@router.delete(
    "/{community_id}/participants",
    summary="Remover participantes de comunidad",
    description="Remueve uno o más participantes de la comunidad.",
)
async def remove_participants(
    community_id: str,
    participants: list[str] = Body(..., embed=True, description="Lista de números de teléfono o contact_ids"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Remueve participantes de la comunidad."""
    try:
        result = await CommunityService.remove_participants(redis, channel_id, community_id, participants)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comunidad '{community_id}' no encontrada.",
            )
        return api_response({"message": f"{len(participants)} participante(s) removido(s) de la comunidad."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al remover participantes de comunidad %s: %s", community_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al remover participantes.",
        )


# ── Gestión de administradores ───────────────────────────────────


@router.patch(
    "/{community_id}/admins",
    summary="Promover administradores",
    description="Promueve uno o más participantes a administradores de la comunidad.",
)
async def promote_admins(
    community_id: str,
    participants: list[str] = Body(..., embed=True, description="Lista de participantes a promover"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Promueve participantes a administradores."""
    try:
        result = await CommunityService.promote_admins(redis, channel_id, community_id, participants)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comunidad '{community_id}' no encontrada.",
            )
        return api_response({"message": f"{len(participants)} participante(s) promovido(s) a administrador."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al promover admins en comunidad %s: %s", community_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al promover administradores.",
        )


@router.delete(
    "/{community_id}/admins",
    summary="Degradar administradores",
    description="Degrada uno o más administradores a participantes regulares.",
)
async def demote_admins(
    community_id: str,
    participants: list[str] = Body(..., embed=True, description="Lista de administradores a degradar"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Degrada administradores a participantes regulares."""
    try:
        result = await CommunityService.demote_admins(redis, channel_id, community_id, participants)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comunidad '{community_id}' no encontrada.",
            )
        return api_response({"message": f"{len(participants)} administrador(es) degradado(s)."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al degradar admins en comunidad %s: %s", community_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al degradar administradores.",
        )


# ── Subgrupos ────────────────────────────────────────────────────


@router.get(
    "/{community_id}/subgroups",
    summary="Obtener subgrupos de comunidad",
    description="Retorna la lista de grupos vinculados a la comunidad.",
)
async def get_subgroups(
    community_id: str,
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=200, description="Elementos por página"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Lista los subgrupos de una comunidad con paginación."""
    try:
        result = await CommunityService.get_subgroups(redis, channel_id, community_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comunidad '{community_id}' no encontrada.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener subgrupos de comunidad %s: %s", community_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener los subgrupos.",
        )


# ── Eventos ──────────────────────────────────────────────────────


@router.post(
    "/event",
    status_code=status.HTTP_201_CREATED,
    summary="Crear evento en comunidad",
    description="Crea un evento dentro del contexto de una comunidad.",
)
async def create_event(
    payload: dict = Body(..., description="Datos del evento (name, description, start_time, end_time, community_id, location)"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Crea un evento asociado a una comunidad."""
    try:
        community_id = payload.get("community_id", "")
        result = await CommunityService.create_event(redis, channel_id, community_id, payload)
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al crear evento en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear el evento.",
        )


# ── Crear grupo en comunidad (alias) ─────────────────────────────


@router.post(
    "/{community_id}/createGroup",
    status_code=status.HTTP_201_CREATED,
    summary="Crear grupo en comunidad (alias)",
    description="Alias alternativo para crear un grupo dentro de una comunidad existente.",
)
async def create_group_alias(
    community_id: str,
    payload: dict = Body(..., description="Datos del grupo (name, participants)"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Crea un grupo dentro de la comunidad (endpoint alternativo)."""
    try:
        result = await CommunityService.create_group_in_community(redis, channel_id, community_id, payload)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comunidad '{community_id}' no encontrada.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al crear grupo en comunidad %s: %s", community_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear el grupo en la comunidad.",
        )
