# api/app/services/group_service.py — Servicio de gestión de grupos
# Operaciones CRUD, participantes, admins, invitaciones y sincronización

import asyncio
import json
import logging
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.models.group import Group

logger = logging.getLogger("agentkit")


class GroupService:
    """Servicio para gestionar grupos de WhatsApp."""

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

    # ── Creación de grupos ───────────────────────────────────────

    @staticmethod
    async def create_group(
        redis: Redis,
        channel_id: UUID,
        name: str,
        participants: list[str],
    ) -> dict:
        """Crea un grupo nuevo en WhatsApp via el engine."""
        response = await GroupService._publish_and_wait(
            redis,
            str(channel_id),
            "create_group",
            {"name": name, "participants": participants},
        )
        return response

    # ── Consulta de grupos ───────────────────────────────────────

    @staticmethod
    async def get_groups(db: AsyncSession, channel_id: UUID) -> list[Group]:
        """Obtiene todos los grupos de un canal."""
        query = (
            select(Group)
            .where(Group.channel_id == channel_id)
            .order_by(Group.name.asc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_group(
        db: AsyncSession, channel_id: UUID, group_id: UUID
    ) -> Group | None:
        """Obtiene un grupo específico por su ID interno."""
        query = select(Group).where(
            Group.id == group_id,
            Group.channel_id == channel_id,
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    # ── Operaciones sobre grupos ─────────────────────────────────

    @staticmethod
    async def update_group(
        redis: Redis, channel_id: UUID, group_id: UUID, data: dict
    ) -> dict:
        """Actualiza información del grupo (nombre, descripción, etc.)."""
        response = await GroupService._publish_and_wait(
            redis,
            str(channel_id),
            "update_group",
            {"group_id": str(group_id), **data},
        )
        return response

    @staticmethod
    async def leave_group(
        redis: Redis, channel_id: UUID, group_id: UUID
    ) -> bool:
        """Sale de un grupo de WhatsApp."""
        await GroupService._publish_command(
            redis,
            str(channel_id),
            "leave_group",
            {"group_id": str(group_id)},
        )
        return True

    @staticmethod
    async def update_setting(
        redis: Redis,
        channel_id: UUID,
        group_id: UUID,
        setting: str,
        value: bool,
    ) -> bool:
        """Actualiza una configuración específica del grupo (announce, restrict, etc.)."""
        await GroupService._publish_command(
            redis,
            str(channel_id),
            "update_group_setting",
            {"group_id": str(group_id), "setting": setting, "value": value},
        )
        return True

    # ── Invitaciones ─────────────────────────────────────────────

    @staticmethod
    async def get_invite(
        redis: Redis, channel_id: UUID, group_id: UUID
    ) -> str:
        """Obtiene el enlace de invitación del grupo."""
        response = await GroupService._publish_and_wait(
            redis,
            str(channel_id),
            "get_group_invite",
            {"group_id": str(group_id)},
        )
        return response.get("invite_link", "")

    @staticmethod
    async def revoke_invite(
        redis: Redis, channel_id: UUID, group_id: UUID
    ) -> bool:
        """Revoca el enlace de invitación actual y genera uno nuevo."""
        await GroupService._publish_command(
            redis,
            str(channel_id),
            "revoke_group_invite",
            {"group_id": str(group_id)},
        )
        return True

    # ── Gestión de participantes ─────────────────────────────────

    @staticmethod
    async def add_participants(
        redis: Redis,
        channel_id: UUID,
        group_id: UUID,
        participants: list[str],
    ) -> dict:
        """Agrega participantes a un grupo."""
        response = await GroupService._publish_and_wait(
            redis,
            str(channel_id),
            "add_group_participants",
            {"group_id": str(group_id), "participants": participants},
        )
        return response

    @staticmethod
    async def remove_participants(
        redis: Redis,
        channel_id: UUID,
        group_id: UUID,
        participants: list[str],
    ) -> dict:
        """Elimina participantes de un grupo."""
        response = await GroupService._publish_and_wait(
            redis,
            str(channel_id),
            "remove_group_participants",
            {"group_id": str(group_id), "participants": participants},
        )
        return response

    @staticmethod
    async def promote_admin(
        redis: Redis,
        channel_id: UUID,
        group_id: UUID,
        participants: list[str],
    ) -> dict:
        """Promueve participantes a administradores del grupo."""
        response = await GroupService._publish_and_wait(
            redis,
            str(channel_id),
            "promote_group_admin",
            {"group_id": str(group_id), "participants": participants},
        )
        return response

    @staticmethod
    async def demote_admin(
        redis: Redis,
        channel_id: UUID,
        group_id: UUID,
        participants: list[str],
    ) -> dict:
        """Degrada administradores a participantes normales."""
        response = await GroupService._publish_and_wait(
            redis,
            str(channel_id),
            "demote_group_admin",
            {"group_id": str(group_id), "participants": participants},
        )
        return response

    # ── Ícono del grupo ──────────────────────────────────────────

    @staticmethod
    async def get_icon(
        redis: Redis, channel_id: UUID, group_id: UUID
    ) -> dict:
        """Obtiene el ícono/foto de perfil del grupo."""
        response = await GroupService._publish_and_wait(
            redis,
            str(channel_id),
            "get_group_icon",
            {"group_id": str(group_id)},
        )
        return response

    @staticmethod
    async def set_icon(
        redis: Redis, channel_id: UUID, group_id: UUID, image_data: str
    ) -> bool:
        """Establece el ícono del grupo (base64 de la imagen)."""
        await GroupService._publish_command(
            redis,
            str(channel_id),
            "set_group_icon",
            {"group_id": str(group_id), "image": image_data},
        )
        return True

    @staticmethod
    async def delete_icon(
        redis: Redis, channel_id: UUID, group_id: UUID
    ) -> bool:
        """Elimina el ícono del grupo."""
        await GroupService._publish_command(
            redis,
            str(channel_id),
            "delete_group_icon",
            {"group_id": str(group_id)},
        )
        return True

    # ── Grupos por invitación ────────────────────────────────────

    @staticmethod
    async def get_group_by_invite(
        redis: Redis, channel_id: UUID, invite_code: str
    ) -> dict:
        """Obtiene información de un grupo usando su código de invitación."""
        response = await GroupService._publish_and_wait(
            redis,
            str(channel_id),
            "get_group_by_invite",
            {"invite_code": invite_code},
        )
        return response

    @staticmethod
    async def accept_invite(
        redis: Redis, channel_id: UUID, invite_code: str
    ) -> dict:
        """Acepta una invitación y se une al grupo."""
        response = await GroupService._publish_and_wait(
            redis,
            str(channel_id),
            "accept_group_invite",
            {"invite_code": invite_code},
        )
        return response

    # ── Solicitudes de ingreso ───────────────────────────────────

    @staticmethod
    async def get_join_requests(
        redis: Redis, channel_id: UUID, group_id: UUID
    ) -> list:
        """Obtiene las solicitudes de ingreso pendientes al grupo."""
        response = await GroupService._publish_and_wait(
            redis,
            str(channel_id),
            "get_group_join_requests",
            {"group_id": str(group_id)},
        )
        return response.get("requests", [])

    @staticmethod
    async def accept_join_request(
        redis: Redis,
        channel_id: UUID,
        group_id: UUID,
        participants: list[str],
    ) -> dict:
        """Acepta solicitudes de ingreso al grupo."""
        response = await GroupService._publish_and_wait(
            redis,
            str(channel_id),
            "accept_group_join_request",
            {"group_id": str(group_id), "participants": participants},
        )
        return response

    @staticmethod
    async def reject_join_request(
        redis: Redis,
        channel_id: UUID,
        group_id: UUID,
        participants: list[str],
    ) -> dict:
        """Rechaza solicitudes de ingreso al grupo."""
        response = await GroupService._publish_and_wait(
            redis,
            str(channel_id),
            "reject_group_join_request",
            {"group_id": str(group_id), "participants": participants},
        )
        return response

    # ── Sincronización desde el engine ───────────────────────────

    @staticmethod
    async def sync_groups(
        db: AsyncSession, channel_id: UUID, groups_data: list[dict]
    ) -> int:
        """
        Sincroniza grupos recibidos del engine con la BD.
        Crea nuevos o actualiza existentes. Retorna cantidad sincronizada.
        """
        synced_count = 0

        for group_data in groups_data:
            group_id_wa = group_data.get(
                "group_id_wa", group_data.get("id", "")
            )
            if not group_id_wa:
                continue

            # Buscar grupo existente
            query = select(Group).where(
                Group.channel_id == channel_id,
                Group.group_id_wa == group_id_wa,
            )
            result = await db.execute(query)
            existing = result.scalar_one_or_none()

            if existing:
                existing.name = group_data.get("name", existing.name)
                existing.description = group_data.get(
                    "description", existing.description
                )
                existing.owner = group_data.get("owner", existing.owner)
                existing.participants = group_data.get(
                    "participants", existing.participants
                )
                existing.admins = group_data.get("admins", existing.admins)
                existing.invite_link = group_data.get(
                    "invite_link", existing.invite_link
                )
                existing.profile_pic_url = group_data.get(
                    "profile_pic_url", existing.profile_pic_url
                )
                existing.settings = group_data.get(
                    "settings", existing.settings
                )
            else:
                new_group = Group(
                    id=uuid4(),
                    channel_id=channel_id,
                    group_id_wa=group_id_wa,
                    name=group_data.get("name", ""),
                    description=group_data.get("description"),
                    owner=group_data.get("owner"),
                    participants=group_data.get("participants", []),
                    admins=group_data.get("admins", []),
                    invite_link=group_data.get("invite_link"),
                    profile_pic_url=group_data.get("profile_pic_url"),
                    settings=group_data.get("settings", {}),
                )
                db.add(new_group)

            synced_count += 1

        await db.flush()
        logger.info(
            f"Grupos sincronizados para canal {channel_id}: {synced_count}"
        )
        return synced_count
