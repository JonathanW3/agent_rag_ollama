"""
Script de migración — registra en platform_db las organizaciones
que ya existen en Redis (campo organization de los agentes).

Uso:
    python migrate_orgs.py

Por cada organización encontrada en Redis que NO esté en platform_db:
  - La crea con max_agents=10 (editable abajo)
  - Genera un API key
  - Muestra el key en pantalla (única oportunidad de verlo)

Las organizaciones que ya existen en platform_db se omiten.
"""

import hashlib
import json
import re
import secrets
import sys
from datetime import datetime

try:
    import redis as redis_lib
except ImportError:
    print("ERROR: pip install redis")
    sys.exit(1)

try:
    import mysql.connector
except ImportError:
    print("ERROR: pip install mysql-connector-python")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import os

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", "6379")),
    "db":   int(os.getenv("REDIS_DB", "0")),
    "decode_responses": True,
}

DB_CONFIG = {
    "host":     os.getenv("MYSQL_HOST", "localhost"),
    "port":     int(os.getenv("MYSQL_PORT", "3306")),
    "user":     os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": "platform_db",
    "charset":  "utf8mb4",
    "autocommit": True,
}

DEFAULT_MAX_AGENTS = 10
KEY_LABEL = "migrado"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_key_pair() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    api_key = f"rag_{raw}"
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    return api_key, key_hash


def to_company_lic_cod(name: str) -> str:
    """
    Convierte el nombre de organización de Redis al formato de company_lic_cod.
    Ej: 'Farmacia Demo' → 'FARMACIA-DEMO', 'PART AUTOS' → 'PART-AUTOS'
    Trunca a 32 caracteres.
    """
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name.strip()).upper().strip("-")
    return slug[:32]


def get_redis_organizations(r) -> dict[str, int]:
    """Lee todos los agentes de Redis y agrupa por organization → count."""
    org_counts: dict[str, int] = {}
    for key in r.scan_iter("agent:*"):
        data = r.get(key)
        if data:
            try:
                agent = json.loads(data)
                org = agent.get("organization")
                if org and org.strip():
                    org_counts[org.strip()] = org_counts.get(org.strip(), 0) + 1
            except Exception:
                pass
    return org_counts


def get_existing_orgs(cursor) -> set[str]:
    """Retorna el conjunto de company_lic_cod ya registrados en platform_db."""
    cursor.execute("SELECT company_lic_cod FROM organizations")
    return {row["company_lic_cod"] for row in cursor.fetchall()}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  RAG Ollama — Migración de organizaciones Redis → MySQL")
    print("=" * 60)

    # Conectar Redis
    r = redis_lib.Redis(**REDIS_CONFIG)
    try:
        r.ping()
    except Exception as e:
        print(f"\nERROR: No se pudo conectar a Redis: {e}")
        sys.exit(1)

    # Conectar MySQL
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)

    # Leer organizaciones de Redis
    redis_orgs = get_redis_organizations(r)
    if not redis_orgs:
        print("\nNo se encontraron organizaciones en Redis.")
        cursor.close()
        conn.close()
        return

    print(f"\nOrganizaciones encontradas en Redis: {len(redis_orgs)}")
    for name, count in sorted(redis_orgs.items()):
        print(f"  · {name!r:40s} ({count} agente{'s' if count != 1 else ''})")

    # Organizaciones ya registradas en MySQL
    existing = get_existing_orgs(cursor)
    print(f"\nYa registradas en platform_db: {existing or '(ninguna aparte de ADMIN-001)'}")

    # Determinar cuáles faltan
    to_migrate = {
        name: count for name, count in redis_orgs.items()
        if to_company_lic_cod(name) not in existing
    }

    if not to_migrate:
        print("\nTodas las organizaciones ya están registradas. Nada que migrar.")
        cursor.close()
        conn.close()
        return

    print(f"\nA migrar: {len(to_migrate)}")
    print("-" * 60)

    results = []

    for org_name, agent_count in sorted(to_migrate.items()):
        cod = to_company_lic_cod(org_name)

        # Si el cod colisiona (ej. dos orgs dan el mismo slug), añadir sufijo
        base_cod = cod
        suffix = 1
        while cod in existing:
            cod = f"{base_cod[:29]}-{suffix:02d}"
            suffix += 1

        api_key, key_hash = generate_key_pair()

        # Insertar organización
        cursor.execute(
            "INSERT INTO organizations (name, company_lic_cod, max_agents) VALUES (%s, %s, %s)",
            (org_name, cod, DEFAULT_MAX_AGENTS)
        )
        org_id = cursor.lastrowid

        # Insertar API key
        cursor.execute(
            "INSERT INTO api_keys (org_id, label, api_key, key_hash) VALUES (%s, %s, %s, %s)",
            (org_id, KEY_LABEL, api_key, key_hash)
        )

        existing.add(cod)  # evitar colisiones en la misma ejecución

        results.append({
            "org_name":         org_name,
            "company_lic_cod":  cod,
            "org_id":           org_id,
            "agent_count":      agent_count,
            "api_key":          api_key,
        })

        print(f"  ✓ {org_name!r} → {cod}")

    print("\n" + "=" * 60)
    print("  API KEYS GENERADAS (cópialas ahora, no se pueden recuperar)")
    print("=" * 60)

    for r_item in results:
        print(f"""
  Organización : {r_item['org_name']}
  Código       : {r_item['company_lic_cod']}
  Agentes      : {r_item['agent_count']}
  API Key      : {r_item['api_key']}
""")

    print(f"Migración completada: {len(results)} organización(es) registrada(s).")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
