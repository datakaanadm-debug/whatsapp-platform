// redis-auth-state.ts — Persistencia de sesion Baileys en Redis
// Sobrevive redeploys en Railway (filesystem es efimero)

import fs from 'fs/promises';
import path from 'path';
import Redis from 'ioredis';
import { useMultiFileAuthState, AuthenticationState } from '@whiskeysockets/baileys';

const AUTH_KEY_PREFIX = 'wa:auth:';

/**
 * Envuelve useMultiFileAuthState, pero sincroniza el directorio con Redis.
 * - Al iniciar: descarga los archivos desde Redis al disco
 * - Al guardar credenciales: sube los archivos a Redis
 */
export async function useRedisBackedAuthState(
  channelId: string,
  redis: Redis,
  sessDir: string,
): Promise<{ state: AuthenticationState; saveCreds: () => Promise<void> }> {
  const redisKey = `${AUTH_KEY_PREFIX}${channelId}`;

  // 1. Crear directorio local
  await fs.mkdir(sessDir, { recursive: true });

  // 2. Descargar sesion de Redis al disco (si existe)
  const snapshot = await redis.hgetall(redisKey);
  if (snapshot && Object.keys(snapshot).length > 0) {
    console.log(`[auth-redis] Restaurando ${Object.keys(snapshot).length} archivos de sesion desde Redis`);
    for (const [filename, content] of Object.entries(snapshot)) {
      await fs.writeFile(path.join(sessDir, filename), content, 'utf-8');
    }
  } else {
    console.log(`[auth-redis] No hay sesion previa en Redis para ${channelId}`);
  }

  // 3. Usar auth state normal de Baileys
  const { state, saveCreds: originalSaveCreds } = await useMultiFileAuthState(sessDir);

  // 4. Wrapper de saveCreds que sube todo a Redis
  const saveCreds = async () => {
    await originalSaveCreds();
    try {
      const files = await fs.readdir(sessDir);
      const pipeline = redis.pipeline();
      for (const file of files) {
        const content = await fs.readFile(path.join(sessDir, file), 'utf-8');
        pipeline.hset(redisKey, file, content);
      }
      await pipeline.exec();
    } catch (err) {
      console.error('[auth-redis] Error guardando en Redis:', err);
    }
  };

  return { state, saveCreds };
}

/**
 * Borra la sesion de Redis (usado al hacer logout).
 */
export async function clearRedisAuthState(channelId: string, redis: Redis): Promise<void> {
  await redis.del(`${AUTH_KEY_PREFIX}${channelId}`);
}
