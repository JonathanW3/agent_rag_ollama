from pydantic import BaseModel
import os
from dotenv import load_dotenv

load_dotenv()  # Carga variables desde .env antes de leer os.getenv()

class Settings(BaseModel):
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    CHAT_MODEL: str = os.getenv("CHAT_MODEL", "llama3")
    EMBED_MODEL: str = os.getenv("EMBED_MODEL", "nomic-embed-text")
    DATA_DIR: str = os.getenv("DATA_DIR", "./data")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./data/uploads")
    CHROMA_DIR: str = os.getenv("CHROMA_DIR", "./data/chroma")
    CHROMA_HOST: str = os.getenv("CHROMA_HOST", "localhost")
    CHROMA_PORT: int = int(os.getenv("CHROMA_PORT", "8001"))
    USE_CHROMA_SERVER: bool = os.getenv("USE_CHROMA_SERVER", "false").lower() == "true"
    PROMPT_FILE: str = os.getenv("PROMPT_FILE", "./data/system_prompt.txt")
    TOP_K: int = int(os.getenv("TOP_K", "4"))
    MAX_CONTEXT_CHARS: int = int(os.getenv("MAX_CONTEXT_CHARS", "12000"))
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "900"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "150"))
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    SESSION_TTL: int = int(os.getenv("SESSION_TTL", "3600"))  # 1 hora en segundos
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")  # Clave para cifrar datos sensibles (SMTP)
    PUBLIC_API_URL: str = os.getenv("PUBLIC_API_URL", "http://localhost:8000")  # URL pública del API (para webhooks)

    class Config:
        validate_assignment = True

settings = Settings()

def set_chat_model(model: str):
    """Cambia el modelo de chat en runtime."""
    settings.CHAT_MODEL = model

def set_embed_model(model: str):
    """Cambia el modelo de embeddings en runtime."""
    settings.EMBED_MODEL = model
