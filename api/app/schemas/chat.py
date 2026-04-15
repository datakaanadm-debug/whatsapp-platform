# api/app/schemas/chat.py — Esquemas para gestión de chats / conversaciones

import uuid
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


class ChatResponse(BaseModel):
    """Representación pública de un chat."""

    id: uuid.UUID
    chat_id_wa: str = Field(description="Identificador de WhatsApp del chat (ej: '5215512345678@s.whatsapp.net')")
    name: Optional[str] = Field(None, description="Nombre del chat o contacto")
    is_group: bool = False
    unread_count: int = 0
    last_message_at: Optional[datetime] = None
    is_archived: bool = False
    is_pinned: bool = False

    model_config = {"from_attributes": True}


class ChatList(BaseModel):
    """Listado de chats con total."""

    chats: list[ChatResponse]
    total: int


class ChatAction(BaseModel):
    """Acción a ejecutar sobre un chat."""

    action: Literal["archive", "unarchive", "pin", "unpin", "mute", "unmute", "mark_read"] = Field(
        ..., description="Acción a realizar sobre el chat"
    )
