// src/session-manager.ts — Gestión de sesiones de WhatsApp (Baileys)
// Generado por AgentKit

import makeWASocket, {
  WASocket,
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
  ConnectionState,
  WAMessageUpdate,
  proto,
  Contact,
  Chat,
  GroupMetadata,
} from '@whiskeysockets/baileys';
import { Boom } from '@hapi/boom';
import path from 'path';
import fs from 'fs/promises';
import pino from 'pino';
import { RedisBridge } from './redis-bridge';
import { MessageHandler } from './message-handler';
import {
  mapConnectionUpdate,
  mapMessageUpdate,
  mapPresenceUpdate,
  mapGroupUpdate,
  mapContactUpdate,
  mapChatUpdate,
} from './event-mapper';
import { config } from './config';
import { logger, createChildLogger } from './utils/logger';

/**
 * Información de estado de reconexión por canal.
 */
interface ReconnectState {
  intentos: number;
  ultimoIntento: number;
}

/**
 * SessionManager gestiona múltiples sesiones de WhatsApp simultáneas.
 * Cada sesión se identifica por un channelId único.
 */
export class SessionManager {
  /** Mapa de sesiones activas */
  private sessions: Map<string, WASocket> = new Map();
  /** Estado de reconexión por canal */
  private reconnectState: Map<string, ReconnectState> = new Map();
  /** Puente de comunicación con Redis */
  private redis: RedisBridge;
  /** Handler de mensajes */
  private messageHandler: MessageHandler;

  constructor(redis: RedisBridge) {
    this.redis = redis;
    this.messageHandler = new MessageHandler(redis);
  }

  /**
   * Crea una nueva sesión de WhatsApp para un canal.
   * Si ya existe una sesión activa, la cierra primero.
   */
  async createSession(channelId: string): Promise<void> {
    const log = createChildLogger({ channelId });
    log.info('Creando sesión de WhatsApp...');

    // Si ya existe una sesión activa, cerrarla primero
    if (this.sessions.has(channelId)) {
      log.warn('Sesión ya existente, cerrando primero...');
      await this.stopSession(channelId);
    }

    try {
      // Directorio de autenticación para este canal
      const authDir = path.join(config.SESSIONS_DIR, channelId);
      await fs.mkdir(authDir, { recursive: true });

      // Cargar estado de autenticación multi-dispositivo
      const { state, saveCreds } = await useMultiFileAuthState(authDir);

      // Obtener la última versión de Baileys
      const { version, isLatest } = await fetchLatestBaileysVersion();
      log.info({ version, isLatest }, 'Versión de WA Web obtenida');

      // Logger silencioso para Baileys (evita spam en consola)
      const baileysLogger = pino({ level: 'silent' });

      // Crear socket de WhatsApp
      const socket = makeWASocket({
        version,
        auth: {
          creds: state.creds,
          keys: makeCacheableSignalKeyStore(state.keys, baileysLogger),
        },
        logger: baileysLogger,
        printQRInTerminal: false, // Nosotros gestionamos el QR via Redis
        browser: ['AgentKit', 'Chrome', '120.0.0'],
        generateHighQualityLinkPreview: true,
        syncFullHistory: false,
        markOnlineOnConnect: true,
      });

      // Almacenar la sesión
      this.sessions.set(channelId, socket);

      // Publicar estado inicial
      await this.redis.publishStatus(channelId, 'connecting');

      // === Registrar event handlers ===

      // Actualización de conexión (QR, conectado, desconectado)
      socket.ev.on('connection.update', async (update: Partial<ConnectionState>) => {
        await this.handleConnectionUpdate(channelId, socket, update, saveCreds);
      });

      // Credenciales actualizadas — guardar en disco
      socket.ev.on('creds.update', saveCreds);

      // Mensajes nuevos
      socket.ev.on('messages.upsert', async ({ messages, type }) => {
        await this.messageHandler.handleIncoming(channelId, messages, type);
      });

      // Actualización de estado de mensajes (entregado, leído)
      socket.ev.on('messages.update', async (updates: WAMessageUpdate[]) => {
        const events = mapMessageUpdate(updates);
        for (const evt of events) {
          await this.redis.publishEvent(channelId, evt.event, evt.data);
        }
      });

      // Actualización de presencia (escribiendo, en línea)
      socket.ev.on('presence.update', async (update) => {
        const evt = mapPresenceUpdate(update);
        await this.redis.publishEvent(channelId, evt.event, evt.data);
      });

      // Actualización de grupos
      socket.ev.on('groups.update', async (updates: Partial<GroupMetadata>[]) => {
        const events = mapGroupUpdate(updates);
        for (const evt of events) {
          await this.redis.publishEvent(channelId, evt.event, evt.data);
        }
      });

      // Actualización de contactos
      socket.ev.on('contacts.update', async (updates: Partial<Contact>[]) => {
        const events = mapContactUpdate(updates);
        for (const evt of events) {
          await this.redis.publishEvent(channelId, evt.event, evt.data);
        }
      });

      // Actualización de chats
      socket.ev.on('chats.update', async (updates: Partial<Chat>[]) => {
        const events = mapChatUpdate(updates);
        for (const evt of events) {
          await this.redis.publishEvent(channelId, evt.event, evt.data);
        }
      });

      // Mensajes eliminados
      socket.ev.on('messages.delete', async (item) => {
        if ('keys' in item) {
          for (const key of item.keys) {
            await this.redis.publishEvent(channelId, 'message.deleted', {
              messageId: key.id || '',
              remoteJid: key.remoteJid || '',
              fromMe: key.fromMe || false,
            });
          }
        }
      });

      // Participantes de grupo actualizados
      socket.ev.on('group-participants.update', async (update) => {
        await this.redis.publishEvent(channelId, 'group.participants.update', {
          groupId: update.id,
          participants: update.participants,
          action: update.action, // add, remove, promote, demote
        });
      });

      log.info('Sesión creada, esperando conexión...');
    } catch (err) {
      log.error({ err }, 'Error al crear sesión');
      await this.redis.publishStatus(channelId, 'error', {
        error: (err as Error).message,
      });
      throw err;
    }
  }

