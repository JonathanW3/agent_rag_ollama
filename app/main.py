import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .agents import create_default_agent
from .utils.json_sanitize import SanitizeJSONMiddleware
from .cron.scheduler import scheduler, add_licencias_job, add_imap_facturas_job, add_sync_licencias_jobs, add_meta_agent_job
from .routers import health, agents, chat, sessions, documents, chromadb, ollama, mcp_sqlite, mysql, ibm, autopart, email, orchestrator, supervisor, google_calendar, whatsapp, organizations, sqlserver, cron_licencias, meta_agent, cron_meta_agent

logger = logging.getLogger("main")


# Metadata para Swagger UI
tags_metadata = [
    {
        "name": "🗃️ SQL Server Webpospa",
        "description": "Acceso de solo lectura a la base de datos webpospa en SQL Server. Consulta de licencias registradas por empresa (Ecuador y otros países)."
    },
    {
        "name": "📅 Google Calendar",
        "description": "Gestión de eventos y reuniones en Google Calendar. Crear, listar, actualizar, eliminar eventos y verificar disponibilidad."
    },
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
        "name": "🏢 MySQL IBM",
        "description": "Acceso de solo lectura a la base de datos IBM (credit_cards, bank_transactions, employees, hr_attrition, sales_orders)."
    },
    {
        "name": "🚗 MySQL Autopart",
        "description": "Acceso de solo lectura a la base de datos Autopart (vehicles, product_category, seller, applications, compatibility)."
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
        "name": "🧠 Meta-Agente",
        "description": "Coordinador inteligente entre LicenciasEC y CorreosEC. Clasifica la consulta, la delega al agente especializado y reintenta automáticamente si no obtiene datos válidos."
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
        "name": "📱 WhatsApp",
        "description": "Integración con WhatsApp: vincular sesiones a organizaciones, registrar números con agentes, recibir y responder mensajes automáticamente."
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
app.include_router(organizations.router)
app.include_router(agents.router)
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(documents.router)
app.include_router(chromadb.router)
app.include_router(ollama.router)
app.include_router(mcp_sqlite.router)
app.include_router(mysql.router)
app.include_router(ibm.router)
app.include_router(autopart.router)
app.include_router(email.router)
app.include_router(google_calendar.router)
app.include_router(orchestrator.router)
app.include_router(supervisor.router)
app.include_router(whatsapp.router)
app.include_router(sqlserver.router)
app.include_router(cron_licencias.router)
app.include_router(cron_meta_agent.router)
app.include_router(meta_agent.router)

# Crear directorios necesarios
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.CHROMA_DIR, exist_ok=True)


@app.on_event("startup")
async def on_startup():
    """Inicialización al arrancar: crea agente por defecto y re-registra webhooks de WhatsApp."""
    try:
        create_default_agent()
    except Exception as e:
        print(f"WARNING: No se pudo crear agente por defecto (Redis disponible?): {e}")

    # ── Programar cron de licencias (carga desde DB) ─────────────────────
    try:
        from .db_platform import list_cron_licencias, upsert_cron_licencias, migrate_cron_licencias, migrate_licencias_ecuador
        migrate_cron_licencias()
        migrate_licencias_ecuador()

        configs = list_cron_licencias(only_active=True)

        # Migración automática: si no hay configs en DB y hay agent_id en env, crear una
        if not configs and settings.CRON_LICENCIAS_AGENT_ID:
            logger.info("[CRON] Sin configs en DB — creando desde variables de entorno")
            cfg = upsert_cron_licencias(
                agent_id=settings.CRON_LICENCIAS_AGENT_ID,
                session_id=settings.CRON_LICENCIAS_SESSION_ID,
                hora=settings.CRON_LICENCIAS_HORA,
                minuto=settings.CRON_LICENCIAS_MINUTO,
                timezone=settings.CRON_LICENCIAS_TIMEZONE,
                dias=settings.CRON_LICENCIAS_DIAS,
                ttl=settings.CRON_LICENCIAS_TTL,
                is_active=True,
            )
            configs = [cfg]

        for cfg in configs:
            add_licencias_job(cfg)

        # ── Job de sincronización SQL Server → MySQL (8:00 y 14:00) ─────────
        try:
            add_sync_licencias_jobs(timezone=settings.CRON_LICENCIAS_TIMEZONE)
        except Exception as e:
            logger.warning(f"[CRON] No se pudo registrar sync_licencias_jobs: {e}")

        # ── Job de sincronización de facturas IMAP ────────────────────────
        try:
            add_imap_facturas_job(interval_minutes=30)
        except Exception as e:
            logger.warning(f"[CRON] No se pudo registrar job imap_facturas_sync: {e}")

        # ── Jobs del meta-agente (un job por sub-agente configurado) ────────
        try:
            from .db_platform import migrate_cron_meta_agent, list_cron_meta_agent
            migrate_cron_meta_agent()
            for meta_cfg in list_cron_meta_agent(only_active=True):
                add_meta_agent_job(meta_cfg)
            logger.info(f"[CRON] Meta-agente jobs cargados desde DB")
        except Exception as e:
            logger.warning(f"[CRON] No se pudieron cargar jobs del meta-agente: {e}")

        scheduler.start()
        logger.info(f"[CRON] Scheduler iniciado con {len(configs)} job(s) de licencias")
    except Exception as e:
        logger.warning(f"[CRON] No se pudo iniciar el scheduler de licencias: {e}")

    # Re-registrar webhooks de WhatsApp para todas las organizaciones vinculadas
    try:
        from app.whatsapp import list_whatsapp_orgs
        from app.whatsapp_client import wa_register_webhook
        orgs = list_whatsapp_orgs()
        for org in orgs:
            webhook_url = org.get("webhook_url")
            wa_session_id = org.get("wa_session_id")
            org_name = org.get("organization", "?")
            if webhook_url and wa_session_id:
                try:
                    await wa_register_webhook(wa_session_id, webhook_url)
                    print(f"[STARTUP] Webhook re-registrado para '{org_name}' → {webhook_url}")
                except Exception as e:
                    print(f"[STARTUP] Error re-registrando webhook para '{org_name}': {e}")
    except Exception as e:
        print(f"WARNING: No se pudieron re-registrar webhooks de WhatsApp: {e}")


@app.on_event("shutdown")
async def on_shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)
