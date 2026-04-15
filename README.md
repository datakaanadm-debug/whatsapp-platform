# WhatsApp Platform API

Plataforma completa para gestionar multiples sesiones de WhatsApp a traves de una API REST unificada. Soporta mensajeria, grupos, contactos, media, webhooks, presencia, newsletters, WhatsApp Business y mas.

## Arquitectura

```
                    +------------------+
                    |   Frontend/App   |
                    +--------+---------+
                             |
                    HTTP / WebSocket
                             |
              +--------------v--------------+
              |      API (FastAPI)          |
              |   - REST endpoints         |
              |   - WebSocket /ws/{id}     |
              |   - Rate limiting          |
              |   - Auth (API Key)         |
              +-+--------+--------+--------+
                |        |        |
          +-----v--+ +--v---+ +--v--------+
          |PostgreSQL| |Redis | |  Worker   |
          |  (DB)    | |(Pub/ | | - Webhooks|
          |  Canales | | Sub  | | - Messages|
          |  Mensajes| | Queue| | - Media   |
          |  Chats   | | Cache| |           |
          +----------+ +--+--+ +-----------+
                          |
                   +------v------+
                   |   Engine    |
                   | (Baileys)   |
                   | Node.js     |
                   +------+------+
                          |
                     WhatsApp Web
```

### Componentes

| Servicio   | Tecnologia             | Puerto | Descripcion                                 |
|------------|------------------------|--------|---------------------------------------------|
| API        | Python 3.11 + FastAPI  | 8000   | REST API + WebSocket                        |
| Engine     | Node.js + Baileys      | -      | Conexion directa con WhatsApp Web           |
| Worker     | Python 3.11            | -      | Webhooks, cola de mensajes, media           |
| PostgreSQL | PostgreSQL 16          | 5432   | Almacenamiento persistente                  |
| Redis      | Redis 7                | 6379   | Pub/Sub, colas, cache                       |

### Flujo de un mensaje entrante

```
WhatsApp Web -> Engine (Baileys) -> Redis Pub/Sub -> API (Event Handler) -> DB
                                                  -> Worker (Webhook Dispatcher) -> Tu servidor
                                                  -> WebSocket -> Tu frontend
```

### Flujo de un mensaje saliente

```
Tu app -> API REST -> Redis (message:queue) -> Worker -> Redis Pub/Sub -> Engine -> WhatsApp Web
```

## Prerequisitos

- Docker y Docker Compose
- Git

Para desarrollo local sin Docker:
- Python 3.11+
- Node.js 18+ (para el engine)
- PostgreSQL 16
- Redis 7

## Inicio rapido

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/whatsapp-platform.git
cd whatsapp-platform/platform
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus valores
```

### 3. Levantar servicios

```bash
# Opcion A: Con el script de desarrollo
bash scripts/dev.sh

# Opcion B: Directamente con Docker Compose
docker compose up --build
```

### 4. Verificar que esta funcionando

```bash
# Health check
curl http://localhost:8000/health

# Readiness check (verifica DB + Redis)
curl http://localhost:8000/health/ready
```

### 5. Explorar la documentacion

Abrir en el navegador: http://localhost:8000/docs

## Documentacion de la API

La documentacion interactiva Swagger esta disponible en:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Endpoints principales

| Recurso      | Prefijo                        | Descripcion                    |
|--------------|--------------------------------|--------------------------------|
| Health       | `/health`                      | Estado del servicio            |
| Channels     | `/api/channels`                | Gestion de sesiones            |
| Messages     | `/api/{channel_id}/messages`   | Envio y consulta de mensajes   |
| Chats        | `/api/{channel_id}/chats`      | Conversaciones                 |
| Contacts     | `/api/{channel_id}/contacts`   | Contactos sincronizados        |
| Groups       | `/api/{channel_id}/groups`     | Gestion de grupos              |
| Webhooks     | `/api/{channel_id}/webhooks`   | Suscripciones a eventos        |
| Presence     | `/api/{channel_id}/presence`   | Estado en linea                |
| Media        | `/api/{channel_id}/media`      | Archivos multimedia            |
| Users        | `/api/users`                   | Perfil y autenticacion         |
| Settings     | `/api/settings`                | Configuracion del canal        |
| Stories      | `/api/stories`                 | Estados/Historias              |
| Newsletters  | `/api/newsletters`             | Canales de WhatsApp            |
| Business     | `/api/business`                | Funciones de negocio           |
| Labels       | `/api/labels`                  | Etiquetas                      |
| Blacklist    | `/api/blacklist`               | Lista negra                    |
| Communities  | `/api/communities`             | Comunidades                    |
| Calls        | `/api/calls`                   | Llamadas                       |

### WebSocket

Conexion en tiempo real para recibir eventos de un canal:

```
ws://localhost:8000/ws/{channel_id}
```

Eventos recibidos: mensajes nuevos, cambios de estado, presencia, QR, etc.

## Variables de entorno

| Variable               | Default                          | Descripcion                                  |
|------------------------|----------------------------------|----------------------------------------------|
| `DATABASE_URL`         | `postgresql+asyncpg://...`       | URL de conexion a PostgreSQL                 |
| `REDIS_URL`            | `redis://localhost:6379/0`       | URL de conexion a Redis                      |
| `PORT`                 | `8000`                           | Puerto de la API                             |
| `LOG_LEVEL`            | `INFO`                           | Nivel de logging (DEBUG, INFO, WARNING, etc) |
| `JWT_SECRET`           | (cambiar)                        | Secreto para tokens JWT                      |
| `CORS_ORIGINS`         | `["http://localhost:3000"]`      | Origenes permitidos para CORS                |
| `RATE_LIMIT_PER_MINUTE`| `60`                            | Limite de requests por minuto por IP         |
| `S3_ENDPOINT`          | `http://localhost:9000`          | Endpoint de almacenamiento S3/MinIO          |
| `ANTHROPIC_API_KEY`    | (vacio)                          | API key de Anthropic para agentes IA         |
| `WEBHOOK_RETRY_MAX`    | `5`                              | Intentos maximos de entrega de webhooks      |

