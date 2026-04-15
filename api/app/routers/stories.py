# api/app/routers/stories.py — Gestión de historias/estados de WhatsApp (Stories/Status)

import logging
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_api_key
from api.app.database import get_redis
from api.app.services.story_service import StoryService

logger = logging.getLogger("platform.stories")

router = APIRouter(
    prefix="/api/stories",
    tags=["Historias"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


# ── Helpers ──────────────────────────────────────────────────────


async def _get_channel_id(auth: dict = Depends(verify_api_key)) -> str:
    """Extrae el channel_id asociado a la API Key autenticada."""
    return auth["channel_id"]


# ── Listado y consulta ───────────────────────────────────────────


@router.get(
    "",
    summary="Listar historias",
    description="Retorna la lista de historias/estados publicados y visibles para el canal.",
)
async def list_stories(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=200, description="Elementos por página"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Lista todas las historias con paginación."""
    try:
        result = await StoryService.get_stories(redis, channel_id)
        return api_response(result)
    except Exception as e:
        logger.error("Error al listar historias del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al listar las historias.",
        )


@router.get(
    "/{message_id}",
    summary="Obtener historia por ID",
    description="Retorna los detalles de una historia específica por su ID de mensaje.",
)
async def get_story(
    message_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Obtiene una historia específica por su ID."""
    try:
        story = await StoryService.get_story(redis, channel_id, message_id)
        if not story:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Historia '{message_id}' no encontrada.",
            )
        return api_response(story)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener historia %s: %s", message_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener la historia.",
        )


# ── Crear y publicar ─────────────────────────────────────────────


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Crear y publicar historia",
    description="Crea y publica una nueva historia/estado de WhatsApp con contenido genérico.",
)
async def create_story(
    payload: dict = Body(..., description="Datos de la historia a publicar"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Crea y publica una historia con los datos proporcionados."""
    try:
        result = await StoryService.create_story(redis, channel_id, payload)
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al crear historia en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear la historia.",
        )


@router.post(
    "/send/text",
    status_code=status.HTTP_201_CREATED,
    summary="Publicar historia de texto",
    description="Publica una historia/estado de WhatsApp con contenido de texto.",
)
async def send_text_story(
    text: str = Body(..., embed=True, description="Texto de la historia"),
    font: Optional[int] = Body(None, description="Tipo de fuente (0-9)"),
    background_color: Optional[str] = Body(None, alias="backgroundColor", description="Color de fondo en hexadecimal"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Publica una historia con texto personalizado."""
    try:
        kwargs = {}
        if font is not None:
            kwargs["font"] = font
        if background_color is not None:
            kwargs["background_color"] = background_color

        result = await StoryService.send_text_story(redis, channel_id, text, **kwargs)
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al publicar historia de texto en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al publicar la historia de texto.",
        )


@router.post(
    "/send/media",
    status_code=status.HTTP_201_CREATED,
    summary="Publicar historia multimedia",
    description="Publica una historia/estado de WhatsApp con imagen o video.",
)
async def send_media_story(
    media: str = Body(..., description="URL o base64 del archivo multimedia"),
    caption: Optional[str] = Body(None, description="Texto descriptivo del contenido"),
    media_type: Optional[str] = Body(None, alias="mediaType", description="Tipo de media: image o video"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Publica una historia con contenido multimedia (imagen o video)."""
    try:
        media_data = {"media": media}
        if media_type is not None:
            media_data["mediaType"] = media_type

        kwargs = {}
        if caption is not None:
            kwargs["caption"] = caption

        result = await StoryService.send_media_story(redis, channel_id, media_data, **kwargs)
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al publicar historia multimedia en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al publicar la historia multimedia.",
        )


@router.post(
    "/send/audio",
    status_code=status.HTTP_201_CREATED,
    summary="Publicar historia de audio",
    description="Publica una historia/estado de WhatsApp con contenido de audio.",
)
async def send_audio_story(
    audio: str = Body(..., embed=True, description="URL o base64 del archivo de audio"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Publica una historia con contenido de audio."""
    try:
        audio_data = {"audio": audio}

        result = await StoryService.send_audio_story(redis, channel_id, audio_data)
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al publicar historia de audio en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al publicar la historia de audio.",
        )


# ── Copiar historia ──────────────────────────────────────────────


@router.put(
    "/{message_id}",
    summary="Copiar historia",
    description="Copia una historia existente para republicarla.",
)
async def copy_story(
    message_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Copia/republica una historia existente por su ID de mensaje."""
    try:
        result = await StoryService.copy_story(redis, channel_id, message_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Historia '{message_id}' no encontrada.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al copiar historia %s: %s", message_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al copiar la historia.",
        )
