# api/app/models/channel.py — Modelo de canal/sesión de WhatsApp

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Enum, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.app.models.base import BaseModel

if TYPE_CHECKING:
    from api.app.models.chat import Chat
    from api.app.models.contact import Contact
    from api.app.models.message import Message


class ChannelStatus(str, enum.Enum):
    """Estados posibles de un canal de WhatsApp."""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    BANNED = "banned"


class Channel(BaseModel):
    """
    Representa una sesión/canal de WhatsApp conectado a la plataforma.
    Cada canal tiene su propia API key y configuración de webhooks.
    """
    __tablename__ = "channels"

    # ── Datos del canal ───────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[ChannelStatus] = mapped_column(
        Enum(ChannelStatus, name="channel_status", native_enum=False),
        default=ChannelStatus.DISCONNECTED,
        nullable=False,
    )

    # ── Autenticación ─────────────────────────────────────────────
    api_key: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    # ── Configuración de webhooks ─────────────────────────────────
    webhook_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    webhook_events: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=list)

    # ── Configuración adicional ───────────────────────────────────
    settings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        default=dict,
    )

    # ── Estado ────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── Relaciones ────────────────────────────────────────────────
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="channel",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    chats: Mapped[list["Chat"]] = relationship(
        "Chat",
        back_populates="channel",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    contacts: Mapped[list["Contact"]] = relationship(
        "Contact",
        back_populates="channel",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