  /**
   * Maneja las actualizaciones de conexión (QR, conexión exitosa, desconexión).
   */
  private async handleConnectionUpdate(
    channelId: string,
    socket: WASocket,
    update: Partial<ConnectionState>,
    saveCreds: () => Promise<void>
  ): Promise<void> {
    const log = createChildLogger({ channelId });
    const { connection, lastDisconnect, qr } = update;

    // Publicar el evento de conexión al formato de plataforma
    const mappedEvent = mapConnectionUpdate(update);
    await this.redis.publishEvent(channelId, mappedEvent.event, mappedEvent.data);

    // Si hay código QR, almacenarlo en Redis
    if (qr) {
      log.info('Nuevo código QR generado');
      await this.redis.setQR(channelId, qr);
      await this.redis.publishStatus(channelId, 'qr', { qr });
    }

    // Conexión abierta exitosamente
    if (connection === 'open') {
      log.info('Conexión establecida exitosamente');
      // Resetear estado de reconexión
      this.reconnectState.delete(channelId);
      await this.redis.publishStatus(channelId, 'connected', {
        user: socket.user ? {
          id: socket.user.id,
          name: socket.user.name || null,
        } : null,
      });
    }

    // Conexión cerrada
    if (connection === 'close') {
      const statusCode = (lastDisconnect?.error as Boom)?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

      log.warn(
        { statusCode, shouldReconnect },
        'Conexión cerrada'
      );

      // Eliminar la sesión del mapa (se recreará si reconecta)
      this.sessions.delete(channelId);

      if (shouldReconnect) {
        await this.redis.publishStatus(channelId, 'reconnecting', {
          reason: statusCode,
        });
        await this.reconnectWithBackoff(channelId);
      } else {
        // LoggedOut — limpiar todo
        log.info('Sesión cerrada por logout, limpiando credenciales...');
        await this.redis.publishStatus(channelId, 'disconnected', {
          reason: 'logged_out',
        });
        // Limpiar archivos de autenticación
        const authDir = path.join(config.SESSIONS_DIR, channelId);
        await fs.rm(authDir, { recursive: true, force: true }).catch(() => {});
        this.reconnectState.delete(channelId);
      }
    }
  }

  /**
   * Reconecta con retroceso exponencial (exponential backoff).
   */
  private async reconnectWithBackoff(channelId: string): Promise<void> {
    const log = createChildLogger({ channelId });
    const state = this.reconnectState.get(channelId) || { intentos: 0, ultimoIntento: 0 };

    state.intentos++;
    this.reconnectState.set(channelId, state);

    // Verificar si excedimos el máximo de reintentos
    if (state.intentos > config.MAX_RECONNECT_RETRIES) {
      log.error(
        { intentos: state.intentos },
        'Máximo de reintentos alcanzado, deteniendo reconexión'
      );
      await this.redis.publishStatus(channelId, 'failed', {
        reason: 'max_retries_exceeded',
        intentos: state.intentos,
      });
      this.reconnectState.delete(channelId);
      return;
    }

    // Calcular delay con exponential backoff + jitter
    const baseDelay = Math.min(1000 * Math.pow(2, state.intentos - 1), config.MAX_RECONNECT_DELAY);
    const jitter = Math.random() * 1000; // Hasta 1 segundo de jitter
    const delay = baseDelay + jitter;

    log.info(
      { intento: state.intentos, delay: Math.round(delay) },
      'Programando reconexión...'
    );

    state.ultimoIntento = Date.now();
    this.reconnectState.set(channelId, state);

    // Esperar y reconectar
    await new Promise((resolve) => setTimeout(resolve, delay));

    try {
      await this.createSession(channelId);
    } catch (err) {
      log.error({ err }, 'Error en reconexión');
    }
  }

