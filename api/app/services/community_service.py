# api/app/services/community_service.py — Servicio de gestión de comunidades
# Operaciones completas sobre comunidades de WhatsApp

import asyncio
import json
import logging
from uuid import UUID, uuid4

from redis.asyncio import Redis

logger = logging.getLogger("agentkit")


class CommunityService:
    """Servicio para gestionar comunidades de WhatsApp."""

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

    # ── Consulta de comunidades ──────────────────────────────────

    @staticmethod
    async def get_communities(redis: Redis, channel_id: UUID) -> list:
        """Obtiene todas las comunidades del canal."""
        response = await CommunityService._publish_and_wait(
            redis,
            str(channel_id),
            "get_communities",
        )
        return response.get("communities", [])

    # ── Creación de comunidades ──────────────────────────────────

    @staticmethod
    async def create_community(
        redis: Redis, channel_id: UUID, data: dict
    ) -> dict:
        """
        Crea una comunidad nueva.
        data debe contener: name, description (opcional), participants (opcional)
        """
        response = await CommunityService._publish_and_wait(
            redis,
            str(channel_id),
            "create_community",
            data,
        )
        return response

    # ── Detalle de comunidad ─────────────────────────────────────

    @staticmethod
    async def get_community(
        redis: Redis, channel_id: UUID, community_id: str
    ) -> dict:
        """Obtiene los detalles de una comunidad específica."""
        response = await CommunityService._publish_and_wait(
            redis,
            str(channel_id),
            "get_community",
            {"community_id": community_id},
        )
        return response

    # ── Grupos dentro de la comunidad ────────────────────────────

    @staticmethod
    async def create_group_in_community(
        redis: Redis, channel_id: UUID, community_id: str, data: dict
    ) -> dict:
        """
        Crea un grupo nuevo dentro de una comunidad.
        data debe contener: name, participants (opcional)
        """
        response = await CommunityService._publish_and_wait(
            redis,
            str(channel_id),
            "create_group_in_community",
            {"community_id": community_id, **data},
        )
        return response

    # ── Desactivación ────────────────────────────────────────────

    @staticmethod
    async def deactivate_community(
        redis: Redis, channel_id: UUID, community_id: str
    ) -> bool:
        """Desactiva una comunidad (no se puede eliminar, solo desactivar)."""
        await CommunityService._publish_command(
            redis,
            str(channel_id),
            "deactivate_community",
            {"community_id": community_id},
        )
        return True

    # ── Invitaciones ─────────────────────────────────────────────

    @staticmethod
    async def revoke_invite(
        redis: Redis, channel_id: UUID, community_id: str
    ) -> bool:
        """Revoca el enlace de invitación actual de la comunidad."""
        await CommunityService._publish_command(
            redis,
            str(channel_id),
            "revoke_community_invite",
            {"community_id": community_id},
        )
        return True

    # ── Vinculación de grupos ────────────────────────────────────

    @staticmethod
    async def link_group(
        redis: Redis, channel_id: UUID, community_id: str, group_id: str
    ) -> bool:
        """Vincula un grupo existente a la comunidad."""
        await CommunityService._publish_command(
            redis,
            str(channel_id),
            "link_group_to_community",
            {"community_id": community_id, "group_id": group_id},
        )
        return True

    @staticmethod
    async def unlink_group(
        redis: Redis, channel_id: UUID, community_id: str, group_id: str
    ) -> bool:
        """Desvincula un grupo de la comunidad."""
        await CommunityService._publish_command(
            redis,
            str(channel_id),
            "unlink_group_from_community",
            {"community_id": community_id, "group_id": group_id},
        )
        return True

    # ── Unirse a un grupo de la comunidad ────────────────────────

    @staticmethod
    async def join_group(
        redis: Redis, channel_id: UUID, community_id: str, group_id: str
    ) -> bool:
        """Se une a un grupo dentro de la comunidad."""
        await CommunityService._publish_command(
            redis,
            str(channel_id),
            "join_community_group",
            {"community_id": community_id, "group_id": group_id},
        )
        return True

    # ── Configuración ────────────────────────────────────────────

    @staticmethod
    async def change_settings(
        redis: Redis, channel_id: UUID, community_id: str, settings: dict
    ) -> bool:
        """
        Cambia la configuración de la comunidad.
        settings puede contener: announce, restrict, etc.
        """
        await CommunityService._publish_command(
            redis,
            str(channel_id),
            "change_community_settings",
            {"community_id": community_id, "settings": settings},
        )
        return True

    # ── Gestión de participantes ─────────────────────────────────

    @staticmethod
    async def add_participants(
        redis: Redis,
        channel_id: UUID,
        community_id: str,
        participants: list[str],
    ) -> dict:
        """Agrega participantes a la comunidad."""
        response = await CommunityService._publish_and_wait(
            redis,
            str(channel_id),
            "add_community_participants",
            {"community_id": community_id, "participants": participants},
        )
        return response

    @staticmethod
    async def remove_participants(
        redis: Redis,
        channel_id: UUID,
        community_id: str,
        participants: list[str],
    ) -> dict:
        """Elimina participantes de la comunidad."""
        response = await CommunityService._publish_and_wait(
            redis,
            str(channel_id),
            "remove_community_participants",
            {"community_id": community_id, "participants": participants},
        )
        return response

    @staticmethod
    async def promote_admins(
        redis: Redis,
        channel_id: UUID,
        community_id: str,
        participants: list[str],
    ) -> dict:
        """Promueve participantes a administradores de la comunidad."""
        response = await CommunityService._publish_and_wait(
            redis,
            str(channel_id),
            "promote_community_admins",
            {"community_id": community_id, "participants": participants},
        )
        return response

    @staticmethod
    async def demote_admins(
        redis: Redis,
        channel_id: UUID,
        community_id: str,
        participants: list[str],
    ) -> dict:
        """Degrada administradores a participantes normales."""
        response = await CommunityService._publish_and_wait(
            redis,
            str(channel_id),
            "demote_community_admins",
            {"community_id": community_id, "participants": participants},
        )
        return response

    # ── Subgrupos ────────────────────────────────────────────────

    @staticmethod
    async def get_subgroups(
        redis: Redis, channel_id: UUID, community_id: str
    ) -> list:
        """Obtiene todos los subgrupos de una comunidad."""
        response = await CommunityService._publish_and_wait(
            redis,
            str(channel_id),
            "get_community_subgroups",
            {"community_id": community_id},
        )
        return response.get("subgroups", [])

    # ── Eventos ──────────────────────────────────────────────────

    @staticmethod
    async def create_event(
        redis: Redis, channel_id: UUID, community_id: str, data: dict
    ) -> dict:
        """
        Crea un evento en la comunidad.
        data debe contener: name, description (opcional), start_time, end_time (opcional),
        location (opcional)
        """
        response = await CommunityService._publish_and_wait(
            redis,
            str(channel_id),
            "create_community_event",
            {"community_id": community_id, **data},
        )
        return response

    # ── Creación de grupo ────────────────────────────────────────

    @staticmethod
    async def create_group(
        redis: Redis, channel_id: UUID, community_id: str, data: dict
    ) -> dict:
        """
        Crea un grupo dentro de la comunidad.
        Alias de create_group_in_community para compatibilidad.
        data debe contener: name, participants (opcional)
        """
        return await CommunityService.create_group_in_community(
            redis, channel_id, community_id, data
        )
