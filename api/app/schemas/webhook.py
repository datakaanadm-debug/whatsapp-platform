# api/app/schemas/webhook.py — Esquemas para configuración y eventos de webhooks

import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


class WebhookCreate(BaseModel):
    """Datos para registrar un nuevo webhook."""

    url: str = Field(..., description="URL HTTPS que recibirá los eventos via POST")
    events: list[str] = Field(
        ..., min_length=1,
        description="Eventos a suscribir (ej: ['message.received', 'message.status', 'session.status'])",
    )
    secret: Optional[str] = Field(
        None,
        description="Secreto compartido para firmar los payloads (HMAC-SHA256 en cabecera X-Webhook-Signature)",
    )


class WebhookUpdate(BaseModel):
    """Campos actualizables de un webhook."""

    url: Optional[str] = None
    events: Optional[list[str]] = None
    is_active: Optional[bool] = None


class WebhookResponse(BaseModel):
    """Representación pública de un webhook registrado."""

    id: uuid.UUID
    url: str
    events: list[str]
    is_active: bool
    last_triggered_at: Optional[datetime] = None
    failure_count: int = 0

    model_config = {"from_attributes": True}


class WebhookEvent(BaseModel):
    """Payload que se envía al URL del webhook cuando ocurre un evento."""

    event: str = Field(description="Tipo de evento (ej: 'message.received')")
    channel_id: uuid.UUID
    data: Any = Field(description="Datos del evento en formato JSON")
    timestamp: datetime


class WebhookLogEntry(BaseModel):
    """Registro de un intento de entrega de webhook."""

    id: uuid.UUID
    event: str
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    success: bool
    attempted_at: datetime
    duration_ms: Optional[int] = Field(None, description="Duración de la solicitud en milisegundos")

    model_config = {"from_attributes": True}
