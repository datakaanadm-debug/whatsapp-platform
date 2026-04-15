# worker/app/media_processor.py — Worker de procesamiento de archivos multimedia
# Redimensiona imagenes, genera thumbnails y convierte stickers a WebP

import asyncio
import io
import json
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from PIL import Image

logger = logging.getLogger("platform.worker.media")

# Limites de WhatsApp para imagenes
MAX_IMAGE_DIMENSION = 2048  # Pixeles maximo por lado
THUMBNAIL_SIZE = (150, 150)  # Thumbnail cuadrado
STICKER_SIZE = (512, 512)  # Tamano obligatorio para stickers WebP
JPEG_QUALITY = 85  # Calidad de compresion JPEG
WEBP_QUALITY = 80  # Calidad de compresion WebP


class MediaProcessor:
    """
    Worker que procesa archivos multimedia subidos a la plataforma.

    Operaciones:
        - Redimensionar imagenes que exceden los limites de WhatsApp
        - Generar thumbnails para previsualizacion
        - Convertir stickers al formato WebP 512x512
        - Comprimir imagenes para optimizar ancho de banda
    """

    def __init__(self, redis: aioredis.Redis):
        self.redis = redis
        self._running = False

    async def start(self) -> None:
        """Inicia el loop de procesamiento de media."""
        self._running = True
        logger.info("Media processor iniciado — escuchando 'media:process:queue'")

        while self._running:
            try:
                result = await self.redis.brpop("media:process:queue", timeout=5)
                if result is None:
                    continue

                _, raw_task = result
                if isinstance(raw_task, bytes):
                    raw_task = raw_task.decode("utf-8")

                task = json.loads(raw_task)
                await self._process_task(task)

            except asyncio.CancelledError:
                logger.info("Media processor cancelado")
                break
            except json.JSONDecodeError as e:
                logger.error("Tarea de media con JSON invalido: %s", e)
            except Exception as e:
                logger.error("Error en media processor: %s", e, exc_info=True)
                await asyncio.sleep(1)

    async def stop(self) -> None:
        """Detiene el processor de forma limpia."""
        self._running = False
        logger.info("Media processor detenido")

    async def _process_task(self, task: dict) -> None:
        """
        Procesa una tarea de media segun su tipo.

        Args:
            task: {media_id, channel_id, operation, input_path/input_data, output_path}
        """
        operation = task.get("operation", "")
        media_id = task.get("media_id", "")
        channel_id = task.get("channel_id", "")

        logger.info(
            "Procesando media %s — operacion: %s",
            media_id, operation,
        )

        try:
            if operation == "resize_image":
                result = await self._resize_image(task)
            elif operation == "generate_thumbnail":
                result = await self._generate_thumbnail(task)
            elif operation == "convert_sticker":
                result = await self._convert_sticker(task)
            elif operation == "compress_image":
                result = await self._compress_image(task)
            else:
                logger.warning("Operacion de media desconocida: %s", operation)
                return

            # Publicar resultado
            await self.redis.set(
                f"media:result:{media_id}",
                json.dumps({
                    "media_id": media_id,
                    "channel_id": channel_id,
                    "operation": operation,
                    "success": True,
                    "result": result,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }),
                ex=3600,  # TTL 1 hora
            )

            logger.info("Media %s procesada exitosamente: %s", media_id, operation)

        except Exception as e:
            logger.error(
                "Error procesando media %s (%s): %s",
                media_id, operation, e, exc_info=True,
            )
            # Publicar error
            await self.redis.set(
                f"media:result:{media_id}",
                json.dumps({
                    "media_id": media_id,
                    "channel_id": channel_id,
                    "operation": operation,
                    "success": False,
                    "error": str(e)[:500],
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }),
                ex=3600,
            )

    async def _resize_image(self, task: dict) -> dict:
        """
        Redimensiona una imagen para que no exceda los limites de WhatsApp.
        Mantiene la relacion de aspecto.
        """
        input_data = self._get_input_data(task)
        max_dim = task.get("max_dimension", MAX_IMAGE_DIMENSION)

        img = Image.open(io.BytesIO(input_data))
        original_size = img.size

        # Solo redimensionar si excede el maximo
        if img.width <= max_dim and img.height <= max_dim:
            return {
                "resized": False,
                "original_size": list(original_size),
                "final_size": list(original_size),
                "output_bytes": len(input_data),
            }

        # Calcular nueva dimension manteniendo proporcion
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        # Guardar resultado
        output_buffer = io.BytesIO()
        output_format = self._get_save_format(img)
        save_kwargs = self._get_save_kwargs(output_format)
        img.save(output_buffer, format=output_format, **save_kwargs)
        output_data = output_buffer.getvalue()

        # Almacenar el resultado procesado en Redis
        await self._store_output(task, output_data)

        return {
            "resized": True,
            "original_size": list(original_size),
            "final_size": list(img.size),
            "output_bytes": len(output_data),
        }

    async def _generate_thumbnail(self, task: dict) -> dict:
        """
        Genera un thumbnail cuadrado de 150x150 para previsualizacion.
        Usa crop centrado para mantener proporcion visual.
        """
        input_data = self._get_input_data(task)
        size = task.get("thumbnail_size", THUMBNAIL_SIZE)
        if isinstance(size, list):
            size = tuple(size)

        img = Image.open(io.BytesIO(input_data))

        # Convertir a RGB si tiene canal alpha (para JPEG output)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Crop centrado y resize
        img_ratio = img.width / img.height
        target_ratio = size[0] / size[1]

        if img_ratio > target_ratio:
            # Imagen mas ancha — recortar lados
            new_width = int(img.height * target_ratio)
            left = (img.width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img.height))
        else:
            # Imagen mas alta — recortar arriba/abajo
            new_height = int(img.width / target_ratio)
            top = (img.height - new_height) // 2
            img = img.crop((0, top, img.width, top + new_height))

        img = img.resize(size, Image.Resampling.LANCZOS)

        output_buffer = io.BytesIO()
        img.save(output_buffer, format="JPEG", quality=75, optimize=True)
        output_data = output_buffer.getvalue()

        await self._store_output(task, output_data, suffix="_thumb")

        return {
            "thumbnail_size": list(size),
            "output_bytes": len(output_data),
            "format": "JPEG",
        }

    async def _convert_sticker(self, task: dict) -> dict:
        """
        Convierte una imagen al formato de sticker de WhatsApp: WebP 512x512.
        Mantiene transparencia si la imagen original la tiene.
        """
        input_data = self._get_input_data(task)

        img = Image.open(io.BytesIO(input_data))
        original_size = img.size

        # Mantener canal alpha si existe
        if img.mode not in ("RGBA", "RGB"):
            img = img.convert("RGBA")

        # Redimensionar a 512x512 manteniendo proporcion, con padding transparente
        img.thumbnail(STICKER_SIZE, Image.Resampling.LANCZOS)

        # Crear canvas 512x512 con fondo transparente
        canvas = Image.new("RGBA", STICKER_SIZE, (0, 0, 0, 0))
        # Centrar la imagen en el canvas
        offset_x = (STICKER_SIZE[0] - img.width) // 2
        offset_y = (STICKER_SIZE[1] - img.height) // 2
        canvas.paste(img, (offset_x, offset_y), img if img.mode == "RGBA" else None)

        output_buffer = io.BytesIO()
        canvas.save(
            output_buffer,
            format="WEBP",
            quality=WEBP_QUALITY,
            lossless=False,
        )
        output_data = output_buffer.getvalue()

        # Verificar tamano (stickers no deben exceder 100KB para animated, 500KB para static)
        max_sticker_size = task.get("max_size", 500 * 1024)
        if len(output_data) > max_sticker_size:
            # Recomprimir con menor calidad
            quality = WEBP_QUALITY
            while len(output_data) > max_sticker_size and quality > 20:
                quality -= 10
                output_buffer = io.BytesIO()
                canvas.save(output_buffer, format="WEBP", quality=quality, lossless=False)
                output_data = output_buffer.getvalue()

        await self._store_output(task, output_data, suffix="_sticker")

        return {
            "original_size": list(original_size),
            "sticker_size": list(STICKER_SIZE),
            "output_bytes": len(output_data),
            "format": "WEBP",
        }

    async def _compress_image(self, task: dict) -> dict:
        """Comprime una imagen para reducir su tamano sin cambiar dimensiones."""
        input_data = self._get_input_data(task)
        target_quality = task.get("quality", JPEG_QUALITY)

        img = Image.open(io.BytesIO(input_data))

        # Convertir a RGB para JPEG
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        output_buffer = io.BytesIO()
        img.save(
            output_buffer,
            format="JPEG",
            quality=target_quality,
            optimize=True,
        )
        output_data = output_buffer.getvalue()

        await self._store_output(task, output_data)

        compression_ratio = (1 - len(output_data) / len(input_data)) * 100

        return {
            "original_bytes": len(input_data),
            "output_bytes": len(output_data),
            "compression_ratio": f"{compression_ratio:.1f}%",
            "quality": target_quality,
        }

    # ── Utilidades internas ───────────────────────────────────────

    def _get_input_data(self, task: dict) -> bytes:
        """Obtiene los datos binarios de entrada de la tarea."""
        # Los datos pueden venir como referencia a Redis o como base64
        input_key = task.get("input_key", "")
        if input_key:
            # Lectura sincrona para simplificar — en produccion usar await
            raise NotImplementedError("Lectura desde Redis key pendiente de implementar con async")

        import base64
        input_b64 = task.get("input_data", "")
        if input_b64:
            return base64.b64decode(input_b64)

        input_path = task.get("input_path", "")
        if input_path:
            with open(input_path, "rb") as f:
                return f.read()

        raise ValueError("No se proporcionaron datos de entrada (input_key, input_data o input_path)")

    async def _store_output(
        self, task: dict, data: bytes, suffix: str = ""
    ) -> None:
        """Almacena el resultado procesado en Redis temporalmente."""
        media_id = task.get("media_id", "")
        output_key = f"media:processed:{media_id}{suffix}"
        await self.redis.set(output_key, data, ex=3600)  # TTL 1 hora

    @staticmethod
    def _get_save_format(img: Image.Image) -> str:
        """Determina el formato de guardado apropiado."""
        if img.mode == "RGBA":
            return "PNG"
        return "JPEG"

    @staticmethod
    def _get_save_kwargs(fmt: str) -> dict:
        """Retorna parametros de guardado segun el formato."""
        if fmt == "JPEG":
            return {"quality": JPEG_QUALITY, "optimize": True}
        elif fmt == "PNG":
            return {"optimize": True}
        elif fmt == "WEBP":
            return {"quality": WEBP_QUALITY}
        return {}
