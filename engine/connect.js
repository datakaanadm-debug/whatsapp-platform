/**
 * Script de conexión con reintentos automáticos.
 * Ejecutar: node connect.js
 *
 * Cuando aparezca "QR LISTO", escanea en:
 * http://localhost:3000/api/channels/3e9c7ac1-26c3-4bb4-8ce1-8f60b01919b6/qr.png
 */
const { default: makeWASocket, useMultiFileAuthState, makeCacheableSignalKeyStore, Browsers, DisconnectReason } = require('@whiskeysockets/baileys');
const path = require('path');
const Redis = require('ioredis');
const pino = require('pino');
require('dotenv').config();

const CHANNEL_ID = process.env.CHANNEL_ID || '3302d4a7-f181-452c-86fd-15abbeaa715f';
const SESS_DIR = path.resolve('./sessions/main');
let redis;
let attempt = 0;

async function connect() {
    attempt++;
    const { state, saveCreds } = await useMultiFileAuthState(SESS_DIR);
    if (!redis) redis = new Redis(process.env.REDIS_URL);
    const logger = pino({ level: 'silent' });

    // Número de teléfono para pairing code (alternativa al QR)
    const PHONE_NUMBER = process.env.PHONE_NUMBER || '';

    console.log(`[Intento ${attempt}] Conectando a WhatsApp... (sessDir: ${SESS_DIR}, phone: ${PHONE_NUMBER || 'QR mode'})`);

    const sock = makeWASocket({
        auth: { creds: state.creds, keys: makeCacheableSignalKeyStore(state.keys, logger) },
        browser: ['WhatsApp Platform', 'Chrome', '22.0'],
        logger,
    });

    sock.ev.on('creds.update', saveCreds);

    // Si hay número de teléfono, solicitar pairing code
    if (PHONE_NUMBER && !state.creds.registered) {
        setTimeout(async () => {
            try {
                const code = await sock.requestPairingCode(PHONE_NUMBER);
                console.log('');
                console.log('============================================');
                console.log(`  CODIGO DE VINCULACION: ${code}`);
                console.log('');
                console.log('  Abre WhatsApp > Dispositivos vinculados');
                console.log('  > Vincular dispositivo > Vincular con numero');
                console.log('  > Ingresa el codigo de arriba');
                console.log('============================================');
                console.log('');
                // Guardar en Redis para el dashboard
                await redis.set(`wa:pairing_code:${CHANNEL_ID}`, code, 'EX', 300);
            } catch (e) {
                console.error('Error solicitando pairing code:', e.message);
            }
        }, 3000);
    }

    sock.ev.on('connection.update', async (u) => {
        console.log('connection.update:', JSON.stringify({connection: u.connection, qr: !!u.qr, lastDisconnect: u.lastDisconnect?.error?.output?.statusCode}));
        if (u.qr) {
            await redis.set(`wa:qr:${CHANNEL_ID}`, u.qr, 'EX', 120);
            console.log('');
            console.log('============================================');
            console.log('  QR LISTO! Escanea en el dashboard:');
            console.log('  http://localhost:3000');
            console.log('  (Tab "Canal" -> "Conectar WhatsApp")');
            console.log('');
            console.log('  O directamente:');
            console.log(`  http://localhost:3000/api/channels/${CHANNEL_ID}/qr.png`);
            console.log('============================================');
            console.log('');
        }
        if (u.connection === 'open') {
            attempt = 0;
            console.log('');
            console.log('========================================');
            console.log('  CONECTADO! WhatsApp listo');
            console.log('  Envia mensajes para probar');
            console.log('========================================');
            await redis.set(`wa:status:${CHANNEL_ID}`, JSON.stringify({status:'connected',updated_at:new Date().toISOString()}));
        }
        if (u.connection === 'close') {
            const code = u.lastDisconnect?.error?.output?.statusCode;
            console.log(`Desconectado (code: ${code})`);

            if (code === 405 || code === 401) {
                // Rate limit de registro — NO reintentar automáticamente
                console.log('WhatsApp rechaza registro de nuevo dispositivo (cooldown activo).');
                console.log('Esperando comando manual start_session para reintentar...');
                require('fs').rmSync(SESS_DIR, { recursive: true, force: true });
                require('fs').mkdirSync(SESS_DIR, { recursive: true });
                // NO auto-retry — esperar comando manual via Redis
            } else if (code === 515 || code === 428 || code === 440) {
                console.log('Reconectando en 3s...');
                setTimeout(connect, 3000);
            } else {
                console.log('Reconectando en 5s...');
                setTimeout(connect, 5000);
            }
        }
    });

    // Mensajes entrantes -> Redis
    sock.ev.on('messages.upsert', async (m) => {
        for (const msg of m.messages) {
            if (msg.key.fromMe) continue;
            const text = msg.message?.conversation || msg.message?.extendedTextMessage?.text || '';
            if (!text) continue;
            console.log(`>>> ${msg.pushName || '?'}: ${text}`);
            await redis.lpush('wa:events:queue', JSON.stringify({
                event: 'message.received',
                channel: `wa:evt:${CHANNEL_ID}`,
                data: { channelId: CHANNEL_ID, remoteJid: msg.key.remoteJid, fromMe: false, pushName: msg.pushName || '', text, type: 'text' }
            }));
        }
    });

    // Comandos del bot -> WhatsApp
    pollCmds(sock);
}

// Polling global de comandos (funciona incluso cuando no hay sesión activa)
async function pollCmds(sock) {
    while (true) {
        try {
            const cmd = await redis.rpop('wa:cmd:queue');
            if (cmd) {
                const p = JSON.parse(cmd);
                if (p.command === 'start_session') {
                    console.log('Comando start_session recibido — reintentando conexion...');
                    connect();
                } else if (p.command === 'send_message' && p.data && sock) {
                    const jid = p.data.to.includes('@') ? p.data.to : p.data.to.replace(/[^0-9]/g, '') + '@s.whatsapp.net';
                    await sock.sendMessage(jid, { text: p.data.body });
                    console.log(`<<< Enviado a ${jid.split('@')[0]}`);
                }
            }
        } catch (e) { }
        await new Promise(r => setTimeout(r, 500));
    }
}

// Arrancar: conectar + polling
async function main() {
    if (!redis) redis = new Redis(process.env.REDIS_URL);
    // Iniciar polling de comandos (siempre activo)
    pollCmds(null);
    // Intentar conexión inicial
    connect();
}

main().catch(console.error);
