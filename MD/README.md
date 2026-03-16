# RAG Ollama API - Multi-Agent System

Sistema de RAG (Retrieval Augmented Generation) con soporte para **múltiples agentes especializados**, cada uno con su propio prompt y personalidad.

## Características

✅ **Múltiples agentes** - Crea agentes especializados con prompts específicos  
✅ **Memoria conversacional** - Cada agente mantiene historial de sesiones independiente  
✅ **RAG integrado** - Todos los agentes acceden al mismo conocimiento vectorial  
✅ **MCP SQLite** - Consulta datos estructurados mediante Model Context Protocol (NUEVO) 
✅ **Híbrido RAG + SQL** - Combina búsqueda vectorial con datos estructurados  
✅ **Persistencia** - Redis para sesiones, ChromaDB para documentos, SQLite para métricas  
✅ **Docker** - Servicios contenedorizados y fáciles de desplegar  
✅ **Frontend React** - Interfaz de chat moderna y responsive (NUEVO)

## 🚀 Inicio Rápido

### 1. Backend (FastAPI)

```bash
# Instalar dependencias
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt

# Iniciar servicios Docker
docker-compose up -d

# Descargar modelos Ollama
ollama pull llama3
ollama pull nomic-embed-text

# Ejecutar API
uvicorn app.main:app --reload
```

Backend disponible en: **http://localhost:8000**

### 2. Frontend (React)

```bash
# En otra terminal
cd front_app
npm install
npm run dev
```

Frontend disponible en: **http://localhost:3000**

O usa el script: `front_app\START_FRONTEND.bat`

### 3. Streamlit Dashboard (Opcional)

```bash
cd Test
pip install -r requirements.txt
streamlit run app_manager.py
```

Dashboard disponible en: **http://localhost:8501**

## 📦 Estructura del Proyecto

```
rag_ollama_api/
├── app/                    # Backend FastAPI
│   ├── agents.py          # Sistema de agentes
│   ├── main.py            # API principal
│   ├── memory.py          # Sesiones y memoria
│   └── rag/               # Sistema RAG
├── front_app/             # Frontend React (NUEVO)
│   ├── src/
│   │   ├── App.jsx        # Componente principal
│   │   └── App.css        # Estilos
│   └── START_FRONTEND.bat # Script de inicio
├── Test/
│   └── app_manager.py     # Dashboard Streamlit
├── mcp_sqlite/            # Integración MCP SQLite
└── docker-compose.yml     # Redis + ChromaDB
```

## 🎨 Frontend React - Características

El frontend proporciona una interfaz de chat moderna y fácil de usar:

- ✅ **Selector de Agentes** - Cambia entre agentes con un dropdown
- 💬 **Chat en Tiempo Real** - Interfaz fluida de mensajería
- 🎨 **Diseño Moderno** - Gradientes, animaciones y UI responsive
- 📱 **Mobile Responsive** - Funciona perfectamente en móviles
- 🔄 **Auto-scroll** - Se desplaza automáticamente a nuevos mensajes
- 🗑️ **Limpieza de Chat** - Reinicia conversaciones fácilmente
- 📊 **Indicadores** - Muestra modelo LLM, RAG y SQLite del agente
- ⚡ **Typing Indicator** - Animación mientras el agente responde
- 🚨 **Manejo de Errores** - Mensajes claros de error

**Tecnologías:** React 18 + Vite + Axios

Ver más: [front_app/README.md](front_app/README.md)

---

## 📄 Endpoints - Documentos y RAG

## 🗄️ Endpoints - ChromaDB

- `GET /chromadb/collections` - Listar colecciones en ChromaDB
- `GET /chromadb/collections/{name}` - Info de una colección
- `GET /chromadb/collections/{name}/peek` - Ver primeros documentos
- `GET /chromadb/collections/{name}/documents` - Ver todos los documentos
- `POST /chromadb/clear` - Vaciar colección principal
- `DELETE /chromadb/collections/{name}` - Eliminar colección

## 🗄️ Endpoints - MCP SQLite (NUEVO)

