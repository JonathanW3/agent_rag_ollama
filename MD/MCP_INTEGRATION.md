# Integración MCP SQLite - Guía de Uso

## Descripción General

Se ha implementado una integración completa del **Model Context Protocol (MCP)** con **SQLite** para permitir que los agentes consulten y almacenen datos estructurados además de los datos vectoriales de ChromaDB.

## Arquitectura

```
┌─────────────────────────────────────────────────────┐
│              FastAPI Application                     │
│                                                      │
│  ┌──────────────┐           ┌──────────────┐       │
│  │  /chat       │           │  /ingest     │       │
│  │  endpoint    │           │  endpoint    │       │
│  └──────┬───────┘           └──────┬───────┘       │
│         │                          │               │
│         ├──────────┬───────────────┤               │
│         │          │               │               │
│    ┌────▼────┐ ┌──▼───────┐  ┌───▼────┐          │
│    │ RAG/    │ │ MCP      │  │ Ollama │          │
│    │ChromaDB │ │ SQLite   │  │ LLM    │          │
│    │         │ │ Client   │  │        │          │
│    └─────────┘ └────┬─────┘  └────────┘          │
│                     │                             │
└─────────────────────┼─────────────────────────────┘
                      │
              ┌───────▼────────┐
              │  MCP SQLite    │
              │  Server        │
              └───────┬────────┘
                      │
        ┌─────────────┴──────────────┐
        │                            │
   ┌────▼─────────┐       ┌─────────▼────┐
   │ System DBs   │       │  Agent DBs   │
   │              │       │              │
   │ system_      │       │ agent_       │
   │ metrics.db   │       │ {id}.db      │
   └──────────────┘       └──────────────┘
```

## Flujo Híbrido RAG + SQL

Cuando un usuario hace una pregunta al agente con `use_sql=true`:

1. **Detección de necesidad SQL**: Sistema detecta palabras clave (estadísticas, métricas, logs, etc.)
2. **Consulta SQL paralela**: Extrae datos estructurados de tablas SQLite
3. **Consulta RAG**: Busca contexto vectorial en ChromaDB (si `use_rag=true`)
4. **Fusión de contextos**: Combina SQL + RAG + historial conversacional
5. **Generación LLM**: Ollama genera respuesta con todos los contextos
6. **Registro**: Guarda la conversación en Redis y SQLite

## Características Implementadas

### ✅ Integración completa MCP

- **Servidor MCP** (`mcp_sqlite/server.py`): Herramientas para query, schema, write
- **Cliente MCP** (`mcp_sqlite/client.py`): API simplificada para FastAPI
- **Esquemas SQL** (`mcp_sqlite/schemas/`): Definiciones para agentes y sistema

### ✅ Endpoint `/chat` mejorado

```python
POST /chat
{
  "message": "¿Cuántos documentos he procesado?",
  "agent_id": "python-expert",
  "session_id": "session_123",
  "use_rag": true,
  "use_sql": true,          # ← NUEVO PARÁMETRO
  "temperature": 0.2
}
```

**Respuesta incluye:**
```json
{
  "answer": "Has procesado 5 documentos...",
  "sources": [...],
  "sql_used": true,         # ← NUEVO CAMPO
  "sql_results_count": 3    # ← NUEVO CAMPO
}
```

### ✅ Endpoint `/ingest` mejorado

Ahora registra automáticamente cada documento en SQLite:
- Nombre del archivo
- Número de chunks
- Tamaño del archivo
- Timestamp de procesamiento

### ✅ Nuevos endpoints MCP

#### Listar bases de datos
```bash
GET /mcp/databases
```

Respuesta:
```json
{
  "success": true,
  "databases": {
    "agents": ["agent_python-expert", "agent_default"],
    "system": ["system_metrics"]
  }
}
```

#### Obtener esquema de BD
```bash
GET /mcp/databases/agent_python-expert/schema
```

#### Consultar BD de agente
```bash
POST /mcp/agents/python-expert/query
{
  "query": "SELECT * FROM agent_logs ORDER BY timestamp DESC LIMIT 10",
  "params": []
}
```

#### Escribir en BD de agente
```bash
POST /mcp/agents/python-expert/write
{
  "query": "INSERT INTO custom_data (data_key, data_value) VALUES (?, ?)",
  "params": ["config_mode", "production"]
}
```

#### Estadísticas de agente
```bash
GET /mcp/agents/python-expert/stats
```

Retorna:
- Total de logs
- Logs por tipo de acción
- Total de métricas
- Documentos procesados
- Métricas recientes

#### Inicializar BD de agente
```bash
POST /mcp/agents/python-expert/init
```

Crea la base de datos con todas las tablas necesarias.

## Esquema de Bases de Datos

### Base de datos de agente (`agent_{id}.db`)

#### `agent_logs`
Registro de todas las acciones del agente.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| id | INTEGER | Primary key |
| timestamp | DATETIME | Fecha/hora |
| action | TEXT | Tipo de acción |
| session_id | TEXT | ID de sesión |
| details | TEXT | JSON con detalles |
| success | BOOLEAN | Si tuvo éxito |

#### `agent_metrics`
Métricas de rendimiento del agente.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| id | INTEGER | Primary key |
| timestamp | DATETIME | Fecha/hora |
| metric_name | TEXT | Nombre de métrica |
| metric_value | REAL | Valor numérico |
| metadata | TEXT | JSON con metadatos |

