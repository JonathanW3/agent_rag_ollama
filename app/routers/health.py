from fastapi import APIRouter
from ..config import settings
from ..prompts import load_system_prompt, save_system_prompt
from ..ollama_client import ollama_list_models, ollama_model_exists
from ..schemas import PromptRequest

router = APIRouter()


@router.get("/health", tags=["🏥 Health"], summary="Verificar estado del servicio")
def health():
    """Verifica el estado del servicio y de Ollama."""
    status = {
        "status": "ok",
        "api": "running",
        "ollama": {
            "status": "unknown",
            "url": settings.OLLAMA_BASE_URL,
            "chat_model": settings.CHAT_MODEL,
            "embed_model": settings.EMBED_MODEL,
            "chat_model_available": False,
            "embed_model_available": False
        }
    }

    # Verificar si Ollama está disponible
    try:
        ollama_list_models()
        status["ollama"]["status"] = "connected"

        # Verificar si los modelos configurados existen
        status["ollama"]["chat_model_available"] = ollama_model_exists(settings.CHAT_MODEL)
        status["ollama"]["embed_model_available"] = ollama_model_exists(settings.EMBED_MODEL)

        if not status["ollama"]["chat_model_available"]:
            status["warnings"] = status.get("warnings", []) + [
                f"Modelo de chat '{settings.CHAT_MODEL}' no encontrado. Descárgalo o cambia el modelo."
            ]
        if not status["ollama"]["embed_model_available"]:
            status["warnings"] = status.get("warnings", []) + [
                f"Modelo de embeddings '{settings.EMBED_MODEL}' no encontrado. Descárgalo o cambia el modelo."
            ]
    except Exception as e:
        status["ollama"]["status"] = "disconnected"
        status["ollama"]["error"] = str(e)
        status["warnings"] = [f"No se puede conectar a Ollama: {str(e)}"]

    return status


@router.get("/prompt", tags=["⚙️ Sistema"], summary="Obtener prompt global (legacy)")
def get_prompt():
    return {"prompt": load_system_prompt()}


@router.post("/prompt", tags=["⚙️ Sistema"], summary="Actualizar prompt global (legacy)")
def set_prompt(req: PromptRequest):
    save_system_prompt(req.prompt)
    return {"status": "ok"}
