# Ejemplos de uso de la API con Sistema Multi-Agente

## 🚀 Iniciar servicios
```bash
# Crear carpetas de datos
mkdir redis_data chroma_data

# Levantar Redis + ChromaDB
docker-compose up -d

# Verificar que están corriendo
docker-compose ps

# Ver logs
docker-compose logs -f

# Detener servicios
docker-compose down
```

---💬 Chat con agentes específicos
## Chat con agente por defecto (backward compatible)

```bash
# Primera pregunta en la sesión "user123" con agente default
# Chatear con agente Python
curl -X POST "http://localhost:8000/chat" \
  -H agent_id": "default",
    ""Content-Type: application/json" \
  -d '{
    "message": "¿Cómo creo un decorador?",
    "agent_id": "python-expert",
    "session_id": "user123",
    "use_rag": true
  }'

# Chaagent_id": "default",
    "session_id": "user123"
  }'
```

---

## 📝 Gestión de Sesiones por Agentees sociales",
    "agent_id": "marketing-pro",
    "session_id": "user123",
    "use_rag": true
  }'
```

## Chat con agente por defecto (backward compatible)

## 🤖 Sistema de Agentes

### Crear agentes especializados
```bash
# Agente experto en Python
curl -X POST "http://localhost:8000/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "python-expert",
    "name": "Python Expert",
    "prompt": "Eres un experto en Python...",
    "description": "Especialista en Python"
  }'

# Agente de marketing
curl -X POST "http://localhost:8000/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "marketing-pro",
    "name": "Marketing Expert",
    "prompt": "Eres un experto en marketing digital...",
    "description": "Especialista en marketing"
  }'
```

### Listar agentes
```bash
curl http://localhost:8000/agents
## 📝 Gestión de Sesiones por Agente

### Listar todas las sesiones
```bash
curl http://localhost:8000/sessions
```

### Listar sesiones de un agente específico
```bash
curl "http://localhost:8000/sessions?agent_id=python-expert"
```

### Ver historial de una sesión específica
```bash
curl http://localhost:8000/sessions/python-expert/user123
## 📄 RAG y Documentos

### Subir documento para RAG
```bash
# Subir a agente específico
curl -X POST "http://localhost:8000/ingest?agent_id=python-expert" \
  -F "upload=@documento.pdf"

# Subir al agente default (si no especificas agent_id)
curl -X POST "http://localhost:8000/ingest" \
  -F "upload=@documento.pdf"
```

**Nota:** Los documentos solo están disponibles para el agente al que se suben.

---

## 🔒 Gestión de Colecciones por Agente

### Ver colecciones de todos los agentes
```bash
curl http://localhost:8000/chromadb/agents
```

### Ver documentos de un agente específico
```bash
curl http://localhost:8000/chromadb/agents/python-expert
```

### Eliminar documentos de un agente
```bash
curl -X DELETE http://localhost:8000/chromadb/agents/python-expert
```

---

## 🔧 Prueba Automatizada

```bash
# Ejecutar script de prueba de agentes
python test_agents.py

# Ejecutar prueba de aislamiento de colecciones
python test_isolation.py
```

**test_agents.py** prueba:
- Creación de agentes
- Chat con diferentes agentes
- Gestión de sesiones
- Estadísticas
- Actualización de agentes

**test_isolation.py** prueba:
- Aislamiento de datos entre agentes
- Que cada agente solo accede a sus propios documentos
- Ingesta específica por agente

---

## 📚 Más Información

Para ejemplos detallados y casos de uso avanzados, consulta:
- **[AGENTES.md](AGENTES.md)** - Documentación completa del sistema de agentes
- **[README.md](README.md)** - Información general de la API

---
    "message": "¿Qué formatos de facturación soportan?",
    "session_id": "user123",
    "use_rag": true
  }'

# Segunda pregunta en la MISMA sesión (mantiene contexto)
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Y cuál me recomiendas?",
    "session_id": "user123"
  }'
```

## Listar todas las sesiones activas
```bash
curl http://localhost:8000/sessions
```

## Ver historial de una sesión
```bash
curl http://localhost:8000/sessions/user123
```

## Limpiar historial de una sesión
```bash
curl -X DELETE http://localhost:8000/sessions/user123
```

## Subir documento para RAG
```bash
curl -X POST "http://localhost:8000/ingest" \
  -F "upload=@documento.pdf"
```

## Configuración de sesión
- Cada `session_id` mantiene su propio historial independiente
- Por defecto se usa "default" si no se especifica
- Las sesiones expiran después de 1 hora de inactividad (configurable con `SESSION_TTL`)
- El historial se recupera automáticamente en cada mensaje

## Administración de ChromaDB

### Listar todas las colecciones
```bash
curl http://localhost:8000/chromadb/collections
```

### Ver información de una colección
```bash
curl http://localhost:8000/chromadb/collections/kb_store
```

### Ver primeros 10 documentos de una colección
```bash
curl http://localhost:8000/chromadb/collections/kb_store/peek
```

### Ver primeros N documentos (límite personalizado)
```bash
curl "http://localhost:8000/chromadb/collections/kb_store/peek?limit=20"
```

### Obtener todos los documentos de una colección
```bash
curl http://localhost:8000/chromadb/collections/kb_store/documents
```

### Vaciar la colección principal
```bash
curl -X POST http://localhost:8000/chromadb/clear
```

### Eliminar una colección específica
```bash
curl -X DELETE http://localhost:8000/chromadb/collections/nombre_coleccion
```

**Nota:** No se puede eliminar la colección principal 'kb_store' directamente. Usa `/chromadb/clear` para vaciarla.
