#!/usr/bin/env bash
# scripts/start.sh — Script de inicio de la API
# Espera a que PostgreSQL este listo, ejecuta migraciones y arranca el servidor

set -e

echo "=================================================="
echo "  WhatsApp Platform API — Iniciando..."
echo "=================================================="

# ── Esperar a PostgreSQL ──────────────────────────────────────────

MAX_RETRIES=30
RETRY_INTERVAL=2
RETRIES=0

echo "Esperando a PostgreSQL..."

while [ $RETRIES -lt $MAX_RETRIES ]; do
    if python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os

async def check():
    url = os.getenv('DATABASE_URL', 'postgresql+asyncpg://postgres:postgres@postgres:5432/whatsapp_platform')
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text('SELECT 1'))
    await engine.dispose()
    return True

asyncio.run(check())
" 2>/dev/null; then
        echo "PostgreSQL listo!"
        break
    fi

    RETRIES=$((RETRIES + 1))
    echo "  Intento $RETRIES/$MAX_RETRIES — PostgreSQL no disponible, reintentando en ${RETRY_INTERVAL}s..."
    sleep $RETRY_INTERVAL
done

if [ $RETRIES -eq $MAX_RETRIES ]; then
    echo "ERROR: No se pudo conectar a PostgreSQL despues de $MAX_RETRIES intentos"
    exit 1
fi

# ── Esperar a Redis ───────────────────────────────────────────────

RETRIES=0
echo "Esperando a Redis..."

while [ $RETRIES -lt $MAX_RETRIES ]; do
    if python -c "
import redis, os
url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
r = redis.from_url(url)
r.ping()
" 2>/dev/null; then
        echo "Redis listo!"
        break
    fi

    RETRIES=$((RETRIES + 1))
    echo "  Intento $RETRIES/$MAX_RETRIES — Redis no disponible, reintentando en ${RETRY_INTERVAL}s..."
    sleep $RETRY_INTERVAL
done

if [ $RETRIES -eq $MAX_RETRIES ]; then
    echo "ERROR: No se pudo conectar a Redis despues de $MAX_RETRIES intentos"
    exit 1
fi

# ── Ejecutar migraciones de Alembic (si existen) ──────────────────

if [ -f "alembic.ini" ]; then
    echo "Ejecutando migraciones de base de datos..."
    alembic upgrade head || echo "ADVERTENCIA: Las migraciones fallaron. Las tablas se crearan automaticamente."
else
    echo "No se encontro alembic.ini — las tablas se crearan automaticamente al iniciar."
fi

# ── Arrancar el servidor ──────────────────────────────────────────

PORT=${PORT:-8000}
WORKERS=${WEB_WORKERS:-1}

echo ""
echo "Iniciando servidor FastAPI en puerto $PORT con $WORKERS worker(s)..."
echo "Documentacion: http://localhost:$PORT/docs"
echo "=================================================="

exec uvicorn api.app.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level "${LOG_LEVEL:-info}" \
    --access-log
