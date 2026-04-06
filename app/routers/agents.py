from fastapi import APIRouter, Depends, HTTPException, Query
from ..schemas import AgentCreate, AgentUpdate
from ..agents import (
    create_agent, get_agent, list_agents, update_agent, delete_agent, get_agent_stats,
    list_organizations,
)
from ..ollama_client import ollama_model_exists
from ..rag.store import delete_agent_collection
from ..auth import get_current_org, log_audit, OrgContext

router = APIRouter(prefix="/agents", tags=["🤖 Agentes"])


# ---------------------------------------------------------------------------
# Helper de acceso
# ---------------------------------------------------------------------------

def _check_agent_access(agent_id: str, org: OrgContext) -> dict:
    """Verifica que el agente existe y que la org tiene acceso. Lanza 404 si no."""
    agent = get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no encontrado")
    if not org.get("is_admin") and agent.get("organization") != org["org_name"]:
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no encontrado")
    return agent


# ---------------------------------------------------------------------------
# Endpoints (el orden importa: /organizations antes de /{agent_id})
# ---------------------------------------------------------------------------

@router.get("/organizations", summary="Listar organizaciones con agentes")
def get_organizations(org: OrgContext = Depends(get_current_org)):
    """
    Admin: lista todas las organizaciones que tienen agentes en Redis.
    Otros: retorna solo su propia organización.
    """
    try:
        if org.get("is_admin"):
            orgs = list_organizations()
        else:
            agents = list_agents(organization=org["org_name"])
            orgs = [{"name": org["org_name"], "agent_count": len(agents)}]
        return {"organizations": orgs, "count": len(orgs)}
    except Exception:
        raise HTTPException(status_code=500, detail="Error listando organizaciones")


@router.post("", summary="Crear nuevo agente")
def create_new_agent(req: AgentCreate, org: OrgContext = Depends(get_current_org)):
    """
    Crea un agente.
    - Admin: puede especificar cualquier organización en el body. Si no manda ninguna
      se usa 'ADMIN-001'.
    - Otros: la organización siempre viene del token (el body se ignora).
    """
    # Resolver organización destino
    if org.get("is_admin") and req.organization and req.organization.strip():
        target_org = req.organization.strip()
    else:
        target_org = org["org_name"]

    # Validar límite solo para orgs no-admin
    if not org.get("is_admin"):
        existing = list_agents(organization=target_org)
        if len(existing) >= org["max_agents"]:
            raise HTTPException(
                status_code=403,
                detail=f"Límite de agentes alcanzado ({org['max_agents']}). Contacta al administrador."
            )

    model_to_use = req.llm_model
    if model_to_use and model_to_use.strip():
        if not ollama_model_exists(model_to_use):
            raise HTTPException(
                status_code=400,
                detail=f"El modelo '{model_to_use}' no existe en Ollama. Usa /ollama/models para ver los disponibles."
            )
    else:
        model_to_use = None

    try:
        agent = create_agent(
            name=req.name,
            prompt=req.prompt,
            description=req.description,
            agent_id=req.agent_id,
            organization=target_org,
            llm_model=model_to_use,
            sqlite_db_path=req.sqlite_db_path,
            use_rag=req.use_rag,
            smtp_config=req.smtp_config,
            use_mysql=req.use_mysql,
            use_email=req.use_email,
            use_charts=req.use_charts,
            use_calendar=req.use_calendar,
            use_ibm=req.use_ibm,
            use_autopart=req.use_autopart,
            imap_config=req.imap_config,
            use_imap=req.use_imap,
            use_fe=req.use_fe,
            top_k=req.top_k,
            temperature=req.temperature,
            alert_wa_session_id=req.alert_wa_session_id,
            alert_wa_number=req.alert_wa_number,
            alert_email=req.alert_email,
        )
        log_audit(org, "agent", "create", entity_id=agent["id"],
                  meta={"name": agent["name"], "target_org": target_org})
        return agent
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", summary="Listar agentes")
def get_agents(
    organization: str = Query(default=None, description="Filtrar por organización (solo admin)"),
    org: OrgContext = Depends(get_current_org),
):
    """
    Lista agentes.
    - Admin: ve todos. Puede filtrar con ?organization=X para ver solo una org.
    - Otros: solo ven los de su propia organización (el filtro se ignora).
    """
    try:
        if org.get("is_admin"):
            # Admin puede filtrar por org específica o ver todas
            filter_org = organization.strip() if organization and organization.strip() else None
            agents = list_agents(organization=filter_org)
        else:
            agents = list_agents(organization=org["org_name"])

        return {
            "agents": agents,
            "count": len(agents),
            "organization": org["company_lic_cod"],
            "is_admin": bool(org.get("is_admin")),
        }
    except Exception:
        raise HTTPException(status_code=500, detail="Error listando agentes")


@router.get("/{agent_id}", summary="Obtener detalles de un agente")
def get_agent_details(agent_id: str, org: OrgContext = Depends(get_current_org)):
    """Admin ve cualquier agente. Otros solo los de su organización."""
    agent = _check_agent_access(agent_id, org)
    agent["stats"] = get_agent_stats(agent_id)
    return agent


@router.put("/{agent_id}", summary="Actualizar agente")
def update_agent_details(agent_id: str, req: AgentUpdate,
                         org: OrgContext = Depends(get_current_org)):
    """Admin puede actualizar cualquier agente. Otros solo los de su organización."""
    existing = _check_agent_access(agent_id, org)

    # Admin puede reasignar la org del agente desde el body; otros no pueden cambiarla
    if org.get("is_admin") and req.organization and req.organization.strip():
        target_org = req.organization.strip()
    else:
        target_org = existing.get("organization")

    model_to_use = req.llm_model
    if model_to_use is not None:
        if not model_to_use.strip():
            model_to_use = None
        elif not ollama_model_exists(model_to_use):
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
            organization=target_org,
            llm_model=model_to_use,
            sqlite_db_path=req.sqlite_db_path,
            use_rag=req.use_rag,
            smtp_config=req.smtp_config,
            use_mysql=req.use_mysql,
            use_email=req.use_email,
            use_charts=req.use_charts,
            use_calendar=req.use_calendar,
            use_ibm=req.use_ibm,
            use_autopart=req.use_autopart,
            imap_config=req.imap_config,
            use_imap=req.use_imap,
            use_fe=req.use_fe,
            top_k=req.top_k,
            temperature=req.temperature,
            alert_wa_session_id=req.alert_wa_session_id,
            alert_wa_number=req.alert_wa_number,
            alert_email=req.alert_email,
        )
        log_audit(org, "agent", "update", entity_id=agent_id)
        return agent
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{agent_id}", summary="Eliminar agente")
def delete_agent_endpoint(agent_id: str,
                          delete_documents: bool = Query(default=True),
                          org: OrgContext = Depends(get_current_org)):
    """Admin puede eliminar cualquier agente. Otros solo los de su organización."""
    if agent_id == "default":
        raise HTTPException(status_code=400, detail="No se puede eliminar el agente 'default'")

    _check_agent_access(agent_id, org)

    success = delete_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no encontrado")

    if delete_documents:
        delete_agent_collection(agent_id)

    log_audit(org, "agent", "delete", entity_id=agent_id,
              meta={"documents_deleted": delete_documents})

    return {
        "status": "ok",
        "message": f"Agente '{agent_id}' eliminado",
        "documents_deleted": delete_documents
    }
