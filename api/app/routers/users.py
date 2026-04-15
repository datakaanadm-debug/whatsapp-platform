# api/app/routers/users.py — Gestión de usuario/autenticación y perfil de WhatsApp

import logging
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import Response

from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_api_key
from api.app.database import get_redis
from api.app.services.user_service import UserService

logger = logging.getLogger("platform.users")

router = APIRouter(
    prefix="/api/users",
    tags=["Usuarios"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


# ── Helpers ──────────────────────────────────────────────────────


async def _get_channel_id(auth: dict = Depends(verify_api_key)) -> str:
    """Extrae el channel_id asociado a la API Key autenticada."""
    return auth["channel_id"]


# ── Login / QR ───────────────────────────────────────────────────


@router.get(
    "/login",
    summary="Obtener QR como JSON base64",
    description="Retorna el código QR para vincular WhatsApp codificado en base64 dentro de un objeto JSON.",
)
async def get_login_qr(
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Genera y retorna el QR de autenticación en formato base64 (JSON)."""
    try:
        qr_data = await UserService.get_qr_base64(redis, channel_id)
        if not qr_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="QR no disponible. Asegúrate de que la sesión esté en estado de conexión.",
            )
        return api_response(qr_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener QR del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener el código QR.",
        )


@router.get(
    "/login/image",
    summary="Obtener QR como imagen PNG",
    description="Retorna el código QR directamente como imagen PNG para mostrarlo en un navegador o app.",
    responses={
        200: {"content": {"image/png": {}}, "description": "Imagen QR en formato PNG"},
    },
)
async def get_login_qr_image(
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Genera y retorna el QR de autenticación como imagen PNG binaria."""
    try:
        image_bytes = await UserService.get_qr_image(redis, channel_id)
        if not image_bytes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="QR no disponible. Asegúrate de que la sesión esté en estado de conexión.",
            )
        return Response(content=image_bytes, media_type="image/png")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Error al obtener imagen QR del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al generar la imagen QR.",
        )


@router.get(
    "/login/rowdata",
    summary="Obtener datos crudos del QR",
    description="Retorna los datos crudos (raw) del código QR sin codificar como imagen.",
)
async def get_login_qr_rawdata(
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Retorna la cadena de texto que codifica el QR para generación externa."""
    try:
        raw_data = await UserService.get_qr_rawdata(redis, channel_id)
        if not raw_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Datos QR no disponibles.",
            )
        return api_response(raw_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener datos QR del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener los datos del QR.",
        )


@router.get(
    "/login/{phone}",
    summary="Obtener código de autenticación por teléfono",
    description="Solicita un código de autenticación para el número de teléfono indicado (autenticación sin QR).",
)
async def get_auth_code_by_phone(
    phone: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Envía un código de autenticación al número de teléfono proporcionado."""
    try:
        result = await UserService.get_auth_code(redis, channel_id, phone)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se pudo obtener el código de autenticación para {phone}.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener código de auth para %s: %s", phone, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al solicitar el código de autenticación.",
        )


# ── Logout ───────────────────────────────────────────────────────


@router.post(
    "/logout",
    summary="Cerrar sesión",
    description="Cierra la sesión activa de WhatsApp. Requiere volver a vincular con QR.",
)
async def logout(
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Desvincula la sesión de WhatsApp del canal."""
    try:
        result = await UserService.logout(redis, channel_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pudo cerrar la sesión. Puede que ya esté desconectada.",
            )
        return api_response({"message": "Sesión cerrada correctamente."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al cerrar sesión del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al cerrar la sesión.",
        )


# ── Perfil ───────────────────────────────────────────────────────


@router.get(
    "/profile",
    summary="Obtener perfil del usuario/canal",
    description="Retorna la información de perfil de WhatsApp asociada al canal autenticado.",
)
async def get_profile(
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Obtiene nombre, foto, estado y demás datos del perfil de WhatsApp."""
    try:
        profile = await UserService.get_profile(redis, channel_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Perfil no disponible. Verifica que la sesión esté activa.",
            )
        return api_response(profile)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener perfil del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener el perfil.",
        )


@router.patch(
    "/profile",
    summary="Actualizar perfil",
    description="Actualiza nombre, estado (about) y/o foto de perfil de WhatsApp.",
)
async def update_profile(
    name: Optional[str] = Body(None, description="Nuevo nombre de perfil"),
    about: Optional[str] = Body(None, description="Nuevo texto de estado (about)"),
    profile_pic: Optional[str] = Body(None, description="URL o base64 de la nueva foto de perfil"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Actualiza uno o más campos del perfil de WhatsApp."""
    try:
        update_data = {}
        if name is not None:
            update_data["name"] = name
        if about is not None:
            update_data["about"] = about
        if profile_pic is not None:
            update_data["profile_pic"] = profile_pic

        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes proporcionar al menos un campo para actualizar (name, about, profile_pic).",
            )

        result = await UserService.update_profile(redis, channel_id, update_data)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pudo actualizar el perfil.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al actualizar perfil del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al actualizar el perfil.",
        )


# ── Status (texto de estado) ────────────────────────────────────

# Nota: Este endpoint usa el prefijo /api/status directamente, fuera de /users.
# Se incluye en este router por afinidad funcional.

status_router = APIRouter(
    prefix="/api",
    tags=["Usuarios"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


@status_router.put(
    "/status",
    summary="Cambiar texto de estado",
    description="Actualiza el texto de estado (status) de WhatsApp del canal autenticado.",
)
async def change_status_text(
    text: str = Body(..., embed=True, description="Nuevo texto de estado"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Cambia el texto de estado visible en el perfil de WhatsApp."""
    try:
        result = await UserService.change_status_text(redis, channel_id, text)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pudo cambiar el texto de estado.",
            )
        return api_response({"message": "Texto de estado actualizado.", "status": text})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al cambiar estado del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al cambiar el texto de estado.",
        )
