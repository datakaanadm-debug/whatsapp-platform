# api/app/events/event_handler.py — Procesador de eventos del engine de WhatsApp
# Escucha eventos del engine Baileys via Redis y los enruta a los handlers apropiados

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.app.events.event_bus import EventBus
from api.app.models.channel import Channel, ChannelStatus
from api.app.models.message import Message, MessageStatus, MessageType
from api.app.models.chat import Chat
from api.app.models.contact import Contact
from api.app.models.group import Group

logger = logging.getLogger("platform.events.handler")


class EventHandler:
    """
    Procesa eventos que llegan desde el engine de Baileys via Redis Pub/Sub.

    Eventos soportados:
        - message.received: Mensaje entrante -> guardar en DB, despachar webhooks
        - message.sent: Mensaje enviado -> actualizar estado en DB
        - message.status: Cambio de ACK (entregado/leido) -> actualizar estado
        - connection.update: Cambio de estado de conexion -> actualizar canal
        - qr.update: Nuevo codigo QR generado -> cachear en Redis
        - contacts.update: Sincronizacion de contactos -> guardar/actualizar en DB
        - chats.update: Sincronizacion de chats -> guardar/actualizar en DB
        - groups.update: Cambio en grupos -> sincronizar metadatos
        - presence.update: Cambio de presencia -> cachear en Redis
    """

    def __init__(
        self,
        event_bus: EventBus,
        session_factory: async_sessionmaker[AsyncSession],
        redis: aioredis.Redis,
    ):
        self.event_bus = event_bus
        self.session_factory = session_factory
        self.redis = redis

        # Mapa de tipos de evento a sus handlers
        self._handlers = {
            "message.received": self._handle_message_received,
            "message.sent": self._handle_message_sent,
            "message.status": self._handle_message_status,
            "connection.update": self._handle_connection_update,
            "qr.update": self._handle_qr_update,
            "contacts.update": self._handle_contacts_update,
            "chats.update": self._handle_chats_update,
            "groups.update": self._handle_groups_update,
            "presence.update": self._handle_presence_update,
        }

    async def setup(self) -> None:
        """Registra el handler principal en el event bus y arranca el listener."""
        await self.event_bus.subscribe("wa:evt:*", self._dispatch_event)
        await self.event_bus.start_listener()
        logger.info("EventHandler configurado y escuchando eventos wa:evt:*")

    async def _dispatch_event(
        self, channel: str, event_type: str, data: dict
    ) -> None:
        """
        Router principal: recibe cada evento y lo envia al handler apropiado.

        Args:
            channel: Canal de Redis (ej: "wa:evt:channel-uuid")
            event_type: Tipo de evento
            data: Payload del evento
        """
        # Extraer el channel_id del nombre del canal Redis
        # Formato: wa:evt:{channel_id}
        parts = channel.split(":")
        if len(parts) < 3:
            logger.warning("Canal Redis con formato inesperado: %s", channel)
            return

        channel_id = parts[2]

        logger.info("Evento recibido: '%s' para canal %s (data keys: %s)", event_type, channel_id, list(data.keys()) if isinstance(data, dict) else type(data))

        handler = self._handlers.get(event_type)
        if handler:
            logger.info("Procesando evento '%s' para canal %s", event_type, channel_id)
            try:
                await handler(channel_id, data)
            except Exception as e:
                logger.error(
                    "Error procesando evento '%s' para canal %s: %s",
                    event_type, channel_id, e,
                    exc_info=True,
                )
        else:
            logger.info("Evento no manejado: '%s' para canal %s", event_type, channel_id)

        # Siempre intentar despachar webhooks para cualquier evento
        await self._dispatch_webhooks(channel_id, event_type, data)

    # ── Handlers de mensajes ──────────────────────────────────────

    async def _handle_message_received(self, channel_id: str, data: dict) -> None:
        """
        Procesa un mensaje entrante recibido de WhatsApp.
        Guarda en base de datos y encola para AI pipeline si esta habilitado.
        """
        async with self.session_factory() as session:
            try:
                msg_data = data.get("message", data)

                message = Message(
                    channel_id=UUID(channel_id),
                    message_id_wa=msg_data.get("id", ""),
                    chat_id=msg_data.get("chat_id", msg_data.get("remoteJid", "")),
                    sender=msg_data.get("sender", msg_data.get("participant", "")),
                    recipient=msg_data.get("recipient", ""),
                    is_from_me=msg_data.get("from_me", False),
                    type=self._resolve_message_type(msg_data),
                    content={"text": msg_data.get("body", msg_data.get("text", "")), "raw": msg_data},
                    status=MessageStatus.DELIVERED,
                    timestamp=datetime.now(timezone.utc),
                )
                session.add(message)
                await session.commit()

                logger.info(
                    "Mensaje recibido guardado: %s en canal %s",
                    message.message_id_wa, channel_id,
                )

                # Verificar si AI pipeline esta habilitado para este canal
                ai_enabled = await self.redis.get(f"wa:ai_enabled:{channel_id}")
                if ai_enabled and ai_enabled.lower() in ("true", "1", "yes"):
                    await self.redis.lpush(
                        "ai:pipeline:queue",
                        json.dumps({
                            "channel_id": channel_id,
                            "message_id": str(message.id),
                            "chat_id": message.chat_id,
                            "text": message.content,
                            "sender": message.sender,
                        }),
                    )
                    logger.debug("Mensaje encolado para AI pipeline: %s", message.id)

            except Exception as e:
                await session.rollback()
                logger.error("Error guardando mensaje recibido: %s", e, exc_info=True)
                raise

    async def _handle_message_sent(self, channel_id: str, data: dict) -> None:
        """Actualiza el estado de un mensaje enviado exitosamente."""
        async with self.session_factory() as session:
            try:
                wa_msg_id = data.get("id", data.get("message_id", ""))
                if not wa_msg_id:
                    return

                stmt = (
                    update(Message)
                    .where(
                        Message.channel_id == UUID(channel_id),
                        Message.message_id_wa == wa_msg_id,
                    )
                    .values(
                        status=MessageStatus.SENT,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.execute(stmt)
                await session.commit()
                logger.debug("Mensaje marcado como enviado: %s", wa_msg_id)

            except Exception as e:
                await session.rollback()
                logger.error("Error actualizando mensaje enviado: %s", e, exc_info=True)

    async def _handle_message_status(self, channel_id: str, data: dict) -> None:
        """
        Actualiza el estado de entrega/lectura de un mensaje (ACK).
        Mapeo de ACK: 1=enviado, 2=entregado, 3=leido, 4=reproducido
        """
        async with self.session_factory() as session:
            try:
                wa_msg_id = data.get("id", data.get("message_id", ""))
                ack_status = data.get("ack", data.get("status", 0))

                if not wa_msg_id:
                    return

                status_map = {
                    0: MessageStatus.PENDING,
                    1: MessageStatus.SENT,
                    2: MessageStatus.DELIVERED,
                    3: MessageStatus.READ,
                    4: MessageStatus.READ,  # "played" para audio/video
                }
                new_status = status_map.get(ack_status, MessageStatus.SENT)

                stmt = (
                    update(Message)
                    .where(
                        Message.channel_id == UUID(channel_id),
                        Message.message_id_wa == wa_msg_id,
                    )
                    .values(
                        status=new_status,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.execute(stmt)
                await session.commit()
                logger.debug("ACK actualizado para %s: %s", wa_msg_id, new_status)

            except Exception as e:
                await session.rollback()
                logger.error("Error actualizando ACK: %s", e, exc_info=True)

    # ── Handlers de conexion ──────────────────────────────────────

    async def _handle_connection_update(self, channel_id: str, data: dict) -> None:
        """
        Actualiza el estado de conexion del canal en la base de datos y Redis.
        Estados: connecting, connected, disconnected, logged_out
        """
        connection_state = data.get("connection", data.get("status", ""))

        status_map = {
            "open": ChannelStatus.CONNECTED,
            "connected": ChannelStatus.CONNECTED,
            "connecting": ChannelStatus.CONNECTING,
            "close": ChannelStatus.DISCONNECTED,
            "disconnected": ChannelStatus.DISCONNECTED,
            "logged_out": ChannelStatus.BANNED,
        }
        new_status = status_map.get(connection_state)
        if not new_status:
            logger.debug("Estado de conexion no mapeado: '%s'", connection_state)
            return

        # Actualizar en DB
        async with self.session_factory() as session:
            try:
                stmt = (
                    update(Channel)
                    .where(Channel.id == UUID(channel_id))
                    .values(
                        status=new_status,
                        updated_at=datetime.now(timezone.utc),
                    )
                )

                # Si se conecto, guardar el numero de telefono si viene en los datos
                phone = data.get("phone_number", data.get("me", {}).get("id", ""))
                if phone and new_status == ChannelStatus.CONNECTED:
                    stmt = stmt.values(phone_number=phone.split(":")[0].split("@")[0])

                await session.execute(stmt)
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error("Error actualizando estado de conexion: %s", e, exc_info=True)

        # Cachear estado en Redis (para consultas rapidas)
        await self.redis.set(
            f"wa:status:{channel_id}",
            json.dumps({
                "status": new_status.value if hasattr(new_status, "value") else str(new_status),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }),
            ex=3600,  # TTL 1 hora
        )

        logger.info("Canal %s -> estado: %s", channel_id, new_status)

    async def _handle_qr_update(self, channel_id: str, data: dict) -> None:
        """Cachea el codigo QR generado por el engine en Redis con TTL de 60 segundos."""
        qr_string = data.get("qr", "")
        if not qr_string:
            return

        await self.redis.set(
            f"wa:qr:{channel_id}",
            qr_string,
            ex=60,  # QR expira en 60 segundos
        )
        logger.debug("QR actualizado para canal %s", channel_id)

    # ── Handlers de sincronizacion ────────────────────────────────

    async def _handle_contacts_update(self, channel_id: str, data: dict) -> None:
        """Sincroniza contactos recibidos del engine con la base de datos."""
        contacts = data.get("contacts", [])
        if not contacts:
            return

        async with self.session_factory() as session:
            try:
                for contact_data in contacts:
                    wa_id = contact_data.get("id", "")
                    if not wa_id:
                        continue

                    # Buscar contacto existente
                    query = select(Contact).where(
                        Contact.channel_id == UUID(channel_id),
                        Contact.contact_id_wa == wa_id,
                    )
                    result = await session.execute(query)
                    existing = result.scalar_one_or_none()

                    if existing:
                        # Actualizar campos
                        existing.name = contact_data.get("name", existing.name)
                        existing.push_name = contact_data.get("notify", existing.push_name)
                        existing.phone_number = wa_id.split("@")[0]
                        existing.is_business = contact_data.get("isBusiness", existing.is_business)
                    else:
                        # Crear nuevo contacto
                        contact = Contact(
                            channel_id=UUID(channel_id),
                            contact_id_wa=wa_id,
                            name=contact_data.get("name", ""),
                            push_name=contact_data.get("notify", ""),
                            phone_number=wa_id.split("@")[0],
                            is_business=contact_data.get("isBusiness", False),
                        )
                        session.add(contact)

                await session.commit()
                logger.info(
                    "Sincronizados %d contacto(s) para canal %s",
                    len(contacts), channel_id,
                )

            except Exception as e:
                await session.rollback()
                logger.error("Error sincronizando contactos: %s", e, exc_info=True)

    async def _handle_chats_update(self, channel_id: str, data: dict) -> None:
        """Sincroniza chats recibidos del engine con la base de datos."""
        chats = data.get("chats", [])
        if not chats:
            return

        async with self.session_factory() as session:
            try:
                for chat_data in chats:
                    wa_id = chat_data.get("id", "")
                    if not wa_id:
                        continue

                    query = select(Chat).where(
                        Chat.channel_id == UUID(channel_id),
                        Chat.chat_id_wa == wa_id,
                    )
                    result = await session.execute(query)
                    existing = result.scalar_one_or_none()

                    if existing:
                        existing.name = chat_data.get("name", existing.name)
                        existing.is_group = wa_id.endswith("@g.us")
                        existing.is_archived = chat_data.get("archived", existing.is_archived)
                        existing.is_pinned = chat_data.get("pinned", existing.is_pinned)
                        existing.is_muted = chat_data.get("muted", existing.is_muted)
                        existing.unread_count = chat_data.get("unreadCount", existing.unread_count)
                        if chat_data.get("lastMessage"):
                            existing.last_message_at = datetime.now(timezone.utc)
                    else:
                        chat = Chat(
                            channel_id=UUID(channel_id),
                            wa_chat_id=wa_id,
                            name=chat_data.get("name", ""),
                            is_group=wa_id.endswith("@g.us"),
                            is_archived=chat_data.get("archived", False),
                            is_pinned=chat_data.get("pinned", False),
                            is_muted=chat_data.get("muted", False),
                            unread_count=chat_data.get("unreadCount", 0),
                        )
                        session.add(chat)

                await session.commit()
                logger.info(
                    "Sincronizados %d chat(s) para canal %s",
                    len(chats), channel_id,
                )

            except Exception as e:
                await session.rollback()
                logger.error("Error sincronizando chats: %s", e, exc_info=True)

    async def _handle_groups_update(self, channel_id: str, data: dict) -> None:
        """Sincroniza metadatos de grupos con la base de datos."""
        groups = data.get("groups", [])
        if not groups:
            # Puede ser actualizacion de un solo grupo
            if data.get("id"):
                groups = [data]
            else:
                return

        async with self.session_factory() as session:
            try:
                for group_data in groups:
                    wa_id = group_data.get("id", "")
                    if not wa_id:
                        continue

                    query = select(Group).where(
                        Group.channel_id == UUID(channel_id),
                        Group.group_id_wa == wa_id,
                    )
                    result = await session.execute(query)
                    existing = result.scalar_one_or_none()

                    if existing:
                        existing.name = group_data.get("subject", existing.name)
                        existing.description = group_data.get("desc", existing.description)
                        existing.participants = group_data.get("participants", existing.participants)
                        existing.owner = group_data.get("owner", existing.owner)
                    else:
                        group = Group(
                            channel_id=UUID(channel_id),
                            group_id_wa=wa_id,
                            name=group_data.get("subject", ""),
                            description=group_data.get("desc", ""),
                            participants=group_data.get("participants", []),
                            owner=group_data.get("owner", ""),
                        )
                        session.add(group)

                await session.commit()
                logger.info(
                    "Sincronizado(s) %d grupo(s) para canal %s",
                    len(groups), channel_id,
                )

            except Exception as e:
                await session.rollback()
                logger.error("Error sincronizando grupos: %s", e, exc_info=True)

    async def _handle_presence_update(self, channel_id: str, data: dict) -> None:
        """
        Cachea actualizaciones de presencia en Redis.
        La presencia es efimera, no se guarda en base de datos.
        """
        contact_id = data.get("id", data.get("contact_id", ""))
        if not contact_id:
            return

        presence_data = {
            "contact_id": contact_id,
            "is_online": data.get("isOnline", data.get("available", False)),
            "last_seen": data.get("lastSeen", data.get("lastKnownPresence", "")),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        await self.redis.set(
            f"wa:presence:{channel_id}:{contact_id}",
            json.dumps(presence_data),
            ex=300,  # TTL 5 minutos
        )
        logger.debug("Presencia actualizada: %s -> online=%s", contact_id, presence_data["is_online"])

    # ── Despacho de webhooks ──────────────────────────────────────

    async def _dispatch_webhooks(
        self, channel_id: str, event_type: str, data: dict
    ) -> None:
        """
        Encola la entrega de webhooks para el evento dado.
        Busca los webhooks suscritos a este tipo de evento y los encola
        en la lista de Redis 'webhook:queue' para que el worker los entregue.
        """
        async with self.session_factory() as session:
            try:
                from api.app.models.webhook import Webhook

                query = select(Webhook).where(
                    Webhook.channel_id == UUID(channel_id),
                    Webhook.is_active == True,
                )
                result = await session.execute(query)
                webhooks = result.scalars().all()

                for webhook in webhooks:
                    # Verificar si el webhook esta suscrito a este tipo de evento
                    subscribed_events = webhook.events or []
                    if "*" not in subscribed_events and event_type not in subscribed_events:
                        continue

                    # Encolar tarea de entrega
                    task = json.dumps({
                        "webhook_id": str(webhook.id),
                        "channel_id": channel_id,
                        "url": webhook.url,
                        "secret": webhook.secret or "",
                        "event_type": event_type,
                        "payload": {
                            "event": event_type,
                            "channel_id": channel_id,
                            "data": data,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                        "attempt": 1,
                    })
                    await self.redis.lpush("webhook:queue", task)
                    logger.debug(
                        "Webhook encolado: %s -> %s (%s)",
                        webhook.id, webhook.url, event_type,
                    )

            except Exception as e:
                logger.error(
                    "Error despachando webhooks para canal %s: %s",
                    channel_id, e, exc_info=True,
                )

    # ── Utilidades ────────────────────────────────────────────────

    @staticmethod
    def _resolve_message_type(msg_data: dict) -> str:
        """Determina el tipo de mensaje a partir de los datos del engine."""
        if msg_data.get("hasMedia") or msg_data.get("mediaUrl"):
            media_type = msg_data.get("type", msg_data.get("mediaType", ""))
            type_map = {
                "image": MessageType.IMAGE,
                "video": MessageType.VIDEO,
                "audio": MessageType.AUDIO,
                "ptt": MessageType.AUDIO,
                "document": MessageType.DOCUMENT,
                "sticker": MessageType.STICKER,
            }
            return type_map.get(media_type, MessageType.DOCUMENT)

        if msg_data.get("location") or msg_data.get("type") == "location":
            return MessageType.LOCATION

        if msg_data.get("vcard") or msg_data.get("type") == "contact":
            return MessageType.CONTACT

        if msg_data.get("poll") or msg_data.get("type") == "poll":
            return MessageType.POLL

        return MessageType.TEXT
