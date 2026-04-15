# api/app/models/media.py — Modelo de archivos multimedia

import uuid
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from api.app.models.base import BaseModel


class Media(BaseModel):
    """
    Representa un archivo multimedia (imagen, video, audio, documento)
    asociado a un mensaje. Almacena referencia al storage (S3 o local).
    """
    __tablename__ = "media"

    # ── Relación con el canal ─────────────────────────────────────
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Relación con el mensaje (nullable: media puede existir sin mensaje) ──
    message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Identificador de WhatsApp para descarga ───────────────────
    media_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # ── Datos del archivo ─────────────────────────────────────────
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(127), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # ── Ubicación en storage ──────────────────────────────────────
    storage_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Hash de verificación de integridad ────────────────────────
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
