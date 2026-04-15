// src/index.ts — Punto de entrada del motor de WhatsApp
// Generado por AgentKit

import dotenv from 'dotenv';
dotenv.config();

import { WAMessageKey } from '@whiskeysockets/baileys';
import { config } from './config';
import { RedisBridge } from './redis-bridge';
import { SessionManager } from './session-manager';
import { logger } from './utils/logger';

// Instancias globales
let redis: RedisBridge;
let sessionManager: SessionManager;

/**
 * Estructura de un comando recibido desde Redis.
 */
interface Command {
  command?: string;
  action?: string;
  channel_id?: string;
  channelId?: string;
  data?: Record<string, unknown>;
  request_id?: string;
  requestId?: string;
}

/**
 * Inicializa las conexiones y empieza a escuchar comandos.
 */
async function main(): Promise<void> {
  logger.info('=== WhatsApp Engine iniciando ===');
  logger.info({ sessionsDir: config.SESSIONS_DIR, logLevel: config.LOG_LEVEL }, 'Configuración cargada');

  // 1. Conectar a Redis
  redis = new RedisBridge();
  await redis.connect();
  logger.info('Conectado a Redis');

  // 2. Inicializar SessionManager
  sessionManager = new SessionManager(redis);

  // 3. Restaurar sesiones previas
  await sessionManager.restoreAllSessions();

  // 4. Suscribirse a canales de comandos
  await redis.subscribe('wa:cmd:*', handleCommand);
  logger.info('Escuchando comandos en wa:cmd:*');

  logger.info('=== WhatsApp Engine listo ===');
}

/**
 * Enruta y ejecuta comandos recibidos desde Redis.
 * Los comandos llegan en canales wa:cmd:{channelId} o wa:cmd:global.
 */
