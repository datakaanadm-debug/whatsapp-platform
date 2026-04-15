# api/app/services/user_service.py — Servicio de gestión de usuario/sesión
# QR, autenticación, perfil del usuario conectado y logout

import asyncio
import base64
import json
import logging
from uuid import UUID, uuid4

from redis.asyncio import Redis

logger = logging.getLogger("agentkit")


class UserService:
    """Servicio para gestionar la sesión y perfil del usuario de WhatsApp."""

    # ── Utilidades internas ──────────────────────────────────────

    @staticmethod
    async def _publish_command(
        redis: Redis, channel_id: str, command: str, data: dict = None
    ) -> str:
        """Publica un comando al engine via Redis."""
        request_id = str(uuid4())
        payload = json.dumps({
            "command": command,
            "channel_id": str(channel_id),
            "data": data or {},
            "request_id": request_id,
        })
        await redis.lpush("wa:cmd:queue", payload)
        return request_id

    @staticmethod
    async def _publish_and_wait(
        redis: Redis,
        channel_id: str,
        command: str,
        data: dict = None,
        timeout: int = 30,
    ) -> dict:
        """Publica un comando y espera respuesta del engine."""
        request_id = str(uuid4())
        response_key = f"wa:res:{request_id}"
        payload = json.dumps({
            "command": command,
            "channel_id": str(channel_id),
            "data": data or {},
            "request_id": request_id,
        })
        await redis.lpush("wa:cmd:queue", payload)
        for _ in range(timeout * 10):
            result = await redis.get(response_key)
            if result:
                await redis.delete(response_key)
                return json.loads(result)
            await asyncio.sleep(0.1)
        raise TimeoutError(
            f"El engine no respondió al comando '{command}' en {timeout}s"
        )

    # ── QR Code ──────────────────────────────────────────────────

    @staticmethod
    async def get_qr_base64(redis: Redis, channel_id: UUID) -> dict:
        """
        Obtiene el código QR en formato base64 desde Redis.
        El engine almacena el QR en wa:qr:{channel_id} cuando está disponible.
        """
        qr_data = await redis.get(f"wa:qr:{channel_id}")
        if qr_data:
            return {
                "available": True,
                "qr_base64": qr_data,
                "channel_id": str(channel_id),
            }
        return {
            "available": False,
            "qr_base64": None,
            "channel_id": str(channel_id),
        }

    @staticmethod
    async def get_qr_image(redis: Redis, channel_id: UUID) -> bytes:
        """
        Obtiene el código QR como bytes de imagen PNG.
        Si el QR almacenado es base64, lo decodifica a bytes.
        Lanza ValueError si no hay QR disponible.
        """
        qr_data = await redis.get(f"wa:qr:{channel_id}")
        if not qr_data:
            raise ValueError(
                f"No hay código QR disponible para el canal {channel_id}"
            )

        # Si es base64, decodificar; si ya es un path o URL, el engine lo maneja
        # Limpiar posible prefijo data URI
        if qr_data.startswith("data:"):
            qr_data = qr_data.split(",", 1)[1]

        try:
            return base64.b64decode(qr_data)
        except Exception:
            # Si no es base64 válido, retornar como bytes directamente
            return qr_data.encode("utf-8")

    @staticmethod
    async def get_qr_rawdata(redis: Redis, channel_id: UUID) -> dict:
        """
        Obtiene los datos crudos del QR (string que se codifica en el QR).
        Útil para generar el QR del lado del cliente.
        """
        raw_data = await redis.get(f"wa:qr:raw:{channel_id}")
        if raw_data:
            return {
                "available": True,
                "raw_data": raw_data,
                "channel_id": str(channel_id),
            }
        return {
            "available": False,
            "raw_data": None,
            "channel_id": str(channel_id),
        }

    # ── Autenticación por código ─────────────────────────────────

    @staticmethod
    async def get_auth_code(
        redis: Redis, channel_id: UUID, phone_number: str
    ) -> dict:
        """
        Solicita un código de autenticación para vincular por número de teléfono
        en lugar de QR (pairing code).
        """
        response = await UserService._publish_and_wait(
            redis,
            str(channel_id),
            "get_auth_code",
            {"phone_number": phone_number},
        )
        return response

    # ── Logout ───────────────────────────────────────────────────

    @staticmethod
    async def logout(redis: Redis, channel_id: UUID) -> bool:
        """Cierra la sesión de WhatsApp del canal."""
        await UserService._publish_command(
            redis,
            str(channel_id),
            "logout",
        )

        # Limpiar datos de sesión en Redis
        await redis.delete(f"wa:qr:{channel_id}")
        await redis.delete(f"wa:qr:raw:{channel_id}")
        await redis.delete(f"wa:status:{channel_id}")

        logger.info(f"Sesión cerrada para canal: {channel_id}")
        return True

    # ── Perfil del usuario conectado ─────────────────────────────

    @staticmethod
    async def get_profile(redis: Redis, channel_id: UUID) -> dict:
        """Obtiene el perfil del número de WhatsApp conectado al canal."""
        response = await UserService._publish_and_wait(
            redis,
            str(channel_id),
            "get_my_profile",
        )
        return response

    @staticmethod
    async def update_profile(
        redis: Redis, channel_id: UUID, data: dict
    ) -> dict:
        """
        Actualiza el perfil del número conectado.
        data puede contener: name, about, profile_picture (base64)
        """
        response = await UserService._publish_and_wait(
            redis,
            str(channel_id),
            "update_my_profile",
            data,
        )
        return response

    # ── Estado de texto ──────────────────────────────────────────

    @staticmethod
    async def change_status_text(
        redis: Redis, channel_id: UUID, text: str
    ) -> bool:
        """Cambia el texto de estado (about) del perfil de WhatsApp."""
        await UserService._publish_command(
            redis,
            str(channel_id),
            "change_status_text",
            {"text": text},
        )
        return True
