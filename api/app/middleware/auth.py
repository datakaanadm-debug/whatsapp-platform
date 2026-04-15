# api/app/middleware/auth.py — Autenticación por API Key y rate limiting
#
# Provee dos dependencias reutilizables de FastAPI:
#   - verify_api_key: valida la cabecera X-API-Key contra la base de datos
#   - rate_limiter:   limita peticiones por IP usando slowapi

import uuid
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.app.config import Settings, get_settings

logger = logging.getLogger("platform.auth")

# ── Esquema de seguridad para Swagger ────────────────────────────

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ── Rate limiter global (slowapi) ────────────────────────────────

limiter = Limiter(key_func=get_remote_address)


def get_limiter() -> Limiter:
    """Retorna la instancia global del rate limiter."""
    return limiter


# ── Dependencia: verificar API Key ───────────────────────────────

async def verify_api_key(
    request: Request,
    api_key: Optional[str] = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> dict:
    """
    Valida la API Key recibida en la cabecera X-API-Key.

    Busca la key en la base de datos y devuelve un diccionario con
    la información del canal asociado. Lanza 401 si la key no existe
    o está desactivada.

    Retorna:
        dict con channel_id, channel_name, is_active
    """
    if not api_key:
        # También aceptar formato Bearer en Authorization
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key requerida. Envíala en la cabecera X-API-Key o como Bearer token.",
        )

    # Buscar la key en la base de datos
    from sqlalchemy import select, text
    from api.app.database import async_session_factory

    async with async_session_factory() as session:
        # Consulta directa a la tabla channels para validar la api_key
        query = text(
            "SELECT id, name, is_active FROM channels WHERE api_key = :api_key LIMIT 1"
        )
        result = await session.execute(query, {"api_key": api_key})
        row = result.fetchone()

        if not row:
            logger.warning("API Key inválida: %s...", api_key[:12])
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key inválida o no encontrada.",
            )

        channel_id, channel_name, is_active = row

        if not is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El canal asociado a esta API Key está desactivado.",
            )

        logger.debug("API Key válida para canal: %s (%s)", channel_name, channel_id)

        return {
            "channel_id": channel_id,
            "channel_name": channel_name,
            "is_active": is_active,
        }

    # Si no se pudo obtener sesión de base de datos
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="No se pudo conectar a la base de datos para validar la API Key.",
    )


# ── Dependencia: verificar API Key y extraer channel_id ──────────

async def get_current_channel_id(
    auth_data: dict = Depends(verify_api_key),
) -> uuid.UUID:
    """
    Atajo que extrae solo el channel_id del resultado de verify_api_key.
    Útil en endpoints donde solo necesitas el ID del canal autenticado.
    """
    return auth_data["channel_id"]


# ── Dependencia: verificar que el channel_id del path coincide ───

async def verify_channel_access(
    channel_id: uuid.UUID,
    auth_data: dict = Depends(verify_api_key),
) -> uuid.UUID:
    """
    Verifica que la API Key corresponda al canal indicado en el path.
    Esto impide que una key de un canal acceda a recursos de otro.
    """
    if str(auth_data["channel_id"]) != str(channel_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La API Key no tiene acceso a este canal.",
        )
    return channel_id
