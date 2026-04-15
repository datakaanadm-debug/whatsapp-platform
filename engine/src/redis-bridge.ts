// src/redis-bridge.ts — Puente de comunicación con Redis (pub/sub + almacenamiento)
// Generado por AgentKit

import Redis from 'ioredis';
import { config } from './config';
import { logger } from './utils/logger';

/**
 * RedisBridge gestiona toda la comunicación con Redis:
 * - Pub/Sub para comandos entrantes y eventos salientes
 * - Almacenamiento de QR codes y estados de sesión
 */
export class RedisBridge {
  /** Cliente principal para publicar y comandos generales */
  private client!: Redis;
  /** Cliente dedicado para suscripciones (Redis requiere un cliente separado) */
  private subscriber!: Redis;
  private connected = false;

  /**
   * Conecta ambos clientes de Redis (publisher y subscriber).
   */
  async connect(): Promise<void> {
    try {
      this.client = new Redis(config.REDIS_URL, {
        maxRetriesPerRequest: 3,
        retryStrategy(times) {
          const delay = Math.min(times * 200, 5000);
          logger.warn({ intento: times, delay }, 'Reintentando conexión a Redis...');
          return delay;
        },
        lazyConnect: true,
      });

      this.subscriber = new Redis(config.REDIS_URL, {
        maxRetriesPerRequest: 3,
        retryStrategy(times) {
          const delay = Math.min(times * 200, 5000);
          return delay;
        },
        lazyConnect: true,
      });

      await this.client.connect();
      await this.subscriber.connect();

      this.connected = true;
      logger.info('Conectado a Redis correctamente');

      // Manejar errores en tiempo de ejecución
      this.client.on('error', (err) => {
        logger.error({ err }, 'Error en cliente Redis (publisher)');
      });

      this.subscriber.on('error', (err) => {
        logger.error({ err }, 'Error en cliente Redis (subscriber)');
      });
    } catch (err) {
      logger.fatal({ err }, 'No se pudo conectar a Redis');
      throw err;
    }
  }

  /**
   * Publica un evento usando LPUSH a la cola de eventos.
   * Compatible con Upstash y cualquier Redis.
   */
  async publish(channel: string, eventType: string, data: Record<string, unknown>): Promise<void> {
    if (!this.connected) {
      logger.warn('Intentando publicar sin conexión a Redis');
      return;
    }

    const payload = JSON.stringify({
      event: eventType,
      channel,
      data,
      timestamp: new Date().toISOString(),
    });

    try {
      // LPUSH a la cola principal de eventos (API la consume con BRPOP)
      await this.client.lpush('wa:events:queue', payload);
      // También LPUSH al canal del WebSocket
      await this.client.lpush(`wa:ws:${channel}`, payload);
      await this.client.ltrim(`wa:ws:${channel}`, 0, 99);
      logger.debug({ channel, eventType }, 'Evento publicado en cola Redis');
    } catch (err) {
      logger.error({ err, channel, eventType }, 'Error al publicar evento en Redis');
    }
  }

  /**
   * Suscribe a comandos usando BRPOP polling.
   * Compatible con Upstash (no usa pub/sub).
   */
  async subscribe(
    pattern: string,
    callback: (channel: string, message: Record<string, unknown>) => void
  ): Promise<void> {
    if (!this.connected) {
      throw new Error('Redis no está conectado');
    }

    // Determinar la cola a escuchar
    // pattern "wa:cmd:*" → escuchar cola "wa:cmd:queue"
    const queueKey = 'wa:cmd:queue';
    logger.info({ pattern, queueKey }, 'Iniciando polling de comandos');

    // Loop de polling con RPOP (compatible con Upstash — no soporta BRPOP)
    const poll = async () => {
      while (this.connected) {
        try {
          const rawMessage = await this.client.rpop(queueKey);
          if (rawMessage) {
            try {
              const parsed = JSON.parse(rawMessage);
              const channelId = parsed.channel_id || parsed.channelId || '';
              callback(`wa:cmd:${channelId}`, parsed);
            } catch (err) {
              logger.error({ err, rawMessage }, 'Error al parsear comando de Redis');
            }
          } else {
            // Sin comandos — esperar antes de volver a consultar
            await new Promise(r => setTimeout(r, 500));
          }
        } catch (err) {
          if (this.connected) {
            logger.error({ err }, 'Error en polling de comandos');
            await new Promise(r => setTimeout(r, 1000));
          }
        }
      }
    };

    // Ejecutar en background
    poll().catch(err => logger.error({ err }, 'Polling loop terminó con error'));
  }

  /**
   * Publica un evento de WhatsApp para un canal específico.
   */
  async publishEvent(channelId: string, eventType: string, data: Record<string, unknown>): Promise<void> {
    await this.publish(`wa:evt:${channelId}`, eventType, {
      channelId,
      ...data,
    });
  }

  /**
   * Publica un cambio de estado para un canal.
   * Canal de destino: wa:status:{channelId}
   */
  async publishStatus(
    channelId: string,
    status: string,
    data: Record<string, unknown> = {}
  ): Promise<void> {
    await this.publish(`wa:status:${channelId}`, 'status.update', {
      channelId,
      status,
      ...data,
    });

    // También guardamos el estado en una key de Redis para consultas directas
    await this.setSessionStatus(channelId, status);
  }

  /**
   * Almacena el código QR en Redis con TTL configurable.
   */
  async setQR(channelId: string, qr: string): Promise<void> {
    try {
      await this.client.setex(`wa:qr:${channelId}`, config.QR_TTL, qr);
      logger.debug({ channelId }, 'QR almacenado en Redis');
    } catch (err) {
      logger.error({ err, channelId }, 'Error al almacenar QR en Redis');
    }
  }

  /**
   * Recupera el código QR almacenado para un canal.
   */
  async getQR(channelId: string): Promise<string | null> {
    try {
      return await this.client.get(`wa:qr:${channelId}`);
    } catch (err) {
      logger.error({ err, channelId }, 'Error al obtener QR de Redis');
      return null;
    }
  }

  /**
   * Guarda el estado de sesión de un canal en Redis.
   */
  async setSessionStatus(channelId: string, status: string): Promise<void> {
    try {
      await this.client.hset(`wa:session:${channelId}`, {
        status,
        updatedAt: new Date().toISOString(),
      });
      logger.debug({ channelId, status }, 'Estado de sesión actualizado en Redis');
    } catch (err) {
      logger.error({ err, channelId }, 'Error al guardar estado de sesión');
    }
  }

  /**
   * Obtiene el estado actual de sesión de un canal.
   */
  async getSessionStatus(channelId: string): Promise<string | null> {
    try {
      return await this.client.hget(`wa:session:${channelId}`, 'status');
    } catch (err) {
      logger.error({ err, channelId }, 'Error al obtener estado de sesión');
      return null;
    }
  }

  /**
   * Desconecta ambos clientes de Redis de forma limpia.
   */
  async disconnect(): Promise<void> {
    try {
      if (this.subscriber) {
        await this.subscriber.punsubscribe();
        await this.subscriber.quit();
      }
      if (this.client) {
        await this.client.quit();
      }
      this.connected = false;
      logger.info('Desconectado de Redis');
    } catch (err) {
      logger.error({ err }, 'Error al desconectar de Redis');
    }
  }

  /**
   * Retorna el cliente principal para operaciones directas si se necesita.
   */
  getClient(): Redis {
    return this.client;
  }
}
