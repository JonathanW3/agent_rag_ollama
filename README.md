# RAG Ollama API

Sistema multi-agente de Retrieval Augmented Generation (RAG) construido con FastAPI. Permite crear y gestionar agentes de IA especializados con almacenamiento de documentos, acceso a bases de datos SQL y capacidades de email.

## Tech Stack

- **Backend:** FastAPI + Uvicorn
- **LLM/Embeddings:** Ollama (llama3, nomic-embed-text)
- **Vector DB:** ChromaDB
- **Cache/Sesiones:** Redis
- **Bases de datos:** MySQL (lectura) + SQLite (por agente)
- **Email:** SMTP con encriptacion
- **Contenedores:** Docker + Docker Compose

## Funcionalidades

- **Agentes aislados** con colecciones ChromaDB independientes y modelos configurables
- **Chat con memoria conversacional** almacenada en Redis con TTL configurable
- **Ingesta de documentos** (PDF, TXT, JSON, XML, CSV) con chunking y embeddings automaticos
- **Orquestador inteligente** que enruta consultas al agente mas adecuado
- **Acceso MySQL** de solo lectura a base de datos de farmacia
- **SQLite por agente** via Model Context Protocol (MCP)
- **Envio de emails** con adjuntos y soporte HTML
- **Gestion de modelos Ollama** en tiempo de ejecucion

## Endpoints principales

| Ruta | Descripcion |
|------|-------------|
| `/agents` | CRUD de agentes |
| `/chat` | Conversacion con contexto RAG, SQL y email |
| `/ingest` | Carga y procesamiento de documentos |
| `/chromadb` | Gestion de colecciones vectoriales |
| `/orchestrator` | Enrutamiento inteligente de consultas |
| `/mysql` | Consultas a base de datos de farmacia |
| `/email` | Configuracion y envio de correos |
| `/mcp_sqlite` | Base de datos SQLite por agente |
| `/sessions` | Gestion de sesiones de conversacion |
| `/ollama` | Administracion de modelos |
| `/health` | Estado del servicio |

## Estructura del proyecto

```
app/
├── main.py              # Aplicacion FastAPI
├── config.py            # Configuracion
├── agents.py            # Gestion de agentes
├── orchestrator.py      # Logica de enrutamiento
├── ollama_client.py     # Cliente Ollama
├── redis_client.py      # Conexion Redis
├── memory.py            # Memoria de sesiones
├── crypto.py            # Encriptacion SMTP
├── schemas.py           # Modelos Pydantic
├── routers/             # Endpoints de la API
└── rag/
    ├── ingest.py        # Pipeline de ingesta
    ├── retrieve.py      # Busqueda semantica
    ├── chunking.py      # Estrategia de chunking
    └── store.py         # Cliente ChromaDB
```

## Requisitos previos

- [Docker](https://www.docker.com/) y Docker Compose
- [Ollama](https://ollama.com/) corriendo localmente con los modelos descargados

## Instalacion y ejecucion

### Con Docker (recomendado)

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/rag_ollama_api.git
cd rag_ollama_api

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# 3. Levantar los servicios
docker-compose up -d

# 4. Descargar modelos de Ollama (si no los tienes)
ollama pull llama3
ollama pull nomic-embed-text
```

### Sin Docker

```bash
# 1. Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env

# 4. Iniciar la aplicacion
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

La API estara disponible en `http://localhost:8000` y la documentacion interactiva en `http://localhost:8000/docs`.

## Variables de entorno

Configurar en el archivo `.env`:

| Variable | Descripcion |
|----------|-------------|
| `OLLAMA_BASE_URL` | URL de Ollama |
| `REDIS_URL` | URL de conexion a Redis |
| `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DB` | Credenciales MySQL |
| `SESSION_TTL` | Tiempo de vida de sesiones (segundos) |
| `ENCRYPTION_KEY` | Clave para encriptar credenciales SMTP |
