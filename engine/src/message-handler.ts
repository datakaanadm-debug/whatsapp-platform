// src/message-handler.ts — Manejo de mensajes entrantes y salientes
// Generado por AgentKit

import { WASocket, proto, AnyMessageContent, generateWAMessageFromContent, WAMessageKey } from '@whiskeysockets/baileys';
import { v4 as uuidv4 } from 'uuid';
import { RedisBridge } from './redis-bridge';
import { MediaHandler } from './media-handler';
import { mapMessageUpsert } from './event-mapper';
import { logger } from './utils/logger';
import fs from 'fs/promises';
import path from 'path';
import httpx from 'https';
import http from 'http';

/**
 * MessageHandler gestiona el envío y recepción de todos los tipos de mensajes.
 * Normaliza mensajes entrantes y proporciona métodos para enviar cada tipo.
 */
export class MessageHandler {
  private redis: RedisBridge;
  private mediaHandler: MediaHandler;

  constructor(redis: RedisBridge) {
    this.redis = redis;
    this.mediaHandler = new MediaHandler();
  }

  /**
   * Procesa un mensaje entrante: normaliza y publica en Redis.
   */
  async handleIncoming(
    channelId: string,
    messages: proto.IWebMessageInfo[],
    type: 'notify' | 'append'
  ): Promise<void> {
    const events = mapMessageUpsert(messages, type);

    for (const event of events) {
      try {
        // Si el mensaje tiene multimedia, intentar descargarlo
        if (event.data.hasMedia) {
          const rawMsg = messages.find((m) => m.key.id === event.data.messageId);
          if (rawMsg) {
            const mediaResult = await this.mediaHandler.downloadAndSave(channelId, rawMsg);
            if (mediaResult) {
              event.data.mediaPath = mediaResult.path;
              event.data.mediaSize = mediaResult.size;
            }
          }
        }

        await this.redis.publishEvent(channelId, event.event, event.data);
        logger.debug(
          { channelId, event: event.event, messageId: event.data.messageId },
          'Mensaje entrante publicado en Redis'
        );
      } catch (err) {
        logger.error({ err, channelId, event: event.event }, 'Error al procesar mensaje entrante');
      }
    }
  }

  /**
   * Envía un mensaje de texto.
   */
  async sendText(
    session: WASocket,
    to: string,
    text: string,
    options?: {
      quotedMessageId?: string;
      quotedParticipant?: string;
      mentions?: string[];
    }
  ): Promise<proto.WebMessageInfo | undefined> {
    try {
      const jid = this.normalizeJid(to);
      const content: AnyMessageContent = { text };

      // Si es una respuesta a otro mensaje
      if (options?.quotedMessageId) {
        (content as any).quoted = {
          key: {
            remoteJid: jid,
            id: options.quotedMessageId,
            participant: options.quotedParticipant || undefined,
          },
          message: { conversation: '' },
        };
      }

      // Menciones
      if (options?.mentions && options.mentions.length > 0) {
        (content as any).mentions = options.mentions.map((m) => this.normalizeJid(m));
      }

      const result = await session.sendMessage(jid, content);
      logger.info({ to: jid, messageId: result?.key?.id }, 'Mensaje de texto enviado');
      return result;
    } catch (err) {
      logger.error({ err, to }, 'Error al enviar mensaje de texto');
      throw err;
    }
  }

  /**
   * Envía una imagen (desde URL o buffer).
   */
  async sendImage(
    session: WASocket,
    to: string,
    imageSource: string | Buffer,
    caption?: string,
    options?: { quotedMessageId?: string; mentions?: string[] }
  ): Promise<proto.WebMessageInfo | undefined> {
    try {
      const jid = this.normalizeJid(to);
      const imageBuffer = typeof imageSource === 'string'
        ? await this.downloadFromUrl(imageSource)
        : imageSource;

      const content: AnyMessageContent = {
        image: imageBuffer,
        caption: caption || undefined,
        mentions: options?.mentions?.map((m) => this.normalizeJid(m)),
      };

      if (options?.quotedMessageId) {
        (content as any).quoted = {
          key: { remoteJid: jid, id: options.quotedMessageId },
          message: { conversation: '' },
        };
      }

      const result = await session.sendMessage(jid, content);
      logger.info({ to: jid, messageId: result?.key?.id }, 'Imagen enviada');
      return result;
    } catch (err) {
      logger.error({ err, to }, 'Error al enviar imagen');
      throw err;
    }
  }

  /**
   * Envía un video (desde URL o buffer).
   */
  async sendVideo(
    session: WASocket,
    to: string,
    videoSource: string | Buffer,
    caption?: string,
    options?: { quotedMessageId?: string; gifPlayback?: boolean }
  ): Promise<proto.WebMessageInfo | undefined> {
    try {
      const jid = this.normalizeJid(to);
      const videoBuffer = typeof videoSource === 'string'
        ? await this.downloadFromUrl(videoSource)
        : videoSource;

      const content: AnyMessageContent = {
        video: videoBuffer,
        caption: caption || undefined,
        gifPlayback: options?.gifPlayback || false,
      };

      if (options?.quotedMessageId) {
        (content as any).quoted = {
          key: { remoteJid: jid, id: options.quotedMessageId },
          message: { conversation: '' },
        };
      }

      const result = await session.sendMessage(jid, content);
      logger.info({ to: jid, messageId: result?.key?.id }, 'Video enviado');
      return result;
    } catch (err) {
      logger.error({ err, to }, 'Error al enviar video');
      throw err;
    }
  }

