# api/app/routers/business.py — Perfil de negocio, productos, pedidos, catálogos y colecciones de WhatsApp Business

import logging
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from api.app.schemas.common import ApiResponse, ErrorResponse, api_response
from api.app.middleware.auth import verify_api_key
from api.app.database import get_redis
from api.app.services.business_service import BusinessService

logger = logging.getLogger("platform.business")

router = APIRouter(
    prefix="/api/business",
    tags=["Business"],
    responses={
        401: {"model": ErrorResponse, "description": "API Key inválida"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)


# ── Helpers ──────────────────────────────────────────────────────


async def _get_channel_id(auth: dict = Depends(verify_api_key)) -> str:
    """Extrae el channel_id asociado a la API Key autenticada."""
    return auth["channel_id"]


# ── Perfil de negocio ────────────────────────────────────────────


@router.get(
    "",
    summary="Obtener perfil de negocio",
    description="Retorna el perfil de WhatsApp Business del canal autenticado.",
)
async def get_business_profile(
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Obtiene el perfil de negocio de WhatsApp Business."""
    try:
        profile = await BusinessService.get_profile(redis, channel_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Perfil de negocio no encontrado.",
            )
        return api_response(profile)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener perfil de negocio del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener el perfil de negocio.",
        )


@router.post(
    "",
    summary="Editar perfil de negocio",
    description="Actualiza el perfil de WhatsApp Business (dirección, descripción, categoría, email, sitio web, etc.).",
)
async def edit_business_profile(
    payload: dict = Body(..., description="Campos del perfil de negocio a actualizar"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Edita el perfil de negocio con los datos proporcionados."""
    try:
        result = await BusinessService.edit_profile(redis, channel_id, payload)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pudo actualizar el perfil de negocio.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al editar perfil de negocio del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al editar el perfil de negocio.",
        )


# ── Productos ────────────────────────────────────────────────────


@router.get(
    "/products",
    summary="Listar todos los productos",
    description="Retorna todos los productos del catálogo de WhatsApp Business del canal.",
)
async def list_products(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=200, description="Elementos por página"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Lista todos los productos del catálogo con paginación."""
    try:
        result = await BusinessService.get_products(redis, channel_id)
        return api_response(result)
    except Exception as e:
        logger.error("Error al listar productos del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al listar productos.",
        )


@router.post(
    "/products",
    status_code=status.HTTP_201_CREATED,
    summary="Crear producto",
    description="Agrega un nuevo producto al catálogo de WhatsApp Business.",
)
async def create_product(
    payload: dict = Body(..., description="Datos del producto (name, description, price, currency, images, url)"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Crea un nuevo producto en el catálogo."""
    try:
        result = await BusinessService.create_product(redis, channel_id, payload)
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al crear producto en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear el producto.",
        )


@router.get(
    "/{contact_id}/products",
    summary="Obtener productos por contacto",
    description="Retorna los productos del catálogo de un contacto de WhatsApp Business específico.",
)
async def get_products_by_contact(
    contact_id: str,
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=200, description="Elementos por página"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Obtiene los productos del catálogo de un contacto específico."""
    try:
        result = await BusinessService.get_products_by_contact(redis, channel_id, contact_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contacto '{contact_id}' no encontrado o sin catálogo.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener productos del contacto %s: %s", contact_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener productos del contacto.",
        )


@router.get(
    "/products/{product_id}",
    summary="Obtener producto",
    description="Retorna los detalles de un producto específico del catálogo.",
)
async def get_product(
    product_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Obtiene un producto por su ID."""
    try:
        product = await BusinessService.get_product(redis, channel_id, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto '{product_id}' no encontrado.",
            )
        return api_response(product)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener producto %s: %s", product_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener el producto.",
        )


@router.post(
    "/products/{product_id}",
    summary="Enviar producto",
    description="Envía un producto del catálogo a un chat o contacto de WhatsApp.",
)
async def send_product(
    product_id: str,
    to: str = Body(..., embed=True, description="Número de teléfono o chat_id destino"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Envía un producto específico a un contacto o chat."""
    try:
        result = await BusinessService.send_product(redis, channel_id, product_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto '{product_id}' no encontrado.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al enviar producto %s: %s", product_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al enviar el producto.",
        )


@router.patch(
    "/products/{product_id}",
    summary="Actualizar producto",
    description="Actualiza los datos de un producto existente en el catálogo.",
)
async def update_product(
    product_id: str,
    payload: dict = Body(..., description="Campos del producto a actualizar"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Actualiza los campos proporcionados de un producto."""
    try:
        result = await BusinessService.update_product(redis, channel_id, product_id, payload)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto '{product_id}' no encontrado.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al actualizar producto %s: %s", product_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al actualizar el producto.",
        )


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar producto",
    description="Elimina un producto del catálogo de WhatsApp Business.",
)
async def delete_product(
    product_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Elimina un producto del catálogo permanentemente."""
    try:
        deleted = await BusinessService.delete_product(redis, channel_id, product_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto '{product_id}' no encontrado.",
            )
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al eliminar producto %s: %s", product_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al eliminar el producto.",
        )


# ── Pedidos ──────────────────────────────────────────────────────


@router.get(
    "/orders/{order_id}",
    summary="Obtener artículos de un pedido",
    description="Retorna los artículos (productos y cantidades) de un pedido específico.",
)
async def get_order_items(
    order_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Obtiene los artículos de un pedido por su ID."""
    try:
        order = await BusinessService.get_order(redis, channel_id, order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Pedido '{order_id}' no encontrado.",
            )
        return api_response(order)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener pedido %s: %s", order_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener los artículos del pedido.",
        )


# ── Catálogos ────────────────────────────────────────────────────


@router.post(
    "/catalogs/{contact_id}",
    summary="Enviar catálogo",
    description="Envía el catálogo completo de productos a un contacto de WhatsApp.",
)
async def send_catalog(
    contact_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Envía el catálogo de productos al contacto indicado."""
    try:
        result = await BusinessService.send_catalog(redis, channel_id, contact_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pudo enviar el catálogo. Verifica que tengas productos registrados.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al enviar catálogo al contacto %s: %s", contact_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al enviar el catálogo.",
        )


# ── Colecciones ──────────────────────────────────────────────────


@router.post(
    "/collections",
    status_code=status.HTTP_201_CREATED,
    summary="Crear colección",
    description="Crea una nueva colección de productos en el catálogo de WhatsApp Business.",
)
async def create_collection(
    payload: dict = Body(..., description="Datos de la colección (name, product_ids)"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Crea una nueva colección con los productos indicados."""
    try:
        result = await BusinessService.create_collection(redis, channel_id, payload)
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al crear colección en canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear la colección.",
        )


@router.get(
    "/collections",
    summary="Listar colecciones",
    description="Retorna todas las colecciones del catálogo de WhatsApp Business.",
)
async def list_collections(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=200, description="Elementos por página"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Lista todas las colecciones con paginación."""
    try:
        result = await BusinessService.get_collections(redis, channel_id)
        return api_response(result)
    except Exception as e:
        logger.error("Error al listar colecciones del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al listar colecciones.",
        )


@router.get(
    "/collections/products",
    summary="Obtener productos de todas las colecciones",
    description="Retorna todos los productos organizados por colección.",
)
async def get_all_collections_products(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=200, description="Elementos por página"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Obtiene los productos de todas las colecciones."""
    try:
        result = await BusinessService.get_collections_products(redis, channel_id)
        return api_response(result)
    except Exception as e:
        logger.error("Error al obtener productos de colecciones del canal %s: %s", channel_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener productos de colecciones.",
        )


@router.get(
    "/collections/{collection_id}",
    summary="Obtener colección",
    description="Retorna los detalles de una colección específica.",
)
async def get_collection(
    collection_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Obtiene una colección por su ID."""
    try:
        collection = await BusinessService.get_collection(redis, channel_id, collection_id)
        if not collection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Colección '{collection_id}' no encontrada.",
            )
        return api_response(collection)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener colección %s: %s", collection_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener la colección.",
        )


@router.patch(
    "/collections/{collection_id}",
    summary="Editar colección",
    description="Actualiza el nombre u otros campos de una colección existente.",
)
async def edit_collection(
    collection_id: str,
    payload: dict = Body(..., description="Campos de la colección a actualizar"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Edita los campos proporcionados de una colección."""
    try:
        result = await BusinessService.edit_collection(redis, channel_id, collection_id, payload)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Colección '{collection_id}' no encontrada.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error al editar colección %s: %s", collection_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al editar la colección.",
        )


@router.delete(
    "/collections/{collection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar colección",
    description="Elimina una colección del catálogo. Los productos no se eliminan.",
)
async def delete_collection(
    collection_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Elimina una colección sin afectar los productos que contiene."""
    try:
        deleted = await BusinessService.delete_collection(redis, channel_id, collection_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Colección '{collection_id}' no encontrada.",
            )
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al eliminar colección %s: %s", collection_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al eliminar la colección.",
        )


@router.get(
    "/collections/{collection_id}/products",
    summary="Obtener productos de una colección",
    description="Retorna los productos pertenecientes a una colección específica.",
)
async def get_collection_products(
    collection_id: str,
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=200, description="Elementos por página"),
    redis: aioredis.Redis = Depends(get_redis),
    channel_id: str = Depends(_get_channel_id),
):
    """Lista los productos de una colección con paginación."""
    try:
        result = await BusinessService.get_collection_products(redis, channel_id, collection_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Colección '{collection_id}' no encontrada.",
            )
        return api_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error al obtener productos de colección %s: %s", collection_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener productos de la colección.",
        )
