# api/app/services/business_service.py — Servicio de perfil de negocio y catálogo
# Gestión de perfil comercial, productos, pedidos, catálogo y colecciones

import asyncio
import json
import logging
from uuid import UUID, uuid4

from redis.asyncio import Redis

logger = logging.getLogger("agentkit")


class BusinessService:
    """Servicio para gestionar el perfil de negocio y catálogo de WhatsApp Business."""

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

    # ── Perfil de negocio ────────────────────────────────────────

    @staticmethod
    async def get_profile(redis: Redis, channel_id: UUID) -> dict:
        """Obtiene el perfil de negocio de WhatsApp Business."""
        response = await BusinessService._publish_and_wait(
            redis,
            str(channel_id),
            "get_business_profile",
        )
        return response

    @staticmethod
    async def edit_profile(
        redis: Redis, channel_id: UUID, data: dict
    ) -> dict:
        """
        Edita el perfil de negocio.
        data puede contener: description, address, email, websites, vertical,
        about, profile_picture
        """
        response = await BusinessService._publish_and_wait(
            redis,
            str(channel_id),
            "edit_business_profile",
            data,
        )
        return response

    # ── Productos ────────────────────────────────────────────────

    @staticmethod
    async def get_products(redis: Redis, channel_id: UUID) -> list:
        """Obtiene todos los productos del catálogo."""
        response = await BusinessService._publish_and_wait(
            redis,
            str(channel_id),
            "get_products",
        )
        return response.get("products", [])

    @staticmethod
    async def create_product(
        redis: Redis, channel_id: UUID, data: dict
    ) -> dict:
        """
        Crea un producto nuevo en el catálogo.
        data debe contener: name, price, currency, description (opcional),
        images (opcional), url (opcional)
        """
        response = await BusinessService._publish_and_wait(
            redis,
            str(channel_id),
            "create_product",
            data,
        )
        return response

    @staticmethod
    async def get_products_by_contact(
        redis: Redis, channel_id: UUID, contact_id: str
    ) -> list:
        """Obtiene los productos del catálogo de un contacto específico."""
        response = await BusinessService._publish_and_wait(
            redis,
            str(channel_id),
            "get_products_by_contact",
            {"contact_id": contact_id},
        )
        return response.get("products", [])

    @staticmethod
    async def get_product(
        redis: Redis, channel_id: UUID, product_id: str
    ) -> dict:
        """Obtiene los detalles de un producto específico."""
        response = await BusinessService._publish_and_wait(
            redis,
            str(channel_id),
            "get_product",
            {"product_id": product_id},
        )
        return response

    @staticmethod
    async def send_product(
        redis: Redis, channel_id: UUID, product_id: str
    ) -> dict:
        """Envía un producto como mensaje a un chat."""
        response = await BusinessService._publish_and_wait(
            redis,
            str(channel_id),
            "send_product",
            {"product_id": product_id},
        )
        return response

    @staticmethod
    async def update_product(
        redis: Redis, channel_id: UUID, product_id: str, data: dict
    ) -> dict:
        """Actualiza un producto existente en el catálogo."""
        response = await BusinessService._publish_and_wait(
            redis,
            str(channel_id),
            "update_product",
            {"product_id": product_id, **data},
        )
        return response

    @staticmethod
    async def delete_product(
        redis: Redis, channel_id: UUID, product_id: str
    ) -> bool:
        """Elimina un producto del catálogo."""
        await BusinessService._publish_command(
            redis,
            str(channel_id),
            "delete_product",
            {"product_id": product_id},
        )
        return True

    # ── Pedidos ──────────────────────────────────────────────────

    @staticmethod
    async def get_order(
        redis: Redis, channel_id: UUID, order_id: str
    ) -> dict:
        """Obtiene los detalles de un pedido."""
        response = await BusinessService._publish_and_wait(
            redis,
            str(channel_id),
            "get_order",
            {"order_id": order_id},
        )
        return response

    # ── Catálogo ─────────────────────────────────────────────────

    @staticmethod
    async def send_catalog(
        redis: Redis, channel_id: UUID, contact_id: str
    ) -> dict:
        """Envía el catálogo completo a un contacto."""
        response = await BusinessService._publish_and_wait(
            redis,
            str(channel_id),
            "send_catalog",
            {"contact_id": contact_id},
        )
        return response

    # ── Colecciones ──────────────────────────────────────────────

    @staticmethod
    async def create_collection(
        redis: Redis, channel_id: UUID, data: dict
    ) -> dict:
        """
        Crea una colección de productos.
        data debe contener: name, product_ids (lista)
        """
        response = await BusinessService._publish_and_wait(
            redis,
            str(channel_id),
            "create_collection",
            data,
        )
        return response

    @staticmethod
    async def get_collections(redis: Redis, channel_id: UUID) -> list:
        """Obtiene todas las colecciones del catálogo."""
        response = await BusinessService._publish_and_wait(
            redis,
            str(channel_id),
            "get_collections",
        )
        return response.get("collections", [])

    @staticmethod
    async def get_collections_products(
        redis: Redis, channel_id: UUID
    ) -> list:
        """Obtiene todas las colecciones con sus productos incluidos."""
        response = await BusinessService._publish_and_wait(
            redis,
            str(channel_id),
            "get_collections_products",
        )
        return response.get("collections", [])

    @staticmethod
    async def get_collection(
        redis: Redis, channel_id: UUID, collection_id: str
    ) -> dict:
        """Obtiene los detalles de una colección específica."""
        response = await BusinessService._publish_and_wait(
            redis,
            str(channel_id),
            "get_collection",
            {"collection_id": collection_id},
        )
        return response

    @staticmethod
    async def edit_collection(
        redis: Redis, channel_id: UUID, collection_id: str, data: dict
    ) -> dict:
        """Edita una colección existente."""
        response = await BusinessService._publish_and_wait(
            redis,
            str(channel_id),
            "edit_collection",
            {"collection_id": collection_id, **data},
        )
        return response

    @staticmethod
    async def delete_collection(
        redis: Redis, channel_id: UUID, collection_id: str
    ) -> bool:
        """Elimina una colección del catálogo."""
        await BusinessService._publish_command(
            redis,
            str(channel_id),
            "delete_collection",
            {"collection_id": collection_id},
        )
        return True

    @staticmethod
    async def get_collection_products(
        redis: Redis, channel_id: UUID, collection_id: str
    ) -> list:
        """Obtiene los productos de una colección específica."""
        response = await BusinessService._publish_and_wait(
            redis,
            str(channel_id),
            "get_collection_products",
            {"collection_id": collection_id},
        )
        return response.get("products", [])
