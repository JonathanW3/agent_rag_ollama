# MCP SQLite Integration

Este módulo implementa la integración del **Model Context Protocol (MCP)** con SQLite para permitir que los agentes consulten datos estructurados además de los datos vectoriales de ChromaDB.

## Estructura de directorios

```
mcp_sqlite/
├── __init__.py          # Módulo principal
├── server.py            # Servidor MCP SQLite
├── client.py            # Cliente MCP para integración con FastAPI
├── schemas/             # Esquemas SQL
│   ├── system_metrics.sql
│   └── agent_schema.sql
└── databases/           # Bases de datos SQLite (generadas automáticamente)
    ├── system/          # Bases de datos del sistema
    │   └── system_metrics.db
    └── agents/          # Bases de datos por agente
        ├── agent_<id1>.db
        └── agent_<id2>.db
```

## Características

### Servidor MCP (`server.py`)

El servidor implementa las siguientes herramientas MCP:

1. **query_sqlite**: Ejecuta consultas SELECT seguras
2. **get_db_schema**: Obtiene el esquema de una base de datos
3. **list_databases**: Lista todas las bases de datos disponibles
4. **execute_write**: Ejecuta operaciones de escritura (INSERT, UPDATE, DELETE)

### Cliente MCP (`client.py`)

El cliente proporciona una interfaz simplificada para:

- Ejecutar consultas SQL desde FastAPI
- Gestionar bases de datos por agente
- Registrar logs y métricas
- Inicializar esquemas automáticamente

## Uso

### Inicializar base de datos de un agente

```python
from mcp_sqlite.client import get_mcp_client

client = get_mcp_client()

# Inicializar BD para un nuevo agente
await client.init_agent_db(agent_id="123")
```

### Registrar una acción del agente

```python
await client.log_agent_action(
    agent_id="123",
    action="chat_response",
    session_id="session_456",
    details={"tokens": 150, "rag_used": True},
    success=True
)
```

### Consultar datos

```python
# Consultar logs recientes
result = await client.query_for_agent(
    agent_id="123",
    query="SELECT * FROM agent_logs ORDER BY timestamp DESC LIMIT 10"
)

if result.get("success"):
    logs = result["rows"]
    print(f"Encontrados {result['count']} logs")
```

### Añadir métricas

```python
await client.add_metric(
    agent_id="123",
    metric_name="response_time_ms",
    metric_value=245.5,
    metadata={"endpoint": "/chat", "model": "llama3"}
)
```

## Esquemas de datos

### Base de datos de agente (`agent_<id>.db`)

- **agent_logs**: Registro de acciones del agente
- **agent_metrics**: Métricas de rendimiento
- **processed_documents**: Documentos ingresados al RAG
- **agent_config**: Configuración personalizada
- **conversations**: Historial de conversaciones
- **rag_statistics**: Estadísticas de consultas RAG
- **custom_data**: Datos personalizados del usuario

### Base de datos del sistema (`system_metrics.db`)

- **system_metrics**: Métricas globales
- **agent_usage**: Uso de todos los agentes
- **sessions**: Información de sesiones
- **error_logs**: Registro de errores

## Seguridad

- Las consultas SELECT están separadas de las operaciones de escritura
- Uso de consultas parametrizadas para prevenir SQL injection
- Aislamiento de datos por agente
- Validación de tipos de consulta

## Integración con FastAPI

El cliente se integra automáticamente con el endpoint `/chat`:

```python
from mcp_sqlite.client import get_mcp_client

@app.post("/chat")
async def chat(request: ChatRequest):
    mcp_client = get_mcp_client()
    
    # Consultar datos estructurados si es necesario
    sql_context = await mcp_client.query_for_agent(
        agent_id=request.agent_id,
        query="SELECT * FROM agent_metrics WHERE metric_name = ?",
        params=["response_time_ms"]
    )
    
    # Combinar con RAG vectorial y generar respuesta
    ...
```

## Ejemplos de consultas útiles

### Top 10 métricas más recientes

```sql
SELECT metric_name, metric_value, timestamp 
FROM agent_metrics 
ORDER BY timestamp DESC 
LIMIT 10
```

### Documentos procesados en el último mes

```sql
SELECT filename, chunks_count, processed_at
FROM processed_documents
WHERE processed_at > datetime('now', '-1 month')
ORDER BY processed_at DESC
```

### Tasa de éxito de acciones

```sql
SELECT 
    action,
    COUNT(*) as total,
    SUM(success) as successful,
    ROUND(100.0 * SUM(success) / COUNT(*), 2) as success_rate
FROM agent_logs
WHERE timestamp > datetime('now', '-7 days')
GROUP BY action
```

### Conversaciones con RAG

```sql
SELECT 
    session_id,
    COUNT(*) as msg_count,
    SUM(rag_used) as rag_uses,
    SUM(tokens) as total_tokens
FROM conversations
GROUP BY session_id
ORDER BY timestamp DESC
LIMIT 20
```
