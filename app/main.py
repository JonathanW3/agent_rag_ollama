import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .agents import create_default_agent
from .utils.json_sanitize import SanitizeJSONMiddleware
from .routers import health, agents, chat, sessions, documents, chromadb, ollama, mcp_sqlite, mysql, email, orchestrator, supervisor


# Metadata para Swagger UI
tags_metadata = [
    {
        "name": "📧 Email",
        "description": "Envío de emails mediante SMTP. Configura agentes con credenciales para enviar emails automáticamente."
    },
    {
        "name": "🏥 Health",
        "description": "Verificación del estado del servicio"
    },
    {
        "name": "🏥 MySQL Farmacia",
        "description": "Acceso de solo lectura a la base de datos de farmacias (farmacia_db)."
    },
    {
        "name": "🗄️ MCP SQLite",
        "description": "Gestión de bases de datos SQLite por agente mediante MCP (Model Context Protocol)."
    },
    {
        "name": "🤖 Agentes",
        "description": "Gestión de agentes con personalidades y prompts específicos. Cada agente puede tener su propio comportamiento y conocimiento."
    },
    {
        "name": "💬 Chat",
        "description": "Interacción con agentes mediante chat. Soporta RAG (Retrieval Augmented Generation) y memoria conversacional."
    },
    {
        "name": "📝 Sesiones",
        "description": "Gestión de sesiones de conversación por agente. Cada combinación agente+sesión mantiene su propio historial."
    },
    {
        "name": "📄 Documentos",
        "description": "Ingesta de documentos para Retrieval Augmented Generation. Los documentos se asignan a agentes específicos."
    },
    {
        "name": "🗄️ ChromaDB - Agentes",
        "description": "Gestión de colecciones ChromaDB por agente. Cada agente tiene su propia colección aislada de documentos."
    },
    {
        "name": "🗂️ ChromaDB - General",
        "description": "Administración general de ChromaDB. Acceso a todas las colecciones y estadísticas."
    },
    {
        "name": "🔧 Ollama",
        "description": "Gestión de modelos de Ollama. Listar, cambiar y descargar modelos LLM."
    },
    {
        "name": "🎯 Orquestador",
        "description": "Router inteligente que analiza la consulta y la dirige al agente más adecuado de una lista configurable."
    },
    {
        "name": "🔍 Supervisor",
        "description": "Agente supervisor que evalúa la calidad de otros agentes, sugiere mejoras de prompts y gestiona aprobaciones humanas."
    },
    {
        "name": "⚙️ Sistema",
        "description": "Configuración del sistema y prompts globales (legacy)."
    }
]

app = FastAPI(
    title="🤖 RAG Ollama API - Multi-Agent System",
    description="""Sistema de RAG (Retrieval Augmented Generation) con múltiples agentes especializados.

## Características Principales

- **🤖 Múltiples Agentes**: Crea agentes con personalidades y conocimientos específicos
- **🔒 Aislamiento de Datos**: Cada agente tiene su propia colección ChromaDB privada
- **💬 Memoria Conversacional**: Mantiene contexto de conversaciones por sesión
- **📚 RAG**: Integración con documentos mediante búsqueda semántica
- **🐳 Docker**: Redis y ChromaDB en contenedores

## Flujo de Trabajo Típico

1. **Crear Agente** → POST /agents
2. **Subir Documentos** → POST /ingest?agent_id=X
3. **Chatear con RAG** → POST /chat
4. **Gestionar Sesiones** → GET/DELETE /sessions
    """,
    version="2.0.0",
    openapi_tags=tags_metadata,
    contact={
        "name": "Soporte RAG API",
    },
    license_info={
        "name": "MIT",
    }
)

# Middleware
app.add_middleware(SanitizeJSONMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:5174",  # Vite dev server alternativo
        "http://localhost:3000",  # React/Next.js dev server
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:3000",
        "http://10.20.50.30:5173",  # IP local
        "http://10.20.50.30:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router)
app.include_router(agents.router)
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(documents.router)
app.include_router(chromadb.router)
app.include_router(ollama.router)
app.include_router(mcp_sqlite.router)
app.include_router(mysql.router)
app.include_router(email.router)
app.include_router(orchestrator.router)
app.include_router(supervisor.router)

# Crear directorios necesarios
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.CHROMA_DIR, exist_ok=True)


@app.on_event("startup")
def on_startup():
    """Inicialización al arrancar: crea agente por defecto si Redis está disponible."""
    try:
        create_default_agent()
    except Exception as e:
        print(f"WARNING: No se pudo crear agente por defecto (Redis disponible?): {e}")
