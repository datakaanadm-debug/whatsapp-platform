# worker/app/main.py — Punto de entrada del proceso worker
# Arranca todos los workers concurrentemente y gestiona shutdown limpio

import asyncio
import logging
import os
import signal
import sys

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger("platform.worker")

# Configuracion desde variables de entorno
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/whatsapp_platform",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def setup_logging() -> None:
    """Configura el sistema de logging para el worker."""
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(name)-35s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def main() -> None:
    """
    Funcion principal del worker.
    Inicializa conexiones, arranca todos los workers y espera a shutdown.
    """
    setup_logging()

    logger.info("=" * 60)
    logger.info("  WhatsApp Platform Worker — Iniciando...")
    logger.info("=" * 60)

    # Crear conexiones
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=10,
        max_overflow=5,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    redis = aioredis.from_url(
        REDIS_URL,
        decode_responses=True,
        max_connections=20,
    )
    # Redis separado para datos binarios (media processor)
    redis_binary = aioredis.from_url(
        REDIS_URL,
        decode_responses=False,
        max_connections=10,
    )

    logger.info("Conexiones a PostgreSQL y Redis establecidas")

    # Inicializar workers
    from worker.app.webhook_dispatcher import WebhookDispatcher
    from worker.app.message_queue import MessageQueue
    from worker.app.media_processor import MediaProcessor

    webhook_dispatcher = WebhookDispatcher(
        redis=redis,
        session_factory=session_factory,
    )
    message_queue = MessageQueue(redis=redis)
    media_processor = MediaProcessor(redis=redis_binary)

    # Evento para shutdown limpio
    shutdown_event = asyncio.Event()

    def handle_signal(sig: int, frame) -> None:
        """Handler para senales SIGTERM/SIGINT."""
        signal_name = signal.Signals(sig).name
        logger.info("Senal %s recibida — iniciando shutdown...", signal_name)
        shutdown_event.set()

    # Registrar signal handlers
    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, lambda: shutdown_event.set())
        loop.add_signal_handler(signal.SIGINT, lambda: shutdown_event.set())
    else:
        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

    # Crear tareas para cada worker
    tasks = [
        asyncio.create_task(
            webhook_dispatcher.start(),
            name="webhook_dispatcher",
        ),
        asyncio.create_task(
            webhook_dispatcher.process_retries(),
            name="webhook_retries",
        ),
        asyncio.create_task(
            message_queue.start(),
            name="message_queue",
        ),
        asyncio.create_task(
            media_processor.start(),
            name="media_processor",
        ),
    ]

    logger.info("Workers activos:")
    logger.info("  - Webhook Dispatcher (cola: webhook:queue)")
    logger.info("  - Webhook Retries (sorted set: webhook:retry)")
    logger.info("  - Message Queue (colas: message:queue, message:queue:bulk)")
    logger.info("  - Media Processor (cola: media:process:queue)")
    logger.info("=" * 60)

    try:
        # Esperar hasta que se reciba senal de shutdown o un worker falle
        shutdown_task = asyncio.create_task(shutdown_event.wait())
        done, pending = await asyncio.wait(
            [*tasks, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Verificar si algun worker fallo
        for task in done:
            if task != shutdown_task and task.exception():
                logger.error(
                    "Worker '%s' fallo: %s",
                    task.get_name(),
                    task.exception(),
                )

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — iniciando shutdown...")

    finally:
        # Shutdown limpio
        logger.info("Deteniendo workers...")

        await webhook_dispatcher.stop()
        await message_queue.stop()
        await media_processor.stop()

        # Cancelar tareas pendientes
        for task in tasks:
            if not task.done():
                task.cancel()

        # Esperar a que las tareas terminen
        await asyncio.gather(*tasks, return_exceptions=True)

        # Cerrar conexiones
        await engine.dispose()
        await redis.aclose()
        await redis_binary.aclose()

        logger.info("Worker finalizado limpiamente")


if __name__ == "__main__":
    asyncio.run(main())
