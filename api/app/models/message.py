# api/app/models/message.py — Modelo de mensajes de WhatsApp

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.app.models.base import BaseModel

if TYPE_CHECKING:
    from api.app.models.channel import Channel


class MessageType(str, enum.Enum):
    """Tipos de mensaje soportados por WhatsApp."""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    STICKER = "sticker"
    LOCATION = "location"
    CONTACT = "contact"
    POLL = "poll"
    INTERACTIVE = "interactive"


class MessageStatus(str, enum.Enum):
    """Estados de entrega de un mensaje."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class Message(BaseModel):
    """
    Representa un mensaje individual enviado o recibido por WhatsApp.
    El campo content es JSON flexible para soportar todos los tipos de mensaje.
    """
    __tablename__ = "messages"

    # ── Relación con el canal ─────────────────────────────────────
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Identificadores ───────────────────────────────────────────
    chat_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    message_id_wa: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        index=True,
    )

    # ── Remitente y destinatario ──────────────────────────────────
    sender: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── Tipo y contenido ──────────────────────────────────────────
    type: Mapped[str] = mapped_column(
        String(20),
        default="text",
        nullable=False,
    )
    content: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # ── Estado de entrega ─────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )

    # ── Flags ─────────────────────────────────────────────────────
    is_from_me: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_forwarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── Mensaje citado ────────────────────────────────────────────
    quoted_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # ── Media adjunta ─────────────────────────────────────────────
    media_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_mime_type: Mapped[Optional[str]] = mapped_column(String(127), nullable=True)

    # ── Marcas de tiempo de entrega ───────────────────────────────
    timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── Relaciones ────────────────────────────────────────────────
    channel: Mapped["Channel"] = relationship(
        "Channel",
        back_populates="messages",
    )
