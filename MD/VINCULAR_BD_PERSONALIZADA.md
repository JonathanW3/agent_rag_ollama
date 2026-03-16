# Vincular Base de Datos SQLite Personalizada a un Agente

## Concepto

Ahora puedes vincular cualquier base de datos SQLite existente (como `Monitoring.db`) a un agente específico. El agente podrá consultar esa BD junto con el RAG para responder preguntas.

## Flujo de Vinculación

```
┌─────────────────────────────────────────┐
│  1. Crear Agente con sqlite_db_path     │
│     POST /agents                         │
│     {"sqlite_db_path": "Monitoring.db"} │
└──────────────┬──────────────────────────┘
               │
               v
┌─────────────────────────────────────────┐
│  2. Tu BD se copia a:                   │
│     mcp_sqlite/databases/custom/        │
│     Monitoring.db                       │
└──────────────┬──────────────────────────┘
               │
               v
┌─────────────────────────────────────────┐
│  3. Chat con use_sql=true               │
│     POST /chat                          │
│     {"use_sql": true}                   │
└──────────────┬──────────────────────────┘
               │
               ├──────> RAG (ChromaDB)
               │
               └──────> Monitoring.db (MCP)
                        │
                        v
                   Respuesta híbrida
```

## Ejemplo Paso a Paso

### 1. Crear agente vinculado a Monitoring.db

```bash
curl -X POST "http://localhost:8000/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "monitor-assistant",
    "name": "Asistente de Monitoreo",
    "prompt": "Eres un asistente experto en análisis de sistemas de monitoreo. Puedes consultar datos de monitoreo y responder preguntas técnicas.",
    "description": "Analiza datos de Monitoring.db",
    "sqlite_db_path": "Monitoring.db"
  }'
```

**Rutas soportadas:**
- `"Monitoring.db"` - Archivo en el directorio actual
- `"./data/Monitoring.db"` - Ruta relativa
- `"C:/Proyectos/databases/Monitoring.db"` - Ruta absoluta (Windows)
- `"/home/user/databases/Monitoring.db"` - Ruta absoluta (Linux)

### 2. El sistema copia automáticamente la BD

La primera vez que uses `use_sql=true`, el sistema copiará `Monitoring.db` a:

```
mcp_sqlite/databases/custom/Monitoring.db
```

**Nota:** Si actualizas la BD original, se sincronizará automáticamente si la fecha de modificación es más reciente.

### 3. Subir documentos al agente (opcional)

```bash
curl -X POST "http://localhost:8000/ingest?agent_id=monitor-assistant" \
  -F "upload=@manual_monitoreo.pdf"
```

### 4. Hacer preguntas híbridas (RAG + SQL)

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Cuáles son los últimos registros de errores en el sistema?",
    "agent_id": "monitor-assistant",
    "session_id": "session_001",
    "use_rag": true,
    "use_sql": true,
    "temperature": 0.2
  }'
```

El agente:
1. 🔍 **Busca en Monitoring.db** - Consulta tablas de logs/errores
2. 📚 **Busca en RAG** - Encuentra contexto en manual_monitoreo.pdf
3. 🤖 **Combina ambos** - Genera respuesta usando SQL + documentos

### 5. Actualizar BD vinculada

Puedes cambiar la BD de un agente existente:

```bash
curl -X PUT "http://localhost:8000/agents/monitor-assistant" \
  -H "Content-Type: application/json" \
  -d '{
    "sqlite_db_path": "Monitoring_v2.db"
  }'
```

## Estructura de Directorios

```
mcp_sqlite/databases/
├── agents/              # BDs automáticas por agente
│   ├── agent_default.db
│   └── agent_python-expert.db
├── system/              # BDs del sistema
│   └── system_metrics.db
└── custom/              # BDs personalizadas vinculadas ← NUEVO
    ├── Monitoring.db
    ├── Sales.db
    └── CustomData.db
```

## Consultas SQL Directas

También puedes ejecutar consultas SQL directamente:

### Ver esquema de la BD

```bash
curl "http://localhost:8000/mcp/databases/custom/Monitoring/schema"
```

### Consultar datos

```bash
curl -X POST "http://localhost:8000/mcp/agents/monitor-assistant/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SELECT * FROM error_logs WHERE timestamp > datetime(\"now\", \"-1 hour\") ORDER BY timestamp DESC"
  }'
