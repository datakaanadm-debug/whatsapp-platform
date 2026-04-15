# api/app/services/contact_service.py — Servicio de gestión de contactos
# Operaciones CRUD, verificación de números, bloqueo y sincronización

import asyncio
import json
import logging
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.models.contact import Contact

logger = logging.getLogger("agentkit")


class ContactService:
    """Servicio para gestionar contactos de WhatsApp."""

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

    # ── Consulta de contactos ────────────────────────────────────

    @staticmethod
    async def get_contacts(
        db: AsyncSession,
        channel_id: UUID,
        page: int = 1,
        limit: int = 50,
    ) -> dict:
        """Obtiene contactos paginados de un canal."""
        count_query = select(func.count(Contact.id)).where(
            Contact.channel_id == channel_id
        )
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * limit
        query = (
            select(Contact)
            .where(Contact.channel_id == channel_id)
            .order_by(Contact.name.asc().nullslast())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query)
        contacts = list(result.scalars().all())

        return {
            "contacts": contacts,
            "total": total,
            "page": page,
            "limit": limit,
        }

    @staticmethod
    async def get_contact(
        db: AsyncSession, channel_id: UUID, contact_id: UUID
    ) -> Contact | None:
        """Obtiene un contacto por su ID interno."""
        query = select(Contact).where(
            Contact.id == contact_id,
            Contact.channel_id == channel_id,
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    # ── Verificación de teléfonos ────────────────────────────────

    @staticmethod
    async def check_phones(
        redis: Redis, channel_id: UUID, phones: list[str]
    ) -> list[dict]:
        """
        Verifica si una lista de teléfonos tienen WhatsApp.
        Envía comando al engine y espera respuesta con los resultados.
        """
        response = await ContactService._publish_and_wait(
            redis,
            str(channel_id),
            "check_phones",
            {"phones": phones},
            timeout=30,
        )
        return response.get("results", [])

    # ── CRUD de contactos ────────────────────────────────────────

    @staticmethod
    async def add_contact(
        db: AsyncSession, channel_id: UUID, data: dict
    ) -> Contact:
        """Agrega un contacto nuevo a la BD."""
        contact = Contact(
            id=uuid4(),
            channel_id=channel_id,
            contact_id_wa=data.get("contact_id_wa", data.get("phone", "")),
            phone_number=data.get("phone", data.get("phone_number")),
            name=data.get("name"),
            push_name=data.get("push_name"),
            business_name=data.get("business_name"),
            profile_pic_url=data.get("profile_pic_url"),
            is_business=data.get("is_business", False),
            is_blocked=data.get("is_blocked", False),
            metadata_=data.get("metadata", {}),
        )
        db.add(contact)
        await db.flush()

        logger.info(f"Contacto agregado: {contact.id} — {contact.name}")
        return contact

    @staticmethod
    async def edit_contact(
        db: AsyncSession, channel_id: UUID, contact_id: UUID, data: dict
    ) -> Contact | None:
        """Actualiza los datos de un contacto existente."""
        contact = await ContactService.get_contact(db, channel_id, contact_id)
        if not contact:
            return None

        allowed_fields = {
            "name", "push_name", "business_name", "profile_pic_url",
            "phone_number", "is_business", "is_blocked", "metadata_",
        }
        for key, value in data.items():
            if key in allowed_fields and hasattr(contact, key):
                setattr(contact, key, value)

        await db.flush()
        logger.info(f"Contacto actualizado: {contact_id}")
        return contact

    @staticmethod
    async def delete_contact(
        db: AsyncSession, channel_id: UUID, contact_id: UUID
    ) -> bool:
        """Elimina un contacto de la BD."""
        contact = await ContactService.get_contact(db, channel_id, contact_id)
        if not contact:
            return False

        await db.delete(contact)
        await db.flush()

        logger.info(f"Contacto eliminado: {contact_id}")
        return True

    # ── Operaciones en WhatsApp via engine ───────────────────────

    @staticmethod
    async def get_profile(
        redis: Redis, channel_id: UUID, contact_id: UUID
    ) -> dict:
        """Obtiene el perfil completo de un contacto desde WhatsApp."""
        response = await ContactService._publish_and_wait(
            redis,
            str(channel_id),
            "get_contact_profile",
            {"contact_id": str(contact_id)},
        )
        return response

    @staticmethod
    async def check_exists(
        redis: Redis, channel_id: UUID, contact_id: UUID
    ) -> bool:
        """Verifica si un contacto existe en WhatsApp."""
        response = await ContactService._publish_and_wait(
            redis,
            str(channel_id),
            "check_contact_exists",
            {"contact_id": str(contact_id)},
        )
        return response.get("exists", False)

    @staticmethod
    async def block_contact(
        redis: Redis, channel_id: UUID, contact_id: UUID
    ) -> bool:
        """Bloquea un contacto en WhatsApp."""
        await ContactService._publish_command(
            redis,
            str(channel_id),
            "block_contact",
            {"contact_id": str(contact_id)},
        )
        return True

    @staticmethod
    async def unblock_contact(
        redis: Redis, channel_id: UUID, contact_id: UUID
    ) -> bool:
        """Desbloquea un contacto en WhatsApp."""
        await ContactService._publish_command(
            redis,
            str(channel_id),
            "unblock_contact",
            {"contact_id": str(contact_id)},
        )
        return True

    # ── Sincronización desde el engine ───────────────────────────

    @staticmethod
    async def sync_contacts(
        db: AsyncSession, channel_id: UUID, contacts_data: list[dict]
    ) -> int:
        """
        Sincroniza contactos recibidos del engine con la BD.
        Crea nuevos o actualiza existentes. Retorna cantidad sincronizada.
        """
        synced_count = 0

        for contact_data in contacts_data:
            contact_id_wa = contact_data.get(
                "contact_id_wa", contact_data.get("id", "")
            )
            if not contact_id_wa:
                continue

            # Buscar contacto existente
            query = select(Contact).where(
                Contact.channel_id == channel_id,
                Contact.contact_id_wa == contact_id_wa,
            )
            result = await db.execute(query)
            existing = result.scalar_one_or_none()

            if existing:
                # Actualizar datos
                existing.name = contact_data.get("name", existing.name)
                existing.push_name = contact_data.get(
                    "push_name", existing.push_name
                )
                existing.business_name = contact_data.get(
                    "business_name", existing.business_name
                )
                existing.profile_pic_url = contact_data.get(
                    "profile_pic_url", existing.profile_pic_url
                )
                existing.phone_number = contact_data.get(
                    "phone_number", existing.phone_number
                )
                existing.is_business = contact_data.get(
                    "is_business", existing.is_business
                )
                existing.is_blocked = contact_data.get(
                    "is_blocked", existing.is_blocked
                )
                if contact_data.get("metadata"):
                    existing.metadata_ = contact_data["metadata"]
            else:
                # Crear contacto nuevo
                new_contact = Contact(
                    id=uuid4(),
                    channel_id=channel_id,
                    contact_id_wa=contact_id_wa,
                    phone_number=contact_data.get("phone_number"),
                    name=contact_data.get("name"),
                    push_name=contact_data.get("push_name"),
                    business_name=contact_data.get("business_name"),
                    profile_pic_url=contact_data.get("profile_pic_url"),
                    is_business=contact_data.get("is_business", False),
                    is_blocked=contact_data.get("is_blocked", False),
                    metadata_=contact_data.get("metadata", {}),
                )
                db.add(new_contact)

            synced_count += 1

        await db.flush()
        logger.info(
            f"Contactos sincronizados para canal {channel_id}: {synced_count}"
        )
        return synced_count
