# agents/responder_agent.py — Agente generador de respuestas
# Produce respuestas contextuales basadas en la intencion y datos del negocio

"""
ResponderAgent genera la respuesta final que se enviara al cliente por WhatsApp.
Usa la intencion clasificada por el RouterAgent para adaptar el tono y contenido.
Carga la configuracion del negocio para personalizar las respuestas.
"""

import logging
import os
import yaml

from api.app.agents.base_agent import BaseAgent, AgentContext, AgentResult
from api.app.agents.prompts import RESPONDER_SYSTEM_PROMPT

logger = logging.getLogger("agentkit")

# Respuestas por defecto cuando no se puede generar con IA
DEFAULT_RESPONSES = {
    "greeting": "Hola! Gracias por escribirnos. En que podemos ayudarte?",
    "farewell": "Gracias por contactarnos! Estamos aqui cuando nos necesites.",
    "spam": None,  # No responder a spam
    "unknown": "Disculpa, no entendi tu mensaje. Podrias reformularlo?",
}

# Instrucciones de tono segun configuracion del negocio
TONE_MAP = {
    "profesional": "Usa un tono profesional y formal. Trata al cliente de 'usted'. Evita coloquialismos.",
    "amigable": "Usa un tono amigable y casual. Tutea al cliente. Se cercano pero respetuoso.",
    "vendedor": "Usa un tono persuasivo orientado a ventas. Destaca beneficios y genera urgencia sin ser agresivo.",
    "empatico": "Usa un tono calido y empatico. Muestra comprension genuina. Prioriza la conexion emocional.",
}


class ResponderAgent(BaseAgent):
    """
    Agente que genera respuestas apropiadas para cada mensaje segun
    su intencion, el contexto del negocio y el historial de conversacion.
    """

    def __init__(self):
        super().__init__(
            name="ResponderAgent",
            description="Genera respuestas contextuales para mensajes de WhatsApp",
        )
        # Cache de configuracion del negocio
        self._business_config: dict | None = None

    def _load_business_config(self) -> dict:
        """
        Carga la configuracion del negocio desde config/business.yaml.
        Retorna un diccionario vacio si el archivo no existe.
        """
        if self._business_config is not None:
            return self._business_config

        # Buscar en varias ubicaciones posibles
        posibles_rutas = [
            "config/business.yaml",
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "business.yaml"),
        ]

        for ruta in posibles_rutas:
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    self._business_config = yaml.safe_load(f) or {}
                    logger.debug(f"[ResponderAgent] Config cargada desde {ruta}")
                    return self._business_config
            except FileNotFoundError:
                continue

        logger.warning("[ResponderAgent] config/business.yaml no encontrado, usando defaults")
        self._business_config = {}
        return self._business_config

    def _build_business_context(self) -> str:
        """Construye el contexto del negocio como texto para el prompt."""
        config = self._load_business_config()
        negocio = config.get("negocio", {})
        agente = config.get("agente", {})

        partes = []

        nombre = negocio.get("nombre")
        if nombre:
            partes.append(f"Negocio: {nombre}")

        descripcion = negocio.get("descripcion")
        if descripcion:
            partes.append(f"Descripcion: {descripcion}")

        horario = negocio.get("horario")
        if horario:
            partes.append(f"Horario de atencion: {horario}")

        nombre_agente = agente.get("nombre")
        if nombre_agente:
            partes.append(f"Tu nombre como asistente: {nombre_agente}")

        casos = agente.get("casos_de_uso", [])
        if casos:
            partes.append(f"Servicios que ofreces: {', '.join(casos)}")

        if not partes:
            return "No hay configuracion de negocio disponible. Responde de forma generica y util."

        return "\n".join(partes)

    def _get_tone_instructions(self) -> str:
        """Obtiene las instrucciones de tono segun la configuracion."""
        config = self._load_business_config()
        tono = config.get("agente", {}).get("tono", "amigable").lower()

        # Buscar en el mapa de tonos, fallback a amigable
        return TONE_MAP.get(tono, TONE_MAP["amigable"])

    async def process(self, context: AgentContext) -> AgentResult:
        """
        Genera una respuesta apropiada para el mensaje del usuario.

        Args:
            context: Contexto con mensaje, intencion ya clasificada e historial

        Returns:
            AgentResult con la respuesta generada
        """
        intent = context.intent or "unknown"

        # Verificar si hay respuesta por defecto para esta intencion
        if intent in DEFAULT_RESPONSES and intent == "spam":
            logger.info(f"[ResponderAgent] Mensaje spam ignorado de {context.phone}")
            return AgentResult(
                response=None,
                intent=intent,
                metadata={"skipped": True, "reason": "spam"},
            )

        # Construir el system prompt personalizado con datos del negocio
        business_context = self._build_business_context()
        tone_instructions = self._get_tone_instructions()

        system_prompt = RESPONDER_SYSTEM_PROMPT.format(
            business_context=business_context,
            tone_instructions=tone_instructions,
        )

        # Construir mensajes incluyendo historial
        messages = []

        # Agregar historial de conversacion
        for msg in context.history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        # Agregar el mensaje actual con metadatos de intencion
        user_content = context.message
        if intent != "unknown":
            # Agregar hint de intencion como contexto interno (no visible al usuario)
            user_content = (
                f"[Intencion detectada: {intent}]\n\n"
                f"Mensaje del cliente:\n{context.message}"
            )

        messages.append({
            "role": "user",
            "content": user_content,
        })

        try:
            respuesta = await self._call_llm(
                system=system_prompt,
                messages=messages,
                max_tokens=1024,
            )

            logger.info(
                f"[ResponderAgent] Respuesta generada para intent '{intent}' "
                f"({len(respuesta)} chars)"
            )

            return AgentResult(
                response=respuesta,
                intent=intent,
                metadata={"response_length": len(respuesta)},
            )

        except Exception as e:
            logger.error(f"[ResponderAgent] Error generando respuesta: {e}")
            # Usar respuesta por defecto segun intencion
            fallback = DEFAULT_RESPONSES.get(
                intent,
                "Lo siento, estoy teniendo problemas tecnicos. Por favor intenta de nuevo en unos minutos.",
            )
            return AgentResult(
                response=fallback,
                intent=intent,
                metadata={"error": str(e), "fallback": True},
            )

    def invalidate_config_cache(self) -> None:
        """Invalida el cache de configuracion para recargar en la proxima llamada."""
        self._business_config = None
        logger.debug("[ResponderAgent] Cache de configuracion invalidado")
