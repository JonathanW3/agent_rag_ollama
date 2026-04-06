"""
Script de bootstrap — crea la primera organización y genera su API key.

Uso:
    python bootstrap_org.py

Ejecutar UNA sola vez para inicializar el sistema.
El API key generado se muestra en pantalla — cópialo y guárdalo.
"""

import hashlib
import secrets
import sys
from datetime import datetime

try:
    import mysql.connector
except ImportError:
    print("ERROR: Instala mysql-connector-python:")
    print("  pip install mysql-connector-python")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import os

# ---------------------------------------------------------------------------
# Configuración — lee desde .env o usa defaults
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host":     os.getenv("MYSQL_HOST", "localhost"),
    "port":     int(os.getenv("MYSQL_PORT", "3306")),
    "user":     os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": "platform_db",
    "charset":  "utf8mb4",
}

ORG_NAME          = "Administración General"
COMPANY_LIC_COD   = "ADMIN-001"
KEY_LABEL         = "bootstrap"
MAX_AGENTS        = 100   # sin límite práctico para el admin


def generate_key_pair() -> tuple[str, str]:
    raw     = secrets.token_urlsafe(48)
    api_key = f"rag_{raw}"
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    return api_key, key_hash


def main():
    print("=" * 60)
    print("  RAG Ollama — Bootstrap de organización inicial")
    print("=" * 60)

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)

    # Verificar si ya existe la organización
    cursor.execute(
        "SELECT id FROM organizations WHERE company_lic_cod = %s",
        (COMPANY_LIC_COD,)
    )
    existing_org = cursor.fetchone()

    if existing_org:
        print(f"\nLa organización '{COMPANY_LIC_COD}' ya existe (id={existing_org['id']}).")
        print("Si necesitas una nueva API key usa el endpoint /organizations/{cod}/keys")
        print("con tu X-Master-Key.\n")
        cursor.close()
        conn.close()
        return

    api_key, key_hash = generate_key_pair()

    # Crear organización
    cursor.execute(
        "INSERT INTO organizations (name, company_lic_cod, max_agents) VALUES (%s, %s, %s)",
        (ORG_NAME, COMPANY_LIC_COD, MAX_AGENTS)
    )
    org_id = cursor.lastrowid

    # Crear API key
    cursor.execute(
        "INSERT INTO api_keys (org_id, label, api_key, key_hash) VALUES (%s, %s, %s, %s)",
        (org_id, KEY_LABEL, api_key, key_hash)
    )
    api_key_id = cursor.lastrowid

    conn.commit()
    cursor.close()
    conn.close()

    print(f"""
  Organización creada correctamente
  ─────────────────────────────────
  Nombre          : {ORG_NAME}
  Código          : {COMPANY_LIC_COD}
  org_id          : {org_id}
  api_key_id      : {api_key_id}
  Generada        : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

  ┌─────────────────────────────────────────────────────┐
  │  API KEY (cópiala ahora, no se puede recuperar)     │
  │                                                     │
  │  {api_key:<51} │
  └─────────────────────────────────────────────────────┘

  Pégala en el login del front_config para acceder.
  Para crear más organizaciones usa:
    POST /organizations  con header  X-Master-Key: {os.getenv('MASTER_KEY','(ver .env)')}
""")


if __name__ == "__main__":
    main()