- `GET /mcp/databases` - Listar bases de datos disponibles
- `GET /mcp/databases/{db_name}/schema` - Obtener esquema de BD
- `POST /mcp/agents/{agent_id}/query` - Consultar BD de agente (SELECT)
- `POST /mcp/agents/{agent_id}/write` - Escribir en BD de agente (INSERT/UPDATE/DELETE)
- `GET /mcp/agents/{agent_id}/stats` - Estadísticas del agente desde SQL
- `POST /mcp/agents/{agent_id}/init` - Inicializar BD del agente

**Ver documentación completa:** [MCP_INTEGRATION.md](MCP_INTEGRATION.md)

---

## 📖 Documentación Completa

- **[AGENTES.md](AGENTES.md)** - Guía completa del sistema de agentes con ejemplos
- **[AISLAMIENTO_CHROMADB.md](AISLAMIENTO_CHROMADB.md)** - Sistema de colecciones aisladas por agente
- **[MCP_INTEGRATION.md](MCP_INTEGRATION.md)** - Integración MCP SQLite para datos estructurados (NUEVO)
- **[VINCULAR_BD_PERSONALIZADA.md](VINCULAR_BD_PERSONALIZADA.md)** - Cómo vincular tu propia BD SQLite a un agente (NUEVO)
- **[EJEMPLOS.md](EJEMPLOS.md)** - Ejemplos de uso de la API
- **Swagger UI** - http://localhost:8000/docs

---

## 🎯 Ejemplo Rápido

```bash
# 1. Crear un agente especializado
curl -X POST "http://localhost:8000/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "python-expert",
    "name": "Experto Python",
    "prompt": "Eres un experto en Python con 10 años de experiencia..."
  }'

# 2. Subir documentación específica para el agente
curl -X POST "http://localhost:8000/ingest?agent_id=python-expert" \
  -F "upload=@python_docs.pdf"

# 3. Chatear con el agente (usa SOLO sus documentos)
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Cómo implemento un decorador?",
    "agent_id": "python-expert",
    "session_id": "user123",
    "use_rag": true
  }'

# 4. Ver estadísticas y documentos del agente
curl http://localhost:8000/agents/python-expert
curl http://localhost:8000/chromadb/agents/python-expert
```

---
## Detener servicios

```bash
docker-compose down
```

---

## 🤖 Endpoints - Agentes

- `POST /agents` - Crear nuevo agente
- `GET /agents` - Listar todos los agentes
- `GET /agents/{agent_id}` - Ver detalles y estadísticas de un agente
- `PUT /agents/{agent_id}` - Actualizar agente
- `DELETE /agents/{agent_id}` - Eliminar agente

## 💬 Endpoints - Chat y Sesiones

- `POST /chat` - Chat con agente específico (`agent_id` + `session_id`)
- `GET /sessions` - Lista todas las sesiones (filtrable por agente)
- `GET /sessions/{agent_id}/{session_id}` - Ver historial de sesión
- `DELETE /sessions/{agent_id}/{session_id}` - Limpiar sesión

## 📄 Endpoints - Documentos y RAG
## Endpoints
- `POST /chat` - Chat con memoria contextual (usa `session_id` para mantener conversaciones)
- `GET /sessions` - Lista todas las sesiones activas
- `GET /sessions/{session_id}` - Ver historial de una sesión
- `DELETE /sessions/{session_id}` - Limpiar historial de una sesión
- `POST /ingest` - Subir documentos para RAG
- `GET/POST /prompt` - Gestionar prompt del sistema
- `GET /chromadb/collections` - Listar colecciones en ChromaDB
- `GET /chromadb/collections/{name}` - Info de una colección
- `GET /chromadb/collections/{name}/peek` - Ver primeros documentos
- `GET /chromadb/collections/{name}/documents` - Ver todos los documentos
- `POST /chromadb/clear` - Vaciar colección principal
- `DELETE /chromadb/collections/{name}` - Eliminar colección

## Configuración

### Variables de entorno
- `USE_CHROMA_SERVER=true` - Usar ChromaDB en Docker (default)
- `USE_CHROMA_SERVER=false` - Usar ChromaDB local embebido
- `CHROMA_HOST=localhost` - Host del servidor ChromaDB
- `CHROMA_PORT=8001` - Puerto del servidor ChromaDB
- `REDIS_HOST=localhost` - Host de Redis
- `REDIS_PORT=6379` - Puerto de Redis
- `SESSION_TTL=3600` - Tiempo de expiración de sesiones en segundos

