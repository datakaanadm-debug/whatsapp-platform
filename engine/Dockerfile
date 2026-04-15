# Dockerfile — Motor de WhatsApp para AgentKit
# Generado por AgentKit

FROM node:20-slim

# Instalar dependencias del sistema necesarias para sharp y canvas
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar manifiestos de dependencias primero (cache de Docker)
COPY package*.json ./

# Instalar dependencias de producción
RUN npm ci --omit=dev

# Copiar código fuente
COPY . .

# Compilar TypeScript a JavaScript
RUN npx tsc

# Crear directorios necesarios
RUN mkdir -p sessions media

# No exponemos puertos — este servicio se comunica solo via Redis
EXPOSE 0

# Ejecutar el engine compilado
CMD ["node", "dist/index.js"]
