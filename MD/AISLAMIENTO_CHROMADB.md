# 🔒 Sistema de Colecciones por Agente - ChromaDB

## ✅ Implementación Completada

Cada agente ahora tiene su **propia colección ChromaDB aislada**. Los documentos ingresados para un agente solo están disponibles para ese agente específico.

---

## 🏗️ Arquitectura

### Antes (Colección Compartida)
```
ChromaDB
└── kb_store  ← Todos los agentes accedían aquí
```

### Ahora (Colecciones Aisladas)
```
ChromaDB
├── kb_store_default           ← Solo agente default
├── kb_store_python-expert     ← Solo agente python-expert
├── kb_store_marketing-pro     ← Solo agente marketing-pro
└── kb_store_data-analyst      ← Solo agente data-analyst
```

---

## 📝 Cambios en la API

### 1. Endpoint `/ingest` - Ahora acepta `agent_id`

**Antes:**
```bash
curl -X POST "http://localhost:8000/ingest" \
  -F "upload=@documento.pdf"
# Se guardaba en colección global
```

**Ahora:**
```bash
# Ingerir documento para agente específico
curl -X POST "http://localhost:8000/ingest?agent_id=python-expert" \
  -F "upload=@documento.pdf"

# Si no especificas agent_id, usa "default"
curl -X POST "http://localhost:8000/ingest" \
  -F "upload=@documento.pdf"
```

**Respuesta:**
```json
{
  "status": "ok",
  "chunks": 42,
  "agent_id": "python-expert",
  "collection": "kb_store_python-expert"
}
```

---

### 2. Endpoint `/chat` - Usa colección del agente automáticamente

```bash
# El agente solo busca en SU colección
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Qué dice la documentación?",
    "agent_id": "python-expert",
    "session_id": "user123",
    "use_rag": true
  }'
```

**Comportamiento:**
- Busca **solo** en `kb_store_python-expert`
- Otros agentes NO tienen acceso a estos documentos

---

### 3. Nuevos Endpoints para Gestión de Colecciones por Agente

#### Listar colecciones de todos los agentes
```bash
GET /chromadb/agents
```

**Respuesta:**
```json
{
  "collections": [
    {
      "agent_id": "default",
      "collection_name": "kb_store_default",
      "count": 15
    },
    {
      "agent_id": "python-expert",
      "collection_name": "kb_store_python-expert",
      "count": 23
    }
  ],
  "count": 2
}
```

#### Ver documentos de un agente específico
```bash
GET /chromadb/agents/{agent_id}
```

**Ejemplo:**
```bash
curl http://localhost:8000/chromadb/agents/python-expert
```

**Respuesta:**
```json
{
  "name": "kb_store_python-expert",
  "count": 23,
  "metadata": {}
}
```

#### Obtener todos los documentos de un agente
```bash
GET /chromadb/agents/{agent_id}/documents
```

**Ejemplo:**
```bash
curl http://localhost:8000/chromadb/agents/python-expert/documents
```

#### Eliminar documentos de un agente
```bash
DELETE /chromadb/agents/{agent_id}
```

**Ejemplo:**
```bash
curl -X DELETE http://localhost:8000/chromadb/agents/python-expert
```

---

### 4. Eliminación de Agente - Ahora con opción de documentos

```bash
# Eliminar agente Y sus documentos (default)
curl -X DELETE "http://localhost:8000/agents/python-expert"

# Eliminar solo el agente, mantener documentos
curl -X DELETE "http://localhost:8000/agents/python-expert?delete_documents=false"
```

---

## 🎯 Casos de Uso

### Caso 1: Agentes con Conocimiento Especializado

```bash
# 1. Crear agente Python
curl -X POST "http://localhost:8000/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "python-expert",
    "name": "Python Expert",
    "prompt": "Eres un experto en Python..."
  }'

# 2. Subir documentación de Python al agente
curl -X POST "http://localhost:8000/ingest?agent_id=python-expert" \
  -F "upload=@python_docs.pdf"

# 3. Crear agente Marketing
curl -X POST "http://localhost:8000/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "marketing-pro",
    "name": "Marketing Expert",
    "prompt": "Eres un experto en marketing..."
  }'

# 4. Subir materiales de marketing
curl -X POST "http://localhost:8000/ingest?agent_id=marketing-pro" \
  -F "upload=@marketing_guide.pdf"

# 5. Cada agente solo ve SU contenido
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explica los decoradores",
    "agent_id": "python-expert",
    "use_rag": true
  }'
# ✅ Busca en python_docs.pdf

curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Estrategias de SEO",
    "agent_id": "marketing-pro",
    "use_rag": true
  }'
# ✅ Busca en marketing_guide.pdf (NO en python_docs.pdf)
```