  /**
   * Envía un audio o nota de voz (desde URL o buffer).
   */
  async sendAudio(
    session: WASocket,
    to: string,
    audioSource: string | Buffer,
    options?: { ptt?: boolean }
  ): Promise<proto.WebMessageInfo | undefined> {
    try {
      const jid = this.normalizeJid(to);
      const audioBuffer = typeof audioSource === 'string'
        ? await this.downloadFromUrl(audioSource)
        : audioSource;

      const content: AnyMessageContent = {
        audio: audioBuffer,
        mimetype: 'audio/ogg; codecs=opus',
        ptt: options?.ptt ?? true, // Por defecto, nota de voz
      };

      const result = await session.sendMessage(jid, content);
      logger.info({ to: jid, messageId: result?.key?.id, ptt: options?.ptt ?? true }, 'Audio enviado');
      return result;
    } catch (err) {
      logger.error({ err, to }, 'Error al enviar audio');
      throw err;
    }
  }

  /**
   * Envía un documento/archivo (desde URL o buffer).
   */
  async sendDocument(
    session: WASocket,
    to: string,
    docSource: string | Buffer,
    filename?: string,
    caption?: string,
    mimeType?: string
  ): Promise<proto.WebMessageInfo | undefined> {
    try {
      const jid = this.normalizeJid(to);
      const docBuffer = typeof docSource === 'string'
        ? await this.downloadFromUrl(docSource)
        : docSource;

      const content: AnyMessageContent = {
        document: docBuffer,
        mimetype: mimeType || 'application/octet-stream',
        fileName: filename || 'document',
        caption: caption || undefined,
      };

      const result = await session.sendMessage(jid, content);
      logger.info({ to: jid, messageId: result?.key?.id, filename }, 'Documento enviado');
      return result;
    } catch (err) {
      logger.error({ err, to }, 'Error al enviar documento');
      throw err;
    }
  }

  /**
   * Envía una ubicación.
   */
  async sendLocation(
    session: WASocket,
    to: string,
    latitude: number,
    longitude: number,
    name?: string,
    address?: string
  ): Promise<proto.WebMessageInfo | undefined> {
    try {
      const jid = this.normalizeJid(to);
      const content: AnyMessageContent = {
        location: {
          degreesLatitude: latitude,
          degreesLongitude: longitude,
          name: name || undefined,
          address: address || undefined,
        },
      };

      const result = await session.sendMessage(jid, content);
      logger.info({ to: jid, messageId: result?.key?.id }, 'Ubicación enviada');
      return result;
    } catch (err) {
      logger.error({ err, to }, 'Error al enviar ubicación');
      throw err;
    }
  }

  /**
   * Envía uno o más contactos como vCard.
   */
  async sendContact(
    session: WASocket,
    to: string,
    contacts: Array<{ name: string; phone: string }>
  ): Promise<proto.WebMessageInfo | undefined> {
    try {
      const jid = this.normalizeJid(to);

      const vcards = contacts.map((c) => {
        const cleanPhone = c.phone.replace(/[^0-9+]/g, '');
        return [
          'BEGIN:VCARD',
          'VERSION:3.0',
          `FN:${c.name}`,
          `TEL;type=CELL;type=VOICE;waid=${cleanPhone.replace('+', '')}:${cleanPhone}`,
          'END:VCARD',
        ].join('\n');
      });

      let content: AnyMessageContent;
      if (vcards.length === 1) {
        content = {
          contacts: {
            displayName: contacts[0].name,
            contacts: [{ vcard: vcards[0] }],
          },
        };
      } else {
        content = {
          contacts: {
            displayName: `${contacts.length} contactos`,
            contacts: vcards.map((vcard, i) => ({
              displayName: contacts[i].name,
              vcard,
            })),
          },
        };
      }

      const result = await session.sendMessage(jid, content);
      logger.info({ to: jid, messageId: result?.key?.id, count: contacts.length }, 'Contacto(s) enviado(s)');
      return result;
    } catch (err) {
      logger.error({ err, to }, 'Error al enviar contacto');
      throw err;
    }
  }

  /**
   * Envía un sticker (desde URL o buffer). La imagen se convierte a WebP.
   */
  async sendSticker(
    session: WASocket,
    to: string,
    stickerSource: string | Buffer
  ): Promise<proto.WebMessageInfo | undefined> {
    try {
      const jid = this.normalizeJid(to);
      const stickerBuffer = typeof stickerSource === 'string'
        ? await this.downloadFromUrl(stickerSource)
        : stickerSource;

      const content: AnyMessageContent = {
        sticker: stickerBuffer,
      };

      const result = await session.sendMessage(jid, content);
      logger.info({ to: jid, messageId: result?.key?.id }, 'Sticker enviado');
      return result;
    } catch (err) {
      logger.error({ err, to }, 'Error al enviar sticker');
      throw err;
    }
  }

