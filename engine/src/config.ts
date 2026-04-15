// src/config.ts — Configuración central del engine
// Generado por AgentKit

import dotenv from 'dotenv';
import path from 'path';

dotenv.config();

/**
 * Configuración del motor de WhatsApp.
 * Todas las variables se cargan desde el entorno con valores por defecto seguros.
 */
export const config = {
  /** URL de conexión a Redis */
  REDIS_URL: process.env.REDIS_URL || 'redis://localhost:6379',

  /** Directorio donde se almacenan las credenciales de sesión de cada canal */
  SESSIONS_DIR: process.env.SESSIONS_DIR || path.resolve(process.cwd(), 'sessions'),

  /** Nivel de logging: trace, debug, info, warn, error, fatal */
  LOG_LEVEL: process.env.LOG_LEVEL || 'info',

  /** Directorio para archivos multimedia descargados */
  MEDIA_DIR: process.env.MEDIA_DIR || path.resolve(process.cwd(), 'media'),

  /** Tiempo máximo de espera para reconexión (ms) */
  MAX_RECONNECT_DELAY: parseInt(process.env.MAX_RECONNECT_DELAY || '60000', 10),

  /** Número máximo de intentos de reconexión antes de desistir */
  MAX_RECONNECT_RETRIES: parseInt(process.env.MAX_RECONNECT_RETRIES || '10', 10),

  /** TTL para el código QR almacenado en Redis (segundos) */
  QR_TTL: parseInt(process.env.QR_TTL || '60', 10),
};
