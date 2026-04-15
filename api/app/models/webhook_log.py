# api/app/models/webhook_log.py — Registro de entregas de webhooks

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.app.models.base import BaseModel

if TYPE_CHECKING:
    from api.app.models.webhook import Webhook


class WebhookLog(BaseModel):
    """
    Registro de cada intento de entrega de un evento via webhook.
    Permite auditoría y diagnóstico de fallos en entregas.
    """
    __tablename__ = "webhook_logs"

    # ── Relación con el webhook ───────────────────────────────────
    webhook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("webhooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Datos del evento ──────────────────────────────────────────
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # ── Respuesta del servidor destino ────────────────────────────
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Control de reintentos ─────────────────────────────────────
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # ── Timestamp de entrega exitosa ──────────────────────────────
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── Relaciones ────────────────────────────────────────────────
    webhook: Mapped["Webhook"] = relationship(
        "Webhook",
        back_populates="logs",
    )
