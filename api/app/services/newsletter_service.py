# api/app/services/newsletter_service.py — Servicio de gestión de newsletters/canales
# Suscripción, administración y publicación en canales de WhatsApp

import asyncio
import json
import logging
from uuid import UUID, uuid4

from redis.asyncio import Redis

logger = logging.getLogger("agentkit")


class NewsletterService:
    """Servicio para gestionar newsletters/canales de WhatsApp."""

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

    # ── Consulta de newsletters ──────────────────────────────────

    @staticmethod
    async def get_newsletters(redis: Redis, channel_id: UUID) -> list:
        """Obtiene todos los newsletters/canales suscritos."""
        response = await NewsletterService._publish_and_wait(
            redis,
            str(channel_id),
            "get_newsletters",
        )
        return response.get("newsletters", [])

    @staticmethod
    async def create_newsletter(
        redis: Redis, channel_id: UUID, data: dict
    ) -> dict:
        """
        Crea un nuevo newsletter/canal.
        data debe contener: name, description (opcional), picture (opcional)
        """
        response = await NewsletterService._publish_and_wait(
            redis,
            str(channel_id),
            "create_newsletter",
            data,
        )
        return response

    @staticmethod
    async def find_newsletters(
        redis: Redis, channel_id: UUID, filters: dict
    ) -> list:
        """
        Busca newsletters por filtros.
        filters puede contener: query (texto), limit, cursor
        """
        response = await NewsletterService._publish_and_wait(
            redis,
            str(channel_id),
            "find_newsletters",
            filters,
        )
        return response.get("newsletters", [])

    @staticmethod
    async def get_recommended(
        redis: Redis, channel_id: UUID, country: str = None
    ) -> list:
        """Obtiene newsletters recomendados, opcionalmente filtrados por país."""
        data = {}
        if country:
            data["country"] = country

        response = await NewsletterService._publish_and_wait(
            redis,
            str(channel_id),
            "get_recommended_newsletters",
            data,
        )
        return response.get("newsletters", [])

    @staticmethod
    async def get_newsletter(
        redis: Redis, channel_id: UUID, newsletter_id: str
    ) -> dict:
        """Obtiene información detallada de un newsletter."""
        response = await NewsletterService._publish_and_wait(
            redis,
            str(channel_id),
            "get_newsletter",
            {"newsletter_id": newsletter_id},
        )
        return response

    # ── Eliminación ──────────────────────────────────────────────

    @staticmethod
    async def delete_newsletter(
        redis: Redis, channel_id: UUID, newsletter_id: str
    ) -> bool:
        """Elimina un newsletter (solo si eres el propietario)."""
        await NewsletterService._publish_command(
            redis,
            str(channel_id),
            "delete_newsletter",
            {"newsletter_id": newsletter_id},
        )
        return True

    # ── Edición ──────────────────────────────────────────────────

    @staticmethod
    async def edit_newsletter(
        redis: Redis, channel_id: UUID, newsletter_id: str, data: dict
    ) -> dict:
        """Edita un newsletter (nombre, descripción, imagen)."""
        response = await NewsletterService._publish_and_wait(
            redis,
            str(channel_id),
            "edit_newsletter",
            {"newsletter_id": newsletter_id, **data},
        )
        return response

    # ── Suscripción ──────────────────────────────────────────────

    @staticmethod
    async def subscribe(
        redis: Redis, channel_id: UUID, newsletter_id: str
    ) -> bool:
        """Suscribirse a un newsletter."""
        await NewsletterService._publish_command(
            redis,
            str(channel_id),
            "subscribe_newsletter",
            {"newsletter_id": newsletter_id},
        )
        return True

    @staticmethod
    async def unsubscribe(
        redis: Redis, channel_id: UUID, newsletter_id: str
    ) -> bool:
        """Desuscribirse de un newsletter."""
        await NewsletterService._publish_command(
            redis,
            str(channel_id),
            "unsubscribe_newsletter",
            {"newsletter_id": newsletter_id},
        )
        return True

    @staticmethod
    async def subscribe_by_invite(
        redis: Redis, channel_id: UUID, invite_code: str
    ) -> bool:
        """Suscribirse a un newsletter usando un código de invitación."""
        await NewsletterService._publish_command(
            redis,
            str(channel_id),
            "subscribe_newsletter_by_invite",
            {"invite_code": invite_code},
        )
        return True

    @staticmethod
    async def unsubscribe_by_invite(
        redis: Redis, channel_id: UUID, invite_code: str
    ) -> bool:
        """Desuscribirse de un newsletter usando su código de invitación."""
        await NewsletterService._publish_command(
            redis,
            str(channel_id),
            "unsubscribe_newsletter_by_invite",
            {"invite_code": invite_code},
        )
        return True

    # ── Seguimiento de actualizaciones ───────────────────────────

    @staticmethod
    async def track_updates(
        redis: Redis, channel_id: UUID, newsletter_id: str
    ) -> bool:
        """Activa el seguimiento de actualizaciones de un newsletter."""
        await NewsletterService._publish_command(
            redis,
            str(channel_id),
            "track_newsletter_updates",
            {"newsletter_id": newsletter_id},
        )
        return True

    # ── Mensajes del newsletter ──────────────────────────────────

    @staticmethod
    async def get_messages(
        redis: Redis, channel_id: UUID, newsletter_id: str
    ) -> list:
        """Obtiene los mensajes/publicaciones de un newsletter."""
        response = await NewsletterService._publish_and_wait(
            redis,
            str(channel_id),
            "get_newsletter_messages",
            {"newsletter_id": newsletter_id},
        )
        return response.get("messages", [])

    # ── Administración ───────────────────────────────────────────

    @staticmethod
    async def create_admin_invite(
        redis: Redis, channel_id: UUID, newsletter_id: str, contact_id: str
    ) -> dict:
        """Crea una invitación de administrador para un contacto."""
        response = await NewsletterService._publish_and_wait(
            redis,
            str(channel_id),
            "create_newsletter_admin_invite",
            {"newsletter_id": newsletter_id, "contact_id": contact_id},
        )
        return response

    @staticmethod
    async def revoke_admin_invite(
        redis: Redis, channel_id: UUID, newsletter_id: str, contact_id: str
    ) -> bool:
        """Revoca una invitación de administrador pendiente."""
        await NewsletterService._publish_command(
            redis,
            str(channel_id),
            "revoke_newsletter_admin_invite",
            {"newsletter_id": newsletter_id, "contact_id": contact_id},
        )
        return True

    @staticmethod
    async def accept_admin_request(
        redis: Redis, channel_id: UUID, newsletter_id: str, contact_id: str
    ) -> bool:
        """Acepta una solicitud de administrador."""
        await NewsletterService._publish_command(
            redis,
            str(channel_id),
            "accept_newsletter_admin_request",
            {"newsletter_id": newsletter_id, "contact_id": contact_id},
        )
        return True

    @staticmethod
    async def demote_admin(
        redis: Redis, channel_id: UUID, newsletter_id: str, contact_id: str
    ) -> bool:
        """Degrada a un administrador del newsletter."""
        await NewsletterService._publish_command(
            redis,
            str(channel_id),
            "demote_newsletter_admin",
            {"newsletter_id": newsletter_id, "contact_id": contact_id},
        )
        return True

    # ── Invitaciones ─────────────────────────────────────────────

    @staticmethod
    async def get_by_invite(
        redis: Redis, channel_id: UUID, invite_code: str
    ) -> dict:
        """Obtiene información de un newsletter por su código de invitación."""
        response = await NewsletterService._publish_and_wait(
            redis,
            str(channel_id),
            "get_newsletter_by_invite",
            {"invite_code": invite_code},
        )
        return response

    @staticmethod
    async def send_invite_link(
        redis: Redis, channel_id: UUID, invite_code: str
    ) -> dict:
        """Envía el enlace de invitación del newsletter."""
        response = await NewsletterService._publish_and_wait(
            redis,
            str(channel_id),
            "send_newsletter_invite_link",
            {"invite_code": invite_code},
        )
        return response
