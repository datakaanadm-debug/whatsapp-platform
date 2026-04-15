# api/app/routers/media.py — Subida, descarga y gestión de archivos multimedia

import uuid
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_channel_access
from api.app.database import get_db
from api.app.services.media_service import MediaService

logger = logging.getLogger("platform.media")

# Tipos MIME aceptados para subida
ALLOWED_MIME_TYPES = {
    # Imágenes
    "image/jpeg", "image/png", "image/webp", "image/gif",
    # Videos
    "video/mp4", "video/3gpp",
    # Audio
    "audio/mpeg", "audio/ogg", "audio/aac", "audio/amr", "audio/opus",
    # Documentos
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "application/zip",
    # Stickers
    "image/webp",
}

# Tamaño máximo de archivo: 64 MB (límite de WhatsApp para documentos)
MAX_FILE_SIZE = 64 * 1024 * 1024

router = APIRouter(
    prefix="/api/{channel_id}/media",
    tags=["Media"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        403: {"model": ErrorResponse, "description": "Sin acceso al canal"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Subir archivo",
    description="Sube un archivo multimedia al almacenamiento. Retorna un media_id para usar en envíos.",
)
async def upload_media(
    channel_id: uuid.UUID,
    file: UploadFile = File(..., description="Archivo a subir (máx 64 MB)"),
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Sube un archivo y retorna su ID para referenciarlo en mensajes."""
    try:
        # Validar tipo MIME
        if file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tipo de archivo no soportado: {file.content_type}",
            )

        # Leer contenido y validar tamaño
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"El archivo excede el tamaño máximo de {MAX_FILE_SIZE // (1024 * 1024)} MB.",
            )

        media = await MediaService.upload_media(
            db,
            channel_id=channel_id,
            file_data=content,
            filename=file.filename or "unnamed",
            mime_type=file.content_type,
        )
        return api_response(media)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al subir archivo en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al subir el archivo.",
        )


@router.get(
    "/{media_id}",
    summary="Info del archivo",
    description="Retorna los metadatos de un archivo multimedia subido.",
)
async def get_media_info(
    channel_id: uuid.UUID,
    media_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Obtiene los metadatos de un archivo (nombre, tipo, tamaño, URL)."""
    try:
        media = await MediaService.get_media(db, media_id)
        if not media:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Archivo {media_id} no encontrado.",
            )
        return api_response(media)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener info de media %s: %s", media_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener la información del archivo.",
        )


@router.get(
    "/{media_id}/download",
    summary="Descargar archivo",
    description="Descarga el contenido binario de un archivo multimedia.",
    responses={
        200: {"content": {"application/octet-stream": {}}, "description": "Archivo descargado"},
        404: {"model": ErrorResponse, "description": "Archivo no encontrado"},
    },
)
async def download_media(
    channel_id: uuid.UUID,
    media_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Descarga el archivo como stream binario."""
    try:
        data, filename, content_type = await MediaService.download_media(db, media_id)

        # Generar función generadora para StreamingResponse
        async def _stream():
            yield data

        return StreamingResponse(
            _stream(),
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(data)),
            },
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Archivo {media_id} no encontrado.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al descargar media %s: %s", media_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al descargar el archivo.",
        )


@router.delete(
    "/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar archivo",
    description="Elimina un archivo multimedia del almacenamiento.",
)
async def delete_media(
    channel_id: uuid.UUID,
    media_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Elimina un archivo del almacenamiento permanentemente."""
    try:
        deleted = await MediaService.delete_media(db, media_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Archivo {media_id} no encontrado.",
            )
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al eliminar media %s: %s", media_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al eliminar el archivo.",
        )
