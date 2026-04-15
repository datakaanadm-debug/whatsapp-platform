# api/app/services/blacklist_service.py — Servicio de gestión de lista negra
# Bloqueo y desbloqueo de contactos a nivel de WhatsApp

import asyncio
import json
import logging
from uuid import UUID, uuid4

from redis.asyncio import Redis

logger = logging.getLogger("agentkit")


class BlacklistService:
    """Servicio para gestionar la lista negra (contactos bloqueados) de WhatsApp."""

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

    # ── Consulta de lista negra ──────────────────────────────────

    @staticmethod
    async def get_blacklist(redis: Redis, channel_id: UUID) -> list:
        """Obtiene la lista de contactos bloqueados del canal."""
        response = await BlacklistService._publish_and_wait(
            redis,
            str(channel_id),
            "get_blacklist",
        )
        return response.get("blocked", [])

    # ── Agregar a lista negra ────────────────────────────────────

    @staticmethod
    async def add_to_blacklist(
        redis: Redis, channel_id: UUID, contact_id: str
    ) -> bool:
        """
        Agrega un contacto a la lista negra (lo bloquea en WhatsApp).
        contact_id es el ID del contacto en WhatsApp (número@s.whatsapp.net).
        """
        await BlacklistService._publish_command(
            redis,
            str(channel_id),
            "block_contact",
            {"contact_id": contact_id},
        )
        logger.info(f"Contacto agregado a lista negra: {contact_id}")
        return True

    # ── Eliminar de lista negra ──────────────────────────────────

    @staticmethod
    async def remove_from_blacklist(
        redis: Redis, channel_id: UUID, contact_id: str
    ) -> bool:
        """
        Elimina un contacto de la lista negra (lo desbloquea en WhatsApp).
        """
        await BlacklistService._publish_command(
            redis,
            str(channel_id),
            "unblock_contact",
            {"contact_id": contact_id},
        )
        logger.info(f"Contacto eliminado de lista negra: {contact_id}")
        return True
