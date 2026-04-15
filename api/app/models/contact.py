# api/app/models/contact.py — Modelo de contactos de WhatsApp

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.app.models.base import BaseModel

if TYPE_CHECKING:
    from api.app.models.channel import Channel


class Contact(BaseModel):
    """
    Representa un contacto de WhatsApp asociado a un canal.
    Almacena información del perfil y estado del contacto.
    """
    __tablename__ = "contacts"

    # ── Relación con el canal ─────────────────────────────────────
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Identificadores ───────────────────────────────────────────
    contact_id_wa: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    phone_number: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    # ── Datos del perfil ──────────────────────────────────────────
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    push_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    business_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    profile_pic_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Flags ─────────────────────────────────────────────────────
    is_business: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

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
        back_populates="contacts",
    )
