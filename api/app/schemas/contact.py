# api/app/schemas/contact.py — Esquemas para contactos de WhatsApp

import uuid
from typing import Optional
from pydantic import BaseModel, Field


class ContactResponse(BaseModel):
    """Datos públicos de un contacto."""

    id: uuid.UUID
    contact_id_wa: str = Field(description="ID de WhatsApp del contacto")
    phone_number: str
    name: Optional[str] = None
    push_name: Optional[str] = Field(None, description="Nombre configurado por el usuario en WhatsApp")
    profile_pic_url: Optional[str] = None
    is_business: bool = False

    model_config = {"from_attributes": True}


class ContactList(BaseModel):
    """Listado de contactos con total."""

    contacts: list[ContactResponse]
    total: int


class ContactCheck(BaseModel):
    """Solicitud para verificar si números de teléfono tienen WhatsApp."""

    phones: list[str] = Field(
        ..., min_length=1, max_length=100,
        description="Lista de números con código de país (ej: ['5215512345678'])",
    )


class ContactCheckResult(BaseModel):
    """Resultado de la verificación de un número individual."""

    phone: str
    exists: bool = Field(description="True si el número está registrado en WhatsApp")
    wa_id: Optional[str] = Field(None, description="ID de WhatsApp (presente solo si exists=True)")
