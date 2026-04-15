# api/app/utils/helpers.py — Utilidades generales de la plataforma
# Funciones auxiliares para UUIDs, fechas, sanitizacion y paginacion

from uuid import uuid4
from datetime import datetime, timezone

from sqlalchemy import Select


def generate_uuid() -> str:
    """Genera un UUID v4 como cadena de texto."""
    return str(uuid4())


def now_utc() -> datetime:
    """Retorna la fecha y hora actual en UTC con timezone-aware."""
    return datetime.now(timezone.utc)


def sanitize_phone(phone: str) -> str:
    """
    Normaliza un numero de telefono: solo digitos, sin +, sin espacios, sin guiones.
    Ejemplo: "+52 (55) 1234-5678" -> "5255123456789"
    """
    cleaned = "".join(c for c in phone if c.isdigit())
    return cleaned


def paginate_query(query: Select, page: int, limit: int) -> Select:
    """
    Aplica paginacion a una query de SQLAlchemy.

    Args:
        query: Query de SQLAlchemy (Select statement)
        page: Numero de pagina (1-indexed)
        limit: Cantidad de resultados por pagina

    Returns:
        Query con offset y limit aplicados
    """
    offset = (page - 1) * limit
    return query.offset(offset).limit(limit)


def format_file_size(size_bytes: int) -> str:
    """
    Formatea un tamano en bytes a una cadena legible.
    Ejemplo: 1536000 -> "1.46 MB"
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def truncate_text(text: str, max_length: int = 100) -> str:
    """
    Trunca un texto a la longitud maxima, agregando '...' si se corta.
    Util para logs y previsualizaciones.
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def safe_json_get(data: dict, *keys, default=None):
    """
    Navega de forma segura por un diccionario anidado.
    Ejemplo: safe_json_get(data, "entry", 0, "changes", 0, "value")
    """
    current = data
    for key in keys:
        try:
            if isinstance(current, dict):
                current = current[key]
            elif isinstance(current, (list, tuple)) and isinstance(key, int):
                current = current[key]
            else:
                return default
        except (KeyError, IndexError, TypeError):
            return default
    return current
