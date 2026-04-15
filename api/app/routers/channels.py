# api/app/routers/channels.py — CRUD y gestión de sesiones de canales de WhatsApp

import uuid
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.schemas.channel import (
    ChannelCreate,
    ChannelQR,
    ChannelResponse,
    ChannelStatus,
    ChannelUpdate,
)
from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_api_key
from api.app.database import get_db, get_redis
from api.app.services.channel_service import ChannelService

logger = logging.getLogger("platform.channels")

router = APIRouter(
    prefix="/api/channels",
    tags=["Canales"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


# ── CRUD ─────────────────────────────────────────────────────────


@router.post(
    "",
    
    status_code=status.HTTP_201_CREATED,
    summary="Crear canal",
    description="Registra un nuevo canal de WhatsApp. Genera automáticamente una API Key única.",
)
async def create_channel(
    payload: ChannelCreate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Crea un nuevo canal y retorna sus datos incluyendo la API Key generada."""
    try:
        channel = await ChannelService.create_channel(
            db,
            name=payload.name,
            webhook_url=payload.webhook_url,
            webhook_events=payload.webhook_events,
        )
        return api_response(channel)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al crear canal: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear el canal.",
        )


@router.get(
    "",
    
    summary="Listar canales",
    description="Retorna todos los canales registrados, con paginación opcional.",
)
async def list_channels(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=200, description="Elementos por página"),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Lista todos los canales con paginación."""
    try:
        channels = await ChannelService.list_channels(db)
        return api_response({"channels": channels, "total": len(channels), "page": page, "limit": limit})
    except Exception as e:
        logger.error("Error al listar canales: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al listar canales.",
        )


@router.get(
    "/{channel_id}",
    
    summary="Obtener canal",
    description="Retorna los detalles de un canal específico.",
)
async def get_channel(
    channel_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Obtiene un canal por su ID."""
    try:
        channel = await ChannelService.get_channel(db, channel_id)
        if not channel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Canal {channel_id} no encontrado.",
            )
        return api_response(channel)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener el canal.",
        )


@router.patch(
    "/{channel_id}",
    
    summary="Actualizar canal",
    description="Actualiza uno o más campos de un canal existente.",
)
async def update_channel(
    channel_id: uuid.UUID,
    payload: ChannelUpdate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Actualiza los campos proporcionados del canal."""
    try:
        channel = await ChannelService.update_channel(
            db, channel_id, **payload.model_dump(exclude_unset=True)
        )
        if not channel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Canal {channel_id} no encontrado.",
            )
        return api_response(channel)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al actualizar canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al actualizar el canal.",
        )


@router.delete(
    "/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar canal",
    description="Elimina un canal y cierra su sesión si estaba activa.",
)
async def delete_channel(
    channel_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Elimina un canal permanentemente."""
    try:
        deleted = await ChannelService.delete_channel(db, channel_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Canal {channel_id} no encontrado.",
            )
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al eliminar canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al eliminar el canal.",
        )


# ── Gestión de sesión ────────────────────────────────────────────


@router.post(
    "/{channel_id}/start",
    
    summary="Iniciar sesión",
    description="Arranca la sesión de WhatsApp y retorna el código QR para vincular.",
)
async def start_session(
    channel_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    auth: dict = Depends(verify_api_key),
):
    """Inicia la sesión de WhatsApp del canal. Retorna QR si requiere escaneo."""
    try:
        result = await ChannelService.start_session(db, redis, channel_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Canal {channel_id} no encontrado.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al iniciar sesión del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al iniciar la sesión.",
        )


@router.post(
    "/{channel_id}/stop",
    
    summary="Detener sesión",
    description="Detiene la sesión de WhatsApp sin borrar los datos de autenticación.",
)
async def stop_session(
    channel_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    auth: dict = Depends(verify_api_key),
):
    """Detiene la sesión activa manteniendo la autenticación guardada."""
    try:
        result = await ChannelService.stop_session(db, redis, channel_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Canal {channel_id} no encontrado.",
            )
        return api_response({"message": "Sesión detenida correctamente."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al detener sesión del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al detener la sesión.",
        )


@router.get(
    "/{channel_id}/status",
    
    summary="Estado de sesión",
    description="Retorna el estado actual de la sesión de WhatsApp.",
)
async def get_session_status(
    channel_id: uuid.UUID,
    redis: aioredis.Redis = Depends(get_redis),
    auth: dict = Depends(verify_api_key),
):
    """Consulta el estado de la sesión (connected, disconnected, etc.)."""
    try:
        status_data = await ChannelService.get_status(redis, channel_id)
        if not status_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Canal {channel_id} no encontrado.",
            )
        return api_response(status_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener estado del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener el estado.",
        )


@router.get(
    "/{channel_id}/qr",

    summary="Obtener QR",
    description="Retorna el código QR actual para vincular WhatsApp.",
)
async def get_qr_code(
    channel_id: uuid.UUID,
    redis: aioredis.Redis = Depends(get_redis),
    auth: dict = Depends(verify_api_key),
):
    """Obtiene el QR vigente. Solo disponible cuando la sesión está en estado 'connecting'."""
    try:
        qr_data = await ChannelService.get_qr(redis, channel_id)
        if not qr_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="QR no disponible. Inicia la sesión primero con POST /start.",
            )
        return api_response(qr_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener QR del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener el QR.",
        )


@router.get(
    "/{channel_id}/qr.png",
    summary="QR como imagen PNG",
    description="Retorna el QR como imagen PNG para escanear directamente en el navegador.",
    include_in_schema=False,
)
async def get_qr_image(
    channel_id: uuid.UUID,
    redis: aioredis.Redis = Depends(get_redis),
):
    """Imagen QR — abre directamente en el navegador sin API key."""
    import io
    import qrcode
    from fastapi.responses import StreamingResponse

    qr_data = await redis.get(f"wa:qr:{channel_id}")
    if not qr_data:
        from fastapi.responses import HTMLResponse
        return HTMLResponse(
            "<html><body style='background:#000;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;'>"
            "<div style='text-align:center'><h2>QR no disponible</h2>"
            "<p>Inicia la sesion primero, luego recarga esta pagina.</p>"
            "<script>setTimeout(()=>location.reload(), 3000)</script></div></body></html>",
            status_code=200,
        )

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="image/png",
        headers={"Cache-Control": "no-cache, no-store", "Refresh": "5"},
    )


@router.post(
    "/{channel_id}/logout",
    
    summary="Cerrar sesión (logout)",
    description="Cierra la sesión de WhatsApp y borra los datos de autenticación. Requiere volver a escanear QR.",
)
async def logout_session(
    channel_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    auth: dict = Depends(verify_api_key),
):
    """Desvincula la sesión de WhatsApp completamente."""
    try:
        result = await ChannelService.logout_session(db, redis, channel_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Canal {channel_id} no encontrado.",
            )
        return api_response({"message": "Sesión cerrada. Deberás escanear el QR nuevamente."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al cerrar sesión del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al cerrar la sesión.",
        )
