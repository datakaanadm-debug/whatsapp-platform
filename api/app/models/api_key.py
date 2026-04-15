# api/app/models/api_key.py — Modelo de API Keys para autenticación

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from api.app.models.base import BaseModel


class ApiKey(BaseModel):
    """
    Representa una API Key para autenticación de requests.
    Si channel_id es NULL, es una key de administrador con acceso global.
    Se almacena el hash de la key, nunca el valor en texto plano.
    """
    __tablename__ = "api_keys"

    # ── Relación con canal (NULL = key de administrador) ──────────
    channel_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # ── Datos de la key ───────────────────────────────────────────
    key_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    prefix: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
    )

    # ── Metadatos ─────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)

    # ── Estado ────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
