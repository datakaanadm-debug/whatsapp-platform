// src/event-mapper.ts — Mapeo de eventos de Baileys al formato de la plataforma
// Generado por AgentKit

import { proto, WAMessageKey, WAMessageUpdate, ConnectionState, GroupMetadata, Contact, Chat } from '@whiskeysockets/baileys';
import { logger } from './utils/logger';

/**
 * Estructura estándar de un evento de la plataforma.
 */
export interface PlatformEvent {
  event: string;
  data: Record<string, unknown>;
}

/**
 * Mapea la actualización de conexión de Baileys al formato de plataforma.
 */
export function mapConnectionUpdate(update: Partial<ConnectionState>): PlatformEvent {
  const { connection, lastDisconnect, qr, isNewLogin, isOnline } = update;

  return {
    event: 'connection.update',
    data: {
      connection: connection || null,
      qr: qr || null,
      isNewLogin: isNewLogin || false,
      isOnline: isOnline || false,
      lastDisconnect: lastDisconnect
        ? {
            reason: (lastDisconnect.error as any)?.output?.statusCode || 'unknown',
            message: lastDisconnect.error?.message || '',
          }
        : null,
    },
  };
}

/**
 * Mapea mensajes entrantes (upsert) al formato de plataforma.
 * Distingue entre mensajes recibidos y enviados.
 */
export function mapMessageUpsert(
  messages: proto.IWebMessageInfo[],
  type: 'notify' | 'append'
): PlatformEvent[] {
  const events: PlatformEvent[] = [];

  for (const msg of messages) {
    try {
      const normalized = normalizeMessageContent(msg);
      if (!normalized) continue;

      const isSent = msg.key.fromMe === true;
      events.push({
        event: isSent ? 'message.sent' : 'message.received',
        data: {
          ...normalized,
          upsertType: type,
        },
      });
    } catch (err) {
      logger.error({ err, messageId: msg.key?.id }, 'Error al mapear mensaje upsert');
    }
  }

  return events;
}

/**
 * Mapea actualizaciones de estado de mensajes (entregado, leído, etc.).
 */
export function mapMessageUpdate(updates: WAMessageUpdate[]): PlatformEvent[] {
  const events: PlatformEvent[] = [];

  for (const update of updates) {
    try {
      const statusMap: Record<number, string> = {
        0: 'error',
        1: 'pending',
        2: 'sent',       // SERVER_ACK
        3: 'delivered',   // DELIVERY_ACK
        4: 'read',        // READ
        5: 'played',      // PLAYED (para audios)
      };

      const statusCode = update.update?.status;
      const status = statusCode !== undefined && statusCode !== null ? statusMap[statusCode as number] || 'unknown' : undefined;

      events.push({
        event: 'message.status',
        data: {
          messageId: update.key.id || '',
          remoteJid: update.key.remoteJid || '',
          fromMe: update.key.fromMe || false,
          participant: update.key.participant || null,
          status: status || null,
          statusCode: statusCode ?? null,
          // Incluir cualquier otra actualización (ej: starred, pinned)
          ...(update.update?.starred !== undefined && { starred: update.update.starred }),
          ...(update.update?.messageStubType !== undefined && {
            stubType: update.update.messageStubType,
          }),
        },
      });
    } catch (err) {
      logger.error({ err }, 'Error al mapear actualización de mensaje');
    }
  }

  return events;
}

/**
 * Mapea actualizaciones de presencia (escribiendo, en línea, etc.).
 */
export function mapPresenceUpdate(update: {
  id: string;
  presences: Record<string, { lastKnownPresence: string; lastSeen?: number }>;
}): PlatformEvent {
  const presences: Record<string, unknown>[] = [];

  for (const [jid, presence] of Object.entries(update.presences)) {
    presences.push({
      jid,
      presence: presence.lastKnownPresence,
      lastSeen: presence.lastSeen || null,
    });
  }

  return {
    event: 'presence.update',
    data: {
      chatId: update.id,
      presences,
    },
  };
}

/**
 * Mapea actualizaciones de grupos.
 */
export function mapGroupUpdate(updates: Partial<GroupMetadata>[]): PlatformEvent[] {
  return updates.map((update) => ({
    event: 'group.update',
    data: {
      groupId: update.id || null,
      subject: update.subject || null,
      description: update.desc || null,
      participants: update.participants?.map((p) => ({
        jid: p.id,
        admin: p.admin || null,
      })) || null,
      size: update.size || null,
      owner: update.owner || null,
      restrict: update.restrict || null,
      announce: update.announce || null,
    },
  }));
}

/**
 * Mapea actualizaciones de contactos.
 */
export function mapContactUpdate(updates: Partial<Contact>[]): PlatformEvent[] {
  return updates.map((contact) => ({
    event: 'contact.update',
    data: {
      jid: contact.id || null,
      name: contact.name || null,
      notify: contact.notify || null,
      verifiedName: contact.verifiedName || null,
      imgUrl: contact.imgUrl || null,
      status: contact.status || null,
    },
  }));
}

/**
 * Mapea actualizaciones de chats.
 */
