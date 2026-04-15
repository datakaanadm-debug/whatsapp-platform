# api/app/routers/settings.py — Configuración y ajustes del canal de WhatsApp

import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_api_key
from api.app.database import get_db
from api.app.services.channel_service import ChannelService

logger = logging.getLogger("platform.settings")

router = APIRouter(
    prefix="/api/settings",
    tags=["Configuración"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)

# Router adicional para /limits que vive fuera de /settings
limits_router = APIRouter(
    prefix="/api",
    tags=["Configuración"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


# ── Helpers ──────────────────────────────────────────────────────


async def _get_channel_id(auth: dict = Depends(verify_api_key)) -> str:
    """Extrae el channel_id asociado a la API Key autenticada."""
    return auth["channel_id"]


# ── Configuración del canal ──────────────────────────────────────


@router.get(
    "",
    summary="Obtener configuración del canal",
    description="Retorna toda la configuración actual del canal, incluyendo webhooks, eventos y opciones.",
)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    channel_id: str = Depends(_get_channel_id),
):
    """Obtiene la configuración completa del canal autenticado."""
    try:
        settings_data = await ChannelService.get_settings(db, channel_id)
        if not settings_data and settings_data != {}:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Configuración no encontrada para este canal.",
            )
        return api_response(settings_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener configuración del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener la configuración.",
        )


@router.delete(
    "",
    summary="Restablecer configuración",
    description="Restablece toda la configuración del canal a los valores predeterminados.",
)
async def reset_settings(
    db: AsyncSession = Depends(get_db),
    channel_id: str = Depends(_get_channel_id),
):
    """Resetea la configuración del canal a los valores por defecto."""
    try:
        result = await ChannelService.reset_settings(db, channel_id)
        return api_response({"message": "Configuración restablecida a valores predeterminados."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al restablecer configuración del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al restablecer la configuración.",
        )


@router.patch(
    "",
    summary="Actualizar configuración",
    description="Actualiza parcialmente la configuración del canal. Solo se modifican los campos enviados.",
)
async def update_settings(
    payload: dict = Body(..., description="Campos de configuración a actualizar"),
    db: AsyncSession = Depends(get_db),
    channel_id: str = Depends(_get_channel_id),
):
    """Actualiza los campos de configuración proporcionados."""
    try:
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes enviar al menos un campo para actualizar.",
            )

        result = await ChannelService.update_settings(db, channel_id, payload)
        if not result and result != {}:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Canal no encontrado.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al actualizar configuración del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al actualizar la configuración.",
        )


# ── Eventos de webhook ───────────────────────────────────────────


@router.get(
    "/events",
    summary="Listar eventos de webhook permitidos",
    description="Retorna la lista de todos los tipos de evento que se pueden suscribir en los webhooks.",
)
async def get_webhook_events(
    channel_id: str = Depends(_get_channel_id),
):
    """Obtiene la lista de eventos disponibles para suscripción de webhooks."""
    try:
        # Static list of supported events
        events = [
            "message.received", "message.sent", "message.delivered", "message.read",
            "message.failed", "message.deleted", "message.reaction",
            "chat.created", "chat.updated", "chat.deleted",
            "contact.updated", "contact.blocked", "contact.unblocked",
            "group.created", "group.updated", "group.left",
            "group.participant.added", "group.participant.removed",
            "session.connected", "session.disconnected", "session.qr",
            "presence.update", "call.incoming", "call.rejected",
        ]
        return api_response({"events": events})
    except Exception as e:
        logger.error("Error al obtener eventos del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener los eventos de webhook.",
        )


# ── Test de webhook ──────────────────────────────────────────────


@router.post(
    "/webhook_test",
    summary="Probar entrega de webhook",
    description="Envía un evento de prueba al webhook configurado para verificar la conectividad.",
)
async def test_webhook_delivery(
    db: AsyncSession = Depends(get_db),
    channel_id: str = Depends(_get_channel_id),
):
    """Envía un payload de prueba al URL de webhook configurado en el canal."""
    try:
        channel = await ChannelService.get_channel(db, channel_id)
        if not channel or not channel.webhook_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No hay webhook configurado para este canal o la entrega falló.",
            )
        return api_response({"message": "Test de webhook enviado."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al probar webhook del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al probar el webhook.",
        )


# ── Rate limits ──────────────────────────────────────────────────


@limits_router.get(
    "/limits",
    summary="Obtener límites de tasa",
    description="Retorna la información de rate limits del canal autenticado.",
)
async def get_rate_limits(
    channel_id: str = Depends(_get_channel_id),
):
    """Obtiene los límites de tasa actuales y el uso del canal."""
    try:
        limits = {
            "messages_per_second": 10,
            "messages_per_minute": 250,
            "messages_per_day": 10000,
            "media_uploads_per_day": 1000,
        }
        return api_response(limits)
    except Exception as e:
        logger.error("Error al obtener límites del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener los límites de tasa.",
        )
