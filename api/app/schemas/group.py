# api/app/schemas/group.py — Esquemas para gestión de grupos de WhatsApp

import uuid
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


class GroupCreate(BaseModel):
    """Datos para crear un grupo nuevo."""

    name: str = Field(..., min_length=1, max_length=100, description="Nombre del grupo")
    participants: list[str] = Field(
        ..., min_length=1,
        description="Lista de números (con código de país) a agregar al grupo",
    )


class GroupUpdate(BaseModel):
    """Campos actualizables de un grupo."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=2048)


class GroupParticipant(BaseModel):
    """Participante de un grupo con su rol."""

    phone: str
    is_admin: bool = False


class GroupResponse(BaseModel):
    """Representación pública de un grupo."""

    id: uuid.UUID
    group_id_wa: str = Field(description="ID de WhatsApp del grupo (ej: '120363xxx@g.us')")
    name: str
    description: Optional[str] = None
    owner: Optional[str] = Field(None, description="Número del creador del grupo")
    participants: list[GroupParticipant] = []
    invite_link: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class GroupParticipantAction(BaseModel):
    """Acción sobre participantes de un grupo."""

    action: Literal["add", "remove", "promote", "demote"] = Field(
        ..., description="Operación a ejecutar sobre los participantes"
    )
    participants: list[str] = Field(
        ..., min_length=1,
        description="Números de teléfono sobre los que se ejecuta la acción",
    )
