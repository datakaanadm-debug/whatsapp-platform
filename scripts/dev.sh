#!/usr/bin/env bash
# scripts/dev.sh — Script de desarrollo local
# Levanta todos los servicios con Docker Compose y muestra logs en tiempo real

set -e

echo "=================================================="
echo "  WhatsApp Platform — Modo Desarrollo"
echo "=================================================="
echo ""

# Verificar que Docker esta instalado
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker no esta instalado."
    echo "Descargalo en: https://docker.com/get-started"
    exit 1
fi

# Verificar que Docker Compose esta disponible
if ! docker compose version &> /dev/null; then
    echo "ERROR: Docker Compose no esta disponible."
    echo "Asegurate de tener Docker Desktop actualizado."
    exit 1
fi

# Verificar que existe el archivo .env
if [ ! -f ".env" ]; then
    echo "Archivo .env no encontrado. Creando desde .env.example..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "Archivo .env creado. Revisa y configura tus variables antes de continuar."
        echo ""
    else
        echo "ERROR: No se encontro .env ni .env.example"
        exit 1
    fi
fi

echo "Construyendo y levantando servicios..."
echo ""

# Build y start con logs
docker compose up --build --remove-orphans "$@"
