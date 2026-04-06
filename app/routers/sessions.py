from fastapi import APIRouter, HTTPException, Query, Depends
from ..auth import get_current_org, OrgContext
from ..memory import get_history, clear_session, get_all_sessions
from ..agents import agent_exists

router = APIRouter(prefix="/sessions", tags=["📝 Sesiones"])


@router.get("", summary="Listar sesiones")
def list_sessions(agent_id: str = Query(None, description="Filtrar por agente"), org: OrgContext = Depends(get_current_org)):
    """Lista todas las sesiones activas, opcionalmente filtradas por agente."""
    sessions = get_all_sessions(agent_id)
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/{agent_id}/{session_id}", summary="Obtener historial de sesión")
def get_session_history(agent_id: str, session_id: str, org: OrgContext = Depends(get_current_org)):
    """Obtiene el historial completo de conversación de una sesión específica."""
    if not agent_exists(agent_id):
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no encontrado")

    history = get_history(agent_id, session_id)
    return {
        "agent_id": agent_id,
        "session_id": session_id,
        "history": history,
        "message_count": len(history)
    }


@router.delete("/{agent_id}/{session_id}", summary="Eliminar sesión")
def delete_session_endpoint(agent_id: str, session_id: str, org: OrgContext = Depends(get_current_org)):
    """Elimina el historial completo de una sesión específica sin afectar al agente."""
    clear_session(agent_id, session_id)
    return {"status": "ok", "message": f"Sesión '{session_id}' del agente '{agent_id}' eliminada"}
