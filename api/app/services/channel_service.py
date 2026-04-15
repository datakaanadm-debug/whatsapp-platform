# api/app/services/channel_service.py — Servicio de gestión de canales/sesiones
# Operaciones CRUD de canales, gestión de sesiones WhatsApp y API keys

import asyncio
import hashlib
import json
import logging
import secrets
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.models.api_key import ApiKey
from api.app.models.channel import Channel, ChannelStatus

logger = logging.getLogger("agentkit")


class ChannelService:
    """Servicio para gestionar canales de WhatsApp y sus sesiones."""

    # ── Utilidades internas ──────────────────────────────────────

    @staticmethod
    def _generate_api_key() -> tuple[str, str, str]:
        """
        Genera una API key segura.
        Retorna: (key_completa, prefijo, hash_sha256)
        """
        raw = secrets.token_hex(24)
        api_key = f"ak_{raw}"
        prefix = api_key[:8]
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        return api_key, prefix, key_hash

    @staticmethod
    async def _publish_command(
        redis: Redis, channel_id: str, command: str, data: dict = None
    ) -> str:
        """Publica un comando al engine de WhatsApp via Redis."""
        request_id = str(uuid4())
        payload = json.dumps({
            "command": command,
            "channel_id": str(channel_id),
            "data": data or {},
            "request_id": request_id,
        })
        await redis.lpush("wa:cmd:queue", payload)
        logger.debug(f"Comando '{command}' publicado para canal {channel_id}")
        return request_id

    @staticmethod
    async def _publish_and_wait(
        redis: Redis,
        channel_id: str,
        command: str,
        data: dict = None,
        timeout: int = 30,
    ) -> dict:
        """Publica un comando y espera la respuesta del engine."""
        request_id = str(uuid4())
        response_key = f"wa:res:{request_id}"
        payload = json.dumps({
            "command": command,
            "channel_id": str(channel_id),
            "data": data or {},
            "request_id": request_id,
        })
        await redis.lpush("wa:cmd:queue", payload)
        # Esperar respuesta con polling
        for _ in range(timeout * 10):
            result = await redis.get(response_key)
            if result:
                await redis.delete(response_key)
                return json.loads(result)
            await asyncio.sleep(0.1)
        raise TimeoutError(
            f"El engine no respondió al comando '{command}' en {timeout}s"
        )

    # ── CRUD de canales ──────────────────────────────────────────

    @staticmethod
    async def create_channel(
        db: AsyncSession,
        name: str,
        webhook_url: str = None,
        webhook_events: list = None,
    ) -> dict:
        """
        Crea un canal nuevo con estado desconectado y genera su API key.
        Retorna el canal con la api_key en texto plano (única vez visible).
        """
        api_key_plain, prefix, key_hash = ChannelService._generate_api_key()

        # Crear el canal
        channel = Channel(
            id=uuid4(),
            name=name,
            status=ChannelStatus.DISCONNECTED,
            api_key=key_hash,
            webhook_url=webhook_url,
            webhook_events=webhook_events or [],
            settings={},
            is_active=True,
        )
        db.add(channel)
        await db.flush()

        # Crear registro de API key
        api_key_record = ApiKey(
            id=uuid4(),
            channel_id=channel.id,
            key_hash=key_hash,
            prefix=prefix,
            name=f"Key para {name}",
            scopes=["channel:full"],
            is_active=True,
        )
        db.add(api_key_record)
        await db.flush()

        logger.info(f"Canal creado: {channel.id} — {name}")

        return {
            "channel": channel,
            "api_key": api_key_plain,
        }

    @staticmethod
    async def get_channel(db: AsyncSession, channel_id: UUID) -> Channel | None:
        """Obtiene un canal por su ID."""
        query = select(Channel).where(
            Channel.id == channel_id,
            Channel.is_active == True,
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_channels(db: AsyncSession) -> list[Channel]:
        """Lista todos los canales activos."""
        query = (
            select(Channel)
            .where(Channel.is_active == True)
            .order_by(Channel.created_at.desc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def update_channel(
        db: AsyncSession, channel_id: UUID, **kwargs
    ) -> Channel | None:
        """Actualiza los campos de un canal."""
        channel = await ChannelService.get_channel(db, channel_id)
        if not channel:
            return None

        # Campos permitidos para actualización
        allowed_fields = {
            "name", "webhook_url", "webhook_events", "settings",
            "metadata_", "phone_number",
        }
        for key, value in kwargs.items():
            if key in allowed_fields and hasattr(channel, key):
                setattr(channel, key, value)

        await db.flush()
        logger.info(f"Canal actualizado: {channel_id}")
        return channel

    @staticmethod
    async def delete_channel(db: AsyncSession, channel_id: UUID) -> bool:
        """Soft delete: desactiva el canal en lugar de eliminarlo."""
        channel = await ChannelService.get_channel(db, channel_id)
        if not channel:
            return False

        channel.is_active = False
        await db.flush()
        logger.info(f"Canal desactivado (soft delete): {channel_id}")
        return True

    # ── Gestión de sesiones de WhatsApp ──────────────────────────

    @staticmethod
    async def start_session(
        db: AsyncSession, redis: Redis, channel_id: UUID
    ) -> dict:
        """Inicia una sesión de WhatsApp para el canal."""
        # Actualizar estado a conectando
        channel = await ChannelService.get_channel(db, channel_id)
        if not channel:
            return {"success": False, "error": "Canal no encontrado"}

        channel.status = ChannelStatus.CONNECTING
        await db.flush()

        await ChannelService._publish_command(
            redis, str(channel_id), "start_session"
        )

        logger.info(f"Sesión iniciada para canal: {channel_id}")
        return {"success": True, "status": "connecting", "channel_id": str(channel_id)}

    @staticmethod
    async def stop_session(
        db: AsyncSession, redis: Redis, channel_id: UUID
    ) -> dict:
        """Detiene la sesión de WhatsApp del canal."""
        channel = await ChannelService.get_channel(db, channel_id)
        if not channel:
            return {"success": False, "error": "Canal no encontrado"}

        channel.status = ChannelStatus.DISCONNECTED
        await db.flush()

        await ChannelService._publish_command(
            redis, str(channel_id), "stop_session"
        )

        logger.info(f"Sesión detenida para canal: {channel_id}")
        return {"success": True, "status": "disconnected", "channel_id": str(channel_id)}

    @staticmethod
    async def get_qr(redis: Redis, channel_id: UUID) -> str | None:
        """Obtiene el código QR actual del canal desde Redis."""
        qr_data = await redis.get(f"wa:qr:{channel_id}")
        return qr_data

    @staticmethod
    async def get_status(redis: Redis, channel_id: UUID) -> dict:
        """Obtiene el estado de conexión del canal desde Redis."""
        status_data = await redis.get(f"wa:status:{channel_id}")
        if status_data:
            return json.loads(status_data)
        return {"status": "unknown", "channel_id": str(channel_id)}

    @staticmethod
    async def logout_session(
        db: AsyncSession, redis: Redis, channel_id: UUID
    ) -> dict:
        """Cierra sesión de WhatsApp y elimina datos de sesión."""
        channel = await ChannelService.get_channel(db, channel_id)
        if not channel:
            return {"success": False, "error": "Canal no encontrado"}

        # Enviar comando de logout al engine
        await ChannelService._publish_command(
            redis, str(channel_id), "logout"
        )
        # Enviar comando para eliminar datos de sesión
        await ChannelService._publish_command(
            redis, str(channel_id), "delete_session"
        )

        # Actualizar estado en DB
        channel.status = ChannelStatus.DISCONNECTED
        channel.phone_number = None
        await db.flush()

        # Limpiar datos en Redis
        await redis.delete(f"wa:qr:{channel_id}")
        await redis.delete(f"wa:status:{channel_id}")

        logger.info(f"Logout completo para canal: {channel_id}")
        return {"success": True, "status": "logged_out", "channel_id": str(channel_id)}

    # ── Configuración del canal ──────────────────────────────────

    @staticmethod
    async def get_settings(db: AsyncSession, channel_id: UUID) -> dict:
        """Obtiene la configuración del canal."""
        channel = await ChannelService.get_channel(db, channel_id)
        if not channel:
            return {}
        return channel.settings or {}

    @staticmethod
    async def update_settings(
        db: AsyncSession, channel_id: UUID, settings: dict
    ) -> dict:
        """Actualiza la configuración del canal (merge con existente)."""
        channel = await ChannelService.get_channel(db, channel_id)
        if not channel:
            return {}

        current = channel.settings or {}
        current.update(settings)
        channel.settings = current
        await db.flush()

        logger.info(f"Configuración actualizada para canal: {channel_id}")
        return channel.settings

    @staticmethod
    async def reset_settings(db: AsyncSession, channel_id: UUID) -> dict:
        """Reinicia la configuración del canal a valores por defecto."""
        channel = await ChannelService.get_channel(db, channel_id)
        if not channel:
            return {}

        channel.settings = {}
        await db.flush()

        logger.info(f"Configuración reiniciada para canal: {channel_id}")
        return channel.settings