---

### Caso 2: Múltiples Departamentos

```bash
# Departamento de RRHH
curl -X POST "http://localhost:8000/agents" -H "Content-Type: application/json" \
  -d '{"agent_id":"hr-assistant","name":"HR Assistant","prompt":"..."}'

curl -X POST "http://localhost:8000/ingest?agent_id=hr-assistant" \
  -F "upload=@politicas_rrhh.pdf"

# Departamento Legal
curl -X POST "http://localhost:8000/agents" -H "Content-Type: application/json" \
  -d '{"agent_id":"legal-advisor","name":"Legal Advisor","prompt":"..."}'

curl -X POST "http://localhost:8000/ingest?agent_id=legal-advisor" \
  -F "upload=@contratos.pdf"

# ✅ HR no puede acceder a documentos legales
# ✅ Legal no puede acceder a documentos de RRHH
```

---

## 🔒 Seguridad y Aislamiento

### ✅ Garantías
- Cada agente **SOLO** puede acceder a su propia colección
- Los documentos están **completamente aislados** por agente
- No hay forma de que un agente acceda a documentos de otro agente
- Al eliminar un agente, puedes optar por mantener o eliminar sus documentos

### ⚠️ Consideraciones
- **Duplicación de datos**: Si necesitas el mismo documento en múltiples agentes, debes subirlo múltiples veces
- **Almacenamiento**: Cada copia de documento consume espacio adicional
- **Mantenimiento**: Actualizar un documento requiere actualizarlo en cada agente

---

## 📊 Monitoreo

### Ver estado de colecciones
```bash
# Ver todas las colecciones de agentes
curl http://localhost:8000/chromadb/agents

# Ver cuántos documentos tiene cada agente
curl http://localhost:8000/agents  # Incluye stats
```

---

## 🔄 Migración de Datos

Si tenías datos en la colección antigua `kb_store`, ahora:
- Están accesibles como `kb_store_default`
- Solo el agente "default" puede acceder a ellos
- Otros agentes necesitan que les subas documentos específicamente

Si quieres migrar documentos existentes a otros agentes, debes:
1. Descargar/copiar los archivos originales
2. Subirlos con el `agent_id` correspondiente

---

## 🧪 Prueba de Aislamiento

```bash
# 1. Crear dos agentes
curl -X POST http://localhost:8000/agents -H "Content-Type: application/json" \
  -d '{"agent_id":"agent-a","name":"Agent A","prompt":"Agente A"}'

curl -X POST http://localhost:8000/agents -H "Content-Type: application/json" \
  -d '{"agent_id":"agent-b","name":"Agent B","prompt":"Agente B"}'

# 2. Subir documento SOLO a agent-a
curl -X POST "http://localhost:8000/ingest?agent_id=agent-a" \
  -F "upload=@documento_secreto.txt"

# 3. Intentar acceder con agent-a (funciona)
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"message":"Resumen del documento","agent_id":"agent-a","use_rag":true}'
# ✅ Recibe información del documento

# 4. Intentar acceder con agent-b (NO funciona)
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"message":"Resumen del documento","agent_id":"agent-b","use_rag":true}'
# ❌ No encuentra el documento, responde sin contexto
```

---

## 📚 Resumen

| Antes | Ahora |
|-------|-------|
| Todos los agentes compartían documentos | Cada agente tiene su colección privada |
| `/ingest` guardaba en colección global | `/ingest?agent_id=X` guarda para agente X |
| Posible filtración de información entre agentes | Aislamiento completo garantizado |
| Difícil controlar acceso a datos | Control granular por agente |

**¡El sistema ahora proporciona aislamiento completo de conocimiento por agente!** 🎉
