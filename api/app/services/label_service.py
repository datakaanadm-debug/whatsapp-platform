# api/app/services/label_service.py — Servicio de gestión de etiquetas
# Creación, consulta y asociación de etiquetas a chats/contactos

import asyncio
import json
import logging
from uuid import UUID, uuid4

from redis.asyncio import Redis

logger = logging.getLogger("agentkit")


class LabelService:
    """Servicio para gestionar etiquetas de WhatsApp Business."""

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

    # ── Consulta de etiquetas ────────────────────────────────────

    @staticmethod
    async def get_labels(redis: Redis, channel_id: UUID) -> list:
        """Obtiene todas las etiquetas del canal."""
        response = await LabelService._publish_and_wait(
            redis,
            str(channel_id),
            "get_labels",
        )
        return response.get("labels", [])

    # ── Creación de etiquetas ────────────────────────────────────

    @staticmethod
    async def create_label(
        redis: Redis, channel_id: UUID, data: dict
    ) -> dict:
        """
        Crea una etiqueta nueva.
        data debe contener: name, color (opcional)
        """
        response = await LabelService._publish_and_wait(
            redis,
            str(channel_id),
            "create_label",
            data,
        )
        return response

    # ── Objetos asociados a una etiqueta ─────────────────────────

    @staticmethod
    async def get_label_objects(
        redis: Redis, channel_id: UUID, label_id: str
    ) -> list:
        """Obtiene todos los chats/contactos asociados a una etiqueta."""
        response = await LabelService._publish_and_wait(
            redis,
            str(channel_id),
            "get_label_objects",
            {"label_id": label_id},
        )
        return response.get("objects", [])

    # ── Gestión de asociaciones ──────────────────────────────────

    @staticmethod
    async def add_association(
        redis: Redis, channel_id: UUID, label_id: str, association_id: str
    ) -> bool:
        """
        Asocia un chat o contacto a una etiqueta.
        association_id es el ID del chat o contacto en WhatsApp.
        """
        await LabelService._publish_command(
            redis,
            str(channel_id),
            "add_label_association",
            {"label_id": label_id, "association_id": association_id},
        )
        return True

    @staticmethod
    async def delete_association(
        redis: Redis, channel_id: UUID, label_id: str, association_id: str
    ) -> bool:
        """
        Elimina la asociación de un chat o contacto con una etiqueta.
        """
        await LabelService._publish_command(
            redis,
            str(channel_id),
            "delete_label_association",
            {"label_id": label_id, "association_id": association_id},
        )
        return True
