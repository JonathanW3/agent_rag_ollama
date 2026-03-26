from fastapi import APIRouter, HTTPException, Query
from ..schemas import AgentCreate, AgentUpdate
from ..agents import (
    create_agent, get_agent, list_agents, update_agent, delete_agent, get_agent_stats,
    list_organizations
)
from ..ollama_client import ollama_model_exists
from ..rag.store import delete_agent_collection

router = APIRouter(prefix="/agents", tags=["🤖 Agentes"])


@router.post("", summary="Crear nuevo agente")
def create_new_agent(req: AgentCreate):
    """Crea un nuevo agente con su prompt específico y base de conocimientos vacía."""
    # Validar que el modelo existe si se especificó uno (y no es cadena vacía)
    model_to_use = req.llm_model
    if model_to_use and model_to_use.strip():  # Solo validar si tiene un valor
        if not ollama_model_exists(model_to_use):
            raise HTTPException(
                status_code=400,
                detail=f"El modelo '{model_to_use}' no existe en Ollama. Usa /ollama/models para ver los disponibles."
            )
    else:
        # Si es cadena vacía o None, usar None para modelo global
        model_to_use = None

    try:
        agent = create_agent(
            name=req.name,
            prompt=req.prompt,
            description=req.description,
            agent_id=req.agent_id,
            organization=req.organization,
            llm_model=model_to_use,
            sqlite_db_path=req.sqlite_db_path,
            use_rag=req.use_rag,
            smtp_config=req.smtp_config,
            use_mysql=req.use_mysql,
            use_email=req.use_email,
            use_charts=req.use_charts,
            use_ibm=req.use_ibm,
            use_autopart=req.use_autopart,
            top_k=req.top_k,
            temperature=req.temperature
        )
        return agent
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", summary="Listar agentes")
def get_agents(
    organization: str = Query(default=None, description="Filtrar por organización (opcional)")
):
    """Lista agentes. Si se pasa ?organization=IBM, retorna solo los de esa organización."""
    try:
        agents = list_agents(organization=organization)
        return {
            "agents": agents,
            "count": len(agents),
            "organization": organization
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error listando agentes: {str(e)}"
        )


@router.get("/organizations", summary="Listar organizaciones")
def get_organizations():
    """Lista todas las organizaciones que tienen agentes registrados."""
    try:
        orgs = list_organizations()
        return {
            "organizations": orgs,
            "count": len(orgs)
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error listando organizaciones: {str(e)}"
        )


@router.get("/{agent_id}", summary="Obtener detalles de un agente")
def get_agent_details(agent_id: str):
    """Obtiene los detalles completos y estadísticas de un agente específico."""
    agent = get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no encontrado")

    # Incluir estadísticas
    stats = get_agent_stats(agent_id)
    agent["stats"] = stats

    return agent


@router.put("/{agent_id}", summary="Actualizar agente")
def update_agent_details(agent_id: str, req: AgentUpdate):
    """Actualiza el nombre, prompt, descripción o modelo LLM de un agente existente."""
    # Validar que el modelo existe si se especificó uno (y no es cadena vacía)
    model_to_use = req.llm_model
    if model_to_use is not None:
        # Si es cadena vacía, convertir a None (usar modelo global)
        if not model_to_use.strip():
            model_to_use = None
        else:
            # Validar que el modelo existe
            if not ollama_model_exists(model_to_use):
                raise HTTPException(
                    status_code=400,
                    detail=f"El modelo '{model_to_use}' no existe en Ollama. Usa /ollama/models para ver los disponibles."
                )

    try:
        agent = update_agent(
            agent_id=agent_id,
            name=req.name,
            prompt=req.prompt,
            description=req.description,
            organization=req.organization,
            llm_model=model_to_use,
            sqlite_db_path=req.sqlite_db_path,
            use_rag=req.use_rag,
            smtp_config=req.smtp_config,
            use_mysql=req.use_mysql,
            use_email=req.use_email,
            use_charts=req.use_charts,
            use_ibm=req.use_ibm,
            use_autopart=req.use_autopart,
            top_k=req.top_k,
            temperature=req.temperature
        )
        return agent
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{agent_id}", summary="Eliminar agente")
def delete_agent_endpoint(agent_id: str, delete_documents: bool = Query(default=True, description="Eliminar también los documentos del agente")):
    """Elimina un agente, todas sus sesiones y opcionalmente su colección de documentos."""
    if agent_id == "default":
        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar el agente 'default'"
        )

    # Eliminar agente
    success = delete_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no encontrado")

    # Eliminar colección de documentos si se solicita
    if delete_documents:
        delete_agent_collection(agent_id)

    return {
        "status": "ok",
        "message": f"Agente '{agent_id}' eliminado",
        "documents_deleted": delete_documents
    }
