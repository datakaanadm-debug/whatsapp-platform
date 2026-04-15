#!/bin/bash
# ============================================
#  WhatsApp Platform — Arrancar todo
#  Uso: bash start.sh
# ============================================

cd "$(dirname "$0")"

echo "==========================================="
echo "  WhatsApp Platform — Iniciando servicios"
echo "==========================================="

# Matar procesos anteriores
echo "[1/4] Limpiando procesos anteriores..."
taskkill //F //IM node.exe 2>/dev/null
taskkill //F //IM uvicorn.exe 2>/dev/null
# Matar pythons del pipeline (no el de venv)
ps aux | grep "run_ai.py\|ai_pipeline" | grep -v grep | awk '{print $2}' | xargs -r kill -9 2>/dev/null
sleep 2

# Directorio base
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"

# Activar venv
source "$BASE_DIR/.venv/Scripts/activate"

# API
echo "[2/4] Arrancando API (puerto 3000)..."
cd "$BASE_DIR" && uvicorn api.app.main:app --host 0.0.0.0 --port 3000 > "$BASE_DIR/logs_api.txt" 2>&1 &
API_PID=$!
sleep 3

# Engine
echo "[3/4] Arrancando Engine (Baileys)..."
cd "$BASE_DIR/engine" && node connect.js > "$BASE_DIR/logs_engine.txt" 2>&1 &
ENGINE_PID=$!
sleep 3

# Bot AI
echo "[4/4] Arrancando Arty AI Bot..."
cd "$BASE_DIR" && python "$BASE_DIR/run_ai.py" > "$BASE_DIR/logs_ai_bot.txt" 2>&1 &
BOT_PID=$!
sleep 2

echo ""
echo "==========================================="
echo "  Todo corriendo!"
echo "==========================================="
echo "  API:    http://localhost:3000      (PID $API_PID)"
echo "  Docs:   http://localhost:3000/docs"
echo "  Engine: Baileys WhatsApp           (PID $ENGINE_PID)"
echo "  Bot:    Arty AI                    (PID $BOT_PID)"
echo ""
echo "  Logs:"
echo "    tail -f logs_api.txt"
echo "    tail -f logs_engine.txt"
echo "    tail -f logs_ai_bot.txt"
echo ""
echo "  Para detener: bash stop.sh"
echo "==========================================="

# Guardar PIDs
echo "$API_PID" > .pids
echo "$ENGINE_PID" >> .pids
echo "$BOT_PID" >> .pids
