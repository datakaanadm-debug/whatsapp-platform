# api/app/services/story_service.py — Servicio de gestión de historias/estados
# Publicación de historias de texto, imagen, video y audio

import asyncio
import json
import logging
from uuid import UUID, uuid4

from redis.asyncio import Redis

logger = logging.getLogger("agentkit")


class StoryService:
    """Servicio para gestionar historias/estados de WhatsApp."""

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

    # ── Consulta de historias ────────────────────────────────────

    @staticmethod
    async def get_stories(redis: Redis, channel_id: UUID) -> list:
        """Obtiene todas las historias visibles para el canal."""
        response = await StoryService._publish_and_wait(
            redis,
            str(channel_id),
            "get_stories",
        )
        return response.get("stories", [])

    @staticmethod
    async def get_story(
        redis: Redis, channel_id: UUID, message_id: str
    ) -> dict:
        """Obtiene una historia específica por su ID de mensaje."""
        response = await StoryService._publish_and_wait(
            redis,
            str(channel_id),
            "get_story",
            {"message_id": message_id},
        )
        return response

    # ── Publicación de historias ─────────────────────────────────

    @staticmethod
    async def send_text_story(
        redis: Redis, channel_id: UUID, text: str, **kwargs
    ) -> dict:
        """
        Publica una historia de texto.
        kwargs opcionales: background_color, font, text_color
        """
        data = {"text": text}
        data.update(kwargs)

        response = await StoryService._publish_and_wait(
            redis,
            str(channel_id),
            "send_text_story",
            data,
        )
        return response

    @staticmethod
    async def send_media_story(
        redis: Redis, channel_id: UUID, media_data: dict, **kwargs
    ) -> dict:
        """
        Publica una historia con imagen o video.
        media_data debe contener: url o base64, mime_type
        kwargs opcionales: caption
        """
        data = {**media_data}
        data.update(kwargs)

        response = await StoryService._publish_and_wait(
            redis,
            str(channel_id),
            "send_media_story",
            data,
        )
        return response

    @staticmethod
    async def send_audio_story(
        redis: Redis, channel_id: UUID, audio_data: dict, **kwargs
    ) -> dict:
        """
        Publica una historia con audio.
        audio_data debe contener: url o base64, mime_type
        """
        data = {**audio_data}
        data.update(kwargs)

        response = await StoryService._publish_and_wait(
            redis,
            str(channel_id),
            "send_audio_story",
            data,
        )
        return response

    # ── Operaciones sobre historias ───────────────────────────────

    @staticmethod
    async def copy_story(
        redis: Redis, channel_id: UUID, message_id: str
    ) -> dict:
        """Copia/repostea una historia de otro contacto."""
        response = await StoryService._publish_and_wait(
            redis,
            str(channel_id),
            "copy_story",
            {"message_id": message_id},
        )
        return response

    @staticmethod
    async def create_story(
        redis: Redis, channel_id: UUID, data: dict
    ) -> dict:
        """
        Crea una historia con datos genéricos.
        data debe contener el tipo y contenido de la historia.
        Útil para tipos de historia personalizados.
        """
        response = await StoryService._publish_and_wait(
            redis,
            str(channel_id),
            "create_story",
            data,
        )
        return response
