# api/app/services/media_service.py — Servicio de gestión de archivos multimedia
# Upload, descarga, almacenamiento local y conversión de formatos

import base64
import hashlib
import logging
import mimetypes
import os
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.models.media import Media

logger = logging.getLogger("agentkit")

# Directorio base para almacenamiento de media
MEDIA_STORAGE_PATH = os.getenv("MEDIA_STORAGE_PATH", "./storage/media")


class MediaService:
    """Servicio para gestionar archivos multimedia."""

    # ── Utilidades internas ──────────────────────────────────────

    @staticmethod
    def _ensure_channel_dir(channel_id: UUID) -> str:
        """Crea el directorio de almacenamiento del canal si no existe."""
        channel_dir = os.path.join(MEDIA_STORAGE_PATH, str(channel_id))
        os.makedirs(channel_dir, exist_ok=True)
        return channel_dir

    @staticmethod
    def _calculate_sha256(data: bytes) -> str:
        """Calcula el hash SHA256 de los datos."""
        return hashlib.sha256(data).hexdigest()

    # ── Upload de archivos ───────────────────────────────────────

    @staticmethod
    async def upload_media(
        db: AsyncSession,
        channel_id: UUID,
        file_data: bytes,
        filename: str,
        mime_type: str,
    ) -> Media:
        """
        Sube un archivo multimedia al almacenamiento local.
        Guarda el archivo en MEDIA_STORAGE_PATH/{channel_id}/{uuid}_{filename}.
        """
        channel_dir = MediaService._ensure_channel_dir(channel_id)

        # Generar nombre único para evitar colisiones
        media_id = uuid4()
        safe_filename = f"{media_id}_{filename}"
        storage_path = os.path.join(channel_dir, safe_filename)

        # Escribir archivo al disco
        with open(storage_path, "wb") as f:
            f.write(file_data)

        # Calcular hash y tamaño
        sha256 = MediaService._calculate_sha256(file_data)
        file_size = len(file_data)

        # Crear registro en BD
        media = Media(
            id=media_id,
            channel_id=channel_id,
            file_name=filename,
            mime_type=mime_type,
            file_size=file_size,
            storage_path=storage_path,
            sha256=sha256,
        )
        db.add(media)
        await db.flush()

        logger.info(
            f"Media subida: {media_id} — {filename} ({file_size} bytes)"
        )
        return media

    # ── Consulta de archivos ─────────────────────────────────────

    @staticmethod
    async def get_media_list(
        db: AsyncSession, channel_id: UUID
    ) -> list[Media]:
        """Obtiene todos los archivos multimedia de un canal."""
        query = (
            select(Media)
            .where(Media.channel_id == channel_id)
            .order_by(Media.created_at.desc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_media(db: AsyncSession, media_id: UUID) -> Media | None:
        """Obtiene un registro de media por su ID."""
        query = select(Media).where(Media.id == media_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    # ── Descarga de archivos ─────────────────────────────────────

    @staticmethod
    async def download_media(
        db: AsyncSession, media_id: UUID
    ) -> tuple[bytes, str, str]:
        """
        Descarga un archivo multimedia.
        Retorna: (datos_binarios, nombre_archivo, mime_type)
        Lanza FileNotFoundError si el archivo no existe en disco.
        """
        media = await MediaService.get_media(db, media_id)
        if not media:
            raise FileNotFoundError(f"Registro de media no encontrado: {media_id}")

        if not media.storage_path or not os.path.exists(media.storage_path):
            raise FileNotFoundError(
                f"Archivo no encontrado en disco: {media.storage_path}"
            )

        with open(media.storage_path, "rb") as f:
            data = f.read()

        return (
            data,
            media.file_name or "file",
            media.mime_type or "application/octet-stream",
        )

    # ── Eliminación de archivos ──────────────────────────────────

    @staticmethod
    async def delete_media(db: AsyncSession, media_id: UUID) -> bool:
        """Elimina un archivo multimedia: borra del disco y de la BD."""
        media = await MediaService.get_media(db, media_id)
        if not media:
            return False

        # Eliminar archivo del disco si existe
        if media.storage_path and os.path.exists(media.storage_path):
            try:
                os.remove(media.storage_path)
            except OSError as e:
                logger.warning(
                    f"No se pudo eliminar archivo del disco: {media.storage_path} — {e}"
                )

        # Eliminar registro de la BD
        await db.delete(media)
        await db.flush()

        logger.info(f"Media eliminada: {media_id}")
        return True

    # ── Guardado desde URL ───────────────────────────────────────

    @staticmethod
    async def save_from_url(
        db: AsyncSession, channel_id: UUID, url: str
    ) -> Media:
        """
        Descarga un archivo desde una URL y lo guarda en almacenamiento local.
        """
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(url)
            response.raise_for_status()
            file_data = response.content

        # Determinar nombre de archivo y tipo MIME
        # Intentar extraer del URL o del header Content-Type
        content_type = response.headers.get("content-type", "application/octet-stream")
        mime_type = content_type.split(";")[0].strip()

        # Extraer nombre del URL
        url_path = url.split("?")[0].split("#")[0]
        filename = url_path.split("/")[-1] if "/" in url_path else "downloaded_file"

        # Si no tiene extensión, intentar deducirla del MIME type
        if "." not in filename:
            ext = mimetypes.guess_extension(mime_type) or ""
            filename = f"{filename}{ext}"

        return await MediaService.upload_media(
            db, channel_id, file_data, filename, mime_type
        )

    # ── Guardado desde Base64 ────────────────────────────────────

    @staticmethod
    async def save_from_base64(
        db: AsyncSession,
        channel_id: UUID,
        data_b64: str,
        mime_type: str,
        filename: str = None,
    ) -> Media:
        """
        Decodifica datos Base64 y los guarda como archivo multimedia.
        """
        # Limpiar posible prefijo data URI (data:image/png;base64,...)
        if "," in data_b64:
            data_b64 = data_b64.split(",", 1)[1]

        file_data = base64.b64decode(data_b64)

        # Generar nombre si no se proporciona
        if not filename:
            ext = mimetypes.guess_extension(mime_type) or ".bin"
            filename = f"media_{uuid4().hex[:8]}{ext}"

        return await MediaService.upload_media(
            db, channel_id, file_data, filename, mime_type
        )
