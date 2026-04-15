# agents/router_agent.py — Agente clasificador de intenciones
# Analiza cada mensaje entrante y determina su intencion para el pipeline

"""
RouterAgent clasifica mensajes de WhatsApp en intenciones predefinidas.
Es el primer agente del pipeline y determina como se procesara el mensaje.
Usa un prompt ligero para clasificacion rapida con respuesta en JSON.
"""

import json
import logging

from api.app.agents.base_agent import BaseAgent, AgentContext, AgentResult
from api.app.agents.prompts import ROUTER_SYSTEM_PROMPT

logger = logging.getLogger("agentkit")

# Intenciones validas que el router puede asignar
VALID_INTENTS = {
    "sales", "support", "faq", "greeting", "farewell",
    "complaint", "appointment", "order", "spam",
    "human_handoff", "unknown",
}


class RouterAgent(BaseAgent):
    """
    Agente clasificador de intenciones. Recibe un mensaje y retorna
    la intencion detectada con su nivel de confianza.
    """

    def __init__(self):
        super().__init__(
            name="RouterAgent",
            description="Clasifica la intencion de mensajes de WhatsApp",
        )

    async def process(self, context: AgentContext) -> AgentResult:
        """
        Clasifica el mensaje del usuario en una intencion.

        Args:
            context: Contexto con el mensaje a clasificar y opcionalmente historial

        Returns:
            AgentResult con intent y confidence establecidos
        """
        # Construir mensajes para la API — incluir historial resumido si existe
        messages = []

        # Si hay historial, agregarlo como contexto para mejor clasificacion
        if context.history:
            # Tomar solo los ultimos 4 mensajes para no sobrecargar al router
            historial_reciente = context.history[-4:]
            resumen = "\n".join(
                f"{'Cliente' if m['role'] == 'user' else 'Agente'}: {m['content']}"
                for m in historial_reciente
            )
            messages.append({
                "role": "user",
                "content": (
                    f"Contexto de la conversacion reciente:\n{resumen}\n\n"
                    f"Nuevo mensaje del cliente a clasificar:\n{context.message}"
                ),
            })
        else:
            messages.append({
                "role": "user",
                "content": f"Mensaje del cliente a clasificar:\n{context.message}",
            })

        try:
            # Llamada al LLM con tokens limitados (la respuesta es corta)
            raw_response = await self._call_llm(
                system=ROUTER_SYSTEM_PROMPT,
                messages=messages,
                max_tokens=256,
            )

            # Parsear la respuesta JSON del modelo
            parsed = self._parse_response(raw_response)

            logger.info(
                f"[RouterAgent] Intent: {parsed['intent']} "
                f"(confidence: {parsed['confidence']:.2f}) — "
                f"Razon: {parsed['reasoning']}"
            )

            return AgentResult(
                intent=parsed["intent"],
                confidence=parsed["confidence"],
                metadata={"reasoning": parsed["reasoning"]},
            )

        except Exception as e:
            logger.error(f"[RouterAgent] Error clasificando mensaje: {e}")
            # Fallback seguro: intencion desconocida con confianza baja
            return AgentResult(
                intent="unknown",
                confidence=0.0,
                metadata={"error": str(e)},
            )

    def _parse_response(self, raw: str) -> dict:
        """
        Parsea la respuesta JSON del LLM con manejo robusto de errores.

        Args:
            raw: Texto crudo de la respuesta del modelo

        Returns:
            Diccionario con intent, confidence y reasoning
        """
        # Limpiar la respuesta — a veces el LLM agrega backticks o texto extra
        cleaned = raw.strip()

        # Remover bloques de codigo markdown si existen
        if cleaned.startswith("```"):
            # Extraer contenido entre los backticks
            lines = cleaned.split("\n")
            json_lines = []
            inside_block = False
            for line in lines:
                if line.strip().startswith("```") and not inside_block:
                    inside_block = True
                    continue
                elif line.strip().startswith("```") and inside_block:
                    break
                elif inside_block:
                    json_lines.append(line)
            cleaned = "\n".join(json_lines).strip()

        # Intentar encontrar JSON en la respuesta
        # A veces el modelo escribe texto antes o despues del JSON
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}") + 1
        if start_idx != -1 and end_idx > start_idx:
            cleaned = cleaned[start_idx:end_idx]

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"[RouterAgent] No se pudo parsear JSON: {raw[:200]}")
            return {
                "intent": "unknown",
                "confidence": 0.0,
                "reasoning": "Error parseando respuesta del clasificador",
            }

        # Validar y normalizar campos
        intent = data.get("intent", "unknown").lower().strip()
        if intent not in VALID_INTENTS:
            logger.warning(f"[RouterAgent] Intent invalido '{intent}', usando 'unknown'")
            intent = "unknown"

        confidence = data.get("confidence", 0.0)
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(1.0, confidence))  # Clamp entre 0 y 1
        except (TypeError, ValueError):
            confidence = 0.0

        reasoning = data.get("reasoning", "Sin razonamiento proporcionado")

        return {
            "intent": intent,
            "confidence": confidence,
            "reasoning": reasoning,
        }
