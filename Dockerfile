# WhatsApp Platform — Dockerfile unificado (API + Engine + Bot)
FROM node:20-slim AS node-base

# Instalar Python 3.11
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Engine (Node.js) — instalar deps + compilar TypeScript
COPY engine/package*.json engine/tsconfig.json engine/
RUN cd engine && npm ci 2>/dev/null || cd engine && npm install

COPY engine/src/ engine/src/
COPY engine/connect.js engine/
RUN cd engine && npx tsc && mkdir -p sessions media

# ── API + Bot (Python) ────────────────────────────────
COPY api/requirements.txt api/
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir -r api/requirements.txt && \
    /app/venv/bin/pip install --no-cache-dir qrcode[pil] pyyaml

COPY api/ api/
COPY config/ config/
COPY run_ai.py .
COPY start_prod.sh .

RUN chmod +x start_prod.sh

ENV PATH="/app/venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PORT=8000

EXPOSE 8000

CMD ["bash", "start_prod.sh"]
