// src/utils/logger.ts — Configuración de logger con Pino
// Generado por AgentKit

import pino from 'pino';
import { config } from '../config';

/**
 * Logger principal de la aplicación.
 * Nivel configurable via LOG_LEVEL en variables de entorno.
 */
export const logger = pino({
  level: config.LOG_LEVEL,
  transport:
    process.env.NODE_ENV !== 'production'
      ? {
          target: 'pino/file',
          options: { destination: 1 }, // stdout
        }
      : undefined,
  formatters: {
    level(label) {
      return { level: label };
    },
  },
  timestamp: pino.stdTimeFunctions.isoTime,
  base: {
    service: 'whatsapp-engine',
  },
});

/**
 * Crea un logger hijo con contexto adicional (ej: channelId).
 */
export function createChildLogger(bindings: Record<string, unknown>) {
  return logger.child(bindings);
}
