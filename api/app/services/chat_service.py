# api/app/services/chat_service.py — Servicio de gestión de chats/conversaciones
# Operaciones CRUD, archivado, configuración y sincronización de chats

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.models.chat import Chat
from api.app.models.message import Message

logger = logging.getLogger("agentkit")


class ChatService:
    """Servicio para gestionar conversaciones de WhatsApp."""

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

    # ── Consulta de chats ────────────────────────────────────────

    @staticmethod
    async def get_chats(
        db: AsyncSession,
        channel_id: UUID,
        page: int = 1,
        limit: int = 50,
    ) -> dict:
        """Obtiene la lista paginada de chats de un canal."""
        # Contar total
        count_query = select(func.count(Chat.id)).where(
            Chat.channel_id == channel_id
        )
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Obtener chats paginados, ordenados por último mensaje
        offset = (page - 1) * limit
        query = (
            select(Chat)
            .where(Chat.channel_id == channel_id)
            .order_by(Chat.last_message_at.desc().nullslast())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query)
        chats = list(result.scalars().all())

        return {
            "chats": chats,
            "total": total,
            "page": page,
            "limit": limit,
        }

    @staticmethod
    async def get_chat(
        db: AsyncSession, channel_id: UUID, chat_id: UUID
    ) -> Chat | None:
        """Obtiene un chat específico por su ID interno."""
        query = select(Chat).where(
            Chat.id == chat_id,
            Chat.channel_id == channel_id,
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    # ── Operaciones sobre chats ──────────────────────────────────

    @staticmethod
    async def delete_chat(
        db: AsyncSession,
        redis: Redis,
        channel_id: UUID,
        chat_id: UUID,
    ) -> bool:
        """Elimina un chat: envía comando al engine y elimina de la BD."""
        chat = await ChatService.get_chat(db, channel_id, chat_id)
        if not chat:
            return False

        # Enviar comando al engine
        await ChatService._publish_command(
            redis,
            str(channel_id),
            "delete_chat",
            {"chat_id_wa": chat.chat_id_wa},
        )

        # Eliminar de la BD
        await db.delete(chat)
        await db.flush()

        logger.info(f"Chat eliminado: {chat_id} (wa: {chat.chat_id_wa})")
        return True

    @staticmethod
    async def archive_chat(
        redis: Redis,
        channel_id: UUID,
        chat_id: UUID,
        archive: bool = True,
    ) -> bool:
        """Archiva o desarchiva un chat en WhatsApp."""
        await ChatService._publish_command(
            redis,
            str(channel_id),
            "archive_chat",
            {"chat_id": str(chat_id), "archive": archive},
        )
        return True

    @staticmethod
    async def update_chat_settings(
        redis: Redis,
        channel_id: UUID,
        chat_id: UUID,
        settings: dict,
    ) -> bool:
        """
        Actualiza configuraciones del chat: pin, mute, mark_read, disappearing.
        Cada clave en settings genera un comando diferente al engine.
        """
        commands_map = {
            "pin": "pin_chat",
            "mute": "mute_chat",
            "mark_read": "mark_chat_read",
            "disappearing": "set_disappearing",
        }

        for key, value in settings.items():
            command = commands_map.get(key)
            if command:
                await ChatService._publish_command(
                    redis,
                    str(channel_id),
                    command,
                    {"chat_id": str(chat_id), "value": value},
                )

        return True

    # ── Mensajes de un chat ──────────────────────────────────────

    @staticmethod
    async def get_chat_messages(
        db: AsyncSession,
        channel_id: UUID,
        chat_id: UUID,
        page: int = 1,
        limit: int = 50,
    ) -> dict:
        """Obtiene los mensajes paginados de un chat específico."""
        # Primero obtener el chat para su chat_id_wa
        chat = await ChatService.get_chat(db, channel_id, chat_id)
        if not chat:
            return {"messages": [], "total": 0, "page": page, "limit": limit}

        chat_id_wa = chat.chat_id_wa

        # Contar total de mensajes del chat
        count_query = select(func.count(Message.id)).where(
            Message.channel_id == channel_id,
            Message.chat_id == chat_id_wa,
        )
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Obtener mensajes paginados
        offset = (page - 1) * limit
        query = (
            select(Message)
            .where(
                Message.channel_id == channel_id,
                Message.chat_id == chat_id_wa,
            )
            .order_by(Message.timestamp.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query)
        messages = list(result.scalars().all())

        return {
            "messages": messages,
            "total": total,
            "page": page,
            "limit": limit,
        }

    # ── Sincronización de chats desde el engine ──────────────────

    @staticmethod
    async def sync_chats(
        db: AsyncSession, channel_id: UUID, chats_data: list[dict]
    ) -> int:
        """
        Sincroniza chats recibidos del engine con la BD.
        Crea nuevos o actualiza existentes. Retorna cantidad sincronizada.
        """
        synced_count = 0

        for chat_data in chats_data:
            chat_id_wa = chat_data.get("chat_id_wa", chat_data.get("id", ""))
            if not chat_id_wa:
                continue

            # Buscar chat existente
            query = select(Chat).where(
                Chat.channel_id == channel_id,
                Chat.chat_id_wa == chat_id_wa,
            )
            result = await db.execute(query)
            existing_chat = result.scalar_one_or_none()

            if existing_chat:
                # Actualizar datos existentes
                existing_chat.name = chat_data.get("name", existing_chat.name)
                existing_chat.is_group = chat_data.get(
                    "is_group", existing_chat.is_group
                )
                existing_chat.is_archived = chat_data.get(
                    "is_archived", existing_chat.is_archived
                )
                existing_chat.is_pinned = chat_data.get(
                    "is_pinned", existing_chat.is_pinned
                )
                existing_chat.is_muted = chat_data.get(
                    "is_muted", existing_chat.is_muted
                )
                existing_chat.unread_count = chat_data.get(
                    "unread_count", existing_chat.unread_count
                )
                if chat_data.get("last_message_at"):
                    existing_chat.last_message_at = datetime.fromisoformat(
                        chat_data["last_message_at"]
                    )
                existing_chat.metadata_ = chat_data.get(
                    "metadata", existing_chat.metadata_
                )
            else:
                # Crear chat nuevo
                last_msg_at = None
                if chat_data.get("last_message_at"):
                    last_msg_at = datetime.fromisoformat(
                        chat_data["last_message_at"]
                    )

                new_chat = Chat(
                    id=uuid4(),
                    channel_id=channel_id,
                    chat_id_wa=chat_id_wa,
                    name=chat_data.get("name"),
                    is_group=chat_data.get("is_group", False),
                    is_archived=chat_data.get("is_archived", False),
                    is_pinned=chat_data.get("is_pinned", False),
                    is_muted=chat_data.get("is_muted", False),
                    unread_count=chat_data.get("unread_count", 0),
                    last_message_at=last_msg_at,
                    metadata_=chat_data.get("metadata", {}),
                )
                db.add(new_chat)

            synced_count += 1

        await db.flush()
        logger.info(
            f"Chats sincronizados para canal {channel_id}: {synced_count}"
        )
        return synced_count