async function handleCommand(channel: string, message: Record<string, unknown>): Promise<void> {
  const raw = message as unknown as Command;
  // La API envía "command" y "channel_id", el engine acepta ambos formatos
  const action = raw.command || raw.action || '';
  const channelId = raw.channel_id || raw.channelId || '';
  const data = raw.data || {};
  const requestId = raw.request_id || raw.requestId || '';

  if (!action) {
    logger.warn({ channel, message }, 'Comando recibido sin acción');
    return;
  }

  const log = logger.child({ action, channelId, requestId });
  log.info('Comando recibido');

  try {
    switch (action) {
      // === Gestión de sesiones ===

      case 'start_session': {
        await sessionManager.createSession(channelId);
        await respondToCommand(channelId, requestId, { success: true, message: 'Sesión iniciada' });
        break;
      }

      case 'stop_session': {
        await sessionManager.stopSession(channelId);
        await respondToCommand(channelId, requestId, { success: true, message: 'Sesión detenida' });
        break;
      }

      case 'delete_session': {
        await sessionManager.deleteSession(channelId);
        await respondToCommand(channelId, requestId, { success: true, message: 'Sesión eliminada' });
        break;
      }

      case 'get_session_status': {
        const session = sessionManager.getSession(channelId);
        const status = session ? 'connected' : await redis.getSessionStatus(channelId) || 'unknown';
        await respondToCommand(channelId, requestId, {
          success: true,
          status,
          user: session?.user ? { id: session.user.id, name: session.user.name } : null,
        });
        break;
      }

      case 'list_sessions': {
        const sessions = sessionManager.getActiveSessions();
        await respondToCommand(channelId || 'global', requestId, {
          success: true,
          sessions,
        });
        break;
      }

      case 'get_qr': {
        const qr = await redis.getQR(channelId);
        await respondToCommand(channelId, requestId, {
          success: true,
          qr: qr || null,
          available: !!qr,
        });
        break;
      }

      // === Envío de mensajes ===

      case 'send_message': {
        const session = sessionManager.getSession(channelId);
        if (!session) {
          await respondToCommand(channelId, requestId, {
            success: false,
            error: 'Sesión no conectada',
          });
          break;
        }

        const handler = sessionManager.getMessageHandler();
        const msgData = data || {};
        const to = msgData.to as string;
        const type = msgData.type as string || 'text';
        let result;

        switch (type) {
          case 'text':
            result = await handler.sendText(session, to, (msgData.body || msgData.text) as string, {
              quotedMessageId: msgData.quotedMessageId as string | undefined,
              quotedParticipant: msgData.quotedParticipant as string | undefined,
              mentions: msgData.mentions as string[] | undefined,
            });
            break;

          case 'image':
            result = await handler.sendImage(
              session, to,
              msgData.url as string || Buffer.from(msgData.base64 as string || '', 'base64'),
              msgData.caption as string | undefined,
              { quotedMessageId: msgData.quotedMessageId as string | undefined },
            );
            break;

          case 'video':
            result = await handler.sendVideo(
              session, to,
              msgData.url as string || Buffer.from(msgData.base64 as string || '', 'base64'),
              msgData.caption as string | undefined,
              {
                quotedMessageId: msgData.quotedMessageId as string | undefined,
                gifPlayback: msgData.gifPlayback as boolean | undefined,
              },
            );
            break;

          case 'audio':
            result = await handler.sendAudio(
              session, to,
              msgData.url as string || Buffer.from(msgData.base64 as string || '', 'base64'),
              { ptt: msgData.ptt as boolean | undefined },
            );
            break;

          case 'document':
            result = await handler.sendDocument(
              session, to,
              msgData.url as string || Buffer.from(msgData.base64 as string || '', 'base64'),
              msgData.filename as string | undefined,
              msgData.caption as string | undefined,
              msgData.mimeType as string | undefined,
            );
            break;

          case 'location':
            result = await handler.sendLocation(
              session, to,
              msgData.latitude as number,
              msgData.longitude as number,
              msgData.name as string | undefined,
              msgData.address as string | undefined,
            );
            break;

          case 'contact':
            result = await handler.sendContact(
              session, to,
              msgData.contacts as Array<{ name: string; phone: string }>,
            );
            break;

          case 'sticker':
            result = await handler.sendSticker(
              session, to,
              msgData.url as string || Buffer.from(msgData.base64 as string || '', 'base64'),
            );
            break;

          case 'poll':
            result = await handler.sendPoll(
              session, to,
              msgData.title as string,
              msgData.options as string[],
              msgData.selectableCount as number | undefined,
            );
            break;

          case 'reaction':
            result = await handler.sendReaction(
              session,
              {
                remoteJid: to,
                id: msgData.targetMessageId as string,
                fromMe: msgData.fromMe as boolean | undefined,
              } as WAMessageKey,
              msgData.emoji as string,
            );
            break;

          default:
            await respondToCommand(channelId, requestId, {
              success: false,
              error: `Tipo de mensaje no soportado: ${type}`,
            });
            return;
        }

        await respondToCommand(channelId, requestId, {
          success: true,
          messageId: result?.key?.id || null,
        });
        break;
      }

      case 'delete_message': {
        const session = sessionManager.getSession(channelId);
        if (!session) {
          await respondToCommand(channelId, requestId, {
            success: false,
            error: 'Sesión no conectada',
          });
          break;
        }

        const handler = sessionManager.getMessageHandler();
        const delData = data || {};
        const messageKey: WAMessageKey = {
          remoteJid: delData.chatId as string,
          id: delData.messageId as string,
          fromMe: delData.fromMe as boolean ?? true,
          participant: delData.participant as string | undefined,
        };

        await handler.deleteMessage(session, delData.chatId as string, messageKey);
        await respondToCommand(channelId, requestId, { success: true, message: 'Mensaje eliminado' });
        break;
      }

      case 'forward_message': {
        const session = sessionManager.getSession(channelId);
        if (!session) {
          await respondToCommand(channelId, requestId, {
            success: false,
            error: 'Sesión no conectada',
          });
          break;
        }

        // Nota: forward_message requiere el mensaje original completo
        // En la práctica, el API server debería almacenar mensajes para esto
        await respondToCommand(channelId, requestId, {
          success: false,
          error: 'forward_message requiere el mensaje original. Usa send_message en su lugar.',
        });
        break;
      }

      default: {
        log.warn({ action }, 'Acción no reconocida');
        await respondToCommand(channelId || 'global', requestId, {
          success: false,
          error: `Acción no reconocida: ${action}`,
        });
      }
    }
  } catch (err) {
    log.error({ err }, 'Error al ejecutar comando');
    await respondToCommand(channelId || 'global', requestId, {
      success: false,
      error: (err as Error).message,
    });
  }
}

/**
 * Publica la respuesta de un comando en Redis.
 * Canal: wa:res:{channelId}
 */
async function respondToCommand(
  channelId: string,
  requestId: string | undefined,
  data: Record<string, unknown>
): Promise<void> {
  if (!requestId) return; // Si no hay requestId, no se espera respuesta

  await redis.publish(`wa:res:${channelId}`, 'command.response', {
    requestId,
    channelId,
    ...data,
  });
}

/**
 * Apagado limpio: cierra sesiones y desconecta de Redis.
 */
async function gracefulShutdown(signal: string): Promise<void> {
  logger.info({ signal }, 'Señal de apagado recibida, cerrando...');

  try {
    // Detener todas las sesiones de WhatsApp
    if (sessionManager) {
      await sessionManager.stopAll();
    }

    // Desconectar de Redis
    if (redis) {
      await redis.disconnect();
    }

    logger.info('Apagado limpio completado');
    process.exit(0);
  } catch (err) {
    logger.error({ err }, 'Error durante apagado');
    process.exit(1);
  }
}

// Registrar handlers de señales de apagado
process.on('SIGINT', () => gracefulShutdown('SIGINT'));
process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));

// Capturar errores no manejados
process.on('uncaughtException', (err) => {
  logger.fatal({ err }, 'Excepción no capturada');
  gracefulShutdown('uncaughtException');
});

process.on('unhandledRejection', (reason, promise) => {
  logger.fatal({ reason }, 'Promesa rechazada sin manejar');
  gracefulShutdown('unhandledRejection');
});

// Arrancar
main().catch((err) => {
  logger.fatal({ err }, 'Error fatal al iniciar el engine');
  process.exit(1);
});
