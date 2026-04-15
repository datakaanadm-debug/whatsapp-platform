# api/app/routers/newsletters.py — Gestión de canales/newsletters de WhatsApp (Threads)

import logging
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_api_key
from api.app.database import get_redis
from api.app.services.newsletter_service import NewsletterService

logger = logging.getLogger("platform.newsletters")

router = APIRouter(
    prefix="/api/newsletters",
    tags=["Newsletters"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


# ── Helpers ──────────────────────────────────────────────────────


async def _get_channel_id(auth: dict = Depends(verify_api_key)) -> str:
    """Extrae el channel_id asociado a la API Key autenticada."""
    return auth["channel_id"]


# ── CRUD de newsletters ──────────────────────────────────────────


@router.get(
    "",
    summary="Listar newsletters",
    description="Retorna las newsletters/canales de WhatsApp del canal autenticado.",
)
async def list_newsletters(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=200, description="Elementos por página"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Lista todas las newsletters con paginación."""
    try:
        result = await NewsletterService.get_newsletters(redis, channel_id)
        return api_response(result)
    except Exception as e:
        logger.error("Error al listar newsletters del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al listar newsletters.",
        )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Crear newsletter",
    description="Crea un nuevo canal/newsletter de WhatsApp.",
)
async def create_newsletter(
    payload: dict = Body(..., description="Datos de la newsletter (name, description, picture)"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Crea una nueva newsletter con los datos proporcionados."""
    try:
        result = await NewsletterService.create_newsletter(redis, channel_id, payload)
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al crear newsletter en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear la newsletter.",
        )


# ── Búsqueda y recomendaciones ───────────────────────────────────


@router.get(
    "/find",
    summary="Buscar newsletters",
    description="Busca newsletters por filtros como nombre o categoría.",
)
async def find_newsletters(
    query: Optional[str] = Query(None, description="Texto de búsqueda"),
    category: Optional[str] = Query(None, description="Categoría para filtrar"),
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=200, description="Elementos por página"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Busca newsletters aplicando los filtros proporcionados."""
    try:
        filters = {}
        if query:
            filters["query"] = query
        if category:
            filters["category"] = category

        result = await NewsletterService.find_newsletters(redis, channel_id, filters)
        return api_response(result)
    except Exception as e:
        logger.error("Error al buscar newsletters: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al buscar newsletters.",
        )


@router.get(
    "/recommended",
    summary="Newsletters recomendadas",
    description="Retorna newsletters recomendadas filtradas por país.",
)
async def get_recommended_newsletters(
    country: Optional[str] = Query(None, description="Código de país ISO 3166-1 alpha-2 (ej: MX, US, ES)"),
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=200, description="Elementos por página"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Obtiene newsletters recomendadas, opcionalmente filtradas por país."""
    try:
        result = await NewsletterService.get_recommended(redis, channel_id, country=country)
        return api_response(result)
    except Exception as e:
        logger.error("Error al obtener newsletters recomendadas: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener newsletters recomendadas.",
        )


# ── Operaciones por newsletter ID ────────────────────────────────


@router.get(
    "/{newsletter_id}",
    summary="Obtener newsletter",
    description="Retorna los detalles de una newsletter específica.",
)
async def get_newsletter(
    newsletter_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Obtiene los detalles de una newsletter por su ID."""
    try:
        newsletter = await NewsletterService.get_newsletter(redis, channel_id, newsletter_id)
        if not newsletter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Newsletter '{newsletter_id}' no encontrada.",
            )
        return api_response(newsletter)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener newsletter %s: %s", newsletter_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener la newsletter.",
        )


@router.delete(
    "/{newsletter_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar newsletter",
    description="Elimina permanentemente una newsletter de WhatsApp.",
)
async def delete_newsletter(
    newsletter_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Elimina una newsletter por su ID."""
    try:
        deleted = await NewsletterService.delete_newsletter(redis, channel_id, newsletter_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Newsletter '{newsletter_id}' no encontrada.",
            )
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al eliminar newsletter %s: %s", newsletter_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al eliminar la newsletter.",
        )


@router.patch(
    "/{newsletter_id}",
    summary="Editar newsletter",
    description="Actualiza nombre, descripción u otros campos de una newsletter.",
)
async def edit_newsletter(
    newsletter_id: str,
    payload: dict = Body(..., description="Campos a actualizar"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Edita los campos proporcionados de una newsletter."""
    try:
        result = await NewsletterService.edit_newsletter(redis, channel_id, newsletter_id, payload)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Newsletter '{newsletter_id}' no encontrada.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al editar newsletter %s: %s", newsletter_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al editar la newsletter.",
        )


# ── Suscripciones ────────────────────────────────────────────────


@router.post(
    "/{newsletter_id}/subscription",
    summary="Suscribirse a newsletter",
    description="Suscribe al canal autenticado a la newsletter indicada.",
)
async def subscribe_to_newsletter(
    newsletter_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Suscribe al canal a una newsletter específica."""
    try:
        result = await NewsletterService.subscribe(redis, channel_id, newsletter_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Newsletter '{newsletter_id}' no encontrada.",
            )
        return api_response({"message": "Suscripción exitosa."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al suscribirse a newsletter %s: %s", newsletter_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al suscribirse a la newsletter.",
        )


@router.delete(
    "/{newsletter_id}/subscription",
    summary="Desuscribirse de newsletter",
    description="Cancela la suscripción a la newsletter indicada.",
)
async def unsubscribe_from_newsletter(
    newsletter_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Cancela la suscripción del canal a una newsletter."""
    try:
        result = await NewsletterService.unsubscribe(redis, channel_id, newsletter_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Newsletter '{newsletter_id}' no encontrada o no estás suscrito.",
            )
        return api_response({"message": "Suscripción cancelada."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al desuscribirse de newsletter %s: %s", newsletter_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al cancelar la suscripción.",
        )


# ── Suscripciones por código de invitación ───────────────────────


@router.post(
    "/invite/{code}/subscription",
    summary="Suscribirse por código de invitación",
    description="Suscribe al canal usando un código de invitación de newsletter.",
)
async def subscribe_by_invite_code(
    code: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Suscribe al canal usando un código de invitación."""
    try:
        result = await NewsletterService.subscribe_by_invite(redis, channel_id, code)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Código de invitación '{code}' inválido o expirado.",
            )
        return api_response({"message": "Suscripción por invitación exitosa."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al suscribirse con código %s: %s", code, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al procesar la invitación.",
        )


@router.delete(
    "/invite/{code}/subscription",
    summary="Desuscribirse por código de invitación",
    description="Cancela la suscripción asociada a un código de invitación.",
)
async def unsubscribe_by_invite_code(
    code: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Cancela la suscripción usando el código de invitación original."""
    try:
        result = await NewsletterService.unsubscribe_by_invite(redis, channel_id, code)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Código de invitación '{code}' inválido.",
            )
        return api_response({"message": "Suscripción cancelada."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al desuscribirse con código %s: %s", code, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al cancelar la suscripción por invitación.",
        )


# ── Seguimiento de actualizaciones ───────────────────────────────


@router.post(
    "/{newsletter_id}/tracking",
    summary="Suscribirse a actualizaciones",
    description="Activa el seguimiento (tracking) de actualizaciones de una newsletter para recibir notificaciones en tiempo real.",
)
async def subscribe_to_updates(
    newsletter_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Activa el tracking de una newsletter para recibir eventos de actualización."""
    try:
        result = await NewsletterService.track_updates(redis, channel_id, newsletter_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Newsletter '{newsletter_id}' no encontrada.",
            )
        return api_response({"message": "Seguimiento de actualizaciones activado."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al activar tracking de newsletter %s: %s", newsletter_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al activar el seguimiento.",
        )


# ── Mensajes de newsletter ───────────────────────────────────────


@router.get(
    "/{newsletter_id}/messages",
    summary="Obtener mensajes de newsletter",
    description="Retorna los mensajes publicados en una newsletter con paginación.",
)
async def get_newsletter_messages(
    newsletter_id: str,
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=200, description="Elementos por página"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Lista los mensajes de una newsletter específica."""
    try:
        result = await NewsletterService.get_messages(redis, channel_id, newsletter_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Newsletter '{newsletter_id}' no encontrada.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener mensajes de newsletter %s: %s", newsletter_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener los mensajes.",
        )


# ── Gestión de administradores ───────────────────────────────────


@router.post(
    "/{newsletter_id}/invite/{contact_id}",
    summary="Crear invitación de administrador",
    description="Envía una invitación a un contacto para ser administrador de la newsletter.",
)
async def create_admin_invite(
    newsletter_id: str,
    contact_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Envía invitación de administrador a un contacto."""
    try:
        result = await NewsletterService.create_admin_invite(redis, channel_id, newsletter_id, contact_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Newsletter '{newsletter_id}' o contacto '{contact_id}' no encontrado.",
            )
        return api_response({"message": "Invitación de administrador enviada."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al crear invitación de admin en newsletter %s: %s", newsletter_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear la invitación de administrador.",
        )


@router.delete(
    "/{newsletter_id}/invite/{contact_id}",
    summary="Revocar invitación de administrador",
    description="Revoca una invitación de administrador pendiente.",
)
async def revoke_admin_invite(
    newsletter_id: str,
    contact_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Revoca la invitación de administrador para un contacto."""
    try:
        result = await NewsletterService.revoke_admin_invite(redis, channel_id, newsletter_id, contact_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invitación no encontrada para el contacto '{contact_id}'.",
            )
        return api_response({"message": "Invitación de administrador revocada."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al revocar invitación de admin en newsletter %s: %s", newsletter_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al revocar la invitación.",
        )


@router.put(
    "/{newsletter_id}/admins/{contact_id}",
    summary="Aceptar solicitud de administrador",
    description="Acepta una solicitud pendiente para agregar un contacto como administrador.",
)
async def accept_admin_request(
    newsletter_id: str,
    contact_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Acepta la solicitud de administrador de un contacto."""
    try:
        result = await NewsletterService.accept_admin_request(redis, channel_id, newsletter_id, contact_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Solicitud de administrador no encontrada.",
            )
        return api_response({"message": "Administrador aceptado correctamente."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al aceptar admin en newsletter %s: %s", newsletter_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al aceptar la solicitud de administrador.",
        )


@router.delete(
    "/{newsletter_id}/admins/{contact_id}",
    summary="Degradar administrador",
    description="Remueve los permisos de administrador de un contacto en la newsletter.",
)
async def demote_admin(
    newsletter_id: str,
    contact_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Degrada a un administrador a miembro regular."""
    try:
        result = await NewsletterService.demote_admin(redis, channel_id, newsletter_id, contact_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Administrador '{contact_id}' no encontrado en la newsletter.",
            )
        return api_response({"message": "Administrador degradado correctamente."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al degradar admin en newsletter %s: %s", newsletter_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al degradar al administrador.",
        )


# ── Enlaces de invitación ────────────────────────────────────────


@router.post(
    "/link/{code}",
    summary="Enviar enlace de invitación",
    description="Envía un enlace de invitación de newsletter a través de WhatsApp.",
)
async def send_invite_link(
    code: str,
    to: str = Body(..., embed=True, description="Número de teléfono o chat_id destino"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Envía un enlace de invitación de newsletter a un contacto."""
    try:
        result = await NewsletterService.send_invite_link(redis, channel_id, code)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se pudo enviar el enlace con código '{code}'.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al enviar enlace de invitación %s: %s", code, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al enviar el enlace de invitación.",
        )


@router.get(
    "/link/{code}",
    summary="Obtener info por código de invitación",
    description="Retorna la información de una newsletter a partir de su código de invitación.",
)
async def get_info_by_invite_code(
    code: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Obtiene la información de una newsletter usando su código de invitación."""
    try:
        result = await NewsletterService.get_by_invite(redis, channel_id, code)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Código de invitación '{code}' no encontrado o expirado.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener info por código %s: %s", code, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener información por código de invitación.",
        )
