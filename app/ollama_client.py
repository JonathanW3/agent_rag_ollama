import requests
from .config import settings

def ollama_chat(messages, temperature=0.2, model: str = None, num_predict: int = None, timeout: int = None, format_json: bool = False):
    """Genera respuesta de chat usando Ollama.

    Args:
        messages: Lista de mensajes en formato [{"role": "user", "content": "..."}]
        temperature: Temperatura del modelo (0.0-2.0)
        model: Nombre del modelo a usar. Si es None, usa settings.CHAT_MODEL
        num_predict: Máximo de tokens a generar. Si es None, usa el default de Ollama.
        timeout: Timeout en segundos para la request HTTP. Default: 120s.
        format_json: Si True, fuerza al modelo a generar JSON válido (Ollama format:"json").

    Returns:
        str: Respuesta generada por el modelo
    """
    # Usar modelo especificado o el modelo por defecto
    model_to_use = model if model is not None else settings.CHAT_MODEL

    url = f"{settings.OLLAMA_BASE_URL}/api/chat"
    options = {"temperature": temperature}
    if num_predict is not None:
        options["num_predict"] = num_predict
    payload = {
        "model": model_to_use,
        "messages": messages,
        "stream": False,
        "options": options
    }
    if format_json:
        payload["format"] = "json"
    try:
        r = requests.post(url, json=payload, timeout=timeout or 120)
        r.raise_for_status()
        return r.json()["message"]["content"]
    except requests.exceptions.HTTPError as e:
        # Mejorar el mensaje de error
        error_detail = ""
        try:
            error_data = r.json()
            error_detail = error_data.get("error", str(e))
        except (ValueError, AttributeError):
            error_detail = str(e)

        raise Exception(
            f"Error de Ollama al usar modelo '{model_to_use}': {error_detail}. "
            f"Verifica que el modelo esté instalado con: ollama list"
        )
    except requests.exceptions.ConnectionError:
        raise Exception(
            f"No se puede conectar a Ollama en {settings.OLLAMA_BASE_URL}. "
            f"Asegúrate de que Ollama esté ejecutándose."
        )

def ollama_embed(texts):
    url = f"{settings.OLLAMA_BASE_URL}/api/embeddings"
    vectors = []
    for t in texts:
        try:
            r = requests.post(url, json={"model": settings.EMBED_MODEL, "prompt": t})
            r.raise_for_status()
            vectors.append(r.json()["embedding"])
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                error_data = r.json()
                error_detail = error_data.get("error", str(e))
            except (ValueError, AttributeError):
                error_detail = str(e)

            raise Exception(
                f"Error de Ollama al usar modelo de embeddings '{settings.EMBED_MODEL}': {error_detail}. "
                f"Verifica que el modelo esté instalado con: ollama list"
            )
        except requests.exceptions.ConnectionError:
            raise Exception(
                f"No se puede conectar a Ollama en {settings.OLLAMA_BASE_URL}. "
                f"Asegúrate de que Ollama esté ejecutándose."
            )
    return vectors

def ollama_list_models():
    """Lista todos los modelos disponibles en Ollama."""
    url = f"{settings.OLLAMA_BASE_URL}/api/tags"
    r = requests.get(url)
    r.raise_for_status()
    return r.json()

def ollama_pull_model(model_name: str):
    """Descarga un modelo de Ollama.
    
    Args:
        model_name: Nombre del modelo a descargar (ej: 'llama3.1', 'mistral')
    
    Returns:
        Generator que yields el progreso de la descarga
    """
    url = f"{settings.OLLAMA_BASE_URL}/api/pull"
    payload = {"name": model_name, "stream": True}
    
    r = requests.post(url, json=payload, stream=True)
    r.raise_for_status()
    
    for line in r.iter_lines():
        if line:
            yield line.decode('utf-8')

def ollama_show_model(model_name: str):
    """Obtiene información detallada de un modelo."""
    url = f"{settings.OLLAMA_BASE_URL}/api/show"
    payload = {"name": model_name}
    r = requests.post(url, json=payload)
    r.raise_for_status()
    return r.json()

def ollama_model_exists(model_name: str) -> bool:
    """Verifica si un modelo existe en Ollama."""
    try:
        ollama_show_model(model_name)
        return True
    except Exception:
        return False
