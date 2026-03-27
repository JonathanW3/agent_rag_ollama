"""
Capa de datos WhatsApp en Redis.

Almacena la vinculación organización → sesión WhatsApp,
y el mapeo número telefónico → agente.

Claves Redis:
  whatsapp:org:{organization}          → JSON {wa_session_id, default_agent_id, created_at, updated_at}
  whatsapp:numbers:{organization}      → Hash  phone_number → agent_id
  whatsapp:session_map:{wa_session_id} → string  organization  (lookup inverso)
"""

import json
from datetime import datetime, timezone
from .redis_client import get_redis_client


def _org_key(organization: str) -> str:
    return f"whatsapp:org:{organization}"


def _numbers_key(organization: str) -> str:
    return f"whatsapp:numbers:{organization}"


def _session_map_key(wa_session_id: str) -> str:
    return f"whatsapp:session_map:{wa_session_id}"


# ── Vinculación organización ↔ sesión WA ─────────────────

def link_session(organization: str, wa_session_id: str, default_agent_id: str = "default") -> dict:
    """Vincula una sesión de WhatsApp a una organización."""
    client = get_redis_client()

    now = datetime.now(timezone.utc).isoformat()
    data = {
        "organization": organization,
        "wa_session_id": wa_session_id,
        "default_agent_id": default_agent_id,
        "created_at": now,
        "updated_at": now,
    }

    client.set(_org_key(organization), json.dumps(data))
    # Lookup inverso: session_id → organización
    client.set(_session_map_key(wa_session_id), organization)
    return data


def get_org_config(organization: str) -> dict | None:
    """Obtiene la configuración WhatsApp de una organización."""
    client = get_redis_client()
    raw = client.get(_org_key(organization))
    return json.loads(raw) if raw else None


def get_org_by_session(wa_session_id: str) -> str | None:
    """Resuelve la organización a partir de un session_id de WhatsApp."""
    client = get_redis_client()
    return client.get(_session_map_key(wa_session_id))


def update_default_agent(organization: str, default_agent_id: str) -> dict:
    """Actualiza el agente por defecto de una organización."""
    client = get_redis_client()
    raw = client.get(_org_key(organization))
    if not raw:
        raise ValueError(f"La organización '{organization}' no tiene WhatsApp vinculado")

    data = json.loads(raw)
    data["default_agent_id"] = default_agent_id
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    client.set(_org_key(organization), json.dumps(data))
    return data


def unlink_session(organization: str) -> bool:
    """Desvincula WhatsApp de una organización y limpia datos."""
    client = get_redis_client()
    raw = client.get(_org_key(organization))
    if not raw:
        return False

    data = json.loads(raw)
    wa_session_id = data.get("wa_session_id")

    # Eliminar lookup inverso
    if wa_session_id:
        client.delete(_session_map_key(wa_session_id))

    # Eliminar números registrados
    client.delete(_numbers_key(organization))

    # Eliminar config
    client.delete(_org_key(organization))
    return True


def list_whatsapp_orgs() -> list[dict]:
    """Lista todas las organizaciones con WhatsApp vinculado."""
    client = get_redis_client()
    orgs = []
    for key in client.scan_iter("whatsapp:org:*"):
        raw = client.get(key)
        if raw:
            orgs.append(json.loads(raw))
    orgs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return orgs


# ── Mapeo número → agente ────────────────────────────────

def register_number(organization: str, phone_number: str, agent_id: str) -> dict:
    """Registra un número telefónico con un agente específico."""
    client = get_redis_client()

    if not client.exists(_org_key(organization)):
        raise ValueError(f"La organización '{organization}' no tiene WhatsApp vinculado")

    client.hset(_numbers_key(organization), phone_number, agent_id)
    return {"phone_number": phone_number, "agent_id": agent_id}


def unregister_number(organization: str, phone_number: str) -> bool:
    """Elimina el registro de un número."""
    client = get_redis_client()
    return client.hdel(_numbers_key(organization), phone_number) > 0


def get_agent_for_number(organization: str, phone_number: str) -> str | None:
    """Obtiene el agent_id asignado a un número. Retorna None si no está registrado."""
    client = get_redis_client()
    return client.hget(_numbers_key(organization), phone_number)


def list_numbers(organization: str) -> list[dict]:
    """Lista todos los números registrados de una organización."""
    client = get_redis_client()
    mapping = client.hgetall(_numbers_key(organization))
    return [
        {"phone_number": phone, "agent_id": agent_id}
        for phone, agent_id in mapping.items()
    ]


def save_webhook_url(organization: str, webhook_url: str) -> None:
    """Persiste el webhook_url en la config de la organización para re-registro al reiniciar."""
    client = get_redis_client()
    raw = client.get(_org_key(organization))
    if not raw:
        return
    data = json.loads(raw)
    data["webhook_url"] = webhook_url
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    client.set(_org_key(organization), json.dumps(data))


def resolve_agent(wa_session_id: str, sender_phone: str) -> tuple[str | None, str | None, str | None]:
    """Dado un session_id de WA y un número de remitente, resuelve el agente.

    Retorna (organization, agent_id, routing_type) donde routing_type es
    'registered' o 'default'. Retorna (None, None, None) si no hay org vinculada.
    """
    organization = get_org_by_session(wa_session_id)
    if not organization:
        return None, None, None

    config = get_org_config(organization)
    if not config:
        return None, None, None

    # Intentar match exacto
    agent_id = get_agent_for_number(organization, sender_phone)
    if agent_id:
        return organization, agent_id, "registered"

    # Fallback al agente por defecto
    default_agent = config.get("default_agent_id", "default")
    return organization, default_agent, "default"
