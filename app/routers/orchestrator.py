from fastapi import APIRouter, HTTPException
from ..schemas import OrchestratorChatRequest, OrchestratorConfigRequest, OrchestratorAddAgentsRequest, ChatRequest
from ..agents import agent_exists
from ..orchestrator import (
    get_orchestrator_config,
    save_orchestrator_config,
    add_agents_to_config,
    remove_agent_from_config,
    get_allowed_agents_details,
    classify_query,
)
from .chat import chat as execute_chat

router = APIRouter(prefix="/orchestrator", tags=["🎯 Orquestador"])


@router.post("/chat", summary="Chat inteligente con routing automático")
async def orchestrator_chat(req: OrchestratorChatRequest):
    """Analiza el mensaje del usuario y lo rutea al agente más adecuado de la lista configurada."""
    config = get_orchestrator_config()

    if not config["allowed_agent_ids"]:
        raise HTTPException(
            status_code=400,
            detail="El orquestador no tiene agentes configurados. Usa PUT /orchestrator/config para agregar agentes.",
        )

    # Obtener detalles de los agentes permitidos
    agents_details = get_allowed_agents_details(config)
    if not agents_details:
        raise HTTPException(
            status_code=400,
            detail="Ninguno de los agentes configurados existe. Verifica los agent_ids.",
        )

    # Clasificar la consulta
    fallback = config["fallback_agent_id"]
    try:
        selected_agent_id = classify_query(
            message=req.message,
            agents_details=agents_details,
            fallback_agent_id=fallback,
            llm_model=config.get("llm_model"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al clasificar la consulta: {str(e)}",
        )

    # Rutear al agente elegido reutilizando el flujo de chat existente
    chat_req = ChatRequest(
        message=req.message,
        agent_id=selected_agent_id,
        session_id=req.session_id,
        use_rag=req.use_rag,
        use_sql=req.use_sql,
        use_mysql=req.use_mysql,
        use_email=req.use_email,
        use_charts=req.use_charts,
    )

    result = await execute_chat(chat_req)

    # Enriquecer respuesta con metadata de routing
    result["orchestrator"] = {
        "routed_to": selected_agent_id,
        "available_agents": [a["agent_id"] for a in agents_details],
        "fallback_agent_id": fallback,
    }

    return result


# ── Configuración del Orquestador ──────────────────────────────────────


@router.get("/config", summary="Ver configuración del orquestador")
async def get_config():
    """Retorna la lista de agentes permitidos y la configuración actual."""
    config = get_orchestrator_config()
    agents_details = get_allowed_agents_details(config)
    return {
        **config,
        "agents_details": agents_details,
        "total_configured": len(config["allowed_agent_ids"]),
        "total_active": len(agents_details),
    }


@router.put("/config", summary="Actualizar configuración del orquestador")
async def update_config(req: OrchestratorConfigRequest):
    """Reemplaza la configuración completa del orquestador."""
    # Validar que los agentes existen
    missing = [aid for aid in req.allowed_agent_ids if not agent_exists(aid)]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Los siguientes agentes no existen: {missing}",
        )

    # Validar fallback
    if req.fallback_agent_id not in req.allowed_agent_ids and not agent_exists(req.fallback_agent_id):
        raise HTTPException(
            status_code=404,
            detail=f"El agente fallback '{req.fallback_agent_id}' no existe.",
        )

    config = save_orchestrator_config(
        allowed_agent_ids=req.allowed_agent_ids,
        fallback_agent_id=req.fallback_agent_id,
        llm_model=req.llm_model,
    )
    return {"message": "Configuración actualizada", "config": config}


@router.post("/config/agents", summary="Agregar agentes al orquestador")
async def add_agents(req: OrchestratorAddAgentsRequest):
    """Agrega uno o más agentes a la lista de permitidos sin afectar los existentes."""
    missing = [aid for aid in req.agent_ids if not agent_exists(aid)]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Los siguientes agentes no existen: {missing}",
        )

    config = add_agents_to_config(req.agent_ids)
    return {"message": f"Agentes agregados: {req.agent_ids}", "config": config}


@router.delete("/config/agents/{agent_id}", summary="Quitar agente del orquestador")
async def remove_agent(agent_id: str):
    """Quita un agente de la lista de permitidos del orquestador."""
    config = get_orchestrator_config()
    if agent_id not in config["allowed_agent_ids"]:
        raise HTTPException(
            status_code=404,
            detail=f"El agente '{agent_id}' no está en la lista del orquestador.",
        )

    config = remove_agent_from_config(agent_id)
    return {"message": f"Agente '{agent_id}' removido del orquestador", "config": config}
