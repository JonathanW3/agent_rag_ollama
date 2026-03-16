from .store import get_collection
from ..ollama_client import ollama_embed

def retrieve(query, agent_id: str = "default", top_k=4):
    """Recupera documentos relevantes de la colección del agente especificado con metadata."""
    col = get_collection(agent_id)  # Colección específica del agente
    q_emb = ollama_embed([query])[0]
    res = col.query(query_embeddings=[q_emb], n_results=top_k)
    docs = res.get("documents", [[]])[0]
    metadatas = res.get("metadatas", [[]])[0]
    
    # Combinar documentos con metadata
    results = []
    for i, doc in enumerate(docs):
        result = {"text": doc}
        if metadatas and i < len(metadatas) and metadatas[i]:
            result["metadata"] = metadatas[i]
        results.append(result)
    
    return results

def build_context(snippets):
    """Construye el contexto para el prompt incluyendo información de metadata cuando esté disponible."""
    context_parts = []
    for snippet in snippets:
        text = snippet["text"]
        metadata = snippet.get("metadata", {})
        
        # Si hay metadata, agregar información de fuente
        if metadata:
            source_info = []
            if metadata.get("title"):
                source_info.append(f"Título: {metadata['title']}")
            if metadata.get("version"):
                source_info.append(f"Versión: {metadata['version']}")
            if metadata.get("country") and metadata.get("country") != "N/A":
                source_info.append(f"País: {metadata['country']}")
            if metadata.get("filename"):
                source_info.append(f"Archivo: {metadata['filename']}")
            
            if source_info:
                context_parts.append(f"[Fuente: {', '.join(source_info)}]\n{text}")
            else:
                context_parts.append(text)
        else:
            context_parts.append(text)
    
    return "\n\n---\n\n".join(context_parts)
