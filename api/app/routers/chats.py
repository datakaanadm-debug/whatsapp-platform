# api/app/routers/chats.py — Gestión de chats / conversaciones

import uuid
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.schemas.chat import ChatAction, ChatList, ChatResponse
from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_channel_access
from api.app.database import get_db, get_redis
from api.app.services.chat_service import ChatService

logger = logging.getLogger("platform.chats")

router = APIRouter(
    prefix="/api/{channel_id}/chats",
    tags=["Chats"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        403: {"model": ErrorResponse, "description": "Sin acceso al canal"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


@router.get(
    "",
    summary="Listar chats",
    description="Retorna todos los chats del canal con paginación.",
)
async def list_chats(
    channel_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    is_group: bool | None = Query(None, description="Filtrar solo grupos o solo chats individuales"),
    is_archived: bool | None = Query(None, description="Filtrar por estado de archivo"),
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Lista chats con filtros opcionales."""
    try:
        result = await ChatService.get_chats(
            db,
            channel_id=channel_id,
            page=page,
            limit=limit,
        )
        return api_response(result)
    except Exception as e:
        logger.error("Error al listar chats del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al listar chats.",
        )


@router.get(
    "/{chat_id}",
    summary="Obtener chat",
    description="Retorna los detalles de un chat específico.",
)
async def get_chat(
    channel_id: uuid.UUID,
    chat_id: str,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Obtiene un chat por su ID de WhatsApp."""
    try:
        chat = await ChatService.get_chat(db, channel_id, chat_id)
        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat '{chat_id}' no encontrado.",
            )
        return api_response(chat)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener chat %s: %s", chat_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener el chat.",
        )


@router.post(
    "/{chat_id}/action",
    summary="Ejecutar acción sobre chat",
    description="Ejecuta una acción como archivar, fijar, silenciar o marcar como leído.",
)
async def chat_action(
    channel_id: uuid.UUID,
    chat_id: str,
    payload: ChatAction,
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Ejecuta la acción indicada sobre el chat."""
    try:
        result = await ChatService.update_chat_settings(
            redis, channel_id, chat_id, {payload.action: True}
        )
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat '{chat_id}' no encontrado.",
            )
        return api_response({"message": f"Acción '{payload.action}' ejecutada correctamente."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al ejecutar acción en chat %s: %s", chat_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al ejecutar la acción.",
        )


@router.delete(
    "/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar chat",
    description="Elimina un chat y todo su historial de mensajes.",
)
async def delete_chat(
    channel_id: uuid.UUID,
    chat_id: str,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Elimina un chat permanentemente."""
    try:
        deleted = await ChatService.delete_chat(db, redis, channel_id, chat_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat '{chat_id}' no encontrado.",
            )
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al eliminar chat %s: %s", chat_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al eliminar el chat.",
        )


@router.get(
    "/{chat_id}/messages",
    summary="Mensajes de un chat",
    description="Lista los mensajes de un chat específico con paginación.",
)
async def get_chat_messages(
    channel_id: uuid.UUID,
    chat_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Lista mensajes de un chat con paginación."""
    try:
        result = await ChatService.get_chat_messages(
            db,
            channel_id=channel_id,
            chat_id=chat_id,
            page=page,
            limit=limit,
        )
        return api_response(result)
    except Exception as e:
        logger.error("Error al listar mensajes del chat %s: %s", chat_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al listar mensajes del chat.",
        )
