#!/usr/bin/env python3
"""
Muestra el QR de WhatsApp en la terminal para que puedas escanearlo.
Uso: python scripts/show_qr.py
"""
import sys
import os
import httpx

API_URL = os.getenv("API_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "ak_332a141604bf5355b67be9efba622f6951d84a7c891d680d")
CHANNEL_ID = os.getenv("CHANNEL_ID", "3e9c7ac1-26c3-4bb4-8ce1-8f60b01919b6")

def main():
    headers = {"X-API-Key": API_KEY}

    # Obtener QR
    print("Obteniendo QR de WhatsApp...")
    r = httpx.get(f"{API_URL}/api/channels/{CHANNEL_ID}/qr", headers=headers)

    if r.status_code != 200:
        print(f"Error: {r.status_code} — {r.text}")
        print("\nAsegúrate de haber ejecutado POST /api/channels/{id}/start primero")
        sys.exit(1)

    data = r.json()
    qr_raw = data.get("data")

    if not qr_raw:
        print("QR no disponible. Ejecuta primero:")
        print(f"  curl -X POST -H 'X-API-Key: {API_KEY}' {API_URL}/api/channels/{CHANNEL_ID}/start")
        sys.exit(1)

    # Mostrar en terminal con qrcode
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=1, border=1)
        qr.add_data(qr_raw)
        qr.make(fit=True)

        print("\n" + "=" * 50)
        print("  Escanea este QR con WhatsApp")
        print("  (WhatsApp > Dispositivos vinculados > Vincular)")
        print("=" * 50 + "\n")

        # Usar caracteres ASCII compatibles con Windows
        matrix = qr.get_matrix()
        for row in matrix:
            line = ""
            for cell in row:
                line += "##" if cell else "  "
            print(line)

        print("\n" + "=" * 50)
        print("  Esperando conexión...")
        print("  El QR expira en 60 segundos")
        print("=" * 50)

    except ImportError:
        print("QR raw data:")
        print(qr_raw)
        print("\nInstala qrcode: pip install qrcode")


if __name__ == "__main__":
    main()
