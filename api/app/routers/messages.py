# api/app/routers/messages.py — Envío, consulta y gestión de mensajes

import uuid
import logging
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.schemas.message import (
    MessageList,
    MessageResponse,
    MessageSendAudio,
    MessageSendContact,
    MessageSendDocument,
    MessageSendImage,
    MessageSendLocation,
    MessageSendPoll,
    MessageSendReaction,
    MessageSendSticker,
    MessageSendText,
    MessageSendVideo,
)
from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_channel_access
from api.app.database import get_db, get_redis
from api.app.services.message_service import MessageService

logger = logging.getLogger("platform.messages")

router = APIRouter(
    prefix="/api/{channel_id}/messages",
    tags=["Mensajes"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        403: {"model": ErrorResponse, "description": "Sin acceso al canal"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


# ── Envío de mensajes ────────────────────────────────────────────


@router.post(
    "/text",
    status_code=status.HTTP_201_CREATED,
    summary="Enviar texto",
    description="Envía un mensaje de texto plano.",
)
async def send_text(
    channel_id: uuid.UUID,
    payload: MessageSendText,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Envía un mensaje de texto al número indicado."""
    try:
        result = await MessageService.send_message(
            db, redis, channel_id, "text", payload.model_dump()
        )
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al enviar texto en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al enviar el mensaje.",
        )


@router.post(
    "/image",
    status_code=status.HTTP_201_CREATED,
    summary="Enviar imagen",
    description="Envía una imagen con caption opcional.",
)
async def send_image(
    channel_id: uuid.UUID,
    payload: MessageSendImage,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Envía una imagen vía URL o base64."""
    try:
        result = await MessageService.send_message(
            db, redis, channel_id, "image", payload.model_dump()
        )
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al enviar imagen en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al enviar la imagen.",
        )


@router.post(
    "/video",
    status_code=status.HTTP_201_CREATED,
    summary="Enviar video",
    description="Envía un video con caption opcional.",
)
async def send_video(
    channel_id: uuid.UUID,
    payload: MessageSendVideo,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Envía un video vía URL o base64."""
    try:
        result = await MessageService.send_message(
            db, redis, channel_id, "video", payload.model_dump()
        )
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al enviar video en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al enviar el video.",
        )


@router.post(
    "/audio",
    status_code=status.HTTP_201_CREATED,
    summary="Enviar audio",
    description="Envía un archivo de audio o nota de voz.",
)
async def send_audio(
    channel_id: uuid.UUID,
    payload: MessageSendAudio,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Envía audio vía URL o base64."""
    try:
        result = await MessageService.send_message(
            db, redis, channel_id, "audio", payload.model_dump()
        )
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al enviar audio en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al enviar el audio.",
        )


@router.post(
    "/document",
    status_code=status.HTTP_201_CREATED,
    summary="Enviar documento",
    description="Envía un archivo adjunto (PDF, DOCX, etc.).",
)
async def send_document(
    channel_id: uuid.UUID,
    payload: MessageSendDocument,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Envía un documento vía URL o base64."""
    try:
        result = await MessageService.send_message(
            db, redis, channel_id, "document", payload.model_dump()
        )
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al enviar documento en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al enviar el documento.",
        )


@router.post(
    "/location",
    status_code=status.HTTP_201_CREATED,
    summary="Enviar ubicación",
    description="Envía una ubicación geográfica.",
)
async def send_location(
    channel_id: uuid.UUID,
    payload: MessageSendLocation,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Envía una ubicación con coordenadas y nombre opcional."""
    try:
        result = await MessageService.send_message(
            db, redis, channel_id, "location", payload.model_dump()
        )
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al enviar ubicación en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al enviar la ubicación.",
        )


@router.post(
    "/contact",
    status_code=status.HTTP_201_CREATED,
    summary="Enviar contacto",
    description="Envía una o varias tarjetas de contacto vCard.",
)
async def send_contact(
    channel_id: uuid.UUID,
    payload: MessageSendContact,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Envía tarjetas de contacto."""
    try:
        result = await MessageService.send_message(
            db, redis, channel_id, "contact", payload.model_dump()
        )
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al enviar contacto en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al enviar el contacto.",
        )


@router.post(
    "/poll",
    status_code=status.HTTP_201_CREATED,
    summary="Enviar encuesta",
    description="Envía una encuesta con opciones de respuesta.",
)
async def send_poll(
    channel_id: uuid.UUID,
    payload: MessageSendPoll,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Envía una encuesta interactiva."""
    try:
        result = await MessageService.send_message(
            db, redis, channel_id, "poll", payload.model_dump()
        )
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al enviar encuesta en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al enviar la encuesta.",
        )


@router.post(
    "/sticker",
    status_code=status.HTTP_201_CREATED,
    summary="Enviar sticker",
    description="Envía un sticker WebP.",
)
async def send_sticker(
    channel_id: uuid.UUID,
    payload: MessageSendSticker,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Envía un sticker vía URL o base64."""
    try:
        result = await MessageService.send_message(
            db, redis, channel_id, "sticker", payload.model_dump()
        )
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al enviar sticker en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al enviar el sticker.",
        )


@router.post(
    "/reaction",
    status_code=status.HTTP_201_CREATED,
    summary="Enviar reacción",
    description="Reacciona a un mensaje con un emoji.",
)
async def send_reaction(
    channel_id: uuid.UUID,
    payload: MessageSendReaction,
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Agrega o quita una reacción a un mensaje existente."""
    try:
        result = await MessageService.react(
            redis, channel_id, payload.message_id, payload.emoji
        )
        return api_response({"success": result})
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al enviar reacción en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al enviar la reacción.",
        )


# ── Consulta de mensajes ────────────────────────────────────────


@router.get(
    "",
    summary="Listar mensajes",
    description="Lista los mensajes del canal con paginación y filtros opcionales.",
)
async def list_messages(
    channel_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    chat_id: Optional[str] = Query(None, description="Filtrar por chat_id"),
    type: Optional[str] = Query(None, description="Filtrar por tipo de mensaje"),
    from_me: Optional[bool] = Query(None, description="Filtrar mensajes propios/ajenos"),
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Lista mensajes con filtros opcionales."""
    try:
        result = await MessageService.get_messages(
            db,
            channel_id=channel_id,
            chat_id=chat_id,
            msg_type=type,
            page=page,
            limit=limit,
        )
        return api_response(result)
    except Exception as e:
        logger.error("Error al listar mensajes del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al listar mensajes.",
        )


@router.get(
    "/{msg_id}",
    summary="Obtener mensaje",
    description="Retorna los detalles de un mensaje específico.",
)
async def get_message(
    channel_id: uuid.UUID,
    msg_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Obtiene un mensaje por su ID interno."""
    try:
        message = await MessageService.get_message(db, channel_id, msg_id)
        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Mensaje {msg_id} no encontrado.",
            )
        return api_response(message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener mensaje %s: %s", msg_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener el mensaje.",
        )


@router.delete(
    "/{msg_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar mensaje",
    description="Elimina un mensaje para todos los participantes del chat.",
)
async def delete_message(
    channel_id: uuid.UUID,
    msg_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Elimina un mensaje enviado (revoke for everyone)."""
    try:
        deleted = await MessageService.delete_message(db, redis, channel_id, msg_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Mensaje {msg_id} no encontrado.",
            )
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al eliminar mensaje %s: %s", msg_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al eliminar el mensaje.",
        )


@router.post(
    "/{msg_id}/forward",
    status_code=status.HTTP_201_CREATED,
    summary="Reenviar mensaje",
    description="Reenvía un mensaje existente a otro chat.",
)
async def forward_message(
    channel_id: uuid.UUID,
    msg_id: uuid.UUID,
    to: str = Query(..., description="Chat destino del reenvío"),
    redis: aioredis.Redis = Depends(get_redis),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Reenvía un mensaje a otro número o grupo."""
    try:
        result = await MessageService.forward_message(redis, channel_id, msg_id, to)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Mensaje {msg_id} no encontrado.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al reenviar mensaje %s: %s", msg_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al reenviar el mensaje.",
        )
