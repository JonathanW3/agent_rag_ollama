"""
Script de validación de conexión IMAP.

Ejecutar antes de levantar el servidor MCP para confirmar que las credenciales
y los nombres de carpetas son correctos.

Uso:
    python -m mcp_imap_facturas.test_connection
  o desde la raíz del proyecto:
    python mcp_imap_facturas/test_connection.py
"""

import os
import sys

# Asegurar que la raíz del proyecto está en sys.path cuando se ejecuta directamente
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

IMAP_SERVER   = os.getenv("IMAP_SERVER", "")
IMAP_PORT     = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER     = os.getenv("IMAP_USER", "")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", "")


def check_env() -> bool:
    missing = [v for v in ("IMAP_SERVER", "IMAP_USER", "IMAP_PASSWORD") if not os.getenv(v)]
    if missing:
        print(f"[ERROR] Variables de entorno faltantes: {', '.join(missing)}")
        print("        Copia mcp_imap_facturas/.env.example a .env y completa los valores.")
        return False
    print(f"[OK] Credenciales encontradas para {IMAP_USER} en {IMAP_SERVER}:{IMAP_PORT}")
    return True


def test_connection() -> None:
    from imap_tools import MailBox, AND

    print("\n=== Test de conexión IMAP ===\n")

    if not check_env():
        sys.exit(1)

    print(f"Conectando a {IMAP_SERVER}:{IMAP_PORT} como {IMAP_USER} ...")

    try:
        with MailBox(IMAP_SERVER, IMAP_PORT).login(IMAP_USER, IMAP_PASSWORD) as mb:
            print("[OK] Conexión y autenticación exitosas.\n")

            # ── Listar carpetas ───────────────────────────────────────────────
            folders = list(mb.folder.list())
            print(f"Carpetas disponibles ({len(folders)}):")
            for f in sorted(folders, key=lambda x: x.name):
                print(f"  · {f.name}")

            # ── Últimos 5 emails del INBOX ────────────────────────────────────
            print("\n--- Últimos 5 emails en INBOX ---")
            mb.folder.set("INBOX")
            count = 0
            for msg in mb.fetch(AND(all=True), mark_seen=False, reverse=True, limit=5):
                print(f"  [{msg.uid}] {msg.date}  De: {msg.from_:<35} Asunto: {msg.subject[:60]}")
                count += 1
            if count == 0:
                print("  (bandeja vacía)")

            # ── Últimos 5 emails de Sent ──────────────────────────────────────
            sent_candidates = [
                name for name in (f.name for f in folders)
                if any(k in name.lower() for k in ("sent", "enviado", "envi"))
            ]
            if sent_candidates:
                sent_folder = sent_candidates[0]
                print(f"\n--- Últimos 5 emails en '{sent_folder}' ---")
                mb.folder.set(sent_folder)
                count = 0
                for msg in mb.fetch(AND(all=True), mark_seen=False, reverse=True, limit=5):
                    to_str = ", ".join(msg.to)[:40]
                    print(f"  [{msg.uid}] {msg.date}  Para: {to_str:<40} Asunto: {msg.subject[:50]}")
                    count += 1
                if count == 0:
                    print("  (carpeta vacía)")
            else:
                print(
                    "\n[AVISO] No se encontró carpeta de Enviados automáticamente. "
                    "Busca el nombre correcto en la lista de carpetas de arriba y "
                    "úsalo en list_recipients_in_period / compare_periods."
                )

    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        print("\nPosibles causas:")
        print("  · Contraseña incorrecta o cuenta bloqueada")
        print("  · IMAP deshabilitado en el servidor (activar en configuración de la cuenta)")
        print("  · Puerto o servidor incorrecto")
        print("  · Firewall bloqueando el puerto 993")
        sys.exit(1)

    print("\n[OK] Test completado. El servidor MCP está listo para usarse.")


if __name__ == "__main__":
    test_connection()
