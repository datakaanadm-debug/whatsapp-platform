# api/app/models/group.py — Modelo de grupos de WhatsApp

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from api.app.models.base import BaseModel


class Group(BaseModel):
    """
    Representa un grupo de WhatsApp con sus participantes y configuración.
    Los participantes y admins se almacenan como listas JSON.
    """
    __tablename__ = "groups"

    # ── Relación con el canal ─────────────────────────────────────
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Identificador de WhatsApp ─────────────────────────────────
    group_id_wa: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    # ── Datos del grupo ───────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # ── Participantes (listas JSON de IDs de WhatsApp) ────────────
    participants: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    admins: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)

    # ── Enlaces y media ───────────────────────────────────────────
    invite_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    profile_pic_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Configuración del grupo (announce, restrict, etc.) ────────
    settings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)

    # ── Fecha de creación en WhatsApp ─────────────────────────────
    created_at_wa: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
