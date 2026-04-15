# api/app/events/event_bus.py — Bus de eventos basado en Redis Lists
# Usa LPUSH/BRPOP en vez de Pub/Sub para compatibilidad con Upstash

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Callable, Awaitable

import redis.asyncio as aioredis

logger = logging.getLogger("platform.events.bus")

# Cola de eventos del engine → API
EVENTS_QUEUE = "wa:events:queue"


class EventBus:
    """
    Bus de eventos que usa Redis Lists para comunicación entre componentes.
    Compatible con Upstash y cualquier Redis.

    El engine publica eventos con LPUSH a wa:events:queue.
    El EventHandler los consume con BRPOP.
    """

    def __init__(self, redis: aioredis.Redis):
        self.redis = redis
        self._callbacks: list[Callable[..., Awaitable]] = []
        self._listener_task: asyncio.Task | None = None
        self._running = False

    async def publish(self, channel: str, event_type: str, data: dict) -> None:
        """
        Publica un evento en la cola de Redis.
        También lo guarda en la lista del canal específico para WebSocket.
        """
        payload = json.dumps({
            "event": event_type,
            "channel": channel,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Push a la cola principal (para el event handler)
        await self.redis.lpush(EVENTS_QUEUE, payload)

        # También push a la cola del canal (para WebSocket)
        await self.redis.lpush(f"wa:ws:{channel}", payload)
        await self.redis.ltrim(f"wa:ws:{channel}", 0, 99)  # Mantener últimos 100

        logger.debug("Evento '%s' publicado en cola", event_type)

    async def subscribe(self, pattern: str, callback: Callable[..., Awaitable]) -> None:
        """Registra un callback para procesar eventos."""
        self._callbacks.append(callback)
        logger.info("Callback registrado para eventos")

    async def start_listener(self) -> None:
        """Inicia el loop de escucha de eventos usando BRPOP."""
        if self._running:
            logger.warning("El listener ya está corriendo")
            return

        self._running = True
        self._listener_task = asyncio.create_task(self._listen_loop())
        logger.info("Event bus listener iniciado (modo lista)")

    async def _listen_loop(self) -> None:
        """Loop que consume eventos de la cola con BRPOP."""
        try:
            while self._running:
                try:
                    raw_data = await self.redis.rpop(EVENTS_QUEUE)

                    if raw_data is None:
                        await asyncio.sleep(0.5)
                        continue

                    try:
                        parsed = json.loads(raw_data)
                    except json.JSONDecodeError:
                        logger.warning("Evento no JSON: %s", str(raw_data)[:200])
                        continue

                    event_type = parsed.get("event", "unknown")
                    event_data = parsed.get("data", {})
                    channel = parsed.get("channel", "")

                    for callback in self._callbacks:
                        try:
                            await callback(channel, event_type, event_data)
                        except Exception as e:
                            logger.error(
                                "Error en callback para evento '%s': %s",
                                event_type, e, exc_info=True,
                            )

                except aioredis.ConnectionError:
                    logger.warning("Conexión Redis perdida, reintentando en 2s...")
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error("Error en listen loop: %s", e, exc_info=True)
                    await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("Event bus listener cancelado")
        finally:
            self._running = False

    async def stop(self) -> None:
        """Detiene el listener."""
        self._running = False
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        logger.info("Event bus listener detenido")

    @property
    def is_running(self) -> bool:
        return self._running
