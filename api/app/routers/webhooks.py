# api/app/routers/webhooks.py — Configuración y gestión de webhooks por canal

import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.schemas.webhook import WebhookCreate, WebhookResponse, WebhookUpdate
from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_channel_access
from api.app.database import get_db
from api.app.services.webhook_service import WebhookService

logger = logging.getLogger("platform.webhooks")

router = APIRouter(
    prefix="/api/{channel_id}/webhooks",
    tags=["Webhooks"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        403: {"model": ErrorResponse, "description": "Sin acceso al canal"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Crear webhook",
    description="Registra un nuevo webhook para recibir eventos del canal.",
)
async def create_webhook(
    channel_id: uuid.UUID,
    payload: WebhookCreate,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Crea un webhook asociado al canal."""
    try:
        webhook = await WebhookService.create_webhook(
            db, channel_id, url=payload.url, events=payload.events, secret=getattr(payload, 'secret', None)
        )
        return api_response(webhook)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al crear webhook en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear el webhook.",
        )


@router.get(
    "",
    summary="Listar webhooks",
    description="Retorna todos los webhooks registrados para el canal.",
)
async def list_webhooks(
    channel_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Lista todos los webhooks del canal."""
    try:
        webhooks = await WebhookService.get_webhooks(db, channel_id)
        return api_response(webhooks)
    except Exception as e:
        logger.error("Error al listar webhooks del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al listar webhooks.",
        )


@router.get(
    "/{webhook_id}",
    summary="Obtener webhook",
    description="Retorna los detalles de un webhook específico.",
)
async def get_webhook(
    channel_id: uuid.UUID,
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Obtiene un webhook por su ID."""
    try:
        webhook = await WebhookService.get_webhook(db, channel_id, webhook_id)
        if not webhook:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Webhook {webhook_id} no encontrado.",
            )
        return api_response(webhook)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener webhook %s: %s", webhook_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener el webhook.",
        )


@router.patch(
    "/{webhook_id}",
    summary="Actualizar webhook",
    description="Actualiza la URL, eventos o estado de un webhook.",
)
async def update_webhook(
    channel_id: uuid.UUID,
    webhook_id: uuid.UUID,
    payload: WebhookUpdate,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Actualiza los campos proporcionados del webhook."""
    try:
        webhook = await WebhookService.update_webhook(
            db, channel_id, webhook_id, **payload.model_dump(exclude_unset=True)
        )
        if not webhook:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Webhook {webhook_id} no encontrado.",
            )
        return api_response(webhook)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al actualizar webhook %s: %s", webhook_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al actualizar el webhook.",
        )


@router.delete(
    "/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar webhook",
    description="Elimina un webhook permanentemente.",
)
async def delete_webhook(
    channel_id: uuid.UUID,
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Elimina un webhook del canal."""
    try:
        deleted = await WebhookService.delete_webhook(db, channel_id, webhook_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Webhook {webhook_id} no encontrado.",
            )
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al eliminar webhook %s: %s", webhook_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al eliminar el webhook.",
        )


@router.get(
    "/{webhook_id}/logs",
    summary="Logs de entrega",
    description="Retorna el historial de entregas de un webhook (éxitos y fallos).",
)
async def get_webhook_logs(
    channel_id: uuid.UUID,
    webhook_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Lista los intentos de entrega del webhook con paginación."""
    try:
        # Verify webhook exists first
        webhook = await WebhookService.get_webhook(db, channel_id, webhook_id)
        if not webhook:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Webhook {webhook_id} no encontrado.",
            )
        logs = await WebhookService.get_logs(db, webhook_id, page=page, limit=limit)
        return api_response(logs)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener logs del webhook %s: %s", webhook_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener los logs.",
        )


@router.post(
    "/{webhook_id}/test",
    summary="Probar webhook",
    description="Envía un evento de prueba al webhook para verificar la conectividad.",
)
async def test_webhook(
    channel_id: uuid.UUID,
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: uuid.UUID = Depends(verify_channel_access),
):
    """Envía un payload de prueba al URL del webhook."""
    try:
        result = await WebhookService.test_webhook(db, webhook_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Webhook {webhook_id} no encontrado.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al probar webhook %s: %s", webhook_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al probar el webhook.",
        )
