# api/app/schemas/message.py — Esquemas para envío y consulta de mensajes

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator


# ── Tarjeta de contacto (sub-esquema) ───────────────────────────

class ContactCard(BaseModel):
    """Representa una tarjeta de contacto vCard simplificada."""

    name: str = Field(..., min_length=1, description="Nombre completo del contacto")
    phone: str = Field(..., min_length=1, description="Número de teléfono con código de país")


# ── Esquemas de envío ────────────────────────────────────────────

class MessageSendText(BaseModel):
    """Enviar mensaje de texto plano."""

    to: str = Field(..., description="Número destino o chat_id (ej: '5215512345678@s.whatsapp.net')")
    body: str = Field(..., min_length=1, max_length=4096, description="Contenido del mensaje")
    quoted_message_id: Optional[str] = Field(None, description="ID del mensaje al que se responde")


class MessageSendImage(BaseModel):
    """Enviar imagen con caption opcional."""

    to: str = Field(..., description="Número destino o chat_id")
    media_url: Optional[str] = Field(None, description="URL pública de la imagen")
    media_base64: Optional[str] = Field(None, description="Imagen codificada en base64")
    caption: Optional[str] = Field(None, max_length=1024)
    quoted_message_id: Optional[str] = None

    @model_validator(mode="after")
    def _requiere_media(self):
        if not self.media_url and not self.media_base64:
            raise ValueError("Se requiere media_url o media_base64")
        return self


class MessageSendVideo(BaseModel):
    """Enviar video con caption opcional."""

    to: str = Field(...)
    media_url: Optional[str] = None
    media_base64: Optional[str] = None
    caption: Optional[str] = Field(None, max_length=1024)

    @model_validator(mode="after")
    def _requiere_media(self):
        if not self.media_url and not self.media_base64:
            raise ValueError("Se requiere media_url o media_base64")
        return self


class MessageSendAudio(BaseModel):
    """Enviar nota de voz o archivo de audio."""

    to: str = Field(...)
    media_url: Optional[str] = None
    media_base64: Optional[str] = None

    @model_validator(mode="after")
    def _requiere_media(self):
        if not self.media_url and not self.media_base64:
            raise ValueError("Se requiere media_url o media_base64")
        return self


class MessageSendDocument(BaseModel):
    """Enviar documento adjunto."""

    to: str = Field(...)
    media_url: Optional[str] = None
    media_base64: Optional[str] = None
    filename: Optional[str] = Field(None, description="Nombre del archivo que verá el destinatario")
    caption: Optional[str] = Field(None, max_length=1024)

    @model_validator(mode="after")
    def _requiere_media(self):
        if not self.media_url and not self.media_base64:
            raise ValueError("Se requiere media_url o media_base64")
        return self


class MessageSendLocation(BaseModel):
    """Enviar ubicación geográfica."""

    to: str = Field(...)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    name: Optional[str] = Field(None, description="Nombre del lugar")
    address: Optional[str] = Field(None, description="Dirección legible")


class MessageSendContact(BaseModel):
    """Enviar una o varias tarjetas de contacto."""

    to: str = Field(...)
    contacts: list[ContactCard] = Field(..., min_length=1)


class MessageSendPoll(BaseModel):
    """Enviar encuesta (solo disponible en WhatsApp reciente)."""

    to: str = Field(...)
    title: str = Field(..., min_length=1, max_length=256, description="Pregunta de la encuesta")
    options: list[str] = Field(..., min_length=2, max_length=12, description="Opciones de respuesta")
    selectable_count: Optional[int] = Field(
        None, ge=1, description="Cantidad de opciones seleccionables (default: 1 = respuesta única)"
    )


class MessageSendReaction(BaseModel):
    """Reaccionar a un mensaje con un emoji."""

    message_id: str = Field(..., description="ID del mensaje de WhatsApp al que se reacciona")
    emoji: str = Field(..., min_length=1, max_length=10, description="Emoji de la reacción (cadena vacía para quitar)")


class MessageSendSticker(BaseModel):
    """Enviar sticker (WebP)."""

    to: str = Field(...)
    media_url: Optional[str] = None
    media_base64: Optional[str] = None

    @model_validator(mode="after")
    def _requiere_media(self):
        if not self.media_url and not self.media_base64:
            raise ValueError("Se requiere media_url o media_base64")
        return self


# ── Esquemas de respuesta / consulta ─────────────────────────────

class MessageResponse(BaseModel):
    """Representación de un mensaje almacenado."""

    id: uuid.UUID
    message_id_wa: Optional[str] = Field(None, description="ID asignado por WhatsApp")
    chat_id: str
    sender: str
    type: str = Field(description="text, image, video, audio, document, location, contact, poll, sticker, reaction")
    content: dict = Field(description="Contenido del mensaje en formato JSON según su tipo")
    status: str = Field(description="pending, sent, delivered, read, failed")
    is_from_me: bool
    timestamp: datetime

    model_config = {"from_attributes": True}


class MessageList(BaseModel):
    """Listado paginado de mensajes."""

    messages: list[MessageResponse]
    total: int
    page: int
    limit: int
