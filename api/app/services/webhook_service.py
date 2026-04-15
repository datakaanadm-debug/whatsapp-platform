# api/app/services/webhook_service.py — Servicio de gestión de webhooks
# Creación, despacho, entrega con firma HMAC, reintentos y logging

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.models.webhook import Webhook
from api.app.models.webhook_log import WebhookLog

logger = logging.getLogger("agentkit")

# Configuración de reintentos
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # Segundos base para backoff exponencial
DELIVERY_TIMEOUT = 10  # Timeout HTTP en segundos


class WebhookService:
    """Servicio para gestionar webhooks y despacho de eventos."""

    # ── CRUD de webhooks ─────────────────────────────────────────

    @staticmethod
    async def create_webhook(
        db: AsyncSession,
        channel_id: UUID,
        url: str,
        events: list[str],
        secret: str = None,
    ) -> Webhook:
        """
        Crea una suscripción de webhook para un canal.
        Si no se proporciona secret, genera uno aleatorio de 32 hex chars.
        """
        if not secret:
            secret = secrets.token_hex(16)

        webhook = Webhook(
            id=uuid4(),
            channel_id=channel_id,
            url=url,
            events=events,
            secret=secret,
            is_active=True,
            failure_count=0,
        )
        db.add(webhook)
        await db.flush()

        logger.info(f"Webhook creado: {webhook.id} -> {url}")
        return webhook

    @staticmethod
    async def get_webhooks(
        db: AsyncSession, channel_id: UUID
    ) -> list[Webhook]:
        """Obtiene todos los webhooks de un canal."""
        query = (
            select(Webhook)
            .where(Webhook.channel_id == channel_id)
            .order_by(Webhook.created_at.desc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_webhook(
        db: AsyncSession, channel_id: UUID, webhook_id: UUID
    ) -> Webhook | None:
        """Obtiene un webhook específico."""
        query = select(Webhook).where(
            Webhook.id == webhook_id,
            Webhook.channel_id == channel_id,
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_webhook(
        db: AsyncSession, channel_id: UUID, webhook_id: UUID, **kwargs
    ) -> Webhook | None:
        """Actualiza los campos de un webhook."""
        webhook = await WebhookService.get_webhook(db, channel_id, webhook_id)
        if not webhook:
            return None

        allowed_fields = {"url", "events", "secret", "is_active"}
        for key, value in kwargs.items():
            if key in allowed_fields and hasattr(webhook, key):
                setattr(webhook, key, value)

        # Reiniciar contador de fallos si se reactiva
        if kwargs.get("is_active", None) is True:
            webhook.failure_count = 0

        await db.flush()
        logger.info(f"Webhook actualizado: {webhook_id}")
        return webhook

    @staticmethod
    async def delete_webhook(
        db: AsyncSession, channel_id: UUID, webhook_id: UUID
    ) -> bool:
        """Elimina un webhook y todos sus logs."""
        webhook = await WebhookService.get_webhook(db, channel_id, webhook_id)
        if not webhook:
            return False

        await db.delete(webhook)
        await db.flush()

        logger.info(f"Webhook eliminado: {webhook_id}")
        return True

    # ── Logs de entregas ─────────────────────────────────────────

    @staticmethod
    async def get_logs(
        db: AsyncSession,
        webhook_id: UUID,
        page: int = 1,
        limit: int = 50,
    ) -> dict:
        """Obtiene logs paginados de entregas de un webhook."""
        count_query = select(func.count(WebhookLog.id)).where(
            WebhookLog.webhook_id == webhook_id
        )
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * limit
        query = (
            select(WebhookLog)
            .where(WebhookLog.webhook_id == webhook_id)
            .order_by(WebhookLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query)
        logs = list(result.scalars().all())

        return {
            "logs": logs,
            "total": total,
            "page": page,
            "limit": limit,
        }

    # ── Despacho de eventos ──────────────────────────────────────

    @staticmethod
    async def dispatch_event(
        db: AsyncSession,
        redis: Redis,
        channel_id: UUID,
        event_type: str,
        payload: dict,
    ) -> int:
        """
        Encuentra todos los webhooks activos que coincidan con el evento
        y encola las tareas de entrega en Redis.
        Retorna el número de webhooks que coinciden.
        """
        # Buscar webhooks activos del canal que escuchen este evento
        query = select(Webhook).where(
            Webhook.channel_id == channel_id,
            Webhook.is_active == True,
        )
        result = await db.execute(query)
        webhooks = list(result.scalars().all())

        matched_count = 0
        for webhook in webhooks:
            # Verificar si el webhook escucha este tipo de evento
            # Si events contiene "*" o el tipo específico
            if "*" in webhook.events or event_type in webhook.events:
                # Encolar tarea de entrega en Redis
                task = json.dumps({
                    "webhook_id": str(webhook.id),
                    "event_type": event_type,
                    "payload": payload,
                    "attempt": 1,
                })
                await redis.lpush("wa:webhook_delivery_queue", task)
                matched_count += 1

        if matched_count > 0:
            logger.info(
                f"Evento '{event_type}' despachado a {matched_count} webhooks "
                f"para canal {channel_id}"
            )

        return matched_count

    # ── Entrega de webhook ───────────────────────────────────────

    @staticmethod
    def _sign_payload(secret: str, payload_bytes: bytes) -> str:
        """Genera firma HMAC-SHA256 del payload."""
        return hmac.new(
            secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    async def deliver_webhook(
        db: AsyncSession,
        webhook_id: UUID,
        event_type: str,
        payload: dict,
    ) -> bool:
        """
        Entrega un evento a un webhook específico.
        Firma el payload con HMAC-SHA256 y registra el intento en WebhookLog.
        Reintenta con backoff exponencial si falla.
        """
        # Obtener webhook
        query = select(Webhook).where(Webhook.id == webhook_id)
        result = await db.execute(query)
        webhook = result.scalar_one_or_none()

        if not webhook:
            logger.error(f"Webhook no encontrado para entrega: {webhook_id}")
            return False

        # Preparar payload
        delivery_payload = {
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "webhook_id": str(webhook_id),
            "data": payload,
        }
        payload_bytes = json.dumps(delivery_payload).encode("utf-8")

        # Generar firma HMAC-SHA256
        signature = ""
        if webhook.secret:
            signature = WebhookService._sign_payload(webhook.secret, payload_bytes)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AgentKit-Webhook/1.0",
            "X-Webhook-Event": event_type,
            "X-Webhook-Signature": f"sha256={signature}",
            "X-Webhook-ID": str(webhook_id),
        }

        # Intentar entrega con reintentos
        for attempt in range(1, MAX_RETRIES + 1):
            status_code = None
            response_body = None
            delivered_at = None

            try:
                async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT) as client:
                    response = await client.post(
                        webhook.url,
                        content=payload_bytes,
                        headers=headers,
                    )
                    status_code = response.status_code
                    response_body = response.text[:2000]  # Limitar tamaño del log

                    if 200 <= status_code < 300:
                        delivered_at = datetime.now(timezone.utc)

                        # Registrar entrega exitosa
                        log = WebhookLog(
                            id=uuid4(),
                            webhook_id=webhook_id,
                            event_type=event_type,
                            payload=delivery_payload,
                            status_code=status_code,
                            response_body=response_body,
                            attempt=attempt,
                            delivered_at=delivered_at,
                        )
                        db.add(log)

                        # Actualizar webhook
                        webhook.last_triggered_at = delivered_at
                        webhook.failure_count = 0
                        await db.flush()

                        logger.info(
                            f"Webhook entregado: {webhook_id} -> {webhook.url} "
                            f"(intento {attempt}, status {status_code})"
                        )
                        return True

            except httpx.TimeoutException:
                response_body = "Timeout: la solicitud excedió el tiempo límite"
                logger.warning(
                    f"Timeout en entrega de webhook {webhook_id} "
                    f"(intento {attempt}/{MAX_RETRIES})"
                )
            except httpx.RequestError as e:
                response_body = f"Error de conexión: {str(e)}"
                logger.warning(
                    f"Error de conexión en webhook {webhook_id}: {e} "
                    f"(intento {attempt}/{MAX_RETRIES})"
                )

            # Registrar intento fallido
            log = WebhookLog(
                id=uuid4(),
                webhook_id=webhook_id,
                event_type=event_type,
                payload=delivery_payload,
                status_code=status_code,
                response_body=response_body,
                attempt=attempt,
                delivered_at=None,
            )
            db.add(log)
            await db.flush()

            # Esperar con backoff exponencial antes del siguiente intento
            if attempt < MAX_RETRIES:
                wait_time = RETRY_BACKOFF_BASE ** attempt
                await asyncio.sleep(wait_time)

        # Todos los intentos fallaron
        webhook.failure_count += 1

        # Desactivar webhook si tiene demasiados fallos consecutivos
        if webhook.failure_count >= 10:
            webhook.is_active = False
            logger.error(
                f"Webhook desactivado por fallos consecutivos: {webhook_id}"
            )

        await db.flush()
        return False

    # ── Test de webhook ──────────────────────────────────────────

    @staticmethod
    async def test_webhook(db: AsyncSession, webhook_id: UUID) -> dict:
        """
        Envía un evento de prueba al webhook para verificar conectividad.
        """
        # Obtener webhook
        query = select(Webhook).where(Webhook.id == webhook_id)
        result = await db.execute(query)
        webhook = result.scalar_one_or_none()

        if not webhook:
            return {"success": False, "error": "Webhook no encontrado"}

        test_payload = {
            "type": "test",
            "message": "Este es un evento de prueba de AgentKit",
            "webhook_id": str(webhook_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Intentar entrega
        payload_bytes = json.dumps({
            "event": "webhook.test",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "webhook_id": str(webhook_id),
            "data": test_payload,
        }).encode("utf-8")

        signature = ""
        if webhook.secret:
            signature = WebhookService._sign_payload(webhook.secret, payload_bytes)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AgentKit-Webhook/1.0",
            "X-Webhook-Event": "webhook.test",
            "X-Webhook-Signature": f"sha256={signature}",
            "X-Webhook-ID": str(webhook_id),
        }

        try:
            async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT) as client:
                response = await client.post(
                    webhook.url,
                    content=payload_bytes,
                    headers=headers,
                )

                # Registrar el test en logs
                log = WebhookLog(
                    id=uuid4(),
                    webhook_id=webhook_id,
                    event_type="webhook.test",
                    payload=test_payload,
                    status_code=response.status_code,
                    response_body=response.text[:2000],
                    attempt=1,
                    delivered_at=datetime.now(timezone.utc)
                    if 200 <= response.status_code < 300
                    else None,
                )
                db.add(log)
                await db.flush()

                return {
                    "success": 200 <= response.status_code < 300,
                    "status_code": response.status_code,
                    "response": response.text[:500],
                }

        except httpx.TimeoutException:
            return {"success": False, "error": "Timeout al conectar con la URL"}
        except httpx.RequestError as e:
            return {"success": False, "error": f"Error de conexión: {str(e)}"}
