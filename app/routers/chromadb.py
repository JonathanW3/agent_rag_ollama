from fastapi import APIRouter, HTTPException, Query, Depends
from ..auth import get_current_org, OrgContext
from ..agents import agent_exists
from ..rag.store import (
    list_collections, get_collection_info, peek_collection, get_all_documents,
    delete_collection, get_agent_collection_name, delete_agent_collection, get_agent_collections
)

router = APIRouter()


# ============================================================================
# ChromaDB - Agent Collections
# ============================================================================

@router.get("/chromadb/agents", tags=["🗄️ ChromaDB - Agentes"], summary="Listar colecciones de agentes")
def get_agent_collections_endpoint(org: OrgContext = Depends(get_current_org)):
    """Lista todas las colecciones de agentes con información de documentos y embeddings."""
    try:
        collections = get_agent_collections()
        return {
            "collections": collections,
            "count": len(collections)
        }
    except Exception as e:
        error_msg = str(e)
        if "'_type'" in error_msg:
            error_msg = "Error de serialización de ChromaDB. Verifica que ChromaDB esté corriendo y sea compatible."
        raise HTTPException(status_code=503, detail=error_msg)


@router.get("/chromadb/agents/{agent_id}", tags=["🗄️ ChromaDB - Agentes"], summary="Info de colección del agente")
def get_agent_collection_info(agent_id: str, org: OrgContext = Depends(get_current_org)):
    """Obtiene información de la colección ChromaDB de un agente específico."""
    if not agent_exists(agent_id):
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no encontrado")

    try:
        collection_name = get_agent_collection_name(agent_id)
        return get_collection_info(collection_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error accediendo colección del agente: {str(e)}")


@router.get("/chromadb/agents/{agent_id}/documents", tags=["🗄️ ChromaDB - Agentes"], summary="Documentos del agente")
def get_agent_documents(agent_id: str, org: OrgContext = Depends(get_current_org)):
    """Obtiene todos los documentos/chunks embebidos de la base de conocimientos del agente."""
    if not agent_exists(agent_id):
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no encontrado")

    try:
        collection_name = get_agent_collection_name(agent_id)
        documents_data = get_all_documents(collection_name)
        return {
            "agent_id": agent_id,
            **documents_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener documentos: {str(e)}")


@router.delete("/chromadb/agents/{agent_id}", tags=["🗄️ ChromaDB - Agentes"], summary="Eliminar documentos del agente")
def clear_agent_documents(agent_id: str, org: OrgContext = Depends(get_current_org)):
    """Elimina todos los documentos de la base de conocimientos de un agente sin eliminar el agente."""
    if not agent_exists(agent_id):
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no encontrado")

    try:
        result = delete_agent_collection(agent_id)
        return {
            "agent_id": agent_id,
            "message": f"Todos los documentos del agente '{agent_id}' han sido eliminados",
            **result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar documentos: {str(e)}")


# ============================================================================
# ChromaDB - General Collections
# ============================================================================

@router.get("/chromadb/collections", tags=["🗂️ ChromaDB - General"], summary="Listar todas las colecciones")
def get_collections(org: OrgContext = Depends(get_current_org)):
    """Lista todas las colecciones en ChromaDB (incluye sistema y agentes)."""
    try:
        collections = list_collections()
        return {
            "collections": [col.name for col in collections],
            "count": len(collections),
            "details": [{"name": col.name, "metadata": col.metadata if col.metadata else {}} for col in collections]
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"ChromaDB no disponible: {str(e)}"
        )


@router.get("/chromadb/collections/{collection_name}", tags=["🗂️ ChromaDB - General"], summary="Detalles de colección")
def get_collection_details(collection_name: str, org: OrgContext = Depends(get_current_org)):
    """Obtiene información detallada de una colección específica de ChromaDB."""
    try:
        return get_collection_info(collection_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Colección '{collection_name}' no encontrada: {str(e)}")


@router.get("/chromadb/collections/{collection_name}/peek", tags=["🗂️ ChromaDB - General"], summary="Vista previa de documentos")
def peek_collection_data(
    collection_name: str,
    limit: int = Query(default=10, ge=1, le=100, description="Número de documentos a mostrar"),
    org: OrgContext = Depends(get_current_org),
):
    """Muestra los primeros N documentos de una colección para exploración rápida."""
    try:
        return peek_collection(collection_name, limit)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Colección '{collection_name}' no encontrada: {str(e)}")


@router.get("/chromadb/collections/{collection_name}/documents", tags=["🗂️ ChromaDB - General"], summary="Todos los documentos")
def get_collection_documents(collection_name: str, org: OrgContext = Depends(get_current_org)):
    """Obtiene todos los documentos de una colección específica (usar con precaución en colecciones grandes)."""
    try:
        return get_all_documents(collection_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Colección '{collection_name}' no encontrada: {str(e)}")


@router.delete("/chromadb/collections/{collection_name}", tags=["🗂️ ChromaDB - General"], summary="Eliminar colección")
def remove_collection(collection_name: str, org: OrgContext = Depends(get_current_org)):
    """Elimina una colección completa de ChromaDB (no permite kb_store por seguridad)."""
    if collection_name == "kb_store":
        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar la colección principal 'kb_store'. Use /chromadb/clear para vaciarla."
        )
    try:
        return delete_collection(collection_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Colección '{collection_name}' no encontrada: {str(e)}")


@router.post("/chromadb/clear", tags=["🗂️ ChromaDB - General"], summary="Vaciar colección principal")
def clear_chromadb(org: OrgContext = Depends(get_current_org)):
    """Vacía todos los documentos de la colección principal (legacy kb_store)."""
    try:
        delete_collection("kb_store")
        return {
            "status": "ok",
            "message": "Colección 'kb_store' eliminada y recreada vacía"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
