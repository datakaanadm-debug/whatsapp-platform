# api/app/models/base.py — Modelo base con campos comunes (UUID, timestamps)

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Clase base declarativa para todos los modelos de la plataforma."""
    pass


class BaseModel(Base):
    """
    Modelo abstracto con campos comunes:
    - id: UUID generado automáticamente
    - created_at: marca de tiempo al crear el registro
    - updated_at: marca de tiempo actualizada en cada modificación
    """
    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def to_dict(self) -> dict:
        """Serializa el modelo a diccionario (excluye relaciones)."""
        from sqlalchemy import inspect as sa_inspect
        result = {}
        mapper = sa_inspect(self.__class__)
        for col_attr in mapper.column_attrs:
            key = col_attr.key
            try:
                val = getattr(self, key, None)
            except Exception:
                continue
            if isinstance(val, uuid.UUID):
                val = str(val)
            elif isinstance(val, datetime):
                val = val.isoformat()
            elif hasattr(val, 'value') and not isinstance(val, (str, int, float, bool, dict, list)):
                val = val.value
            result[key] = val
        return result
