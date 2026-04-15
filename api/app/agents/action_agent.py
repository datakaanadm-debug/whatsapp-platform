# agents/action_agent.py — Agente determinador de acciones automatizadas
# Analiza la respuesta y la intencion para ejecutar acciones del sistema

"""
ActionAgent decide que acciones automatizadas deben ejecutarse despues de
procesar un mensaje. Acciones incluyen: followups, escalaciones, etiquetado,
envio de medios y actualizaciones de CRM.
"""

import json
import logging

from api.app.agents.base_agent import BaseAgent, AgentContext, AgentResult
from api.app.agents.prompts import ACTION_SYSTEM_PROMPT

logger = logging.getLogger("agentkit")

# Tipos de acciones validas que el sistema puede ejecutar
VALID_ACTION_TYPES = {
    "send_message",
    "send_media",
    "schedule_followup",
    "escalate_human",
    "tag_contact",
    "update_crm",
}

# Umbral minimo de confianza para ejecutar acciones
CONFIDENCE_THRESHOLD = 0.7


class ActionAgent(BaseAgent):
    """
    Agente que determina acciones automatizadas basadas en el contexto
    de la conversacion, la intencion y la respuesta generada.
    """

    def __init__(self):
        super().__init__(
            name="ActionAgent",
            description="Determina acciones automatizadas post-respuesta",
        )

    async def process(self, context: AgentContext) -> AgentResult:
        """
        Analiza el contexto completo para determinar acciones necesarias.

        Args:
            context: Contexto con mensaje, intencion, y metadata que incluye
                     la respuesta generada y la confianza del router

        Returns:
            AgentResult con lista de acciones a ejecutar
        """
        intent = context.intent or "unknown"
        confidence = context.metadata.get("confidence", 0.0)
        response_text = context.metadata.get("response", "")

        # Si la confianza es baja, no ejecutar acciones automaticas
        if confidence < CONFIDENCE_THRESHOLD:
            logger.info(
                f"[ActionAgent] Confianza insuficiente ({confidence:.2f} < {CONFIDENCE_THRESHOLD}), "
                f"sin acciones automaticas"
            )
            return AgentResult(
                actions=[],
                metadata={"skipped": True, "reason": "low_confidence"},
            )

        # Construir el prompt con contexto especifico
        system_prompt = ACTION_SYSTEM_PROMPT.format(
            intent=intent,
            confidence=confidence,
            response_preview=response_text[:300] if response_text else "Sin respuesta",
        )

        # Construir el mensaje para el LLM con todo el contexto
        contexto_completo = self._build_context_summary(context, response_text)

        messages = [
            {
                "role": "user",
                "content": contexto_completo,
            }
        ]

        try:
            raw_response = await self._call_llm(
                system=system_prompt,
                messages=messages,
                max_tokens=512,
            )

            # Parsear y validar acciones
            actions = self._parse_actions(raw_response)

            if actions:
                logger.info(
                    f"[ActionAgent] {len(actions)} acciones determinadas: "
                    f"{[a['type'] for a in actions]}"
                )
            else:
                logger.debug("[ActionAgent] Sin acciones necesarias")

            return AgentResult(
                actions=actions,
                intent=intent,
                metadata={"raw_actions_count": len(actions)},
            )

        except Exception as e:
            logger.error(f"[ActionAgent] Error determinando acciones: {e}")
            return AgentResult(
                actions=[],
                metadata={"error": str(e)},
            )

    def _build_context_summary(self, context: AgentContext, response_text: str) -> str:
        """
        Construye un resumen del contexto para que el LLM tome decisiones.

        Args:
            context: Contexto del agente
            response_text: Respuesta generada por el ResponderAgent

        Returns:
            Texto formateado con el contexto completo
        """
        partes = [
            f"Canal: {context.channel_id}",
            f"Telefono del cliente: {context.phone}",
            f"Intencion detectada: {context.intent or 'unknown'}",
            f"Mensaje del cliente: {context.message}",
        ]

        if response_text:
            partes.append(f"Respuesta generada por el agente: {response_text[:500]}")

        # Incluir ultimos mensajes del historial para contexto
        if context.history:
            ultimos = context.history[-4:]
            hist_text = "\n".join(
                f"  {'Cliente' if m['role'] == 'user' else 'Agente'}: {m['content'][:100]}"
                for m in ultimos
            )
            partes.append(f"Ultimos mensajes:\n{hist_text}")

        # Incluir entidades conocidas si estan en metadata
        entities = context.metadata.get("entities", {})
        if entities:
            ent_text = ", ".join(f"{k}={v}" for k, v in entities.items())
            partes.append(f"Entidades conocidas del cliente: {ent_text}")

        return "\n\n".join(partes)

    def _parse_actions(self, raw: str) -> list[dict]:
        """
        Parsea y valida la lista de acciones del JSON retornado por el LLM.

        Args:
            raw: Texto crudo de la respuesta del modelo

        Returns:
            Lista de acciones validadas, cada una con type y params
        """
        # Limpiar respuesta
        cleaned = raw.strip()

        # Remover backticks markdown
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

        # Encontrar JSON en el texto
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start == -1 or end <= start:
            logger.warning(f"[ActionAgent] No se encontro JSON en respuesta: {raw[:150]}")
            return []

        cleaned = cleaned[start:end]

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"[ActionAgent] JSON parse fallido: {raw[:200]}")
            return []

        raw_actions = data.get("actions", [])
        if not isinstance(raw_actions, list):
            logger.warning(f"[ActionAgent] 'actions' no es una lista: {type(raw_actions)}")
            return []

        # Validar cada accion
        acciones_validas = []
        for action in raw_actions:
            if not isinstance(action, dict):
                continue

            action_type = action.get("type", "").lower().strip()
            if action_type not in VALID_ACTION_TYPES:
                logger.warning(f"[ActionAgent] Tipo de accion invalido ignorado: '{action_type}'")
                continue

            params = action.get("params", {})
            if not isinstance(params, dict):
                params = {}

            acciones_validas.append({
                "type": action_type,
                "params": params,
            })

        # Limitar a maximo 3 acciones por mensaje
        if len(acciones_validas) > 3:
            logger.warning(
                f"[ActionAgent] Demasiadas acciones ({len(acciones_validas)}), truncando a 3"
            )
            acciones_validas = acciones_validas[:3]

        return acciones_validas
