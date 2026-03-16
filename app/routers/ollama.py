import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from ..config import settings, set_chat_model, set_embed_model
from ..schemas import ModelSelectRequest, ModelDownloadRequest
from ..ollama_client import ollama_list_models, ollama_pull_model, ollama_show_model

router = APIRouter(prefix="/ollama", tags=["🔧 Ollama"])


@router.get("/models", summary="Listar modelos disponibles")
def list_ollama_models():
    """Lista todos los modelos LLM disponibles en Ollama instalados localmente.

    Ejecuta internamente el comando `ollama list` y devuelve información detallada
    sobre cada modelo disponible.
    """
    try:
        response = ollama_list_models()
        models = response.get("models", [])

        # Formatear respuesta
        formatted_models = []
        for model in models:
            formatted_models.append({
                "name": model.get("name"),
                "size": model.get("size"),
                "modified": model.get("modified_at"),
                "digest": model.get("digest", "")[:16] + "...",  # Hash corto
            })

        current_chat = settings.CHAT_MODEL
        current_embed = settings.EMBED_MODEL

        return {
            "status": "ok",
            "count": len(formatted_models),
            "current_chat_model": current_chat,
            "current_embed_model": current_embed,
            "models": formatted_models,
            "models_raw": models
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar modelos: {str(e)}")


@router.get("/models/current", summary="Ver modelos activos")
def get_current_models():
    """Obtiene los modelos actualmente en uso para chat y embeddings."""
    return {
        "status": "ok",
        "chat_model": settings.CHAT_MODEL,
        "embed_model": settings.EMBED_MODEL,
        "ollama_url": settings.OLLAMA_BASE_URL
    }


@router.post("/models/select", summary="Cambiar modelo activo")
def select_model(request: ModelSelectRequest):
    """Cambia el modelo LLM activo en runtime.

    Permite cambiar entre modelos ya descargados sin reiniciar el servidor.

    - **model_name**: Nombre del modelo (ej: 'llama3.1', 'mistral')
    - **model_type**: 'chat' para modelo de conversación o 'embed' para embeddings
    """
    try:
        model_name = request.model_name
        model_type = request.model_type.lower()

        # Validar tipo
        if model_type not in ["chat", "embed"]:
            raise HTTPException(
                status_code=400,
                detail="model_type debe ser 'chat' o 'embed'"
            )

        # Verificar que el modelo existe
        try:
            ollama_show_model(model_name)
        except Exception:
            raise HTTPException(
                status_code=404,
                detail=f"Modelo '{model_name}' no encontrado. Descárgalo primero con POST /ollama/models/download"
            )

        # Cambiar modelo
        if model_type == "chat":
            old_model = settings.CHAT_MODEL
            set_chat_model(model_name)
            return {
                "status": "ok",
                "message": "Modelo de chat cambiado exitosamente",
                "previous_model": old_model,
                "current_model": settings.CHAT_MODEL,
                "type": "chat"
            }
        else:
            old_model = settings.EMBED_MODEL
            set_embed_model(model_name)
            return {
                "status": "ok",
                "message": "Modelo de embeddings cambiado exitosamente",
                "previous_model": old_model,
                "current_model": settings.EMBED_MODEL,
                "type": "embed"
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al cambiar modelo: {str(e)}")


@router.post("/models/download", summary="Descargar nuevo modelo")
def download_model(request: ModelDownloadRequest):
    """Descarga un nuevo modelo de Ollama.

    Ejecuta internamente `ollama pull <modelo>` en streaming.

    **Modelos populares:**
    - llama3.1, llama3.2
    - mistral, mixtral
    - codellama (especializado en código)
    - gemma, qwen2.5
    - nomic-embed-text (embeddings)

    **Nota:** La descarga puede tardar varios minutos dependiendo del tamaño del modelo.
    """
    model_name = request.model_name

    def generate_progress():
        """Genera el progreso de la descarga en formato JSON."""
        try:
            yield json.dumps({"status": "starting", "message": f"Iniciando descarga de {model_name}..."}) + "\n"

            for line in ollama_pull_model(model_name):
                # Enviar cada línea de progreso
                yield line + "\n"

            yield json.dumps({
                "status": "completed",
                "message": f"Modelo '{model_name}' descargado exitosamente",
                "model": model_name
            }) + "\n"

        except Exception as e:
            yield json.dumps({
                "status": "error",
                "message": f"Error al descargar modelo: {str(e)}"
            }) + "\n"

    return StreamingResponse(
        generate_progress(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/models/{model_name}", summary="Información de modelo")
def get_model_info(model_name: str):
    """Obtiene información detallada de un modelo específico."""
    try:
        info = ollama_show_model(model_name)
        return {
            "status": "ok",
            "model": model_name,
            "info": info
        }
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Modelo '{model_name}' no encontrado: {str(e)}"
        )
