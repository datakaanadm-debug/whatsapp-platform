#!/bin/bash
# WhatsApp Platform — Script de producción
# Arranca los 3 servicios en un solo contenedor

echo "==========================================="
echo "  WhatsApp Platform — Production"
echo "==========================================="

PORT=${PORT:-8000}

# Crear directorios necesarios
mkdir -p engine/sessions engine/media

# 1. Engine (Baileys + Redis) — output a stdout para ver en Railway logs
echo "[1/3] Arrancando Engine..."
cd /app/engine && node connect.js 2>&1 &
ENGINE_PID=$!
cd /app

# 2. AI Bot (Claude) — output a stdout
echo "[2/3] Arrancando AI Bot..."
python3 run_ai.py 2>&1 &
BOT_PID=$!

# 3. API (FastAPI) — en foreground para que Railway lo detecte
echo "[3/3] Arrancando API en puerto $PORT..."
echo ""
echo "  Dashboard:  https://TU-URL.up.railway.app"
echo "  Swagger:    https://TU-URL.up.railway.app/docs"
echo "  QR:         https://TU-URL.up.railway.app/api/channels/CHANNEL_ID/qr.png"
echo ""
echo "==========================================="

exec uvicorn api.app.main:app --host 0.0.0.0 --port $PORT
