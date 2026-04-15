# api/app/schemas/channel.py — Esquemas para gestión de canales (sesiones de WhatsApp)

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl


class ChannelCreate(BaseModel):
    """Datos requeridos para crear un nuevo canal."""

    name: str = Field(..., min_length=1, max_length=100, description="Nombre descriptivo del canal")
    webhook_url: Optional[str] = Field(None, description="URL de webhook para recibir eventos")
    webhook_events: Optional[list[str]] = Field(
        None,
        description="Lista de eventos a los que suscribir el webhook (ej: ['message', 'status'])",
    )


class ChannelUpdate(BaseModel):
    """Campos actualizables de un canal. Solo se envían los que se quieren cambiar."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    webhook_url: Optional[str] = None
    webhook_events: Optional[list[str]] = None
    settings: Optional[dict] = Field(None, description="Configuración adicional del canal en JSON")
    is_active: Optional[bool] = None


class ChannelResponse(BaseModel):
    """Representación pública de un canal."""

    id: uuid.UUID
    name: str
    phone_number: Optional[str] = None
    status: str = Field(description="Estado de la sesión: disconnected, connecting, connected, error")
    is_active: bool
    api_key: str = Field(description="Clave API asignada al canal")
    webhook_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChannelQR(BaseModel):
    """Código QR para vincular la sesión de WhatsApp."""

    qr_code: str = Field(description="Código QR en formato base64 (imagen PNG) o texto para terminal")
    timeout: int = Field(description="Segundos antes de que el QR expire")


class ChannelStatus(BaseModel):
    """Estado en tiempo real de la sesión de WhatsApp."""

    status: str = Field(description="disconnected | connecting | connected | error")
    phone_number: Optional[str] = None
    battery: Optional[int] = Field(None, ge=0, le=100, description="Nivel de batería del dispositivo")
    platform: Optional[str] = Field(None, description="Plataforma del dispositivo (Android, iOS, etc.)")
