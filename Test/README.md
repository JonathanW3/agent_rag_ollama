# 🤖 RAG Ollama API - Manager Dashboard

Aplicación web interactiva construida con Streamlit para gestionar y probar todas las funcionalidades del sistema multi-agente RAG Ollama API.

## 🚀 Instalación

1. Activar el entorno virtual (si no está activado):
```powershell
.venv\Scripts\Activate.ps1
```

2. Instalar dependencias de Streamlit:
```powershell
pip install streamlit requests
```

O usar el archivo de requirements:
```powershell
pip install -r Test/requirements.txt
```

## ▶️ Ejecución

1. Asegurarse de que la API FastAPI esté ejecutándose:
```powershell
uvicorn app.main:app --reload
```

2. En otra terminal, ejecutar la aplicación Streamlit:
```powershell
streamlit run Test/app_manager.py
```

3. La aplicación se abrirá automáticamente en tu navegador en `http://localhost:8501`

## 📋 Funcionalidades

### 🏠 Dashboard Inicio
- **Vista general del sistema** con métricas en tiempo real
- Número de agentes activos
- Sesiones de conversación
- Documentos cargados
- Resumen de todos los agentes con sus estadísticas

### 🤖 Gestión de Agentes
**Crear nuevos agentes:**
1. Define un ID único (ej: `bot-legal`, `asistente-medico`)
2. Asigna un nombre descriptivo
3. Escribe una descripción (opcional)
4. Configura el prompt del sistema que define su comportamiento

**Administrar agentes existentes:**
- Ver detalles completos de cada agente
- Actualizar configuración
- Eliminar agentes (excepto el agente `default`)
- Ver estadísticas de uso

### 💬 Chat & Conversación
**Conversar con cualquier agente:**
1. Selecciona el agente con el que quieres chatear
2. Define un Session ID (puedes tener múltiples conversaciones separadas)
3. Configura opciones avanzadas:
   - Activar/desactivar RAG (recuperación de documentos)
   - Ajustar Top K (cantidad de chunks a recuperar)
   - Modificar temperature (creatividad de respuestas)
4. Envía mensajes y mantén conversaciones contextualizadas

**Características:**
- Historial de conversación persistente por sesión
- Visualización de mensajes en formato chat
- Opción para limpiar historial
- Vista de fuentes RAG utilizadas

### 📄 Gestión de Documentos
**Cargar documentos PDF:**
1. Selecciona el agente propietario de la base de conocimientos
2. Sube un archivo PDF
3. El sistema automáticamente:
   - Extrae el texto del PDF
   - Divide en chunks semánticos
   - Genera embeddings
   - Almacena en la colección del agente

**Administrar documentos:**
- Ver cantidad de documentos por agente
- Preview de documentos/chunks cargados
- Eliminar documentos de un agente específico

### 📝 Gestión de Sesiones
**Monitorear conversaciones:**
- Lista de todas las sesiones activas
- Filtrar sesiones por agente
- Ver historial completo de cada sesión
- Eliminar sesiones individuales
- Contador de mensajes por sesión

### 🗄️ ChromaDB Admin
**Administración avanzada de ChromaDB:**
- Vista de todas las colecciones en ChromaDB
- Estadísticas de cada colección
- Preview de documentos embebidos
- Información detallada de metadata
- Eliminar colecciones específicas

### 📧 Email (SMTP)
**Envío de emails desde agentes:**
- **Enviar Emails**: Envía emails usando la configuración SMTP de cualquier agente
- **Proveedores SMTP**: Configuraciones predefinidas para Gmail, Outlook, Yahoo, Office365
- **Configurar Agente**: Asigna credenciales SMTP a un agente
- **Historial**: Ver registro de emails enviados (con MCP SQLite)

**Características:**
- Soporte para múltiples proveedores SMTP
- CC, BCC y formato HTML
- App Passwords para Gmail/Yahoo
- Registro automático en SQLite
- Configuración por agente

## 🎯 Flujo Recomendado de Uso

### Primera vez / Crear un nuevo agente:

1. **🤖 Ir a "Gestión de Agentes"**
   - Crear un nuevo agente con un prompt específico
   - Ejemplo: "Asistente Médico" con prompt sobre terminología médica

2. **📄 Ir a "Documentos"** (Opcional)
   - Cargar documentos PDF relevantes para el agente
   - Los documentos proporcionan contexto RAG

3. **💬 Ir a "Chat & Conversación"**
   - Seleccionar el agente creado
   - Iniciar conversación
   - Activar RAG para usar los documentos cargados

4. **� Configurar Email (Opcional)**
   - Ir a "Email" → "Configurar Agente"
   - Agregar credenciales SMTP al agente
   - Ahora el agente puede enviar emails automáticamente

5. **�📝 Monitorear "Sesiones"**
   - Ver el historial de conversaciones
   - Gestionar sesiones antiguas

