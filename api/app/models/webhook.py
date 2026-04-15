# api/app/models/webhook.py — Modelo de suscripciones a webhooks

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.app.models.base import BaseModel

if TYPE_CHECKING:
    from api.app.models.webhook_log import WebhookLog


class Webhook(BaseModel):
    """
    Suscripción a webhook para recibir eventos de un canal.
    Incluye firma HMAC para verificación de autenticidad.
    """
    __tablename__ = "webhooks"

    # ── Relación con el canal ─────────────────────────────────────
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Configuración del webhook ─────────────────────────────────
    url: Mapped[str] = mapped_column(Text, nullable=False)
    events: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # ── Seguridad (firma HMAC-SHA256) ─────────────────────────────
    secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # ── Estado ────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Relaciones ────────────────────────────────────────────────
    logs: Mapped[list["WebhookLog"]] = relationship(
        "WebhookLog",
        back_populates="webhook",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
