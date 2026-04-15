# api/app/services/status_service.py — Servicio de consulta de vistas de estados
# Obtiene quién ha visto un estado/historia publicado

import asyncio
import json
import logging
from uuid import UUID, uuid4

from redis.asyncio import Redis

logger = logging.getLogger("agentkit")


class StatusService:
    """Servicio para consultar vistas de estados de WhatsApp."""

    # ── Utilidades internas ──────────────────────────────────────

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

    # ── Consulta de vistas de estados ────────────────────────────

    @staticmethod
    async def get_view_statuses(
        redis: Redis, channel_id: UUID, message_id: str
    ) -> dict:
        """
        Obtiene la información de vistas de un estado/historia publicado.
        Retorna quiénes lo han visto y cuándo.
        message_id es el ID del mensaje del estado en WhatsApp.
        """
        response = await StatusService._publish_and_wait(
            redis,
            str(channel_id),
            "get_view_statuses",
            {"message_id": message_id},
        )
        return response
