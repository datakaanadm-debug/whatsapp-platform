"""
AI Bot standalone — Lee eventos de WhatsApp y responde con Claude.
Ejecutar: python run_ai.py
"""
import asyncio
import json
import logging
import os
import sys
import yaml
from datetime import datetime, timezone

# Setup
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

import redis.asyncio as aioredis
from anthropic import AsyncAnthropic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
log = logging.getLogger("arty")

REDIS_URL = os.getenv("REDIS_URL")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID", "3302d4a7-f181-452c-86fd-15abbeaa715f")

# Cargar system prompt
SYSTEM_PROMPT = "Eres un asistente útil. Responde en español."
for path in ["config/prompts.yaml", "../config/prompts.yaml"]:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        SYSTEM_PROMPT = cfg.get("system_prompt", SYSTEM_PROMPT)
        log.info("Prompt cargado desde %s (%d chars)", path, len(SYSTEM_PROMPT))
        break

# Historial en memoria (por chat_id)
histories: dict[str, list[dict]] = {}
MAX_HISTORY = 20


def get_redis():
    """Crea conexión Redis fresca cada vez (Upstash cierra conexiones inactivas)."""
    return aioredis.from_url(REDIS_URL, decode_responses=True, socket_timeout=10)


async def main():
    claude = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    log.info("=" * 50)
    log.info("  Arty AI Bot — Conectado y escuchando")
    log.info("=" * 50)

    while True:
        try:
            # Conexión fresca para cada poll (evita timeouts de Upstash)
            redis = get_redis()
            raw = await redis.rpop("wa:events:queue")
            await redis.aclose()

            if raw is None:
                await asyncio.sleep(0.5)
                continue

            event = json.loads(raw)
            event_type = event.get("event", "")
            data = event.get("data", {})

            # Solo mensajes recibidos, no propios
            if event_type != "message.received":
                continue
            if data.get("fromMe", False):
                continue

            text = data.get("text", data.get("body", ""))
            chat_id = data.get("remoteJid", "")
            sender = data.get("pushName", "usuario")

            if not text or not chat_id:
                continue

            log.info(">>> %s: %s", sender, text)

            # Historial
            if chat_id not in histories:
                histories[chat_id] = []
            histories[chat_id].append({"role": "user", "content": text})
            if len(histories[chat_id]) > MAX_HISTORY:
                histories[chat_id] = histories[chat_id][-MAX_HISTORY:]

            # Generar respuesta con Claude
            try:
                response = await claude.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    messages=histories[chat_id],
                )
                reply = response.content[0].text
                log.info("<<< Arty: %s", reply[:80])
                histories[chat_id].append({"role": "assistant", "content": reply})
            except Exception as e:
                log.error("Error Claude: %s", e)
                continue

            # Enviar respuesta + guardar dashboard data (todo en una conexión)
            try:
                r2 = get_redis()
                now = datetime.now(timezone.utc).isoformat()

                # Enviar respuesta via engine (PRIMERO - lo más importante)
                cmd = json.dumps({
                    "command": "send_message",
                    "channel_id": CHANNEL_ID,
                    "data": {"type": "text", "to": chat_id, "body": reply},
                    "request_id": f"ai-{now}",
                })
                await r2.lpush("wa:cmd:queue", cmd)

                # Dashboard: mensajes
                pipe = r2.pipeline()
                pipe.lpush("bot:messages", json.dumps({"dir": "in", "sender": sender, "chat_id": chat_id, "text": text, "time": now}))
                pipe.lpush("bot:messages", json.dumps({"dir": "out", "sender": "Arty", "chat_id": chat_id, "text": reply, "time": now}))
                pipe.ltrim("bot:messages", 0, 199)
                pipe.hset("bot:chats", chat_id, json.dumps({"sender": sender, "last_message": text, "last_time": now, "message_count": len(histories[chat_id])}))
                pipe.incr("bot:stats:messages_in")
                pipe.incr("bot:stats:messages_out")
                pipe.incr("bot:stats:tokens_in", response.usage.input_tokens)
                pipe.incr("bot:stats:tokens_out", response.usage.output_tokens)
                await pipe.execute()
                await r2.aclose()
                log.info("Dashboard actualizado")
            except Exception as e:
                log.error("Error Redis dashboard: %s", e)

        except Exception as e:
            log.error("Error en loop: %s", e)
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
