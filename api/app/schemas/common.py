# api/app/schemas/common.py — Esquemas compartidos: paginación, respuestas genéricas, errores

import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse


class PaginationParams(BaseModel):
    """Parámetros de paginación reutilizables en cualquier listado."""

    page: int = Field(default=1, ge=1, description="Número de página (comienza en 1)")
    limit: int = Field(default=50, ge=1, le=500, description="Elementos por página (máx 500)")

    @property
    def offset(self) -> int:
        """Calcula el offset SQL a partir de page y limit."""
        return (self.page - 1) * self.limit


class ApiResponse(BaseModel):
    """Envoltorio estándar para respuestas exitosas de la API."""

    success: bool = True
    data: Any = None
    error: Optional[str] = None


def api_response(data: Any = None, success: bool = True, error: str = None, status_code: int = 200) -> JSONResponse:
    """
    Helper que serializa la respuesta automáticamente como JSONResponse.
    Convierte objetos SQLAlchemy a dicts antes de devolver.
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "success": success,
            "data": _serialize(data),
            "error": error,
        },
    )


def _serialize(obj: Any) -> Any:
    """Convierte objetos SQLAlchemy a dicts recursivamente."""
    if hasattr(obj, 'to_dict'):
        return obj.to_dict()
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, 'value'):  # Enums
        return obj.value
    return obj


class ErrorResponse(BaseModel):
    """Estructura de error devuelta al cliente cuando algo falla."""

    detail: str = Field(..., description="Descripción legible del error")
    code: str = Field(..., description="Código interno del error (ej: 'CHANNEL_NOT_FOUND')")