  /**
   * Envía una encuesta (poll).
   */
  async sendPoll(
    session: WASocket,
    to: string,
    title: string,
    pollOptions: string[],
    selectableCount?: number
  ): Promise<proto.WebMessageInfo | undefined> {
    try {
      const jid = this.normalizeJid(to);

      const content: AnyMessageContent = {
        poll: {
          name: title,
          values: pollOptions,
          selectableCount: selectableCount || 1,
        },
      };

      const result = await session.sendMessage(jid, content);
      logger.info({ to: jid, messageId: result?.key?.id, title }, 'Encuesta enviada');
      return result;
    } catch (err) {
      logger.error({ err, to }, 'Error al enviar encuesta');
      throw err;
    }
  }

  /**
   * Envía una reacción (emoji) a un mensaje específico.
   */
  async sendReaction(
    session: WASocket,
    messageKey: WAMessageKey,
    emoji: string
  ): Promise<proto.WebMessageInfo | undefined> {
    try {
      const jid = messageKey.remoteJid!;
      const content: AnyMessageContent = {
        react: {
          text: emoji, // String vacío para quitar la reacción
          key: messageKey,
        },
      };

      const result = await session.sendMessage(jid, content);
      logger.info(
        { to: jid, targetMessageId: messageKey.id, emoji },
        'Reacción enviada'
      );
      return result;
    } catch (err) {
      logger.error({ err, targetMessageId: messageKey.id }, 'Error al enviar reacción');
      throw err;
    }
  }

  /**
   * Elimina un mensaje (revoke) para todos.
   */
  async deleteMessage(
    session: WASocket,
    chatId: string,
    messageKey: WAMessageKey
  ): Promise<proto.WebMessageInfo | undefined> {
    try {
      const jid = this.normalizeJid(chatId);
      const result = await session.sendMessage(jid, { delete: messageKey });
      logger.info({ chatId: jid, messageId: messageKey.id }, 'Mensaje eliminado');
      return result;
    } catch (err) {
      logger.error({ err, chatId, messageId: messageKey.id }, 'Error al eliminar mensaje');
      throw err;
    }
  }

  /**
   * Reenvía un mensaje a otro chat.
   */
  async forwardMessage(
    session: WASocket,
    to: string,
    message: proto.IWebMessageInfo
  ): Promise<proto.WebMessageInfo | undefined> {
    try {
      const jid = this.normalizeJid(to);

      if (!message.message) {
        throw new Error('El mensaje a reenviar no tiene contenido');
      }

      // Generar un mensaje con el flag de reenviado
      const content = generateWAMessageFromContent(jid, message.message, {
        userJid: session.user?.id || '',
      });

      // Marcar como reenviado
      if (content.message) {
        const msgType = Object.keys(content.message)[0] as keyof proto.IMessage;
        const innerMsg = (content.message as any)[msgType];
        if (innerMsg && typeof innerMsg === 'object') {
          if (!innerMsg.contextInfo) innerMsg.contextInfo = {};
          innerMsg.contextInfo.isForwarded = true;
          innerMsg.contextInfo.forwardingScore = 1;
        }
      }

      await session.relayMessage(jid, content.message!, {
        messageId: content.key.id!,
      });

      logger.info({ to: jid, originalId: message.key?.id }, 'Mensaje reenviado');
      return content as proto.WebMessageInfo;
    } catch (err) {
      logger.error({ err, to }, 'Error al reenviar mensaje');
      throw err;
    }
  }

  /**
   * Normaliza un JID de WhatsApp.
   * Agrega @s.whatsapp.net si no tiene sufijo.
   */
  private normalizeJid(jid: string): string {
    if (jid.includes('@')) return jid;
    // Limpiar caracteres no numéricos
    const cleaned = jid.replace(/[^0-9]/g, '');
    return `${cleaned}@s.whatsapp.net`;
  }

  /**
   * Descarga un archivo desde una URL y retorna el buffer.
   */
  private downloadFromUrl(url: string): Promise<Buffer> {
    return new Promise((resolve, reject) => {
      const protocol = url.startsWith('https') ? httpx : http;
      const request = protocol.get(url, (response) => {
        // Seguir redirecciones
        if (response.statusCode && response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
          this.downloadFromUrl(response.headers.location).then(resolve).catch(reject);
          return;
        }

        if (response.statusCode && response.statusCode !== 200) {
          reject(new Error(`Error HTTP ${response.statusCode} al descargar ${url}`));
          return;
        }

        const chunks: Buffer[] = [];
        response.on('data', (chunk: Buffer) => chunks.push(chunk));
        response.on('end', () => resolve(Buffer.concat(chunks)));
        response.on('error', reject);
      });

      request.on('error', reject);
      request.setTimeout(30000, () => {
        request.destroy();
        reject(new Error(`Timeout al descargar ${url}`));
      });
    });
  }
}
