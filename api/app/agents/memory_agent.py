# agents/memory_agent.py — Agente de memoria y gestion de contexto
# Maneja el historial de conversaciones, resumenes y almacenamiento en Redis

"""
MemoryAgent gestiona la memoria de corto y largo plazo del sistema.
Usa Redis para almacenamiento rapido de contexto por numero de telefono
y el LLM para resumir historiales largos y extraer entidades.
"""

import json
import logging
from typing import Any

from api.app.agents.base_agent import BaseAgent, AgentContext, AgentResult
from api.app.agents.prompts import MEMORY_SYSTEM_PROMPT

logger = logging.getLogger("agentkit")

# Prefijos para keys de Redis
REDIS_PREFIX_CONTEXT = "agentkit:context:"
REDIS_PREFIX_SUMMARY = "agentkit:summary:"
REDIS_PREFIX_ENTITIES = "agentkit:entities:"

# TTL por defecto para datos en Redis (24 horas)
DEFAULT_TTL_SECONDS = 86400


class MemoryAgent(BaseAgent):
    """
    Agente especializado en gestion de memoria conversacional.
    Maneja resumenes, extraccion de entidades y almacenamiento en Redis.
    """

    def __init__(self):
        super().__init__(
            name="MemoryAgent",
            description="Gestiona memoria conversacional y contexto en Redis",
        )

    async def process(self, context: AgentContext) -> AgentResult:
        """
        Procesa el contexto para extraer entidades del mensaje actual.

        Args:
            context: Contexto con el mensaje a analizar

        Returns:
            AgentResult con entidades extraidas en context_updates
        """
        entities = await self.extract_entities(context.message)
        return AgentResult(
            context_updates={"entities": entities},
            metadata={"entities_found": len(entities)},
        )

    async def summarize_history(self, history: list[dict]) -> str:
        """
        Resume un historial de conversacion largo en un parrafo conciso.
        Util para comprimir conversaciones que exceden la ventana de contexto.

        Args:
            history: Lista de mensajes [{role, content}]

        Returns:
            Resumen en texto plano de la conversacion
        """
        if not history:
            return ""

        # Si el historial es muy corto, no necesita resumen
        if len(history) <= 3:
            return " | ".join(
                f"{'Cliente' if m['role'] == 'user' else 'Agente'}: {m['content'][:100]}"
                for m in history
            )

        # Formatear historial para el LLM
        formatted = "\n".join(
            f"{'Cliente' if m['role'] == 'user' else 'Agente'}: {m['content']}"
            for m in history
        )

        messages = [
            {
                "role": "user",
                "content": (
                    "Resume la siguiente conversacion de forma concisa. "
                    "Captura los puntos clave, decisiones y datos del cliente.\n\n"
                    f"Conversacion:\n{formatted}"
                ),
            }
        ]

        try:
            resumen = await self._call_llm(
                system=MEMORY_SYSTEM_PROMPT,
                messages=messages,
                max_tokens=300,
            )
            logger.debug(
                f"[MemoryAgent] Historial de {len(history)} msgs resumido a {len(resumen)} chars"
            )
            return resumen

        except Exception as e:
            logger.error(f"[MemoryAgent] Error resumiendo historial: {e}")
            # Fallback: retornar los ultimos mensajes como resumen basico
            ultimos = history[-3:]
            return " | ".join(
                f"{'Cliente' if m['role'] == 'user' else 'Agente'}: {m['content'][:80]}"
                for m in ultimos
            )

    async def extract_entities(self, message: str) -> dict:
        """
        Extrae entidades nombradas de un mensaje usando el LLM.
        Identifica nombres, fechas, productos, emails, direcciones, etc.

        Args:
            message: Texto del mensaje a analizar

        Returns:
            Diccionario con las entidades encontradas
        """
        if not message or len(message.strip()) < 3:
            return {}

        messages = [
            {
                "role": "user",
                "content": (
                    "Extrae las entidades del siguiente mensaje. "
                    "Responde SOLO con JSON valido.\n\n"
                    f"Mensaje:\n{message}"
                ),
            }
        ]

        try:
            raw = await self._call_llm(
                system=MEMORY_SYSTEM_PROMPT,
                messages=messages,
                max_tokens=256,
            )

            # Parsear JSON de la respuesta
            parsed = self._parse_json_safe(raw)
            entities = parsed.get("entities", parsed)

            # Filtrar valores vacios o nulos
            entities = {
                k: v for k, v in entities.items()
                if v is not None and str(v).strip()
            }

            logger.debug(f"[MemoryAgent] Entidades extraidas: {list(entities.keys())}")
            return entities

        except Exception as e:
            logger.error(f"[MemoryAgent] Error extrayendo entidades: {e}")
            return {}

    async def get_relevant_context(
        self,
        redis: Any,
        channel_id: str,
        phone: str,
    ) -> dict:
        """
        Recupera el contexto almacenado en Redis para un telefono.
        Incluye resumen previo, entidades conocidas y metadata.

        Args:
            redis: Instancia de conexion Redis (aioredis)
            channel_id: ID del canal de WhatsApp
            phone: Numero de telefono del contacto

        Returns:
            Diccionario con el contexto almacenado, vacio si no existe
        """
        context_key = f"{REDIS_PREFIX_CONTEXT}{channel_id}:{phone}"
        summary_key = f"{REDIS_PREFIX_SUMMARY}{channel_id}:{phone}"
        entities_key = f"{REDIS_PREFIX_ENTITIES}{channel_id}:{phone}"

        result = {
            "summary": "",
            "entities": {},
            "metadata": {},
        }

        try:
            # Obtener contexto general (hash de Redis)
            context_data = await redis.hgetall(context_key)
            if context_data:
                # Redis retorna bytes, decodificar
                result["metadata"] = {
                    k.decode("utf-8") if isinstance(k, bytes) else k:
                    v.decode("utf-8") if isinstance(v, bytes) else v
                    for k, v in context_data.items()
                }

            # Obtener resumen previo
            summary = await redis.get(summary_key)
            if summary:
                result["summary"] = (
                    summary.decode("utf-8") if isinstance(summary, bytes) else summary
                )

            # Obtener entidades conocidas
            entities_raw = await redis.get(entities_key)
            if entities_raw:
                decoded = (
                    entities_raw.decode("utf-8")
                    if isinstance(entities_raw, bytes)
                    else entities_raw
                )
                result["entities"] = json.loads(decoded)

            logger.debug(
                f"[MemoryAgent] Contexto recuperado para {phone}: "
                f"summary={bool(result['summary'])}, "
                f"entities={len(result['entities'])}"
            )

        except Exception as e:
            logger.error(f"[MemoryAgent] Error recuperando contexto de Redis: {e}")

        return result

    async def store_context(
        self,
        redis: Any,
        channel_id: str,
        phone: str,
        context: dict,
        ttl: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        """
        Almacena contexto actualizado en Redis con TTL.

        Args:
            redis: Instancia de conexion Redis (aioredis)
            channel_id: ID del canal de WhatsApp
            phone: Numero de telefono del contacto
            context: Diccionario con datos a almacenar
            ttl: Tiempo de vida en segundos (default: 24 horas)
        """
        context_key = f"{REDIS_PREFIX_CONTEXT}{channel_id}:{phone}"
        summary_key = f"{REDIS_PREFIX_SUMMARY}{channel_id}:{phone}"
        entities_key = f"{REDIS_PREFIX_ENTITIES}{channel_id}:{phone}"

        try:
            # Almacenar metadata como hash de Redis
            metadata = context.get("metadata", {})
            if metadata:
                # Convertir todos los valores a string para Redis hash
                hash_data = {
                    str(k): str(v) for k, v in metadata.items()
                }
                if hash_data:
                    await redis.hset(context_key, mapping=hash_data)
                    await redis.expire(context_key, ttl)

            # Almacenar resumen si existe
            summary = context.get("summary")
            if summary:
                await redis.set(summary_key, summary, ex=ttl)

            # Almacenar entidades como JSON
            entities = context.get("entities", {})
            if entities:
                # Merge con entidades existentes
                existing_raw = await redis.get(entities_key)
                if existing_raw:
                    decoded = (
                        existing_raw.decode("utf-8")
                        if isinstance(existing_raw, bytes)
                        else existing_raw
                    )
                    existing = json.loads(decoded)
                    existing.update(entities)
                    entities = existing

                await redis.set(entities_key, json.dumps(entities, ensure_ascii=False), ex=ttl)

            logger.debug(f"[MemoryAgent] Contexto almacenado para {phone} (TTL: {ttl}s)")

        except Exception as e:
            logger.error(f"[MemoryAgent] Error almacenando contexto en Redis: {e}")

    async def manage_window(
        self,
        history: list[dict],
        max_messages: int = 20,
    ) -> list[dict]:
        """
        Gestiona la ventana de contexto del historial.
        Si el historial excede max_messages, resume los mensajes antiguos
        y los reemplaza con un resumen, manteniendo los recientes intactos.

        Args:
            history: Historial completo de la conversacion
            max_messages: Numero maximo de mensajes a mantener

        Returns:
            Historial ajustado con resumen de mensajes antiguos si aplica
        """
        if not history or len(history) <= max_messages:
            return history

        # Dividir: mensajes antiguos (a resumir) y recientes (a mantener)
        punto_corte = len(history) - max_messages
        mensajes_antiguos = history[:punto_corte]
        mensajes_recientes = history[punto_corte:]

        # Resumir los mensajes antiguos
        resumen = await self.summarize_history(mensajes_antiguos)

        # Construir historial con resumen al inicio
        historial_ajustado = [
            {
                "role": "user",
                "content": f"[Resumen de conversacion anterior: {resumen}]",
            },
            {
                "role": "assistant",
                "content": "Entendido, tengo el contexto de nuestra conversacion anterior.",
            },
        ]
        historial_ajustado.extend(mensajes_recientes)

        logger.info(
            f"[MemoryAgent] Historial comprimido: {len(history)} → {len(historial_ajustado)} msgs"
        )

        return historial_ajustado

    def _parse_json_safe(self, raw: str) -> dict:
        """
        Parsea JSON de forma segura desde una respuesta del LLM.

        Args:
            raw: Texto crudo que deberia contener JSON

        Returns:
            Diccionario parseado, vacio si falla
        """
        cleaned = raw.strip()

        # Remover backticks de markdown
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            json_lines = []
            inside = False
            for line in lines:
                if line.strip().startswith("```") and not inside:
                    inside = True
                    continue
                elif line.strip().startswith("```") and inside:
                    break
                elif inside:
                    json_lines.append(line)
            cleaned = "\n".join(json_lines).strip()

        # Buscar JSON en el texto
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start != -1 and end > start:
            cleaned = cleaned[start:end]

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"[MemoryAgent] JSON parse fallido: {raw[:150]}")
            return {}
