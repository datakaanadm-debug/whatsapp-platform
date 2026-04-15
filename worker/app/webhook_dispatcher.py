# worker/app/webhook_dispatcher.py — Worker de entrega de webhooks
# Consume tareas de la cola Redis 'webhook:queue' y entrega eventos HTTP con reintentos

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

import httpx
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger("platform.worker.webhook")

# Configuracion de reintentos con backoff exponencial
MAX_ATTEMPTS = 5
BASE_DELAY_SECONDS = 2  # 2, 4, 8, 16, 32 segundos
REQUEST_TIMEOUT = 30  # Timeout HTTP en segundos


class WebhookDispatcher:
    """
    Worker que procesa la cola de entregas de webhooks.

    Flujo:
        1. Lee tareas de la lista Redis 'webhook:queue' (BRPOP bloqueante)
        2. Construye el request HTTP con firma HMAC si hay secreto
        3. Envia POST al URL del webhook
        4. Si falla, reencola con backoff exponencial hasta MAX_ATTEMPTS
        5. Registra cada intento en la tabla webhook_logs de la DB
    """

    def __init__(
        self,
        redis: aioredis.Redis,
        session_factory: async_sessionmaker[AsyncSession],
    ):
        self.redis = redis
        self.session_factory = session_factory
        self._running = False

    async def start(self) -> None:
        """Inicia el loop de procesamiento de webhooks."""
        self._running = True
        logger.info("Webhook dispatcher iniciado — escuchando 'webhook:queue'")

        while self._running:
            try:
                # BRPOP: espera bloqueante hasta que haya una tarea (timeout 5s)
                result = await self.redis.brpop("webhook:queue", timeout=5)
                if result is None:
                    continue  # Timeout — volver a intentar

                _, raw_task = result
                if isinstance(raw_task, bytes):
                    raw_task = raw_task.decode("utf-8")

                task = json.loads(raw_task)
                await self._process_task(task)

            except asyncio.CancelledError:
                logger.info("Webhook dispatcher cancelado")
                break
            except json.JSONDecodeError as e:
                logger.error("Tarea con JSON invalido: %s", e)
            except Exception as e:
                logger.error("Error inesperado en webhook dispatcher: %s", e, exc_info=True)
                await asyncio.sleep(1)  # Pausa breve ante errores inesperados

    async def stop(self) -> None:
        """Detiene el dispatcher de forma limpia."""
        self._running = False
        logger.info("Webhook dispatcher detenido")

    async def _process_task(self, task: dict) -> None:
        """
        Procesa una tarea individual de entrega de webhook.

        Args:
            task: Diccionario con webhook_id, url, secret, event_type, payload, attempt
        """
        webhook_id = task.get("webhook_id", "")
        url = task.get("url", "")
        secret = task.get("secret", "")
        event_type = task.get("event_type", "")
        payload = task.get("payload", {})
        attempt = task.get("attempt", 1)
        channel_id = task.get("channel_id", "")

        if not url:
            logger.warning("Tarea de webhook sin URL — descartada: %s", webhook_id)
            return

        logger.info(
            "Entregando webhook %s (intento %d/%d) -> %s [%s]",
            webhook_id, attempt, MAX_ATTEMPTS, url, event_type,
        )

        # Construir headers
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "WhatsApp-Platform/1.0",
            "X-Webhook-Event": event_type,
            "X-Webhook-Delivery": webhook_id,
            "X-Webhook-Attempt": str(attempt),
        }

        # Agregar firma HMAC si hay secreto configurado
        if secret:
            from api.app.utils.security import sign_webhook_payload
            signature = sign_webhook_payload(payload, secret)
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        # Intentar la entrega HTTP
        status_code = 0
        response_body = ""
        error_message = ""
        success = False

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                )
                status_code = response.status_code
                response_body = response.text[:2000]  # Limitar tamano del log

                # Considerar exitoso cualquier 2xx
                success = 200 <= status_code < 300

                if success:
                    logger.info(
                        "Webhook entregado exitosamente: %s -> %s (HTTP %d)",
                        webhook_id, url, status_code,
                    )
                else:
                    error_message = f"HTTP {status_code}: {response_body[:200]}"
                    logger.warning(
                        "Webhook rechazado: %s -> %s (HTTP %d)",
                        webhook_id, url, status_code,
                    )

        except httpx.TimeoutException:
            error_message = f"Timeout despues de {REQUEST_TIMEOUT}s"
            logger.warning("Timeout en webhook %s -> %s", webhook_id, url)

        except httpx.ConnectError as e:
            error_message = f"Error de conexion: {str(e)[:200]}"
            logger.warning("Error de conexion en webhook %s -> %s: %s", webhook_id, url, e)

        except Exception as e:
            error_message = f"Error inesperado: {str(e)[:200]}"
            logger.error("Error inesperado en webhook %s: %s", webhook_id, e, exc_info=True)

        # Registrar el intento en la base de datos
        await self._log_attempt(
            webhook_id=webhook_id,
            channel_id=channel_id,
            event_type=event_type,
            url=url,
            attempt=attempt,
            status_code=status_code,
            response_body=response_body,
            error_message=error_message,
            success=success,
        )

        # Si fallo y quedan intentos, reencolar con backoff exponencial
        if not success and attempt < MAX_ATTEMPTS:
            delay = BASE_DELAY_SECONDS ** attempt  # 2, 4, 8, 16, 32
            task["attempt"] = attempt + 1

            logger.info(
                "Reintentando webhook %s en %d segundos (intento %d/%d)",
                webhook_id, delay, attempt + 1, MAX_ATTEMPTS,
            )

            # Usar Redis ZADD con score = timestamp futuro para delay
            retry_at = datetime.now(timezone.utc).timestamp() + delay
            await self.redis.zadd(
                "webhook:retry",
                {json.dumps(task): retry_at},
            )

        elif not success:
            logger.error(
                "Webhook %s agotado despues de %d intentos — movido a dead letter",
                webhook_id, MAX_ATTEMPTS,
            )
            await self.redis.lpush(
                "webhook:dead_letter",
                json.dumps({
                    **task,
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                    "last_error": error_message,
                }),
            )

    async def _log_attempt(
        self,
        webhook_id: str,
        channel_id: str,
        event_type: str,
        url: str,
        attempt: int,
        status_code: int,
        response_body: str,
        error_message: str,
        success: bool,
    ) -> None:
        """Registra el intento de entrega en la tabla webhook_logs."""
        async with self.session_factory() as session:
            try:
                from api.app.models.webhook_log import WebhookLog

                log = WebhookLog(
                    webhook_id=UUID(webhook_id) if webhook_id else None,
                    channel_id=UUID(channel_id) if channel_id else None,
                    event_type=event_type,
                    url=url,
                    attempt=attempt,
                    status_code=status_code,
                    response_body=response_body[:4000],
                    error_message=error_message[:1000],
                    success=success,
                    delivered_at=datetime.now(timezone.utc),
                )
                session.add(log)
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error("Error registrando log de webhook: %s", e, exc_info=True)

    async def process_retries(self) -> None:
        """
        Procesa tareas de reintento cuyo delay ya expiro.
        Lee del sorted set 'webhook:retry' las tareas con score <= ahora.
        """
        while self._running:
            try:
                now = datetime.now(timezone.utc).timestamp()

                # Obtener tareas cuyo delay ya expiro
                tasks = await self.redis.zrangebyscore(
                    "webhook:retry", "-inf", now, start=0, num=10
                )

                for raw_task in tasks:
                    if isinstance(raw_task, bytes):
                        raw_task = raw_task.decode("utf-8")

                    # Remover del sorted set
                    removed = await self.redis.zrem("webhook:retry", raw_task)
                    if removed:
                        # Re-encolar en la cola principal
                        await self.redis.lpush("webhook:queue", raw_task)
                        logger.debug("Tarea de reintento re-encolada")

                await asyncio.sleep(1)  # Revisar cada segundo

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error procesando reintentos: %s", e, exc_info=True)
                await asyncio.sleep(5)
