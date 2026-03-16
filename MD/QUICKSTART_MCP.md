# Inicio Rápido - MCP SQLite Integration

## 1. Instalar dependencias

```bash
pip install -r requirements.txt
```

Esto instalará el paquete `mcp>=0.9.0` necesario para la integración.

## 2. Verificar instalación

```bash
python -c "import mcp; print('MCP instalado correctamente')"
```

## 3. Iniciar el servidor FastAPI

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 4. Probar la integración MCP

### Opción A: Script de prueba automatizado

```bash
python test_mcp_integration.py
```

Este script probará:
- ✅ Inicialización de base de datos
- ✅ Inserción de logs y métricas
- ✅ Consultas SQL básicas y avanzadas
- ✅ Datos personalizados

### Opción B: Probar con Swagger UI

1. Abre http://localhost:8000/docs
2. Busca la sección **🗄️ MCP SQLite**
3. Prueba los endpoints:

#### a) Inicializar BD de agente

```http
POST /mcp/agents/default/init
```

#### b) Consultar logs del agente

```http
POST /mcp/agents/default/query
Content-Type: application/json

{
  "query": "SELECT * FROM agent_logs ORDER BY timestamp DESC LIMIT 10"
}
```

#### c) Obtener estadísticas

```http
GET /mcp/agents/default/stats
```

### Opción C: Probar con cURL

```bash
# 1. Inicializar BD del agente
curl -X POST "http://localhost:8000/mcp/agents/default/init"

# 2. Listar bases de datos
curl "http://localhost:8000/mcp/databases"

# 3. Ver esquema
curl "http://localhost:8000/mcp/databases/agent_default/schema"

# 4. Consultar logs
curl -X POST "http://localhost:8000/mcp/agents/default/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT * FROM agent_logs LIMIT 5"}'

# 5. Obtener estadísticas
curl "http://localhost:8000/mcp/agents/default/stats"
```

## 5. Probar chat con SQL habilitado

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Cuántos documentos he procesado?",
    "agent_id": "default",
    "session_id": "test_session",
    "use_rag": true,
    "use_sql": true
  }'
```

**Nota:** El parámetro `use_sql: true` es necesario para activar las consultas SQL.

## 6. Verificar bases de datos creadas

Las bases de datos se crean automáticamente en:

```
mcp_sqlite/databases/
├── agents/
│   └── agent_default.db    # BD del agente "default"
└── system/
    └── system_metrics.db   # BD del sistema (futuro)
```

Puedes explorarlas con cualquier cliente SQLite:

```bash
# SQLite CLI
sqlite3 mcp_sqlite/databases/agents/agent_default.db

# Dentro del CLI
.tables
.schema agent_logs
SELECT * FROM agent_logs LIMIT 5;
```

## 7. Ejemplo completo end-to-end

```bash
# 1. Crear un agente
curl -X POST "http://localhost:8000/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "data-analyst",
    "name": "Analista de Datos",
    "prompt": "Eres un experto analista de datos que puede consultar tanto documentos como bases de datos SQL."
  }'

# 2. Inicializar su BD
curl -X POST "http://localhost:8000/mcp/agents/data-analyst/init"

# 3. Subir documentos
curl -X POST "http://localhost:8000/ingest?agent_id=data-analyst" \
  -F "upload=@datos.pdf"

# 4. Insertar datos personalizados
curl -X POST "http://localhost:8000/mcp/agents/data-analyst/write" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "INSERT INTO custom_data (data_key, data_value, category) VALUES (?, ?, ?)",
    "params": ["sales_2024", "1500000", "revenue"]
  }'

# 5. Hacer una pregunta que combine RAG + SQL
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Dame un resumen de los documentos que he subido y las métricas de ventas que tengo registradas",
    "agent_id": "data-analyst",
    "use_rag": true,
    "use_sql": true
  }'
```

## Troubleshooting

### Error: "module 'mcp' not found"

```bash
pip install mcp
```

### Error: "No such table: agent_logs"

La BD no fue inicializada. Ejecuta:

```bash
curl -X POST "http://localhost:8000/mcp/agents/{agent_id}/init"
```

### Error: "database is locked"

SQLite está siendo accedido por otro proceso. Cierra cualquier cliente SQLite conectado.

### Las consultas SQL no retornan datos

Asegúrate de que:
1. La BD fue inicializada
2. Has insertado datos (el chat con `use_sql=true` insertará automáticamente)
3. Has subido al menos un documento (registra en `processed_documents`)

## Próximos pasos

1. Lee la documentación completa: [MCP_INTEGRATION.md](MCP_INTEGRATION.md)
2. Explora los esquemas SQL: `mcp_sqlite/schemas/`
3. Crea consultas personalizadas según tus necesidades
4. Integra con dashboards externos (Grafana, Metabase, etc.)

## Soporte

Para más información y ejemplos avanzados, consulta:
- [MCP_INTEGRATION.md](MCP_INTEGRATION.md)
- [Swagger UI](http://localhost:8000/docs)
- [mcp_sqlite/README.md](mcp_sqlite/README.md)
