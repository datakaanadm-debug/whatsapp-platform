# api/app/services/message_service.py — Servicio de gestión de mensajes
# Envío, recepción, paginación y operaciones sobre mensajes de WhatsApp

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.models.message import Message, MessageStatus, MessageType

logger = logging.getLogger("agentkit")


class MessageService:
    """Servicio para gestionar mensajes de WhatsApp."""

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

    # ── Envío de mensajes ────────────────────────────────────────

    @staticmethod
    async def send_message(
        db: AsyncSession,
        redis: Redis,
        channel_id: UUID,
        msg_type: str,
        data: dict,
    ) -> dict:
        """
        Envía un mensaje a través del engine de WhatsApp.
        Crea un registro pendiente en la BD y publica el comando.
        """
        message_id = uuid4()
        chat_id = data.get("to", data.get("chat_id", ""))
        recipient = data.get("to", "")

        # Determinar el tipo de mensaje
        try:
            message_type = MessageType(msg_type)
        except ValueError:
            message_type = MessageType.TEXT

        # Crear registro de mensaje pendiente en la BD
        message = Message(
            id=message_id,
            channel_id=channel_id,
            chat_id=chat_id,
            sender="me",
            recipient=recipient,
            type=message_type,
            content=data,
            status=MessageStatus.PENDING,
            is_from_me=True,
            is_forwarded=False,
            timestamp=datetime.now(timezone.utc),
        )
        db.add(message)
        await db.flush()

        # Publicar comando al engine
        await MessageService._publish_command(
            redis,
            str(channel_id),
            "send_message",
            {
                "message_id": str(message_id),
                "type": msg_type,
                **data,
            },
        )

        logger.info(f"Mensaje enviado (pendiente): {message_id} -> {recipient}")
        return {
            "message_id": str(message_id),
            "status": "pending",
        }

    # ── Consulta de mensajes ─────────────────────────────────────

    @staticmethod
    async def get_messages(
        db: AsyncSession,
        channel_id: UUID,
        chat_id: str = None,
        msg_type: str = None,
        page: int = 1,
        limit: int = 50,
    ) -> dict:
        """
        Obtiene mensajes paginados con filtros opcionales.
        Retorna diccionario con mensajes, total, página y límite.
        """
        # Consulta base
        base_query = select(Message).where(Message.channel_id == channel_id)
        count_query = select(func.count(Message.id)).where(
            Message.channel_id == channel_id
        )

        # Filtro por chat
        if chat_id:
            base_query = base_query.where(Message.chat_id == chat_id)
            count_query = count_query.where(Message.chat_id == chat_id)

        # Filtro por tipo de mensaje
        if msg_type:
            try:
                message_type = MessageType(msg_type)
                base_query = base_query.where(Message.type == message_type)
                count_query = count_query.where(Message.type == message_type)
            except ValueError:
                pass

        # Obtener total
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginación
        offset = (page - 1) * limit
        query = (
            base_query
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

    @staticmethod
    async def get_message(
        db: AsyncSession, channel_id: UUID, message_id: UUID
    ) -> Message | None:
        """Obtiene un mensaje específico por su ID."""
        query = select(Message).where(
            Message.id == message_id,
            Message.channel_id == channel_id,
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    # ── Operaciones sobre mensajes ───────────────────────────────

    @staticmethod
    async def delete_message(
        db: AsyncSession,
        redis: Redis,
        channel_id: UUID,
        message_id: UUID,
    ) -> bool:
        """Elimina un mensaje: envía comando al engine y marca como eliminado."""
        message = await MessageService.get_message(db, channel_id, message_id)
        if not message:
            return False

        # Publicar comando de eliminación al engine
        await MessageService._publish_command(
            redis,
            str(channel_id),
            "delete_message",
            {
                "message_id": str(message_id),
                "message_id_wa": message.message_id_wa,
                "chat_id": message.chat_id,
            },
        )

        # Marcar como eliminado en BD
        message.status = MessageStatus.FAILED
        message.content = {"_deleted": True, "_original_type": message.type.value}
        await db.flush()

        logger.info(f"Mensaje eliminado: {message_id}")
        return True

    @staticmethod
    async def forward_message(
        redis: Redis,
        channel_id: UUID,
        message_id: UUID,
        to: str,
    ) -> dict:
        """Reenvía un mensaje a otro chat."""
        request_id = await MessageService._publish_command(
            redis,
            str(channel_id),
            "forward_message",
            {
                "message_id": str(message_id),
                "to": to,
            },
        )
        return {
            "success": True,
            "message_id": str(message_id),
            "forwarded_to": to,
            "request_id": request_id,
        }

    @staticmethod
    async def mark_as_read(
        redis: Redis, channel_id: UUID, message_id: UUID
    ) -> bool:
        """Marca un mensaje como leído en WhatsApp."""
        await MessageService._publish_command(
            redis,
            str(channel_id),
            "mark_as_read",
            {"message_id": str(message_id)},
        )
        return True

    @staticmethod
    async def react(
        redis: Redis, channel_id: UUID, message_id: UUID, emoji: str
    ) -> bool:
        """Agrega una reacción (emoji) a un mensaje."""
        await MessageService._publish_command(
            redis,
            str(channel_id),
            "react",
            {"message_id": str(message_id), "emoji": emoji},
        )
        return True

    @staticmethod
    async def remove_reaction(
        redis: Redis, channel_id: UUID, message_id: UUID
    ) -> bool:
        """Elimina la reacción de un mensaje."""
        await MessageService._publish_command(
            redis,
            str(channel_id),
            "remove_reaction",
            {"message_id": str(message_id)},
        )
        return True

    @staticmethod
    async def star_message(
        db: AsyncSession, channel_id: UUID, message_id: UUID
    ) -> bool:
        """Marca un mensaje como destacado en la BD."""
        message = await MessageService.get_message(db, channel_id, message_id)
        if not message:
            return False

        content = message.content or {}
        content["_starred"] = True
        message.content = content
        await db.flush()
        return True

    @staticmethod
    async def pin_message(
        redis: Redis, channel_id: UUID, message_id: UUID
    ) -> bool:
        """Fija un mensaje en el chat."""
        await MessageService._publish_command(
            redis,
            str(channel_id),
            "pin_message",
            {"message_id": str(message_id)},
        )
        return True

    @staticmethod
    async def unpin_message(
        redis: Redis, channel_id: UUID, message_id: UUID
    ) -> bool:
        """Desfija un mensaje del chat."""
        await MessageService._publish_command(
            redis,
            str(channel_id),
            "unpin_message",
            {"message_id": str(message_id)},
        )
        return True

    # ── Procesamiento de mensajes entrantes ──────────────────────

    @staticmethod
    async def save_incoming(db: AsyncSession, data: dict) -> Message:
        """
        Guarda un mensaje entrante recibido del engine.
        Llamado por el manejador de eventos cuando llega un mensaje nuevo.
        """
        # Determinar tipo de mensaje
        try:
            msg_type = MessageType(data.get("type", "text"))
        except ValueError:
            msg_type = MessageType.TEXT

        message = Message(
            id=uuid4(),
            channel_id=data["channel_id"],
            chat_id=data.get("chat_id", data.get("from", "")),
            message_id_wa=data.get("message_id_wa"),
            sender=data.get("from", data.get("sender", "")),
            recipient=data.get("to", data.get("recipient", "me")),
            type=msg_type,
            content=data.get("content", {}),
            status=MessageStatus.DELIVERED,
            is_from_me=data.get("is_from_me", False),
            is_forwarded=data.get("is_forwarded", False),
            quoted_message_id=data.get("quoted_message_id"),
            media_url=data.get("media_url"),
            media_mime_type=data.get("media_mime_type"),
            timestamp=datetime.fromisoformat(data["timestamp"])
            if data.get("timestamp")
            else datetime.now(timezone.utc),
        )
        db.add(message)
        await db.flush()

        logger.info(
            f"Mensaje entrante guardado: {message.id} de {message.sender}"
        )
        return message

    @staticmethod
    async def update_status(
        db: AsyncSession,
        wa_message_id: str,
        status: str,
        timestamp: datetime = None,
    ) -> bool:
        """
        Actualiza el estado de entrega de un mensaje identificado por su ID de WhatsApp.
        """
        query = select(Message).where(Message.message_id_wa == wa_message_id)
        result = await db.execute(query)
        message = result.scalar_one_or_none()

        if not message:
            logger.warning(
                f"Mensaje WA no encontrado para actualización de estado: {wa_message_id}"
            )
            return False

        try:
            new_status = MessageStatus(status)
        except ValueError:
            logger.warning(f"Estado de mensaje no válido: {status}")
            return False

        message.status = new_status
        ts = timestamp or datetime.now(timezone.utc)

        # Actualizar timestamps específicos según el estado
        if new_status == MessageStatus.SENT:
            message.sent_at = ts
        elif new_status == MessageStatus.DELIVERED:
            message.delivered_at = ts
        elif new_status == MessageStatus.READ:
            message.read_at = ts

        await db.flush()
        logger.debug(f"Estado de mensaje {wa_message_id} actualizado a: {status}")
        return True
