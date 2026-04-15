# api/app/services/presence_service.py — Servicio de presencia y estado de escritura
# Gestión de presencia online/offline, indicadores de escritura y caché

import asyncio
import json
import logging
from uuid import UUID, uuid4

from redis.asyncio import Redis

logger = logging.getLogger("agentkit")

# TTL para caché de presencia en Redis (5 minutos)
PRESENCE_CACHE_TTL = 300


class PresenceService:
    """Servicio para gestionar presencia y estados de escritura."""

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

    # ── Consulta de presencia ────────────────────────────────────

    @staticmethod
    async def get_presence(
        redis: Redis, channel_id: UUID, contact_id: str
    ) -> dict:
        """
        Obtiene la presencia de un contacto.
        Primero revisa el caché de Redis; si no existe, consulta al engine.
        """
        # Revisar caché
        cache_key = f"wa:presence:{channel_id}:{contact_id}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        # Consultar al engine
        response = await PresenceService._publish_and_wait(
            redis,
            str(channel_id),
            "get_presence",
            {"contact_id": contact_id},
        )

        # Guardar en caché
        await redis.setex(
            cache_key,
            PRESENCE_CACHE_TTL,
            json.dumps(response),
        )

        return response

    # ── Suscripción a presencia ──────────────────────────────────

    @staticmethod
    async def subscribe_presence(
        redis: Redis, channel_id: UUID, contact_id: str
    ) -> bool:
        """
        Suscribe al canal para recibir actualizaciones de presencia de un contacto.
        El engine enviará eventos cuando cambie el estado del contacto.
        """
        await PresenceService._publish_command(
            redis,
            str(channel_id),
            "subscribe_presence",
            {"contact_id": contact_id},
        )
        return True

    # ── Estado propio ────────────────────────────────────────────

    @staticmethod
    async def set_my_presence(
        redis: Redis, channel_id: UUID, status: str
    ) -> bool:
        """
        Establece la presencia propia del canal (online/offline).
        status: "online" o "offline"
        """
        if status not in ("online", "offline"):
            logger.warning(f"Estado de presencia no válido: {status}")
            return False

        await PresenceService._publish_command(
            redis,
            str(channel_id),
            "set_presence",
            {"status": status},
        )
        return True

    # ── Indicadores de escritura ─────────────────────────────────

    @staticmethod
    async def send_typing(
        redis: Redis,
        channel_id: UUID,
        chat_id: str,
        composing: bool = True,
    ) -> bool:
        """
        Envía indicador de escritura a un chat.
        composing=True muestra "escribiendo...", composing=False muestra "grabando audio..."
        """
        state = "composing" if composing else "recording"
        await PresenceService._publish_command(
            redis,
            str(channel_id),
            "send_typing",
            {"chat_id": chat_id, "state": state},
        )
        return True

    # ── Actualización de caché ───────────────────────────────────

    @staticmethod
    async def update_cache(
        redis: Redis, contact_id: str, data: dict
    ) -> None:
        """
        Actualiza el caché de presencia de un contacto.
        Llamado internamente cuando el engine envía eventos de presencia.
        El channel_id se extrae del data si está disponible.
        """
        channel_id = data.get("channel_id", "global")
        cache_key = f"wa:presence:{channel_id}:{contact_id}"
        await redis.setex(
            cache_key,
            PRESENCE_CACHE_TTL,
            json.dumps(data),
        )
        logger.debug(f"Caché de presencia actualizado: {contact_id}")
