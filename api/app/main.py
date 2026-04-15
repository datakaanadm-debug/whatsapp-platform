# api/app/main.py — Aplicacion principal FastAPI de la plataforma WhatsApp
# Punto de entrada que configura routers, middleware, WebSocket y eventos

import asyncio
import json
import logging
from contextlib import asynccontextmanager

import os
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.app.config import get_settings
from api.app.database import engine, redis_pool, async_session_factory
from api.app.events.event_bus import EventBus
from api.app.events.event_handler import EventHandler
from api.app.middleware.auth import limiter
from api.app.models.base import Base
from api.app.openapi_tags import tags_metadata

# Routers
from api.app.routers.health import router as health_router
from api.app.routers.channels import router as channels_router
from api.app.routers.messages import router as messages_router
from api.app.routers.chats import router as chats_router
from api.app.routers.contacts import router as contacts_router
from api.app.routers.groups import router as groups_router
from api.app.routers.webhooks import router as webhooks_router
from api.app.routers.presence import router as presence_router
from api.app.routers.media import router as media_router
from api.app.routers.users import router as users_router, status_router
from api.app.routers.settings import router as settings_router, limits_router
from api.app.routers.stories import router as stories_router
from api.app.routers.statuses import router as statuses_router
from api.app.routers.newsletters import router as newsletters_router
from api.app.routers.business import router as business_router
from api.app.routers.labels import router as labels_router
from api.app.routers.blacklist import router as blacklist_router
from api.app.routers.communities import router as communities_router
from api.app.routers.calls import router as calls_router

settings = get_settings()

# Configuracion de logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(name)-30s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("platform.main")

