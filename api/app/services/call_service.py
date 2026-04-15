# api/app/services/call_service.py — Servicio de gestión de llamadas
# Creación de llamadas, rechazo y enlaces de llamada grupal

import asyncio
import json
import logging
from uuid import UUID, uuid4

from redis.asyncio import Redis

logger = logging.getLogger("agentkit")


class CallService:
    """Servicio para gestionar llamadas de WhatsApp."""

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

    # ── Creación de llamadas ─────────────────────────────────────

    @staticmethod
    async def create_call(
        redis: Redis, channel_id: UUID, data: dict
    ) -> dict:
        """
        Inicia una llamada de WhatsApp.
        data debe contener: to (número o JID), type ("voice" o "video")
        """
        response = await CallService._publish_and_wait(
            redis,
            str(channel_id),
            "create_call",
            data,
        )
        return response

    # ── Rechazo de llamadas ──────────────────────────────────────

    @staticmethod
    async def reject_call(
        redis: Redis, channel_id: UUID, call_id: str
    ) -> bool:
        """Rechaza una llamada entrante."""
        await CallService._publish_command(
            redis,
            str(channel_id),
            "reject_call",
            {"call_id": call_id},
        )
        logger.info(f"Llamada rechazada: {call_id}")
        return True

    # ── Enlaces de llamada grupal ────────────────────────────────

    @staticmethod
    async def create_group_call_link(
        redis: Redis, channel_id: UUID
    ) -> dict:
        """
        Crea un enlace para una llamada grupal.
        Retorna un diccionario con el enlace generado.
        """
        response = await CallService._publish_and_wait(
            redis,
            str(channel_id),
            "create_group_call_link",
        )
        return response
