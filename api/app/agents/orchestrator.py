# agents/orchestrator.py — Orquestador del pipeline de agentes de IA
# Coordina la ejecucion secuencial de todos los agentes para procesar cada mensaje

"""
AgentOrchestrator coordina el pipeline completo de procesamiento de mensajes:
Router → Responder → Action, con Memory transversal.
No es un agente en si mismo, sino el director que orquesta a los demas.
"""

import logging
import time
from typing import Any

from api.app.agents.base_agent import AgentContext
from api.app.agents.router_agent import RouterAgent
from api.app.agents.responder_agent import ResponderAgent
from api.app.agents.memory_agent import MemoryAgent
from api.app.agents.action_agent import ActionAgent

logger = logging.getLogger("agentkit")

# Mensajes predefinidos para casos especiales
SPAM_RESPONSE = None  # No responder a spam
HUMAN_HANDOFF_RESPONSE = (
    "Entiendo que prefieres hablar con una persona. "
    "Te estoy conectando con un miembro de nuestro equipo. "
    "Alguien te atendera en breve."
)
FALLBACK_RESPONSE = (
    "Lo siento, estoy teniendo problemas tecnicos. "
    "Por favor intenta de nuevo en unos minutos."
)


class AgentOrchestrator:
    """
    Orquesta el pipeline completo de agentes para procesar mensajes de WhatsApp.
    Maneja el flujo: memoria → clasificacion → respuesta → acciones → almacenamiento.
    """

    def __init__(self, redis: Any = None):
        """
        Inicializa el orquestador con instancias de todos los agentes.

        Args:
            redis: Instancia de conexion Redis para el MemoryAgent (opcional)
        """
        self.router = RouterAgent()
        self.responder = ResponderAgent()
        self.memory = MemoryAgent()
        self.action = ActionAgent()
        self.redis = redis

    async def process_message(
        self,
        channel_id: str,
        phone: str,
        message: str,
        history: list[dict],
        ai_enabled: bool = True,
    ) -> dict:
        """
        Procesa un mensaje a traves del pipeline completo de agentes.

        Args:
            channel_id: ID del canal de WhatsApp
            phone: Numero de telefono del remitente
            message: Texto del mensaje
            history: Historial de la conversacion [{role, content}]
            ai_enabled: Si False, retorna respuesta minima sin IA

        Returns:
            Diccionario con:
                - response: str | None — Texto de respuesta
                - intent: str — Intencion clasificada
                - actions: list[dict] — Acciones a ejecutar
                - confidence: float — Confianza de la clasificacion
                - metadata: dict — Datos adicionales del pipeline
        """
        pipeline_start = time.monotonic()
        timing = {}

        # Si la IA esta deshabilitada para este canal, retornar inmediatamente
        if not ai_enabled:
            logger.info(f"[Orchestrator] IA deshabilitada para canal {channel_id}")
            return {
                "response": None,
                "intent": "disabled",
                "actions": [],
                "confidence": 0.0,
                "metadata": {"ai_disabled": True},
            }

        try:
            # ── Paso 1: Recuperar contexto de Redis ────────────────────
            stored_context = {}
            if self.redis:
                step_start = time.monotonic()
                stored_context = await self.memory.get_relevant_context(
                    self.redis, channel_id, phone
                )
                timing["memory_get"] = round(time.monotonic() - step_start, 3)

            # ── Paso 2: Gestionar ventana de historial ─────────────────
            step_start = time.monotonic()
            managed_history = await self.memory.manage_window(history)
            timing["memory_window"] = round(time.monotonic() - step_start, 3)

            # ── Paso 3: Clasificar intencion (Router) ──────────────────
            step_start = time.monotonic()
            router_context = AgentContext(
                channel_id=channel_id,
                phone=phone,
                message=message,
                history=managed_history,
                metadata=stored_context,
            )
            router_result = await self.router.process(router_context)
            timing["router"] = round(time.monotonic() - step_start, 3)

            intent = router_result.intent or "unknown"
            confidence = router_result.confidence

            logger.info(
                f"[Orchestrator] {phone} → intent={intent} "
                f"confidence={confidence:.2f}"
            )

            # ── Paso 4: Manejo de casos especiales ─────────────────────

            # Spam: no responder
            if intent == "spam":
                logger.info(f"[Orchestrator] Mensaje spam de {phone}, ignorando")
                total_time = round(time.monotonic() - pipeline_start, 3)
                timing["total"] = total_time
                return {
                    "response": SPAM_RESPONSE,
                    "intent": "spam",
                    "actions": [],
                    "confidence": confidence,
                    "metadata": {"timing": timing, "filtered": True},
                }

            # Handoff a humano: respuesta fija + accion de escalacion
            if intent == "human_handoff":
                logger.info(f"[Orchestrator] Handoff a humano solicitado por {phone}")
                total_time = round(time.monotonic() - pipeline_start, 3)
                timing["total"] = total_time
                return {
                    "response": HUMAN_HANDOFF_RESPONSE,
                    "intent": "human_handoff",
                    "actions": [
                        {
                            "type": "escalate_human",
                            "params": {
                                "reason": "Cliente solicito hablar con persona",
                                "priority": "high",
                            },
                        }
                    ],
                    "confidence": confidence,
                    "metadata": {"timing": timing},
                }

            # ── Paso 5: Generar respuesta (Responder) ──────────────────
            step_start = time.monotonic()
            responder_context = AgentContext(
                channel_id=channel_id,
                phone=phone,
                message=message,
                history=managed_history,
                intent=intent,
                metadata={
                    **stored_context,
                    "confidence": confidence,
                    "router_reasoning": router_result.metadata.get("reasoning", ""),
                },
            )
            responder_result = await self.responder.process(responder_context)
            timing["responder"] = round(time.monotonic() - step_start, 3)

            response_text = responder_result.response

            # ── Paso 6: Determinar acciones (Action) ───────────────────
            step_start = time.monotonic()
            action_context = AgentContext(
                channel_id=channel_id,
                phone=phone,
                message=message,
                history=managed_history,
                intent=intent,
                metadata={
                    "confidence": confidence,
                    "response": response_text or "",
                    "entities": stored_context.get("entities", {}),
                },
            )
            action_result = await self.action.process(action_context)
            timing["action"] = round(time.monotonic() - step_start, 3)

            # ── Paso 7: Extraer entidades y almacenar contexto ─────────
            if self.redis:
                step_start = time.monotonic()

                # Extraer entidades del mensaje actual
                new_entities = await self.memory.extract_entities(message)

                # Resumir si el historial es largo
                summary = stored_context.get("summary", "")
                if len(history) > 15:
                    summary = await self.memory.summarize_history(history)

                # Almacenar contexto actualizado
                await self.memory.store_context(
                    self.redis,
                    channel_id,
                    phone,
                    {
                        "summary": summary,
                        "entities": new_entities,
                        "metadata": {
                            "last_intent": intent,
                            "last_confidence": str(confidence),
                            "message_count": str(len(history) + 1),
                        },
                    },
                )
                timing["memory_store"] = round(time.monotonic() - step_start, 3)

            # ── Paso 8: Construir resultado final ──────────────────────
            total_time = round(time.monotonic() - pipeline_start, 3)
            timing["total"] = total_time

            logger.info(
                f"[Orchestrator] Pipeline completo para {phone} en {total_time}s "
                f"(intent={intent}, actions={len(action_result.actions)})"
            )

            return {
                "response": response_text,
                "intent": intent,
                "actions": action_result.actions,
                "confidence": confidence,
                "metadata": {
                    "timing": timing,
                    "router_reasoning": router_result.metadata.get("reasoning", ""),
                    "is_fallback": responder_result.metadata.get("fallback", False),
                },
            }

        except Exception as e:
            # Error critico en el pipeline — retornar respuesta de fallback
            total_time = round(time.monotonic() - pipeline_start, 3)
            logger.error(
                f"[Orchestrator] Error critico en pipeline para {phone}: {e}",
                exc_info=True,
            )

            return {
                "response": FALLBACK_RESPONSE,
                "intent": "error",
                "actions": [],
                "confidence": 0.0,
                "metadata": {
                    "error": str(e),
                    "timing": {"total": total_time},
                    "is_fallback": True,
                },
            }
