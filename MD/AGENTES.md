# Sistema de Múltiples Agentes - Ejemplos de Uso

## 🤖 Gestión de Agentes

### Crear un nuevo agente
```bash
curl -X POST "http://localhost:8000/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Experto en Python",
    "prompt": "Eres un experto en programación Python con 10 años de experiencia. Siempre proporcionas código limpio, bien documentado y siguiendo las mejores prácticas. Explicas conceptos complejos de manera clara.",
    "description": "Agente especializado en desarrollo Python"
  }'
```

### Crear agente con ID personalizado
```bash
curl -X POST "http://localhost:8000/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "python-expert",
    "name": "Python Expert",
    "prompt": "Eres un experto en Python...",
    "description": "Experto en Python"
  }'
```

### Listar todos los agentes
```bash
curl http://localhost:8000/agents
```

### Ver detalles de un agente (incluye estadísticas)
```bash
curl http://localhost:8000/agents/default
```

### Actualizar un agente
```bash
curl -X PUT "http://localhost:8000/agents/python-expert" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Senior Python Developer",
    "prompt": "Eres un desarrollador senior Python especializado en arquitecturas escalables...",
    "description": "Senior Python developer"
  }'
```

### Actualizar solo el prompt
```bash
curl -X PUT "http://localhost:8000/agents/python-expert" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Nuevo prompt actualizado..."
  }'
```

### Eliminar un agente
```bash
curl -X DELETE http://localhost:8000/agents/python-expert
```

**Nota:** El agente "default" no se puede eliminar.

---

## 💬 Chat con Agentes Específicos

### Chat con el agente por defecto
```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hola, ¿cómo estás?",
    "agent_id": "default",
    "session_id": "user123"
  }'
```

### Chat con agente personalizado
```bash
# 1. Crear agente
curl -X POST "http://localhost:8000/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "python-expert",
    "name": "Python Expert",
    "prompt": "Eres un experto en Python..."
  }'

# 2. Subir documentos ESPECÍFICOS para este agente
curl -X POST "http://localhost:8000/ingest?agent_id=python-expert" \
  -F "upload=@python_docs.pdf"

# 3. Primera pregunta (con RAG de SU colección)
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Cómo implemento un decorador en Python?",
    "agent_id": "python-expert",
    "session_id": "dev001",
    "use_rag": true
  }'

# 4. Segunda pregunta en la MISMA sesión (mantiene contexto)
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Y cómo lo uso con argumentos?",
    "agent_id": "python-expert",
    "session_id": "dev001"
  }'
```

### Múltiples usuarios con el mismo agente
```bash
# Usuario 1 con agente Python
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explícame los generadores",
    "agent_id": "python-expert",
    "session_id": "user1"
  }'

# Usuario 2 con el mismo agente (conversación independiente)
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Qué son las list comprehensions?",
    "agent_id": "python-expert",
    "session_id": "user2"
  }'
```

---

## 📝 Gestión de Sesiones

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
curl http://localhost:8000/sessions/python-expert/dev001
```

### Limpiar historial de una sesión
```bash
curl -X DELETE http://localhost:8000/sessions/python-expert/dev001
```

---

## 🎯 Ejemplos de Agentes Especializados

### Agente de Soporte Técnico
```bash
curl -X POST "http://localhost:8000/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "soporte-tecnico",
    "name": "Soporte Técnico 24/7",
    "prompt": "Eres un agente de soporte técnico profesional y paciente. Tu objetivo es ayudar a resolver problemas técnicos de manera clara y paso a paso. Siempre preguntas para entender mejor el problema antes de dar soluciones. Eres amable y empático.",
    "description": "Agente especializado en soporte técnico"
  }'
```

### Agente de Marketing
```bash
curl -X POST "http://localhost:8000/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "marketing-expert",
    "name": "Experto en Marketing Digital",
    "prompt": "Eres un experto en marketing digital con especialización en redes sociales, SEO y contenido. Proporcionas estrategias creativas, basadas en datos y orientadas a resultados. Tu comunicación es persuasiva pero honesta.",
    "description": "Especialista en marketing digital y estrategia"
  }'
```

### Agente de Análisis de Datos
```bash
curl -X POST "http://localhost:8000/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "data-analyst",
    "name": "Analista de Datos",
    "prompt": "Eres un analista de datos senior especializado en Python, SQL y visualización. Ayudas a interpretar datos, crear visualizaciones significativas y proporcionar insights accionables. Explicas conceptos estadísticos de manera accesible.",
    "description": "Especialista en análisis de datos"
  }'
```

---

## 🔧 Uso Avanzado

### Conversación multi-agente (mismo usuario, diferentes especialistas)
```bash
# Consulta técnica con agente de Python
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Necesito optimizar una consulta SQL",
    "agent_id": "data-analyst",
    "session_id": "proyecto-abc"
  }'

# Consulta de marketing para el mismo proyecto
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Cómo promociono esta nueva feature?",
    "agent_id": "marketing-expert",
    "session_id": "proyecto-abc"
  }'
```

### Configuración de temperatura personalizada
```bash
# Respuestas más creativas (temperatura alta)
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Dame ideas creativas para nombres de producto",
    "agent_id": "marketing-expert",
    "session_id": "brainstorm",
    "temperature": 0.8
  }'

# Respuestas más precisas (temperatura baja)
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Cuál es la sintaxis exacta de list comprehension?",
    "agent_id": "python-expert",
    "session_id": "learning",
    "temperature": 0.1
  }'
```

---

## 📊 Monitoreo y Estadísticas

### Ver estadísticas de un agente
```bash
curl http://localhost:8000/agents/python-expert
# Incluye: active_sessions, total_messages
```

### Ver todas las sesiones activas
```bash
curl http://localhost:8000/sessions
```

---

## 🛠️ Arquitectura

- **Agentes**: Cada agente tiene su propio prompt y personalidad
- **Sesiones**: Cada combinación `agent_id + session_id` mantiene su propio historial
- **Persistencia**: Todo se guarda en Redis con TTL configurable
- **RAG**: Todos los agentes pueden usar el mismo conocimiento vectorial

**Ejemplo de claves en Redis:**
```
agent:default → Información del agente default
agent:python-expert → Información del agente python-expert
chat_session:python-expert:user123 → Historial de conversación
chat_session:marketing-expert:user123 → Otro historial independiente
```