# Instancia global del event bus (se inicializa en lifespan)
event_bus: EventBus | None = None
event_handler: EventHandler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Contexto de vida de la aplicacion:
    - Al iniciar: crea tablas en DB, arranca el event handler
    - Al cerrar: detiene el event handler, cierra conexiones
    """
    global event_bus, event_handler

    logger.info("=" * 60)
    logger.info("  WhatsApp Platform API — Iniciando...")
    logger.info("=" * 60)

    # Crear tablas en la base de datos si no existen
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tablas de base de datos verificadas/creadas")

    # Event bus desactivado en la API — el AI Pipeline worker consume wa:events:queue
    # Para reactivar: descomentar las líneas siguientes
    # event_bus = EventBus(redis_pool)
    # event_handler = EventHandler(
    #     event_bus=event_bus,
    #     session_factory=async_session_factory,
    #     redis=redis_pool,
    # )
    # await event_handler.setup()
    logger.info("API lista — eventos procesados por AI Pipeline worker")

    logger.info("Servidor listo en puerto %s", settings.CORS_ORIGINS)
    logger.info("Documentacion: http://localhost:8000/docs")
    logger.info("=" * 60)

    yield

    # Shutdown
    logger.info("Apagando servidor...")
    if event_bus:
        await event_bus.stop()
    from api.app.database import close_connections
    await close_connections()
    logger.info("Conexiones cerradas. Servidor detenido.")


# ── Aplicacion FastAPI ────────────────────────────────────────────

app = FastAPI(
    title="WhatsApp Platform API",
    version="1.0.0",
    description=(
        "API REST completa para gestionar multiples sesiones de WhatsApp. "
        "Soporta mensajeria, grupos, contactos, media, webhooks, "
        "presencia, newsletters, Business API y mas."
    ),
    openapi_tags=tags_metadata,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Middleware ─────────────────────────────────────────────────────

# Rate limiting con SlowAPI
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — en desarrollo se permite todo, en produccion restringir
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Dashboard Web ─────────────────────────────────────────────────

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    """Dashboard web para gestionar canales de WhatsApp."""
    html_file = STATIC_DIR / "dashboard.html"
    return HTMLResponse(content=html_file.read_text(encoding="utf-8"))


# ── Bot Dashboard API ──────────────────────────────────────────────


@app.get("/api/bot/messages", include_in_schema=False)
async def bot_messages():
    """Últimos mensajes procesados por el bot."""
    import json as _json
    messages = await redis_pool.lrange("bot:messages", 0, 49)
    return [_json.loads(m) for m in messages]


@app.get("/api/bot/chats", include_in_schema=False)
async def bot_chats():
    """Chats activos del bot."""
    import json as _json
    raw = await redis_pool.hgetall("bot:chats")
    chats = []
    for chat_id, data in raw.items():
        info = _json.loads(data)
        info["chat_id"] = chat_id
        chats.append(info)
    chats.sort(key=lambda x: x.get("last_time", ""), reverse=True)
    return chats


@app.get("/api/bot/stats", include_in_schema=False)
async def bot_stats():
    """Estadísticas del bot."""
    msgs_in = await redis_pool.get("bot:stats:messages_in") or "0"
    msgs_out = await redis_pool.get("bot:stats:messages_out") or "0"
    tokens_in = await redis_pool.get("bot:stats:tokens_in") or "0"
    tokens_out = await redis_pool.get("bot:stats:tokens_out") or "0"
    ai_enabled = await redis_pool.get("wa:ai_enabled:3e9c7ac1-26c3-4bb4-8ce1-8f60b01919b6") or "false"
    return {
        "messages_in": int(msgs_in),
        "messages_out": int(msgs_out),
        "tokens_in": int(tokens_in),
        "tokens_out": int(tokens_out),
        "ai_enabled": ai_enabled == "true",
        "model": "claude-sonnet-4-6",
        "agent_name": "Arty",
        "prompt_chars": 7881,
    }


# ── Routers ───────────────────────────────────────────────────────

# Health (sin prefijo)
app.include_router(health_router)

# Canales / Sesiones
app.include_router(channels_router)

# Mensajes (ya tiene prefix /api/{channel_id}/messages)
app.include_router(messages_router)

# Chats (ya tiene prefix /api/{channel_id}/chats)
app.include_router(chats_router)

# Contactos (ya tiene prefix /api/{channel_id}/contacts)
app.include_router(contacts_router)

# Grupos (ya tiene prefix /api/{channel_id}/groups)
app.include_router(groups_router)

# Webhooks (ya tiene prefix /api/{channel_id}/webhooks)
app.include_router(webhooks_router)

# Presencia (ya tiene prefix /api/{channel_id}/presence)
app.include_router(presence_router)

# Media (ya tiene prefix /api/{channel_id}/media)
app.include_router(media_router)

# Usuarios (prefix /api/users)
app.include_router(users_router)
# Status endpoint (prefix /api — PUT /api/status)
app.include_router(status_router)

# Configuracion (prefix /api/settings)
app.include_router(settings_router)
# Limites (prefix /api — GET /api/limits)
app.include_router(limits_router)

# Historias/Estados de WhatsApp (prefix /api/stories)
app.include_router(stories_router)

# Estados de visualizacion — ACK (prefix /api/statuses)
app.include_router(statuses_router)

# Newsletters/Canales de WhatsApp (prefix /api/newsletters)
app.include_router(newsletters_router)

# WhatsApp Business (prefix /api/business)
app.include_router(business_router)

# Etiquetas (prefix /api/labels)
app.include_router(labels_router)

# Lista negra (prefix /api/blacklist)
app.include_router(blacklist_router)

# Comunidades (prefix /api/communities)
app.include_router(communities_router)

# Llamadas (prefix /api/calls)
app.include_router(calls_router)


# ── WebSocket para eventos en tiempo real ─────────────────────────


@app.websocket("/ws/{channel_id}")
async def websocket_events(websocket: WebSocket, channel_id: str):
    """
    WebSocket que retransmite eventos de un canal de WhatsApp en tiempo real.

    El cliente se conecta a /ws/{channel_id} y recibe cada evento que el engine
    publica en el canal Redis wa:evt:{channel_id}.

    Esto permite a dashboards y aplicaciones frontend recibir actualizaciones
    sin necesidad de polling ni webhooks.
    """
    await websocket.accept()
    logger.info("WebSocket conectado para canal: %s", channel_id)

    pubsub = redis_pool.pubsub()
    redis_channel = f"wa:evt:{channel_id}"

    try:
        await pubsub.subscribe(redis_channel)
        logger.debug("WebSocket suscrito a Redis canal: %s", redis_channel)

        while True:
            # Escuchar mensajes de Redis
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )

            if message and message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")

                # Enviar el evento al cliente WebSocket
                await websocket.send_text(data)

            # Tambien verificar si el cliente envio algo (para keep-alive / ping)
            try:
                client_msg = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=0.01,
                )
                # Si el cliente envia "ping", responder "pong"
                if client_msg.strip().lower() == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                pass  # Normal — no habia mensaje del cliente
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        logger.info("WebSocket desconectado para canal: %s", channel_id)
    except Exception as e:
        logger.error("Error en WebSocket para canal %s: %s", channel_id, e, exc_info=True)
    finally:
        await pubsub.unsubscribe(redis_channel)
        await pubsub.aclose()
        logger.debug("WebSocket cleanup completado para canal: %s", channel_id)