Ver `.env.example` para la lista completa.

## Desarrollo

### Estructura del proyecto

```
platform/
  api/
    app/
      main.py              <- Aplicacion FastAPI principal
      config.py            <- Configuracion con pydantic-settings
      database.py          <- Conexiones a PostgreSQL y Redis
      openapi_tags.py      <- Tags para documentacion Swagger
      events/
        event_bus.py       <- Bus de eventos Redis Pub/Sub
        event_handler.py   <- Procesador de eventos del engine
      middleware/
        auth.py            <- Autenticacion por API Key
      models/              <- Modelos SQLAlchemy
      routers/             <- Endpoints de la API
      schemas/             <- Esquemas Pydantic (request/response)
      services/            <- Logica de negocio
      utils/
        security.py        <- HMAC, API keys, firma de webhooks
        helpers.py         <- UUID, fechas, paginacion, sanitizacion
    Dockerfile
    requirements.txt
  engine/
    src/                   <- Engine Baileys (Node.js)
    Dockerfile
  worker/
    app/
      main.py              <- Punto de entrada del worker
      webhook_dispatcher.py <- Entrega de webhooks con reintentos
      message_queue.py     <- Cola de mensajes con rate limiting
      media_processor.py   <- Procesamiento de imagenes/stickers
    Dockerfile
    requirements.txt
  scripts/
    start.sh               <- Script de inicio (espera DB, migraciones)
    dev.sh                  <- Script de desarrollo (docker compose up)
  docker-compose.yml
  .env.example
```

### Ejecutar sin Docker

```bash
# Instalar dependencias de la API
cd platform/api
pip install -r requirements.txt

# Iniciar la API (requiere PostgreSQL y Redis corriendo)
uvicorn api.app.main:app --reload --port 8000

# En otra terminal, iniciar el worker
python -m worker.app.main

# En otra terminal, iniciar el engine
cd platform/engine
npm install
npm run dev
```

### Agregar un nuevo endpoint

1. Crear o editar el router en `api/app/routers/`
2. Crear esquemas en `api/app/schemas/`
3. Crear servicio en `api/app/services/`
4. Registrar el router en `api/app/main.py`

## Produccion

### Recomendaciones

- Cambiar `JWT_SECRET` por un valor aleatorio de al menos 32 caracteres
- Configurar `CORS_ORIGINS` con los dominios reales
- Usar PostgreSQL gestionado (RDS, Cloud SQL, etc.)
- Usar Redis gestionado (ElastiCache, Memorystore, etc.)
- Configurar SSL/TLS con un reverse proxy (nginx, Traefik)
- Configurar backups automaticos de la base de datos
- Monitorear logs y metricas

### Escalamiento

- **API**: Escalar horizontalmente con multiples instancias detras de un load balancer
- **Worker**: Escalar el numero de instancias segun la carga de webhooks/mensajes
- **Engine**: Una instancia por sesion de WhatsApp activa
- **PostgreSQL**: Read replicas para consultas pesadas
- **Redis**: Cluster para alta disponibilidad

### Deploy con Docker

```bash
# Build de produccion
docker compose -f docker-compose.yml build

# Iniciar en background
docker compose -f docker-compose.yml up -d

# Ver logs
docker compose logs -f api worker engine

# Escalar workers
docker compose up -d --scale worker=3
```
