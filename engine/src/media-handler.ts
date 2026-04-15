// src/media-handler.ts — Descarga y gestión de archivos multimedia
// Generado por AgentKit

import { downloadMediaMessage, WASocket, proto } from '@whiskeysockets/baileys';
import fs from 'fs/promises';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import { config } from './config';
import { logger } from './utils/logger';

/**
 * Extensiones por tipo MIME para nombrar archivos descargados.
 */
const MIME_EXTENSIONS: Record<string, string> = {
  'image/jpeg': '.jpg',
  'image/png': '.png',
  'image/webp': '.webp',
  'image/gif': '.gif',
  'video/mp4': '.mp4',
  'video/3gpp': '.3gp',
  'audio/ogg': '.ogg',
  'audio/ogg; codecs=opus': '.ogg',
  'audio/mpeg': '.mp3',
  'audio/mp4': '.m4a',
  'application/pdf': '.pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
  'application/zip': '.zip',
  'text/plain': '.txt',
};

/**
 * MediaHandler gestiona la descarga y almacenamiento de archivos multimedia
 * recibidos en mensajes de WhatsApp.
 */
export class MediaHandler {
  /**
   * Asegura que el directorio de media para un canal exista.
   */
  private async ensureMediaDir(channelId: string): Promise<string> {
    const dir = path.join(config.MEDIA_DIR, channelId);
    await fs.mkdir(dir, { recursive: true });
    return dir;
  }

  /**
   * Descarga el contenido multimedia de un mensaje de WhatsApp.
   * Retorna el buffer con los datos binarios.
   */
  async downloadMedia(message: proto.IWebMessageInfo): Promise<Buffer | null> {
    try {
      const buffer = await downloadMediaMessage(
        message,
        'buffer',
        {},
      );
      return buffer as Buffer;
    } catch (err) {
      logger.error({ err, messageId: message.key?.id }, 'Error al descargar multimedia');
      return null;
    }
  }

  /**
   * Guarda un buffer multimedia en el sistema de archivos.
   * Retorna la ruta relativa del archivo guardado.
   *
   * @param channelId ID del canal/sesión
   * @param mediaKey Identificador único del medio (o se genera uno)
   * @param buffer Datos binarios del archivo
   * @param mimeType Tipo MIME del archivo
   * @returns Ruta relativa al archivo guardado
   */
  async saveMedia(
    channelId: string,
    mediaKey: string | null,
    buffer: Buffer,
    mimeType: string
  ): Promise<string> {
    const dir = await this.ensureMediaDir(channelId);
    const ext = MIME_EXTENSIONS[mimeType] || this.guessExtension(mimeType);
    const fileName = `${mediaKey || uuidv4()}${ext}`;
    const filePath = path.join(dir, fileName);

    try {
      await fs.writeFile(filePath, buffer);
      logger.debug({ channelId, fileName, size: buffer.length }, 'Multimedia guardado');

      // Retorna ruta relativa para portabilidad
      return path.relative(config.MEDIA_DIR, filePath);
    } catch (err) {
      logger.error({ err, filePath }, 'Error al guardar multimedia');
      throw err;
    }
  }

  /**
   * Obtiene la ruta absoluta de un archivo multimedia.
   */
  getMediaPath(channelId: string, mediaKey: string): string {
    return path.join(config.MEDIA_DIR, channelId, mediaKey);
  }

  /**
   * Lee un archivo multimedia del disco como buffer.
   */
  async readMedia(channelId: string, mediaKey: string): Promise<Buffer | null> {
    try {
      const filePath = this.getMediaPath(channelId, mediaKey);
      return await fs.readFile(filePath);
    } catch (err) {
      logger.error({ err, channelId, mediaKey }, 'Error al leer multimedia');
      return null;
    }
  }

  /**
   * Descarga multimedia de un mensaje y lo guarda automáticamente.
   * Combina downloadMedia + saveMedia en un solo paso.
   */
  async downloadAndSave(
    channelId: string,
    message: proto.IWebMessageInfo
  ): Promise<{ path: string; mimeType: string; size: number } | null> {
    const msg = message.message;
    if (!msg) return null;

    // Determinar tipo MIME según el tipo de mensaje
    let mimeType = 'application/octet-stream';
    if (msg.imageMessage) mimeType = msg.imageMessage.mimetype || 'image/jpeg';
    else if (msg.videoMessage) mimeType = msg.videoMessage.mimetype || 'video/mp4';
    else if (msg.audioMessage) mimeType = msg.audioMessage.mimetype || 'audio/ogg';
    else if (msg.documentMessage) mimeType = msg.documentMessage.mimetype || 'application/octet-stream';
    else if (msg.stickerMessage) mimeType = msg.stickerMessage.mimetype || 'image/webp';

    const buffer = await this.downloadMedia(message);
    if (!buffer) return null;

    const mediaId = message.key.id || uuidv4();
    const relativePath = await this.saveMedia(channelId, mediaId, buffer, mimeType);

    return {
      path: relativePath,
      mimeType,
      size: buffer.length,
    };
  }

  /**
   * Elimina un archivo multimedia del disco.
   */
  async deleteMedia(channelId: string, mediaKey: string): Promise<boolean> {
    try {
      const filePath = this.getMediaPath(channelId, mediaKey);
      await fs.unlink(filePath);
      logger.debug({ channelId, mediaKey }, 'Multimedia eliminado');
      return true;
    } catch (err) {
      logger.error({ err, channelId, mediaKey }, 'Error al eliminar multimedia');
      return false;
    }
  }

  /**
   * Limpia todos los archivos multimedia de un canal.
   */
  async cleanChannelMedia(channelId: string): Promise<void> {
    try {
      const dir = path.join(config.MEDIA_DIR, channelId);
      await fs.rm(dir, { recursive: true, force: true });
      logger.info({ channelId }, 'Multimedia del canal limpiado');
    } catch (err) {
      logger.error({ err, channelId }, 'Error al limpiar multimedia del canal');
    }
  }

  /**
   * Intenta adivinar la extensión de archivo a partir del MIME type.
   */
  private guessExtension(mimeType: string): string {
    const parts = mimeType.split('/');
    if (parts.length === 2) {
      const sub = parts[1].split(';')[0].trim();
      return `.${sub}`;
    }
    return '.bin';
  }
}