## 💡 Consejos de Uso

### Creación de Agentes
- **IDs descriptivos:** Usa nombres claros como `bot-legal`, `asistente-ventas`
- **Prompts específicos:** Define claramente el rol y comportamiento esperado
- **Descripciones útiles:** Ayudan a recordar el propósito de cada agente

### Chat
- **Session IDs:** Usa diferentes IDs para separar contextos (ej: `cliente-123`, `consulta-tecnica`)
- **RAG activado:** Mejor usa RAG=true si has cargado documentos relevantes
- **Top K:** Valores entre 3-5 son ideales para la mayoría de casos
- **Temperature:** 
  - 0.1-0.3: Respuestas más determinísticas y precisas
  - 0.7-0.9: Respuestas más creativas y variadas

### Documentos
- **PDFs estructurados:** Funcionan mejor que documentos con mucho formato
- **Documentos por agente:** Asigna documentos relevantes a cada agente específico

### Email (SMTP)
- **Gmail/Yahoo:** Requieren App Passwords, no tu contraseña normal
- **Proveedores:** Usa las plantillas predefinidas para configuración rápida
- **Testing:** Envía un email de prueba antes de usar en producción
- **Seguridad:** Las credenciales se almacenan en Redis (considera cifrado para producción)
- **Rate Limits:** Gmail: 500/día (gratis), 2000/día (Workspace)
- **Tamaño:** No hay límite estricto, pero documentos muy grandes tardarán más en procesarse

### Sesiones
- **Limpieza regular:** Elimina sesiones antiguas para mantener el sistema organizado
- **Identificación:** Usa Session IDs descriptivos para encontrar conversaciones fácilmente

## 🛠️ Troubleshooting

### La API no está disponible
**Error:** "❌ API No Disponible"

**Solución:**
1. Verifica que la API esté ejecutándose: `http://localhost:8000/docs`
2. Revisa los contenedores Docker:
   ```powershell
   docker ps
   ```
3. Verifica que Redis y ChromaDB estén activos

### No puedo cargar documentos
**Solución:**
1. Asegúrate de que el archivo sea PDF válido
2. Verifica que el agente exista
3. Revisa los logs de la API FastAPI
4. Confirma que ChromaDB esté funcionando

### El email no se envía
**Error:** "Error de autenticación SMTP"

**Solución:**
1. Para Gmail/Yahoo: Usa App Password, no tu contraseña normal
   - Gmail: https://myaccount.google.com/apppasswords (requiere 2FA)
   - Yahoo: https://login.yahoo.com/account/security
2. Verifica que el servidor y puerto sean correctos
3. Confirma que TLS/SSL esté configurado correctamente
4. Prueba las credenciales con un cliente de email primero

### Email enviado pero no aparece en historial
**Solución:**
1. Verifica que MCP SQLite esté habilitado
2. Inicializa la base de datos del agente: Ir a "MCP SQLite" → Inicializar
3. Revisa los logs en la pestaña "MCP SQLite" → "Query Builder"

### El chat no responde
**Solución:**
1. Verifica que Ollama esté ejecutándose
2. Confirma que el modelo `llama3` esté disponible:
   ```powershell
   ollama list
   ```
3. Revisa los logs de la terminal donde corre FastAPI

### Sesiones no aparecen
**Solución:**
1. Verifica que Redis esté activo:
   ```powershell
   docker ps | findstr redis
   ```
2. Revisa la conexión Redis en la API
3. Prueba el botón "🔄 Actualizar Lista"

## 📚 Recursos Adicionales

- **API Docs:** `http://localhost:8000/docs`
- **Streamlit Docs:** `https://docs.streamlit.io`
- **Ollama Models:** `https://ollama.ai/library`

## 🎨 Características de la UI

- ✅ **Interfaz intuitiva** con tabs organizados
- ✅ **Estado en tiempo real** de la API
- ✅ **Guía rápida** en el sidebar
- ✅ **Métricas visuales** con cards y gráficos
- ✅ **Confirmaciones** para acciones destructivas
- ✅ **Feedback visual** con mensajes de éxito/error
- ✅ **Responsive design** con columnas adaptativas

## 🔧 Configuración

### Cambiar URL de la API
Si la API está en otro puerto o servidor, modifica en `app_manager.py`:

```python
API_BASE_URL = "http://localhost:8000"  # Cambiar aquí
```

### Puerto de Streamlit
Por defecto usa el puerto 8501. Para cambiarlo:

```powershell
streamlit run Test/app_manager.py --server.port 8502
```

## 📝 Notas

- La aplicación requiere que la API FastAPI esté ejecutándose
- Todos los cambios son persistentes (almacenados en Redis y ChromaDB)
- El agente `default` no puede ser eliminado
- Las sesiones tienen TTL configurado en Redis (por defecto 24 horas)

---

**🤖 Desarrollado para RAG Ollama API Multi-Agent System**
