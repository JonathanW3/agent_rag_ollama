import chromadb
from chromadb.config import Settings as ChromaSettings
from ..config import settings

_chroma_client = None


def get_chroma_client():
    """Obtiene el cliente singleton de ChromaDB según la configuración."""
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client

    if settings.USE_CHROMA_SERVER:
        # Modo servidor ChromaDB (Docker) - API v2
        try:
            _chroma_client = chromadb.HttpClient(
                host=settings.CHROMA_HOST,
                port=settings.CHROMA_PORT,
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    chroma_api_impl="chromadb.api.fastapi.FastAPI"
                )
            )
        except Exception:
            try:
                _chroma_client = chromadb.HttpClient(
                    host=settings.CHROMA_HOST,
                    port=settings.CHROMA_PORT
                )
            except Exception:
                _chroma_client = chromadb.PersistentClient(
                    path=settings.CHROMA_DIR,
                    settings=ChromaSettings(anonymized_telemetry=False)
                )
    else:
        _chroma_client = chromadb.PersistentClient(
            path=settings.CHROMA_DIR,
            settings=ChromaSettings(anonymized_telemetry=False)
        )

    return _chroma_client

def get_collection(agent_id: str = "default"):
    """Obtiene o crea la colección de conocimiento para un agente específico."""
    client = get_chroma_client()
    collection_name = f"kb_store_{agent_id}"
    return client.get_or_create_collection(collection_name)

def get_agent_collection_name(agent_id: str) -> str:
    """Genera el nombre de colección para un agente."""
    return f"kb_store_{agent_id}"

def list_collections():
    """Lista todas las colecciones en ChromaDB."""
    client = get_chroma_client()
    return client.list_collections()

def get_collection_info(collection_name: str = "kb_store"):
    """Obtiene información detallada de una colección.

    Raises:
        Exception: si la colección no existe o ChromaDB no está disponible.
    """
    client = get_chroma_client()
    collection = client.get_collection(collection_name)
    count = collection.count()
    return {
        "name": collection_name,
        "count": count,
        "metadata": collection.metadata if hasattr(collection, 'metadata') else {}
    }

def peek_collection(collection_name: str = "kb_store", limit: int = 10):
    """Muestra los primeros documentos de una colección.

    Raises:
        Exception: si la colección no existe o ChromaDB no está disponible.
    """
    client = get_chroma_client()
    collection = client.get_collection(collection_name)
    result = collection.peek(limit=limit)
    return {
        "collection": collection_name,
        "count": collection.count(),
        "documents": result.get("documents", []),
        "ids": result.get("ids", []),
        "metadatas": result.get("metadatas", [])
    }

def get_all_documents(collection_name: str = "kb_store"):
    """Obtiene todos los documentos de una colección.

    Raises:
        Exception: si la colección no existe o ChromaDB no está disponible.
    """
    client = get_chroma_client()
    collection = client.get_collection(collection_name)
    result = collection.get()
    return {
        "collection": collection_name,
        "count": len(result.get("ids", [])),
        "documents": result.get("documents", []),
        "ids": result.get("ids", []),
        "metadatas": result.get("metadatas", [])
    }

def delete_collection(collection_name: str):
    """Elimina una colección completa.

    Raises:
        Exception: si la colección no existe o ChromaDB no está disponible.
    """
    client = get_chroma_client()
    client.delete_collection(collection_name)
    return {"status": "ok", "message": f"Collection '{collection_name}' deleted"}

def delete_agent_collection(agent_id: str):
    """Elimina la colección de conocimiento de un agente."""
    collection_name = get_agent_collection_name(agent_id)
    return delete_collection(collection_name)

def get_agent_collections() -> list[dict]:
    """Lista todas las colecciones de agentes."""
    try:
        client = get_chroma_client()
        all_collections = client.list_collections()
        agent_collections = []
        
        for col in all_collections:
            # Extraer solo el nombre como string para evitar problemas de serialización
            collection_name = str(col.name) if hasattr(col, 'name') else str(col)
            
            if collection_name.startswith("kb_store_"):
                agent_id = collection_name.replace("kb_store_", "")
                try:
                    # Obtener la colección completa para acceder a count()
                    full_collection = client.get_collection(collection_name)
                    count = full_collection.count()
                    
                    # Obtener metadata si existe
                    metadata = {}
                    if hasattr(full_collection, 'metadata') and full_collection.metadata:
                        metadata = dict(full_collection.metadata)
                    
                except Exception as e:
                    count = 0
                    metadata = {}
                
                agent_collections.append({
                    "agent_id": agent_id,
                    "collection_name": collection_name,
                    "count": count,
                    "metadata": metadata
                })
        
        return agent_collections
    except Exception as e:
        # Si hay cualquier error con ChromaDB, retornar lista vacía
        # El endpoint principal manejará el error
        raise Exception(f"Error al obtener colecciones: {str(e)}")
