# api/app/models/chat.py — Modelo de conversaciones/chats

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.app.models.base import BaseModel

if TYPE_CHECKING:
    from api.app.models.channel import Channel


class Chat(BaseModel):
    """
    Representa una conversación de WhatsApp (individual o grupal).
    Almacena metadatos del chat y estado de lectura.
    """
    __tablename__ = "chats"

    # ── Relación con el canal ─────────────────────────────────────
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Identificador de WhatsApp ─────────────────────────────────
    chat_id_wa: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    # ── Datos del chat ────────────────────────────────────────────
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_group: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── Contadores y timestamps ───────────────────────────────────
    unread_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── Metadatos flexibles ───────────────────────────────────────
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        default=dict,
    )

    # ── Relaciones ────────────────────────────────────────────────
    channel: Mapped["Channel"] = relationship(
        "Channel",
        back_populates="chats",
    )