#### `processed_documents`
Documentos ingresados al RAG.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| id | INTEGER | Primary key |
| document_id | TEXT | UUID del documento |
| filename | TEXT | Nombre del archivo |
| processed_at | DATETIME | Fecha de procesamiento |
| chunks_count | INTEGER | Número de chunks |
| file_size_bytes | INTEGER | Tamaño en bytes |
| file_type | TEXT | Extensión (.pdf, .txt) |
| status | TEXT | Estado (completed, failed) |

#### `agent_config`
Configuración personalizada.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| key | TEXT | Clave de configuración |
| value | TEXT | Valor |
| updated_at | DATETIME | Última actualización |

#### `conversations`
Historial de conversaciones.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| id | INTEGER | Primary key |
| session_id | TEXT | ID de sesión |
| timestamp | DATETIME | Fecha/hora |
| role | TEXT | 'user' o 'assistant' |
| message | TEXT | Contenido del mensaje |
| tokens | INTEGER | Tokens consumidos |
| rag_used | BOOLEAN | Si usó RAG |
| sql_used | BOOLEAN | Si usó SQL |

#### `custom_data`
Datos personalizados del usuario.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| id | INTEGER | Primary key |
| created_at | DATETIME | Fecha de creación |
| data_key | TEXT | Clave |
| data_value | TEXT | Valor |
| category | TEXT | Categoría |

## Ejemplos de Uso

### Ejemplo 1: Chat con datos estructurados

```python
import requests

response = requests.post("http://localhost:8000/chat", json={
    "message": "¿Cuántos documentos he procesado en los últimos 7 días?",
    "agent_id": "default",
    "session_id": "session_123",
    "use_rag": True,
    "use_sql": True
})

print(response.json()["answer"])
# "Has procesado 3 documentos en los últimos 7 días: ..."
```

### Ejemplo 2: Consultar métricas de rendimiento

```python
response = requests.post(
    "http://localhost:8000/mcp/agents/default/query",
    json={
        "query": """
            SELECT 
                metric_name,
                AVG(metric_value) as avg_value,
                MIN(metric_value) as min_value,
                MAX(metric_value) as max_value
            FROM agent_metrics
            WHERE timestamp > datetime('now', '-7 days')
            GROUP BY metric_name
        """
    }
)

print(response.json())
```

### Ejemplo 3: Registrar datos personalizados

```python
# Guardar configuración
requests.post(
    "http://localhost:8000/mcp/agents/default/write",
    json={
        "query": "INSERT INTO custom_data (data_key, data_value, category) VALUES (?, ?, ?)",
        "params": ["theme", "dark", "ui_settings"]
    }
)

# Consultar configuración
response = requests.post(
    "http://localhost:8000/mcp/agents/default/query",
    json={
        "query": "SELECT data_value FROM custom_data WHERE data_key = ?",
        "params": ["theme"]
    }
)

theme = response.json()["rows"][0]["data_value"]
print(f"Theme: {theme}")
```

### Ejemplo 4: Análisis de sesiones

```bash
POST /mcp/agents/default/query
{
  "query": "SELECT session_id, COUNT(*) as message_count, SUM(rag_used) as rag_uses FROM conversations GROUP BY session_id ORDER BY message_count DESC LIMIT 10"
}
```

## Instalación y Configuración

### 1. Instalar dependencias

```bash
pip install -r requirements.txt
```

El archivo `requirements.txt` incluye:
```
mcp>=0.9.0
```

### 2. Estructura de archivos

La integración crea automáticamente:
```
mcp_sqlite/
├── databases/
│   ├── agents/          # BDs de agentes (auto)
│   │   └── agent_*.db
│   └── system/          # BDs del sistema (auto)
│       └── system_metrics.db
├── schemas/             # Definiciones SQL
│   ├── agent_schema.sql
│   └── system_metrics.sql
├── __init__.py          # Módulo
├── server.py            # Servidor MCP
├── client.py            # Cliente MCP
└── README.md            # Documentación
```

### 3. Iniciar la aplicación

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Inicializar BD de un agente

```bash
curl -X POST "http://localhost:8000/mcp/agents/default/init"
```

## Swagger UI

Accede a la documentación interactiva completa en:
```
http://localhost:8000/docs
```

Busca la sección **🗄️ MCP SQLite** para ver todos los endpoints disponibles.

## Seguridad

### ✅ Implementado

- **Consultas parametrizadas**: Prevención de SQL injection
- **Separación lectura/escritura**: Tools diferentes para query y write
- **Validación de tipos**: Solo SELECT en queries, INSERT/UPDATE/DELETE en writes
- **Aislamiento por agente**: Cada agente tiene su propia BD

### ⚠️ Consideraciones

- Los endpoints MCP no tienen autenticación por defecto
- Considera añadir rate limiting para operaciones de escritura
- Valida permisos de usuario antes de ejecutar queries

## Troubleshooting

### Error: "module 'mcp' not found"

```bash
pip install mcp
```

### Error: "database is locked"

SQLite puede bloquearse con acceso concurrente. Solución:
- Usar conexiones con timeout
- Implementar retry logic
- Considerar PostgreSQL para alta concurrencia

### BD no se crea automáticamente

Ejecuta manualmente:
```bash
curl -X POST "http://localhost:8000/mcp/agents/{agent_id}/init"
```

## Roadmap

### Próximas mejoras

- [ ] Soporte para transacciones SQL
- [ ] Backup automático de bases de datos
- [ ] Interfaz web para explorar BDs
- [ ] Export a CSV/JSON
- [ ] Queries guardadas (templates)
- [ ] Notificaciones de eventos SQL
- [ ] Integración con dashboards (Grafana)

## Contacto y Soporte

Para reportar issues o sugerencias, consulta la documentación principal del proyecto.
