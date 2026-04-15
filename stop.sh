#!/bin/bash
# ============================================
#  WhatsApp Platform — Detener todo
#  Uso: bash stop.sh
# ============================================

echo "Deteniendo servicios..."

if [ -f .pids ]; then
    while read pid; do
        kill $pid 2>/dev/null && echo "  Proceso $pid detenido"
    done < .pids
    rm .pids
fi

taskkill //F //IM node.exe 2>/dev/null
taskkill //F //IM uvicorn.exe 2>/dev/null

echo "Todos los servicios detenidos."