  /**
   * Detiene una sesión de forma limpia.
   */
  async stopSession(channelId: string): Promise<void> {
    const log = createChildLogger({ channelId });
    const session = this.sessions.get(channelId);

    if (!session) {
      log.warn('No se encontró sesión activa para detener');
      return;
    }

    try {
      // Remover todos los listeners
      session.ev.removeAllListeners('connection.update');
      session.ev.removeAllListeners('creds.update');
      session.ev.removeAllListeners('messages.upsert');
      session.ev.removeAllListeners('messages.update');
      session.ev.removeAllListeners('messages.delete');
      session.ev.removeAllListeners('presence.update');
      session.ev.removeAllListeners('groups.update');
      session.ev.removeAllListeners('contacts.update');
      session.ev.removeAllListeners('chats.update');
      session.ev.removeAllListeners('group-participants.update');

      // Cerrar la conexión WebSocket
      session.end(undefined);

      this.sessions.delete(channelId);
      this.reconnectState.delete(channelId);

      await this.redis.publishStatus(channelId, 'stopped');
      log.info('Sesión detenida correctamente');
    } catch (err) {
      log.error({ err }, 'Error al detener sesión');
      // Asegurarse de limpiar de cualquier forma
      this.sessions.delete(channelId);
    }
  }

  /**
   * Obtiene la sesión activa de un canal.
   */
  getSession(channelId: string): WASocket | undefined {
    return this.sessions.get(channelId);
  }

  /**
   * Elimina una sesión: la detiene y borra sus archivos de autenticación.
   */
  async deleteSession(channelId: string): Promise<void> {
    const log = createChildLogger({ channelId });

    // Primero detener la sesión si está activa
    await this.stopSession(channelId);

    // Eliminar archivos de autenticación
    const authDir = path.join(config.SESSIONS_DIR, channelId);
    try {
      await fs.rm(authDir, { recursive: true, force: true });
      log.info('Archivos de sesión eliminados');
    } catch (err) {
      log.error({ err }, 'Error al eliminar archivos de sesión');
    }

    // Limpiar estado en Redis
    await this.redis.publishStatus(channelId, 'deleted');
  }

  /**
   * Restaura todas las sesiones previas al iniciar el engine.
   * Lee los directorios de sesión guardados y reconecta cada uno.
   */
  async restoreAllSessions(): Promise<void> {
    logger.info('Restaurando sesiones previas...');

    try {
      // Verificar que el directorio de sesiones exista
      await fs.mkdir(config.SESSIONS_DIR, { recursive: true });
      const entries = await fs.readdir(config.SESSIONS_DIR, { withFileTypes: true });

      // Filtrar solo directorios (cada uno es una sesión)
      const sessionDirs = entries.filter((e) => e.isDirectory());

      if (sessionDirs.length === 0) {
        logger.info('No hay sesiones previas para restaurar');
        return;
      }

      logger.info({ count: sessionDirs.length }, 'Sesiones encontradas para restaurar');

      // Restaurar cada sesión en paralelo (con límite de concurrencia)
      const MAX_CONCURRENT = 5;
      for (let i = 0; i < sessionDirs.length; i += MAX_CONCURRENT) {
        const batch = sessionDirs.slice(i, i + MAX_CONCURRENT);
        await Promise.allSettled(
          batch.map(async (dir) => {
            const channelId = dir.name;
            try {
              // Verificar que tenga archivos de auth (creds.json indica sesión válida)
              const credsPath = path.join(config.SESSIONS_DIR, channelId, 'creds.json');
              await fs.access(credsPath);

              logger.info({ channelId }, 'Restaurando sesión...');
              await this.createSession(channelId);
            } catch (err) {
              logger.warn(
                { channelId, err },
                'No se pudo restaurar sesión (posiblemente sin credenciales)'
              );
            }
          })
        );
      }

      logger.info('Restauración de sesiones completada');
    } catch (err) {
      logger.error({ err }, 'Error al restaurar sesiones');
    }
  }

  /**
   * Retorna el handler de mensajes para uso externo (comandos de envío).
   */
  getMessageHandler(): MessageHandler {
    return this.messageHandler;
  }

  /**
   * Retorna la lista de sesiones activas y su estado.
   */
  getActiveSessions(): Array<{ channelId: string; user: unknown }> {
    const result: Array<{ channelId: string; user: unknown }> = [];
    for (const [channelId, socket] of this.sessions) {
      result.push({
        channelId,
        user: socket.user ? { id: socket.user.id, name: socket.user.name } : null,
      });
    }
    return result;
  }

  /**
   * Detiene todas las sesiones activas (para shutdown limpio).
   */
  async stopAll(): Promise<void> {
    logger.info({ count: this.sessions.size }, 'Deteniendo todas las sesiones...');
    const channels = Array.from(this.sessions.keys());
    await Promise.allSettled(channels.map((id) => this.stopSession(id)));
    logger.info('Todas las sesiones detenidas');
  }
}
