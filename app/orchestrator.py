"""
Orquestador inteligente de agentes.

Clasifica consultas del usuario y las rutea al agente más adecuado
de una lista configurable de agentes permitidos.
"""

import json
from .redis_client import get_redis_client
from .agents import get_agent
from .ollama_client import ollama_chat
from .config import settings

ORCHESTRATOR_CONFIG_KEY = "orchestrator:config"

DEFAULT_CONFIG = {
    "allowed_agent_ids": [],
    "fallback_agent_id": "default",
    "llm_model": None,
}


def get_orchestrator_config() -> dict:
    """Lee la configuración del orquestador desde Redis."""
    client = get_redis_client()
    data = client.get(ORCHESTRATOR_CONFIG_KEY)
    if data is None:
        return dict(DEFAULT_CONFIG)
    return json.loads(data)


def save_orchestrator_config(
    allowed_agent_ids: list[str],
    fallback_agent_id: str = "default",
    llm_model: str | None = None,
) -> dict:
    """Guarda la configuración del orquestador en Redis."""
    client = get_redis_client()
    config = {
        "allowed_agent_ids": allowed_agent_ids,
        "fallback_agent_id": fallback_agent_id,
        "llm_model": llm_model,
    }
    client.set(ORCHESTRATOR_CONFIG_KEY, json.dumps(config))
    return config


def add_agents_to_config(agent_ids: list[str]) -> dict:
    """Agrega agentes a la lista de permitidos (sin duplicados)."""
    config = get_orchestrator_config()
    current = set(config["allowed_agent_ids"])
    current.update(agent_ids)
    config["allowed_agent_ids"] = list(current)
    client = get_redis_client()
    client.set(ORCHESTRATOR_CONFIG_KEY, json.dumps(config))
    return config


def remove_agent_from_config(agent_id: str) -> dict:
    """Quita un agente de la lista de permitidos."""
    config = get_orchestrator_config()
    config["allowed_agent_ids"] = [
        aid for aid in config["allowed_agent_ids"] if aid != agent_id
    ]
    client = get_redis_client()
    client.set(ORCHESTRATOR_CONFIG_KEY, json.dumps(config))
    return config


def get_allowed_agents_details(config: dict) -> list[dict]:
    """Obtiene name y description de cada agente permitido que exista."""
    details = []
    for agent_id in config["allowed_agent_ids"]:
        agent = get_agent(agent_id)
        if agent:
            details.append({
                "agent_id": agent["id"],
                "name": agent["name"],
                "description": agent.get("description", ""),
            })
    return details


def build_classification_prompt(
    message: str,
    agents_details: list[dict],
    fallback_agent_id: str,
) -> list[dict]:
    """Construye el prompt para que el LLM clasifique la consulta."""
    agents_list = "\n".join(
        f'  - agent_id: "{a["agent_id"]}" | {a["name"]}: {a["description"]}'
        for a in agents_details
    )

    system_prompt = (
        "Eres un router inteligente. Tu ÚNICA tarea es elegir el agente más adecuado "
        "para responder la consulta del usuario.\n\n"
        "REGLAS:\n"
        "- Responde ÚNICAMENTE con el agent_id exacto del agente elegido.\n"
        "- NO agregues explicación, puntuación, comillas ni texto adicional.\n"
        "- Si ningún agente es claramente adecuado, responde exactamente: "
        f"{fallback_agent_id}\n\n"
        f"Agentes disponibles:\n{agents_list}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]


def classify_query(
    message: str,
    agents_details: list[dict],
    fallback_agent_id: str,
    llm_model: str | None = None,
) -> str:
    """Usa el LLM para determinar qué agente debe responder.

    Returns:
        agent_id del agente seleccionado.
    """
    messages = build_classification_prompt(message, agents_details, fallback_agent_id)
    model = llm_model or settings.CHAT_MODEL

    raw = ollama_chat(messages, temperature=0.1, model=model)
    selected = raw.strip().strip('"').strip("'").strip()

    # Validar que el agente seleccionado está en la lista de permitidos
    allowed_ids = {a["agent_id"] for a in agents_details}
    if selected not in allowed_ids:
        return fallback_agent_id

    return selected
