# worker/app/message_queue.py — Worker de cola de mensajes salientes
# Rate-limita y gestiona el envio de mensajes via el engine de WhatsApp

import asyncio
import json
import logging
from datetime import datetime, timezone
from collections import defaultdict

import redis.asyncio as aioredis

logger = logging.getLogger("platform.worker.messages")

# Configuracion de rate limiting
MAX_MESSAGES_PER_MINUTE = 30  # Por canal
MAX_RETRIES = 3
RATE_WINDOW_SECONDS = 60


class MessageQueue:
    """
    Worker que procesa la cola de mensajes salientes con rate limiting.

    Flujo:
        1. Lee tareas de 'message:queue' (cola regular) y 'message:queue:bulk' (cola bulk)
        2. Aplica rate limiting: maximo 30 mensajes por minuto por canal
        3. Los mensajes regulares tienen prioridad sobre los bulk
        4. Publica comandos al engine via Redis para enviar cada mensaje
        5. Mensajes fallidos van a 'message:dead_letter' despues de 3 reintentos
    """

    def __init__(self, redis: aioredis.Redis):
        self.redis = redis
        self._running = False
        # Contadores de rate limit por canal: {channel_id: [(timestamp, count), ...]}
        self._rate_counters: dict[str, list[float]] = defaultdict(list)

    async def start(self) -> None:
        """Inicia el loop de procesamiento de mensajes."""
        self._running = True
        logger.info("Message queue worker iniciado")

        while self._running:
            try:
                # Prioridad 1: mensajes regulares
                processed = await self._process_queue("message:queue")
                if processed:
                    continue

                # Prioridad 2: mensajes bulk (solo si no hay regulares)
                processed = await self._process_queue("message:queue:bulk")
                if processed:
                    continue

                # No habia tareas — esperar brevemente
                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                logger.info("Message queue worker cancelado")
                break
            except Exception as e:
                logger.error("Error en message queue: %s", e, exc_info=True)
                await asyncio.sleep(1)

    async def stop(self) -> None:
        """Detiene el worker de forma limpia."""
        self._running = False
        logger.info("Message queue worker detenido")

    async def _process_queue(self, queue_name: str) -> bool:
        """
        Intenta procesar un mensaje de la cola indicada.

        Returns:
            True si proceso un mensaje, False si la cola estaba vacia
        """
        # BRPOP con timeout corto para no bloquear mucho
        result = await self.redis.brpop(queue_name, timeout=1)
        if result is None:
            return False

        _, raw_task = result
        if isinstance(raw_task, bytes):
            raw_task = raw_task.decode("utf-8")

        try:
            task = json.loads(raw_task)
        except json.JSONDecodeError:
            logger.error("Mensaje con JSON invalido descartado")
            return True

        channel_id = task.get("channel_id", "")
        if not channel_id:
            logger.warning("Mensaje sin channel_id descartado")
            return True

        # Verificar rate limit
        if not self._check_rate_limit(channel_id):
            # Re-encolar al frente con un pequeno delay
            logger.debug("Rate limit alcanzado para canal %s — re-encolando", channel_id)
            await self.redis.lpush(queue_name, raw_task)
            await asyncio.sleep(0.5)  # Esperar un poco antes de reintentar
            return True

        # Procesar el mensaje
        await self._send_message(task, queue_name)
        return True

    def _check_rate_limit(self, channel_id: str) -> bool:
        """
        Verifica si el canal tiene disponibilidad para enviar un mensaje.
        Implementa una ventana deslizante de 60 segundos.

        Returns:
            True si puede enviar, False si excede el limite
        """
        now = datetime.now(timezone.utc).timestamp()
        window_start = now - RATE_WINDOW_SECONDS

        # Limpiar timestamps viejos
        self._rate_counters[channel_id] = [
            ts for ts in self._rate_counters[channel_id]
            if ts > window_start
        ]

        # Verificar si hay espacio
        if len(self._rate_counters[channel_id]) >= MAX_MESSAGES_PER_MINUTE:
            return False

        # Registrar este envio
        self._rate_counters[channel_id].append(now)
        return True

    async def _send_message(self, task: dict, source_queue: str) -> None:
        """
        Envia un mensaje al engine de WhatsApp via Redis.

        Args:
            task: Datos del mensaje (channel_id, to, type, content, etc.)
            source_queue: Cola de origen para re-encolar si falla
        """
        channel_id = task.get("channel_id", "")
        to = task.get("to", "")
        msg_type = task.get("type", "text")
        content = task.get("content", {})
        attempt = task.get("attempt", 1)
        request_id = task.get("request_id", "")

        if not to:
            logger.warning("Mensaje sin destinatario descartado: %s", request_id)
            return

        # Construir comando para el engine
        command_payload = json.dumps({
            "command": "send_message",
            "channel_id": channel_id,
            "request_id": request_id,
            "data": {
                "to": to,
                "type": msg_type,
                "content": content,
            },
        })

        try:
            # Publicar comando al engine
            receivers = await self.redis.publish(
                f"wa:cmd:{channel_id}",
                command_payload,
            )

            if receivers > 0:
                logger.info(
                    "Mensaje encolado al engine: %s -> %s (canal %s)",
                    msg_type, to, channel_id,
                )

                # Registrar metrica de envio
                await self.redis.incr(f"stats:messages:sent:{channel_id}")
                await self.redis.expire(f"stats:messages:sent:{channel_id}", 86400)
            else:
                # No hay engine escuchando — reintentar
                logger.warning(
                    "Engine no disponible para canal %s — reintentando",
                    channel_id,
                )
                await self._handle_failure(task, source_queue, "Engine no disponible")

        except Exception as e:
            logger.error("Error enviando mensaje: %s", e, exc_info=True)
            await self._handle_failure(task, source_queue, str(e))

    async def _handle_failure(
        self, task: dict, source_queue: str, error: str
    ) -> None:
        """
        Maneja un fallo en el envio de un mensaje.
        Reintenta hasta MAX_RETRIES, luego mueve a dead letter queue.
        """
        attempt = task.get("attempt", 1)

        if attempt < MAX_RETRIES:
            task["attempt"] = attempt + 1
            task["last_error"] = error

            # Delay exponencial: 1s, 2s, 4s
            delay = 2 ** (attempt - 1)
            logger.info(
                "Reintentando mensaje en %ds (intento %d/%d)",
                delay, attempt + 1, MAX_RETRIES,
            )
            await asyncio.sleep(delay)
            await self.redis.lpush(source_queue, json.dumps(task))
        else:
            logger.error(
                "Mensaje agotado despues de %d intentos — movido a dead letter: %s",
                MAX_RETRIES, task.get("request_id", ""),
            )
            await self.redis.lpush(
                "message:dead_letter",
                json.dumps({
                    **task,
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                    "last_error": error,
                }),
            )

    async def get_queue_stats(self) -> dict:
        """Retorna estadisticas de las colas de mensajes."""
        regular_len = await self.redis.llen("message:queue")
        bulk_len = await self.redis.llen("message:queue:bulk")
        dead_len = await self.redis.llen("message:dead_letter")

        return {
            "regular_queue": regular_len,
            "bulk_queue": bulk_len,
            "dead_letter_queue": dead_len,
        }
