import json
from .config import settings
from .redis_client import get_redis_client

def get_session_key(agent_id: str, session_id: str) -> str:
    """Genera la clave de Redis para una sesión de un agente específico."""
    return f"chat_session:{agent_id}:{session_id}"

def save_message(agent_id: str, session_id: str, role: str, content: str, charts: list[dict] = None):
    """Guarda un mensaje en el historial de la sesión.

    Args:
        charts: Lista opcional de specs Plotly para persistir gráficos generados.
    """
    client = get_redis_client()
    key = get_session_key(agent_id, session_id)
    message = {"role": role, "content": content}
    if charts:
        message["charts"] = charts
    client.rpush(key, json.dumps(message))
    client.expire(key, settings.SESSION_TTL)

def get_history(agent_id: str, session_id: str) -> list[dict]:
    """Obtiene el historial de mensajes de una sesión."""
    client = get_redis_client()
    key = get_session_key(agent_id, session_id)
    messages = client.lrange(key, 0, -1)
    return [json.loads(msg) for msg in messages]

def clear_session(agent_id: str, session_id: str):
    """Elimina el historial de una sesión."""
    client = get_redis_client()
    key = get_session_key(agent_id, session_id)
    client.delete(key)

def get_all_sessions(agent_id: str = None) -> list[dict]:
    """Obtiene todas las sesiones activas, opcionalmente filtradas por agente."""
    client = get_redis_client()

    if agent_id:
        pattern = f"chat_session:{agent_id}:*"
    else:
        pattern = "chat_session:*"

    sessions = []
    for key in client.scan_iter(pattern):
        parts = key.replace("chat_session:", "").split(":", 1)
        if len(parts) == 2:
            sessions.append({
                "agent_id": parts[0],
                "session_id": parts[1],
                "key": key
            })

    return sessions
