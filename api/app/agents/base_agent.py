# agents/base_agent.py — Clase base para todos los agentes de IA del sistema
# Cada agente especializado hereda de BaseAgent y sobreescribe process()

"""
Define las estructuras de datos comunes (AgentContext, AgentResult) y la clase
base que proporciona la conexion con Claude API a todos los agentes del pipeline.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from anthropic import AsyncAnthropic

logger = logging.getLogger("agentkit")


@dataclass
class AgentContext:
    """Contexto que recibe cada agente para procesar un mensaje entrante."""
    channel_id: str          # ID del canal de WhatsApp
    phone: str               # Numero de telefono del remitente
    message: str             # Texto del mensaje actual
    history: list[dict] = field(default_factory=list)    # Historial de la conversacion
    intent: str | None = None                            # Intencion clasificada (la llena el router)
    metadata: dict = field(default_factory=dict)         # Datos adicionales (config del canal, etc.)


@dataclass
class AgentResult:
    """Resultado que retorna cada agente despues de procesar."""
    response: str | None = None              # Texto de respuesta generado
    intent: str | None = None                # Intencion detectada
    confidence: float = 0.0                  # Nivel de confianza (0.0 a 1.0)
    actions: list[dict] = field(default_factory=list)         # Acciones a ejecutar
    context_updates: dict = field(default_factory=dict)       # Actualizaciones al contexto compartido
    metadata: dict = field(default_factory=dict)              # Datos adicionales del procesamiento


class BaseAgent:
    """
    Clase base para agentes de IA. Provee la conexion con Claude API
    y el metodo _call_llm que todos los agentes especializados usan.
    """

    def __init__(self, name: str, description: str, model: str = "claude-sonnet-4-6"):
        self.name = name
        self.description = description
        self.model = model
        self.client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    async def process(self, context: AgentContext) -> AgentResult:
        """
        Metodo principal que cada agente debe implementar.
        Recibe el contexto y retorna un resultado estructurado.
        """
        raise NotImplementedError(
            f"El agente '{self.name}' debe implementar el metodo process()"
        )

    async def _call_llm(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> str:
        """
        Llama al LLM con el system prompt y mensajes dados.
        Centraliza el manejo de errores y logging de la API.

        Args:
            system: System prompt para la llamada
            messages: Lista de mensajes [{role, content}]
            max_tokens: Limite de tokens en la respuesta

        Returns:
            Texto de la respuesta del modelo

        Raises:
            Exception: Si la llamada a la API falla
        """
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            texto = response.content[0].text
            logger.debug(
                f"[{self.name}] LLM call OK — "
                f"{response.usage.input_tokens} in / {response.usage.output_tokens} out"
            )
            return texto

        except Exception as e:
            logger.error(f"[{self.name}] Error en llamada LLM: {e}")
            raise
