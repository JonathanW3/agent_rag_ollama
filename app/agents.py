import json
import uuid
from datetime import datetime, timezone
from .redis_client import get_redis_client
from .crypto import encrypt_dict, decrypt_dict

def get_agent_key(agent_id: str) -> str:
    """Genera la clave de Redis para un agente."""
    return f"agent:{agent_id}"


def _encrypt_agent_smtp(agent: dict) -> dict:
    """Cifra smtp_config antes de guardar en Redis. Retorna copia modificada."""
    if agent.get("smtp_config") and isinstance(agent["smtp_config"], dict):
        agent = dict(agent)
        agent["smtp_config_encrypted"] = encrypt_dict(agent["smtp_config"])
        agent["smtp_config"] = None  # No guardar en texto plano
    return agent


def _decrypt_agent_smtp(agent: dict) -> dict:
    """Descifra smtp_config al leer de Redis. Retorna copia modificada."""
    if agent.get("smtp_config_encrypted"):
        agent = dict(agent)
        try:
            agent["smtp_config"] = decrypt_dict(agent["smtp_config_encrypted"])
        except Exception:
            agent["smtp_config"] = None  # Clave cambió o dato corrupto
        del agent["smtp_config_encrypted"]
    return agent


def create_agent(name: str, prompt: str, description: str = "", agent_id: str = None, organization: str = None, llm_model: str = None, sqlite_db_path: str = None, use_rag: bool = True, smtp_config: dict = None, use_mysql: bool = False, use_email: bool = False, use_charts: bool = False, use_ibm: bool = False, use_autopart: bool = False, top_k: int = 4, temperature: float = 0.7) -> dict:
    """Crea un nuevo agente."""
    client = get_redis_client()

    if agent_id is None:
        agent_id = str(uuid.uuid4())

    # Verificar que no exista
    key = get_agent_key(agent_id)
    if client.exists(key):
        raise ValueError(f"El agente {agent_id} ya existe")

    now = datetime.now(timezone.utc).isoformat()
    agent = {
        "id": agent_id,
        "name": name,
        "prompt": prompt,
        "description": description,
        "organization": organization,
        "llm_model": llm_model,
        "sqlite_db_path": sqlite_db_path,
        "use_rag": use_rag,
        "smtp_config": smtp_config,
        "use_mysql": use_mysql,
        "use_email": use_email,
        "use_charts": use_charts,
        "use_ibm": use_ibm,
        "use_autopart": use_autopart,
        "top_k": top_k,
        "temperature": temperature,
        "created_at": now,
        "updated_at": now
    }

    # Cifrar SMTP antes de almacenar
    to_store = _encrypt_agent_smtp(agent)
    client.set(key, json.dumps(to_store))
    return agent

def get_agent(agent_id: str) -> dict | None:
    """Obtiene un agente por su ID."""
    client = get_redis_client()
    key = get_agent_key(agent_id)
    data = client.get(key)

    if data is None:
        return None

    agent = json.loads(data)
    return _decrypt_agent_smtp(agent)

def list_agents(organization: str = None) -> list[dict]:
    """Lista agentes. Si se pasa organization, filtra por esa organización."""
    client = get_redis_client()

    agents = []
    for key in client.scan_iter("agent:*"):
        data = client.get(key)
        if data:
            agent = json.loads(data)
            agent = _decrypt_agent_smtp(agent)
            if organization is not None:
                if agent.get("organization", "").lower() == organization.lower():
                    agents.append(agent)
            else:
                agents.append(agent)

    # Ordenar por fecha de creación
    agents.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return agents


def list_organizations() -> list[dict]:
    """Lista todas las organizaciones con su conteo de agentes."""
    client = get_redis_client()

    org_counts: dict[str, int] = {}
    for key in client.scan_iter("agent:*"):
        data = client.get(key)
        if data:
            agent = json.loads(data)
            org = agent.get("organization")
            if org:
                org_counts[org] = org_counts.get(org, 0) + 1

    return [
        {"name": name, "agent_count": count}
        for name, count in sorted(org_counts.items())
    ]

def update_agent(agent_id: str, name: str = None, prompt: str = None, description: str = None, organization: str = None, llm_model: str = None, sqlite_db_path: str = None, use_rag: bool = None, smtp_config: dict = None, use_mysql: bool = None, use_email: bool = None, use_charts: bool = None, use_ibm: bool = None, use_autopart: bool = None, top_k: int = None, temperature: float = None) -> dict:
    """Actualiza un agente existente."""
    client = get_redis_client()
    key = get_agent_key(agent_id)

    # Obtener agente actual (ya viene descifrado)
    agent = get_agent(agent_id)
    if agent is None:
        raise ValueError(f"El agente {agent_id} no existe")

    # Actualizar campos
    if name is not None:
        agent["name"] = name
    if prompt is not None:
        agent["prompt"] = prompt
    if description is not None:
        agent["description"] = description
    if organization is not None:
        agent["organization"] = organization
    if llm_model is not None:
        agent["llm_model"] = llm_model
    if sqlite_db_path is not None:
        agent["sqlite_db_path"] = sqlite_db_path
    if use_rag is not None:
        agent["use_rag"] = use_rag
    if smtp_config is not None:
        agent["smtp_config"] = smtp_config
    if use_mysql is not None:
        agent["use_mysql"] = use_mysql
    if use_email is not None:
        agent["use_email"] = use_email
    if use_charts is not None:
        agent["use_charts"] = use_charts
    if use_ibm is not None:
        agent["use_ibm"] = use_ibm
    if use_autopart is not None:
        agent["use_autopart"] = use_autopart
    if top_k is not None:
        agent["top_k"] = top_k
    if temperature is not None:
        agent["temperature"] = temperature

    agent["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Cifrar SMTP antes de almacenar
    to_store = _encrypt_agent_smtp(agent)
    client.set(key, json.dumps(to_store))
    return agent

def delete_agent(agent_id: str) -> bool:
    """Elimina un agente."""
    client = get_redis_client()
    key = get_agent_key(agent_id)

    # También eliminar todas las sesiones de este agente
    for session_key in client.scan_iter(f"chat_session:{agent_id}:*"):
        client.delete(session_key)

    result = client.delete(key)
    return result > 0

def agent_exists(agent_id: str) -> bool:
    """Verifica si un agente existe."""
    client = get_redis_client()
    key = get_agent_key(agent_id)
    return client.exists(key) > 0

def get_agent_stats(agent_id: str) -> dict:
    """Obtiene estadísticas de un agente."""
    client = get_redis_client()

    # Contar sesiones activas y mensajes totales
    session_count = 0
    total_messages = 0
    for session_key in client.scan_iter(f"chat_session:{agent_id}:*"):
        session_count += 1
        total_messages += client.llen(session_key)

    return {
        "agent_id": agent_id,
        "active_sessions": session_count,
        "total_messages": total_messages
    }

def create_default_agent():
    """Crea el agente por defecto si no existe."""
    default_id = "default"
    if not agent_exists(default_id):
        create_agent(
            agent_id=default_id,
            name="Asistente General",
            prompt="Eres un asistente profesional de atención al cliente 24/7.",
            description="Agente general para consultas diversas"
        )
        return True
    return False
