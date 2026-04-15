# api/app/utils/security.py — Funciones de seguridad: API keys, HMAC, webhook signing
# Utilidades criptograficas reutilizables en toda la plataforma

import secrets
import hashlib
import hmac
import json


def generate_api_key() -> str:
    """
    Genera una API key segura con prefijo 'ak_' y 24 bytes aleatorios en hex.
    Formato: ak_<48 caracteres hex>
    """
    return "ak_" + secrets.token_hex(24)


def hash_api_key(key: str) -> str:
    """
    Genera un hash SHA-256 de la API key para almacenamiento seguro.
    Nunca se guarda la key en texto plano en la base de datos.
    """
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key_hash(key: str, key_hash: str) -> bool:
    """
    Verifica que una API key coincida con su hash almacenado.
    Usa comparacion de tiempo constante para prevenir timing attacks.
    """
    return hmac.compare_digest(hash_api_key(key), key_hash)


def generate_webhook_secret() -> str:
    """
    Genera un secreto aleatorio de 16 bytes en hex para firmar payloads de webhooks.
    Se asigna a cada webhook al momento de su creacion.
    """
    return secrets.token_hex(16)


def sign_webhook_payload(payload: dict, secret: str) -> str:
    """
    Firma un payload de webhook usando HMAC-SHA256.
    El receptor puede verificar la firma para confirmar la autenticidad del evento.

    Args:
        payload: Diccionario con los datos del evento
        secret: Secreto compartido entre la plataforma y el receptor

    Returns:
        Firma HMAC-SHA256 en formato hexadecimal
    """
    payload_bytes = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


def verify_webhook_signature(payload: dict, secret: str, signature: str) -> bool:
    """
    Verifica la firma HMAC de un payload de webhook.
    Usa comparacion de tiempo constante para prevenir timing attacks.

    Args:
        payload: Diccionario con los datos recibidos
        secret: Secreto compartido
        signature: Firma recibida en la cabecera del request

    Returns:
        True si la firma es valida
    """
    expected = sign_webhook_payload(payload, secret)
    return hmac.compare_digest(expected, signature)
