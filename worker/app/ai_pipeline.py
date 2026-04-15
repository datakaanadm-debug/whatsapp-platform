# worker/app/ai_pipeline.py — Pipeline de IA para responder mensajes automáticamente
# Escucha la cola ai:pipeline:queue y genera respuestas con Claude

import asyncio
import json
import logging
import os
import yaml
from datetime import datetime, timezone

import redis.asyncio as aioredis
from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from api.app.models.message import Message

logger = logging.getLogger("platform.ai_pipeline")

HISTORY_LIMIT = 20  # Mensajes de historial a incluir


def _get_env(key: str, default: str = "") -> str:
    """Lee variable de entorno (dotenv ya debe estar cargado)."""
    return os.getenv(key, default)


class AIPipeline:
    """Procesa mensajes entrantes con Claude y envía respuestas."""

    def __init__(self):
        self.redis: aioredis.Redis | None = None
        self.session_factory: async_sessionmaker | None = None
        self.claude: AsyncAnthropic | None = None
        self.system_prompt: str = ""
        self.fallback_message: str = "Disculpa, no entendí tu mensaje."
        self.error_message: str = "Lo siento, estoy teniendo problemas técnicos."

    async def setup(self):
        """Inicializa conexiones y carga configuración."""
        redis_url = _get_env("REDIS_URL", "redis://localhost:6379/0")
        db_url = _get_env("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/whatsapp_platform")
        api_key = _get_env("ANTHROPIC_API_KEY")

        logger.info("Redis URL: %s...", redis_url[:40])

        # Redis
        self.redis = aioredis.from_url(redis_url, decode_responses=True)
        logger.info("Redis conectado")

        # PostgreSQL
        engine = create_async_engine(db_url, pool_size=5)
        self.session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        logger.info("PostgreSQL conectado")

        # Claude
        self.claude = AsyncAnthropic(api_key=api_key)
        logger.info("Cliente Anthropic inicializado")

        # Cargar prompts
        self._load_prompts()

    def _load_prompts(self):
        """Carga el system prompt desde config/prompts.yaml."""
        # Buscar en varias ubicaciones
        paths = [
            "config/prompts.yaml",
            "../config/prompts.yaml",
            "../../config/prompts.yaml",
        ]
        for path in paths:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                self.system_prompt = config.get("system_prompt", "")
                self.fallback_message = config.get("fallback_message", self.fallback_message)
                self.error_message = config.get("error_message", self.error_message)
                logger.info("System prompt cargado desde %s (%d chars)", path, len(self.system_prompt))
                return

        logger.warning("No se encontró prompts.yaml — usando prompt genérico")
        self.system_prompt = "Eres un asistente útil. Responde en español de forma concisa."

    async def get_history(self, db: AsyncSession, chat_id: str, channel_id: str) -> list[dict]:
        """Obtiene el historial de conversación para un chat."""
        query = (
            select(Message)
            .where(
                Message.chat_id == chat_id,
                Message.channel_id == channel_id,
            )
            .order_by(Message.timestamp.desc())
            .limit(HISTORY_LIMIT)
        )
        result = await db.execute(query)
        messages = list(result.scalars().all())
        messages.reverse()  # Orden cronológico

        history = []
        for msg in messages:
            role = "assistant" if msg.is_from_me else "user"
            text = ""
            if isinstance(msg.content, dict):
                text = msg.content.get("text", msg.content.get("body", ""))
            elif isinstance(msg.content, str):
                text = msg.content
            if text:
                history.append({"role": role, "content": text})

        return history

    async def generate_response(self, message_text: str, history: list[dict]) -> str:
        """Genera una respuesta con Claude."""
        if not message_text or len(message_text.strip()) < 2:
            return self.fallback_message

        # Construir mensajes — historial + mensaje actual
        messages = []
        for msg in history:
            messages.append(msg)

        # El mensaje actual ya debería estar al final del historial
        # Si no, lo agregamos
        if not messages or messages[-1].get("content") != message_text:
            messages.append({"role": "user", "content": message_text})

        # Asegurar que los mensajes alternan correctamente
        messages = self._fix_message_order(messages)

        try:
            response = await self.claude.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=self.system_prompt,
                messages=messages,
            )
            reply = response.content[0].text
            logger.info(
                "Respuesta generada (%d in / %d out tokens)",
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
            return reply

        except Exception as e:
            logger.error("Error Claude API: %s", e, exc_info=True)
            return self.error_message

    @staticmethod
    def _fix_message_order(messages: list[dict]) -> list[dict]:
        """Asegura que los mensajes alternen user/assistant correctamente."""
        if not messages:
            return [{"role": "user", "content": "Hola"}]

        fixed = []
        for msg in messages:
            if fixed and fixed[-1]["role"] == msg["role"]:
                # Mismo rol consecutivo — combinar
                fixed[-1]["content"] += "\n" + msg["content"]
            else:
                fixed.append(msg)

        # Debe empezar con user
        if fixed[0]["role"] != "user":
            fixed.insert(0, {"role": "user", "content": "..."})

        # Debe terminar con user
        if fixed[-1]["role"] != "user":
            fixed.append({"role": "user", "content": "..."})

        return fixed

    async def process_message(self, task_data: dict):
        """Procesa un mensaje de la cola de AI."""
        channel_id = task_data.get("channel_id", "")
        chat_id = task_data.get("chat_id", "")
        sender = task_data.get("sender", "")
        raw_text = task_data.get("text", "")

        # Extraer texto del contenido
        if isinstance(raw_text, dict):
            message_text = raw_text.get("text", raw_text.get("body", ""))
        else:
            message_text = str(raw_text)

        if not message_text or not channel_id:
            logger.warning("Mensaje sin texto o channel_id: %s", task_data)
            return

        logger.info("Procesando mensaje AI: '%s' de %s", message_text[:50], sender)

        try:
            # Obtener historial
            async with self.session_factory() as db:
                history = await self.get_history(db, chat_id, channel_id)

            # Generar respuesta
            reply = await self.generate_response(message_text, history)
            logger.info("Respuesta AI: '%s'", reply[:80])

            # Enviar respuesta via Redis -> Engine
            send_command = json.dumps({
                "command": "send_message",
                "channel_id": channel_id,
                "data": {
                    "type": "text",
                    "to": chat_id,  # chat_id ya tiene el JID correcto
                    "body": reply,
                },
                "request_id": f"ai-{datetime.now(timezone.utc).timestamp()}",
            })
            await self.redis.lpush("wa:cmd:queue", send_command)
            logger.info("Respuesta enviada a %s via engine", chat_id)

            # Guardar respuesta en DB
            async with self.session_factory() as db:
                from uuid import uuid4
                response_msg = Message(
                    id=uuid4(),
                    channel_id=channel_id,
                    chat_id=chat_id,
                    sender="me",
                    recipient=chat_id,
                    is_from_me=True,
                    type="text",
                    content={"text": reply},
                    status="sent",
                    is_forwarded=False,
                    timestamp=datetime.now(timezone.utc),
                )
                db.add(response_msg)
                await db.commit()

        except Exception as e:
            logger.error("Error en AI pipeline para %s: %s", chat_id, e, exc_info=True)

    async def run(self):
        """Loop principal — lee directamente de wa:events:queue (eventos del engine)."""
        logger.info("AI Pipeline iniciado — escuchando wa:events:queue directamente")

        while True:
            try:
                # Leer eventos del engine (RPOP — compatible con Upstash)
                raw_data = await self.redis.rpop("wa:events:queue")

                if raw_data is None:
                    await asyncio.sleep(0.5)  # Polling interval
                    continue
                event = json.loads(raw_data)
                event_type = event.get("event", "")
                data = event.get("data", {})
                channel = event.get("channel", "")

                # Log TODOS los eventos para debug
                logger.info("Evento: %s | fromMe=%s | text=%s",
                    event_type, data.get("fromMe"), str(data.get("text", ""))[:50])

                # Solo procesar mensajes recibidos que NO sean propios
                if event_type != "message.received":
                    continue

                if data.get("fromMe", False):
                    logger.info("Ignorando mensaje propio")
                    continue

                # Extraer channel_id del channel name (wa:evt:{channel_id})
                parts = channel.split(":")
                channel_id = parts[2] if len(parts) >= 3 else data.get("channelId", "")

                # Verificar si AI está habilitado
                ai_enabled = await self.redis.get(f"wa:ai_enabled:{channel_id}")
                if not ai_enabled or ai_enabled.lower() not in ("true", "1", "yes"):
                    logger.debug("AI no habilitado para canal %s", channel_id)
                    continue

                # Construir task data desde el evento del engine
                task_data = {
                    "channel_id": channel_id,
                    "chat_id": data.get("remoteJid", data.get("chat_id", "")),
                    "sender": data.get("pushName", data.get("sender", "")),
                    "text": data.get("text", data.get("body", "")),
                }

                logger.info("Mensaje entrante: '%s' de %s",
                    str(task_data["text"])[:50], task_data["sender"])

                await self.process_message(task_data)

            except asyncio.CancelledError:
                logger.info("AI Pipeline detenido")
                break
            except Exception as e:
                logger.error("Error en AI pipeline loop: %s", e, exc_info=True)
                await asyncio.sleep(1)


async def main():
    """Entry point del AI Pipeline worker."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

    from dotenv import load_dotenv
    # Cargar .env desde la raíz del proyecto platform/
    platform_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    env_path = os.path.join(platform_root, ".env")
    load_dotenv(env_path)
    print(f"Cargando .env desde: {env_path} (existe: {os.path.exists(env_path)})")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-30s | %(levelname)-8s | %(message)s",
    )

    pipeline = AIPipeline()
    await pipeline.setup()
    await pipeline.run()


if __name__ == "__main__":
    asyncio.run(main())