export function mapChatUpdate(updates: Partial<Chat>[]): PlatformEvent[] {
  return updates.map((chat) => ({
    event: 'chat.update',
    data: {
      chatId: chat.id || null,
      name: chat.name || null,
      unreadCount: chat.unreadCount ?? null,
      archived: chat.archived || false,
      pinned: chat.pinned || null,
      muted: (chat as any).mute || null,
      readOnly: chat.readOnly || false,
      conversationTimestamp: chat.conversationTimestamp || null,
    },
  }));
}

/**
 * Normaliza el contenido de un mensaje de Baileys al formato estándar de la plataforma.
 */
function normalizeMessageContent(raw: proto.IWebMessageInfo): Record<string, unknown> | null {
  const key = raw.key;
  if (!key || !key.remoteJid) return null;

  const msg = raw.message;
  if (!msg) return null;

  const base: Record<string, unknown> = {
    messageId: key.id || '',
    remoteJid: key.remoteJid,
    fromMe: key.fromMe || false,
    participant: key.participant || null,
    pushName: raw.pushName || null,
    timestamp: typeof raw.messageTimestamp === 'number'
      ? raw.messageTimestamp
      : Number(raw.messageTimestamp) || Date.now() / 1000,
    isGroup: key.remoteJid.endsWith('@g.us'),
  };

  // Texto simple
  if (msg.conversation) {
    return { ...base, type: 'text', text: msg.conversation };
  }

  // Texto extendido (con enlaces, menciones, etc.)
  if (msg.extendedTextMessage) {
    return {
      ...base,
      type: 'text',
      text: msg.extendedTextMessage.text || '',
      contextInfo: extractContextInfo(msg.extendedTextMessage.contextInfo),
      matchedText: msg.extendedTextMessage.matchedText || null,
      canonicalUrl: (msg.extendedTextMessage as any).canonicalUrl || null,
      title: msg.extendedTextMessage.title || null,
      description: msg.extendedTextMessage.description || null,
    };
  }

  // Imagen
  if (msg.imageMessage) {
    return {
      ...base,
      type: 'image',
      caption: msg.imageMessage.caption || '',
      mimeType: msg.imageMessage.mimetype || 'image/jpeg',
      fileLength: Number(msg.imageMessage.fileLength) || 0,
      width: msg.imageMessage.width || 0,
      height: msg.imageMessage.height || 0,
      mediaKey: msg.imageMessage.mediaKey ? Buffer.from(msg.imageMessage.mediaKey).toString('base64') : null,
      directPath: msg.imageMessage.directPath || null,
      url: msg.imageMessage.url || null,
      contextInfo: extractContextInfo(msg.imageMessage.contextInfo),
      hasMedia: true,
    };
  }

  // Video
  if (msg.videoMessage) {
    return {
      ...base,
      type: 'video',
      caption: msg.videoMessage.caption || '',
      mimeType: msg.videoMessage.mimetype || 'video/mp4',
      fileLength: Number(msg.videoMessage.fileLength) || 0,
      seconds: msg.videoMessage.seconds || 0,
      mediaKey: msg.videoMessage.mediaKey ? Buffer.from(msg.videoMessage.mediaKey).toString('base64') : null,
      directPath: msg.videoMessage.directPath || null,
      url: msg.videoMessage.url || null,
      contextInfo: extractContextInfo(msg.videoMessage.contextInfo),
      hasMedia: true,
    };
  }

  // Audio / nota de voz
  if (msg.audioMessage) {
    return {
      ...base,
      type: msg.audioMessage.ptt ? 'ptt' : 'audio',
      mimeType: msg.audioMessage.mimetype || 'audio/ogg',
      fileLength: Number(msg.audioMessage.fileLength) || 0,
      seconds: msg.audioMessage.seconds || 0,
      ptt: msg.audioMessage.ptt || false,
      mediaKey: msg.audioMessage.mediaKey ? Buffer.from(msg.audioMessage.mediaKey).toString('base64') : null,
      directPath: msg.audioMessage.directPath || null,
      url: msg.audioMessage.url || null,
      hasMedia: true,
    };
  }

  // Documento
  if (msg.documentMessage) {
    return {
      ...base,
      type: 'document',
      caption: msg.documentMessage.caption || '',
      mimeType: msg.documentMessage.mimetype || 'application/octet-stream',
      fileName: msg.documentMessage.fileName || 'document',
      fileLength: Number(msg.documentMessage.fileLength) || 0,
      mediaKey: msg.documentMessage.mediaKey ? Buffer.from(msg.documentMessage.mediaKey).toString('base64') : null,
      directPath: msg.documentMessage.directPath || null,
      url: msg.documentMessage.url || null,
      contextInfo: extractContextInfo(msg.documentMessage.contextInfo),
      hasMedia: true,
    };
  }

  // Sticker
  if (msg.stickerMessage) {
    return {
      ...base,
      type: 'sticker',
      mimeType: msg.stickerMessage.mimetype || 'image/webp',
      isAnimated: msg.stickerMessage.isAnimated || false,
      mediaKey: msg.stickerMessage.mediaKey ? Buffer.from(msg.stickerMessage.mediaKey).toString('base64') : null,
      directPath: msg.stickerMessage.directPath || null,
      url: msg.stickerMessage.url || null,
      hasMedia: true,
    };
  }

  // Ubicación
  if (msg.locationMessage) {
    return {
      ...base,
      type: 'location',
      latitude: msg.locationMessage.degreesLatitude || 0,
      longitude: msg.locationMessage.degreesLongitude || 0,
      name: msg.locationMessage.name || null,
      address: msg.locationMessage.address || null,
      url: msg.locationMessage.url || null,
    };
  }

  // Ubicación en vivo
  if (msg.liveLocationMessage) {
    return {
      ...base,
      type: 'live_location',
      latitude: msg.liveLocationMessage.degreesLatitude || 0,
      longitude: msg.liveLocationMessage.degreesLongitude || 0,
      caption: msg.liveLocationMessage.caption || '',
      sequenceNumber: msg.liveLocationMessage.sequenceNumber || 0,
    };
  }

  // Contacto
  if (msg.contactMessage) {
    return {
      ...base,
      type: 'contact',
      displayName: msg.contactMessage.displayName || '',
      vcard: msg.contactMessage.vcard || '',
    };
  }

  // Múltiples contactos
  if (msg.contactsArrayMessage) {
    return {
      ...base,
      type: 'contacts_array',
      displayName: msg.contactsArrayMessage.displayName || '',
      contacts: (msg.contactsArrayMessage.contacts || []).map((c) => ({
        displayName: c.displayName || '',
        vcard: c.vcard || '',
      })),
    };
  }

  // Encuesta (poll)
  if (msg.pollCreationMessage || msg.pollCreationMessageV2 || msg.pollCreationMessageV3) {
    const poll = msg.pollCreationMessage || msg.pollCreationMessageV2 || msg.pollCreationMessageV3;
    return {
      ...base,
      type: 'poll',
      title: poll?.name || '',
      options: (poll?.options || []).map((o) => o.optionName || ''),
      selectableCount: poll?.selectableOptionsCount || 1,
    };
  }

  // Actualización de voto en encuesta
  if (msg.pollUpdateMessage) {
    return {
      ...base,
      type: 'poll_update',
      pollCreationMessageKey: msg.pollUpdateMessage.pollCreationMessageKey || null,
      vote: msg.pollUpdateMessage.vote || null,
    };
  }

  // Reacción
  if (msg.reactionMessage) {
    return {
      ...base,
      type: 'reaction',
      targetMessageId: msg.reactionMessage.key?.id || null,
      emoji: msg.reactionMessage.text || '',
    };
  }

  // Mensaje protocolo (eliminar, editar, etc.)
  if (msg.protocolMessage) {
    const protoType = msg.protocolMessage.type;
    if (protoType === proto.Message.ProtocolMessage.Type.REVOKE) {
      return {
        ...base,
        type: 'message_revoke',
        revokedMessageId: msg.protocolMessage.key?.id || null,
      };
    }
    if (protoType === proto.Message.ProtocolMessage.Type.MESSAGE_EDIT) {
      const editedMsg = msg.protocolMessage.editedMessage;
      return {
        ...base,
        type: 'message_edit',
        editedMessageId: msg.protocolMessage.key?.id || null,
        newText: editedMsg?.conversation || editedMsg?.extendedTextMessage?.text || '',
      };
    }
    // Otros tipos de protocolo los ignoramos
    return null;
  }

  // Mensaje de botón / template (respuestas rápidas)
  if (msg.buttonsResponseMessage) {
    return {
      ...base,
      type: 'button_response',
      selectedButtonId: msg.buttonsResponseMessage.selectedButtonId || '',
      selectedDisplayText: msg.buttonsResponseMessage.selectedDisplayText || '',
      contextInfo: extractContextInfo(msg.buttonsResponseMessage.contextInfo),
    };
  }

  // Lista de respuestas
  if (msg.listResponseMessage) {
    return {
      ...base,
      type: 'list_response',
      title: msg.listResponseMessage.title || '',
      selectedRowId: msg.listResponseMessage.singleSelectReply?.selectedRowId || '',
      description: msg.listResponseMessage.description || '',
    };
  }

  // Tipo no reconocido — incluir lo que hay disponible
  logger.debug({ messageTypes: Object.keys(msg) }, 'Tipo de mensaje no mapeado');
  return {
    ...base,
    type: 'unknown',
    rawTypes: Object.keys(msg),
  };
}

/**
 * Extrae información de contexto (respuestas, menciones, etc.)
 */
function extractContextInfo(
  contextInfo?: proto.IContextInfo | null
): Record<string, unknown> | null {
  if (!contextInfo) return null;

  return {
    quotedMessageId: contextInfo.stanzaId || null,
    quotedParticipant: contextInfo.participant || null,
    mentionedJids: contextInfo.mentionedJid || [],
    isForwarded: contextInfo.isForwarded || false,
    forwardingScore: contextInfo.forwardingScore || 0,
  };
}
