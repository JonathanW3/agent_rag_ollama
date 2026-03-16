# 🔧 API de Gestión de Modelos Ollama

Esta documentación describe las nuevas APIs para gestionar modelos LLM de Ollama.

## 📋 Endpoints Disponibles

### 1. **Listar Modelos Disponibles**
```bash
GET /ollama/models
```

Lista todos los modelos LLM descargados en tu sistema Ollama.

**Ejemplo:**
```bash
curl http://localhost:8000/ollama/models
```

**Respuesta:**
```json
{
  "status": "ok",
  "count": 3,
  "current_chat_model": "llama3",
  "current_embed_model": "nomic-embed-text",
  "models": [
    {
      "name": "llama3:latest",
      "size": 4661211808,
      "modified": "2024-01-15T10:30:00Z",
      "digest": "a4f4b8a6c8d9..."
    },
    {
      "name": "mistral:latest",
      "size": 4109856768,
      "modified": "2024-01-10T15:20:00Z",
      "digest": "b3c2d1e5f9a8..."
    }
  ]
}
```

---

### 2. **Ver Modelos Actualmente en Uso**
```bash
GET /ollama/models/current
```

Muestra qué modelos están activos para chat y embeddings.

**Ejemplo:**
```bash
curl http://localhost:8000/ollama/models/current
```

**Respuesta:**
```json
{
  "status": "ok",
  "chat_model": "llama3",
  "embed_model": "nomic-embed-text",
  "ollama_url": "http://localhost:11434"
}
```

---

### 3. **Cambiar Modelo Activo**
```bash
POST /ollama/models/select
```

Cambia el modelo LLM en runtime sin reiniciar el servidor.

**Parámetros:**
- `model_name` (string) - Nombre del modelo a usar
- `model_type` (string) - Tipo: `"chat"` o `"embed"`

**Ejemplo - Cambiar modelo de chat:**
```bash
curl -X POST "http://localhost:8000/ollama/models/select" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "llama3.1",
    "model_type": "chat"
  }'
```

**Ejemplo - Cambiar modelo de embeddings:**
```bash
curl -X POST "http://localhost:8000/ollama/models/select" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "nomic-embed-text",
    "model_type": "embed"
  }'
```

**Respuesta:**
```json
{
  "status": "ok",
  "message": "Modelo de chat cambiado exitosamente",
  "previous_model": "llama3",
  "current_model": "llama3.1",
  "type": "chat"
}
```

---

### 4. **Descargar Nuevo Modelo**
```bash
POST /ollama/models/download
```

Descarga un nuevo modelo de Ollama (equivalente a `ollama pull`).

**Parámetros:**
- `model_name` (string) - Nombre del modelo a descargar

**Ejemplo:**
```bash
curl -X POST "http://localhost:8000/ollama/models/download" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "mistral"
  }'
```

**Respuesta (Streaming):**
```json
{"status":"starting","message":"Iniciando descarga de mistral..."}
{"status":"pulling manifest"}
{"status":"downloading","digest":"sha256:1234...","total":4234567890,"completed":512000000}
{"status":"downloading","digest":"sha256:1234...","total":4234567890,"completed":1024000000}
...
{"status":"completed","message":"Modelo 'mistral' descargado exitosamente","model":"mistral"}
```

---

### 5. **Información Detallada de un Modelo**
```bash
GET /ollama/models/{model_name}
```

Obtiene información detallada sobre un modelo específico.

**Ejemplo:**
```bash
curl http://localhost:8000/ollama/models/llama3
```

**Respuesta:**
```json
{
  "status": "ok",
  "model": "llama3",
  "info": {
    "modelfile": "...",
    "parameters": "...",
    "template": "...",
    "details": {
      "format": "gguf",
      "family": "llama",
      "families": ["llama"],
      "parameter_size": "7B",
      "quantization_level": "Q4_0"
    }
  }
}
```

---

## 🚀 Flujo de Trabajo Típico

### 1. Ver modelos disponibles
```bash
curl http://localhost:8000/ollama/models
```

### 2. Descargar un nuevo modelo (opcional)
```bash
curl -X POST "http://localhost:8000/ollama/models/download" \
  -H "Content-Type: application/json" \
  -d '{"model_name": "llama3.1"}'
```

### 3. Cambiar al nuevo modelo
```bash
curl -X POST "http://localhost:8000/ollama/models/select" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "llama3.1",
    "model_type": "chat"
  }'
```

### 4. Chatear con el nuevo modelo
```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hola, ¿qué modelo eres?",
    "agent_id": "default",
    "session_id": "test123"
  }'
```

---

## 🤖 Modelos Populares Disponibles

### Modelos de Chat:
- **llama3**, **llama3.1**, **llama3.2** - Modelos de Meta (recomendados)
- **mistral** - Modelo eficiente y rápido
- **mixtral** - Modelo mixture-of-experts
- **codellama** - Especializado en programación
- **gemma** - Modelo de Google
- **qwen2.5** - Modelo multilingüe

### Modelos de Embeddings:
- **nomic-embed-text** - Embeddings de alta calidad (recomendado)
- **all-minilm** - Embeddings ligeros y rápidos

Para ver todos los modelos disponibles en Ollama:
https://ollama.ai/library

---

## 💡 Notas Importantes

1. **Sin Reinicio**: Puedes cambiar modelos sin reiniciar el servidor
2. **Persistencia**: El cambio persiste solo mientras el servidor está activo
3. **Variable de Entorno**: Para cambio permanente, usa `CHAT_MODEL` o `EMBED_MODEL`
4. **Descarga**: Los modelos grandes pueden tardar varios minutos en descargarse
5. **Espacio**: Verifica que tengas suficiente espacio en disco

---

## 🐛 Troubleshooting

### Error: "Modelo no encontrado"
```bash
# Primero descarga el modelo
curl -X POST "http://localhost:8000/ollama/models/download" \
  -H "Content-Type: application/json" \
  -d '{"model_name": "tu-modelo"}'
```

### Verificar que Ollama esté corriendo
```powershell
ollama list
```

### Ver logs del servidor
```powershell
# En el terminal donde corre uvicorn
# Los errores aparecerán ahí
```

---

## 📝 Acceso desde Swagger UI

Todos estos endpoints están disponibles en la interfaz Swagger:

```
http://localhost:8000/docs
```

Busca la sección **"🔧 Ollama"** en la documentación interactiva.