```

## Keywords para Activación Automática

Si tu pregunta incluye estas palabras, el sistema activará consultas SQL automáticamente:

- estadísticas, métricas, logs, historial
- cuántos, cuántas, total, promedio, suma
- documentos procesados, conversaciones
- **datos, registros, tabla, consulta** ← NUEVO

## Ejemplo Completo: Sistema de Ventas

```bash
# 1. Crear agente de ventas vinculado a Sales.db
curl -X POST "http://localhost:8000/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "sales-analyst",
    "name": "Analista de Ventas",
    "prompt": "Eres un analista de ventas experto. Analizas datos de ventas y generas insights.",
    "sqlite_db_path": "./data/Sales.db"
  }'

# 2. Subir catálogo de productos
curl -X POST "http://localhost:8000/ingest?agent_id=sales-analyst" \
  -F "upload=@catalogo_productos.pdf"

# 3. Consultar ventas del mes con contexto
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Cuáles fueron las ventas totales de este mes y qué productos se vendieron más?",
    "agent_id": "sales-analyst",
    "use_rag": true,
    "use_sql": true
  }'
```

**Respuesta esperada:**
> "Según los datos de ventas:
> - Total ventas: $45,230.50 (datos de Sales.db)
> - Productos más vendidos: Laptop Pro X1 (23 unidades), Mouse Inalámbrico (45 unidades)
> - El catálogo indica que estos productos tienen promoción vigente hasta fin de mes."

## Comparación: BD Automática vs Personalizada

| Aspecto | BD Automática (`agent_{id}.db`) | BD Personalizada (`Monitoring.db`) |
|---------|----------------------------------|-------------------------------------|
| **Creación** | Automática al crear agente | Debe existir previamente |
| **Tablas** | 7 tablas predefinidas | Las que tenga tu BD |
| **Datos** | Logs/métricas del agente | Tus datos de negocio |
| **Ubicación** | `mcp_sqlite/databases/agents/` | `mcp_sqlite/databases/custom/` |
| **Uso** | Tracking interno | Análisis de datos externos |
| **Actualización** | Automática por el sistema | Manual (sincronización automática) |

## Casos de Uso

### ✅ Usa BD Personalizada cuando:
- Tienes una BD existente con datos de negocio
- Necesitas consultar datos de producción (logs, métricas, ventas, etc.)
- Quieres analizar datos históricos
- La BD se actualiza externamente (otro sistema)

### ✅ Usa BD Automática cuando:
- Solo necesitas tracking del agente
- Quieres registrar métricas de uso
- Necesitas historial de conversaciones
- No tienes una BD preexistente

## Solución de Problemas

### Error: "No se pudo acceder a la BD personalizada"

**Causa:** La ruta de la BD no existe o no es accesible.

**Solución:**
```bash
# Verificar que el archivo existe
ls -l Monitoring.db

# Usar ruta absoluta
curl -X PUT "http://localhost:8000/agents/monitor-assistant" \
  -H "Content-Type: application/json" \
  -d '{
    "sqlite_db_path": "C:/Proyectos/rag_ollama_api/Monitoring.db"
  }'
```

### Error: "No such table"

**Causa:** La tabla no existe en la BD vinculada.

**Solución:**
```bash
# Ver esquema de la BD
curl "http://localhost:8000/mcp/databases/custom/Monitoring/schema"

# Usar nombres de tabla correctos
```

### La BD no se actualiza

El sistema sincroniza automáticamente si detecta cambios en la fecha de modificación. Si necesitas forzar actualización:

1. Elimina la copia en `mcp_sqlite/databases/custom/`
2. Reinicia el chat con `use_sql=true`

## Documentación Relacionada

- [MCP_INTEGRATION.md](MCP_INTEGRATION.md) - Arquitectura completa MCP
- [QUICKSTART_MCP.md](QUICKSTART_MCP.md) - Inicio rápido
- [mcp_sqlite/README.md](mcp_sqlite/README.md) - API del módulo
