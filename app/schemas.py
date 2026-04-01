from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Modelo para solicitudes de chat con agentes.

    Los campos use_rag, use_mysql, use_email, top_k y temperature son opcionales.
    Si se envían como None, se usan los valores guardados en la configuración del agente.
    """
    message: str = Field(..., description="Mensaje del usuario", example="¿Cómo implemento un decorador en Python?")
    agent_id: str = Field(default="default", description="ID del agente con el que chatear", example="python-expert")
    session_id: str = Field(default="default", description="ID de sesión para mantener contexto conversacional", example="user123")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0, description="Temperatura del modelo (None=usar config del agente)")
    top_k: int | None = Field(default=None, ge=1, le=100, description="Número de documentos a recuperar de RAG (None=usar config del agente)")
    use_rag: bool | None = Field(default=None, description="Usar RAG (None=usar config del agente)")
    use_sql: bool = Field(default=False, description="Permitir consultas a datos estructurados (SQLite) mediante MCP")
    use_mysql: bool | None = Field(default=None, description="Permitir consultas MySQL (None=usar config del agente)")
    use_email: bool | None = Field(default=None, description="Permitir envío de emails (None=usar config del agente)")
    use_charts: bool | None = Field(default=None, description="Habilitar gráficos Plotly (None=usar config del agente)")
    use_calendar: bool | None = Field(default=None, description="Habilitar Google Calendar (None=usar config del agente)")
    use_ibm: bool | None = Field(default=None, description="Habilitar consultas MySQL IBM (None=usar config del agente)")
    use_autopart: bool | None = Field(default=None, description="Habilitar consultas MySQL Autopart (None=usar config del agente)")


class AgentCreate(BaseModel):
    """Modelo para crear un nuevo agente."""
    name: str = Field(..., description="Nombre del agente", example="Experto en Python")
    prompt: str = Field(..., description="Prompt del sistema que define la personalidad y expertise del agente", example="Eres un experto en Python con 10 años de experiencia...")
    description: str = Field(default="", description="Descripción breve del agente", example="Especialista en desarrollo Python")
    agent_id: str | None = Field(default=None, description="ID personalizado (opcional, se genera automáticamente si se omite)", example="python-expert")
    organization: str | None = Field(default=None, description="Organización a la que pertenece el agente. Permite agrupar agentes por empresa/equipo.", example="IBM")
    llm_model: str | None = Field(default=None, description="Modelo LLM específico para este agente (opcional, usa el modelo global si se omite)", example="codellama")
    sqlite_db_path: str | None = Field(default=None, description="Ruta a base de datos SQLite personalizada (ej: 'Monitoring.db', './data/custom.db')", example="Monitoring.db")
    use_rag: bool = Field(default=True, description="Habilitar RAG/ChromaDB para este agente. Si es False, el agente no usará búsqueda vectorial.", example=True)
    smtp_config: dict | None = Field(default=None, description="Configuración SMTP para envío de emails", example={
        "server": "smtp.gmail.com",
        "port": 587,
        "email": "bot@gmail.com",
        "password": "app_password",
        "use_tls": True
    })
    use_mysql: bool = Field(default=False, description="Habilitar consultas MySQL (farmacia_db) por defecto para este agente")
    use_email: bool = Field(default=False, description="Habilitar envío de emails por defecto para este agente (requiere smtp_config)")
    use_charts: bool = Field(default=False, description="Habilitar gráficos Plotly por defecto para este agente")
    use_calendar: bool = Field(default=False, description="Habilitar Google Calendar por defecto para este agente")
    use_ibm: bool = Field(default=False, description="Habilitar consultas MySQL IBM (credit_cards, employees, sales_orders, etc.) por defecto")
    use_autopart: bool = Field(default=False, description="Habilitar consultas MySQL Autopart (vehicles, applications, compatibility, etc.) por defecto")
    top_k: int = Field(default=4, ge=1, le=100, description="Número de documentos RAG a recuperar por defecto")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Temperatura del modelo por defecto")
    alert_wa_session_id: str | None = Field(default=None, description="ID de sesión WhatsApp para enviar alertas internas", example="miempresawhts")
    alert_wa_number: str | None = Field(default=None, description="Número WhatsApp destino de alertas (formato internacional sin +)", example="5215512345678")
    alert_email: str | None = Field(default=None, description="Email destino de alertas internas (usa smtp_config del agente)", example="gerencia@empresa.com")


class AgentUpdate(BaseModel):
    """Modelo para actualizar un agente existente."""
    name: str | None = Field(default=None, description="Nuevo nombre del agente")
    prompt: str | None = Field(default=None, description="Nuevo prompt del sistema")
    description: str | None = Field(default=None, description="Nueva descripción")
    organization: str | None = Field(default=None, description="Organización a la que pertenece el agente")
    llm_model: str | None = Field(default=None, description="Nuevo modelo LLM (usa None para mantener el actual, '' para usar el global)")
    sqlite_db_path: str | None = Field(default=None, description="Ruta a base de datos SQLite personalizada (ej: 'Monitoring.db')")
    use_rag: bool | None = Field(default=None, description="Habilitar/deshabilitar RAG para este agente")
    smtp_config: dict | None = Field(default=None, description="Configuración SMTP para envío de emails")
    use_mysql: bool | None = Field(default=None, description="Habilitar/deshabilitar MySQL para este agente")
    use_email: bool | None = Field(default=None, description="Habilitar/deshabilitar email para este agente")
    use_charts: bool | None = Field(default=None, description="Habilitar/deshabilitar gráficos Plotly para este agente")
    use_calendar: bool | None = Field(default=None, description="Habilitar/deshabilitar Google Calendar para este agente")
    use_ibm: bool | None = Field(default=None, description="Habilitar/deshabilitar MySQL IBM para este agente")
    use_autopart: bool | None = Field(default=None, description="Habilitar/deshabilitar MySQL Autopart para este agente")
    top_k: int | None = Field(default=None, ge=1, le=100, description="Número de documentos RAG a recuperar por defecto")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0, description="Temperatura del modelo por defecto")
    alert_wa_session_id: str | None = Field(default=None, description="ID de sesión WhatsApp para alertas internas")
    alert_wa_number: str | None = Field(default=None, description="Número WhatsApp destino de alertas")
    alert_email: str | None = Field(default=None, description="Email destino de alertas internas")


class ModelSelectRequest(BaseModel):
    """Modelo para cambiar el modelo LLM activo."""
    model_config = {"protected_namespaces": ()}

    model_name: str = Field(..., description="Nombre del modelo a usar", example="llama3.1")
    model_type: str = Field(default="chat", description="Tipo de modelo: 'chat' o 'embed'", example="chat")


class ModelDownloadRequest(BaseModel):
    """Modelo para descargar un nuevo modelo de Ollama."""
    model_config = {"protected_namespaces": ()}

    model_name: str = Field(..., description="Nombre del modelo a descargar", example="mistral")


class PromptRequest(BaseModel):
    """Modelo para actualizar el prompt global del sistema (legacy)."""
    prompt: str = Field(..., description="Nuevo prompt del sistema")


class SQLQueryRequest(BaseModel):
    """Modelo para ejecutar consultas SQL."""
    query: str = Field(..., description="Consulta SQL a ejecutar", example="SELECT * FROM agent_logs ORDER BY timestamp DESC LIMIT 10")
    params: list | None = Field(default=None, description="Parámetros opcionales para la consulta", example=["chat_response"])


class SQLWriteRequest(BaseModel):
    """Modelo para ejecutar operaciones de escritura SQL."""
    query: str = Field(..., description="Operación SQL a ejecutar (INSERT, UPDATE, DELETE)", example="INSERT INTO custom_data (data_key, data_value) VALUES (?, ?)")
    params: list | None = Field(default=None, description="Parámetros para la consulta", example=["config_key", "config_value"])


class EmailSendRequest(BaseModel):
    """Modelo para enviar un email."""
    agent_id: str = Field(..., description="ID del agente que enviará el email (debe tener smtp_config)", example="email-assistant")
    to: str = Field(..., description="Email del destinatario", example="usuario@example.com")
    subject: str = Field(..., description="Asunto del email", example="Recordatorio importante")
    body: str = Field(..., description="Cuerpo del email", example="Hola, este es un mensaje de prueba.")
    cc: list[str] | None = Field(default=None, description="Emails en copia", example=["copia@example.com"])
    bcc: list[str] | None = Field(default=None, description="Emails en copia oculta", example=[])
    html: bool = Field(default=False, description="Si True, el body se interpreta como HTML")
    attachments: list[str] | None = Field(default=None, description="Rutas de archivos a adjuntar", example=[])


class MySQLQueryRequest(BaseModel):
    """Modelo para consultas MySQL."""
    query: str = Field(..., description="Consulta SELECT a ejecutar", example="SELECT * FROM farmacia LIMIT 5")
    params: list = Field(default=[], description="Parámetros para placeholders %s")


class IBMQueryRequest(BaseModel):
    """Modelo para consultas a la base de datos IBM."""
    query: str = Field(..., description="Consulta SELECT a ejecutar", example="SELECT * FROM credit_cards LIMIT 5")
    params: list = Field(default=[], description="Parámetros para placeholders %s")


class AutopartQueryRequest(BaseModel):
    """Modelo para consultas a la base de datos Autopart."""
    query: str = Field(..., description="Consulta SELECT a ejecutar", example="SELECT * FROM vehicles LIMIT 5")
    params: list = Field(default=[], description="Parámetros para placeholders %s")


class OrchestratorChatRequest(BaseModel):
    """Modelo para solicitudes al orquestador inteligente.

    El orquestador analiza el mensaje y lo rutea automáticamente al agente más adecuado
    de su lista de agentes permitidos.
    """
    message: str = Field(..., description="Mensaje del usuario", example="¿Cuál es el stock de paracetamol?")
    session_id: str = Field(default="default", description="ID de sesión para mantener contexto", example="user123")
    use_rag: bool | None = Field(default=None, description="Usar RAG (None=usar config del agente elegido)")
    use_sql: bool = Field(default=False, description="Permitir consultas SQLite")
    use_mysql: bool | None = Field(default=None, description="Permitir consultas MySQL (None=usar config del agente)")
    use_email: bool | None = Field(default=None, description="Permitir envío de emails (None=usar config del agente)")
    use_charts: bool | None = Field(default=None, description="Habilitar gráficos Plotly (None=usar config del agente)")
    use_calendar: bool | None = Field(default=None, description="Habilitar Google Calendar (None=usar config del agente)")
    use_ibm: bool | None = Field(default=None, description="Habilitar MySQL IBM (None=usar config del agente)")
    use_autopart: bool | None = Field(default=None, description="Habilitar MySQL Autopart (None=usar config del agente)")


class OrchestratorConfigRequest(BaseModel):
    """Modelo para configurar el orquestador."""
    allowed_agent_ids: list[str] = Field(..., description="Lista de agent_ids que el orquestador puede consultar", example=["farmacia-bot", "python-expert"])
    fallback_agent_id: str = Field(default="default", description="Agente a usar si ninguno es adecuado", example="default")
    llm_model: str | None = Field(default=None, description="Modelo LLM para clasificación (None=usa el global)", example="llama3.1")


class OrchestratorAddAgentsRequest(BaseModel):
    """Modelo para agregar agentes al orquestador."""
    agent_ids: list[str] = Field(..., description="IDs de agentes a agregar", example=["nuevo-agente"])


class FeedbackRequest(BaseModel):
    """Modelo para enviar feedback de un mensaje (thumbs up/down).

    Ejemplo mínimo:
    {"agent_id": "farmacia-bot", "session_id": "user123", "message_index": 1, "score": 1}
    """
    agent_id: str = Field(..., description="ID del agente", example="farmacia-bot")
    session_id: str = Field(..., description="ID de la sesión", example="user123")
    message_index: int = Field(..., ge=0, description="Índice del mensaje del asistente en el historial (0-based)", example=1)
    score: int = Field(..., ge=-1, le=1, description="Puntuación: 1 (positivo) o -1 (negativo). No se permite 0.", example=1)


class PromptProposalRequest(BaseModel):
    """Modelo para aprobar o rechazar una propuesta de prompt."""
    reason: str = Field(default="", description="Razón de la aprobación o rechazo")


class SupervisorTestRequest(BaseModel):
    """Modelo para configurar una prueba activa del supervisor contra un agente.

    El supervisor genera preguntas de prueba, las ejecuta contra el agente
    y evalúa las respuestas, uso de herramientas y adherencia al prompt.
    """
    num_turns: int = Field(default=5, ge=1, le=50, description="Número de preguntas de prueba a generar")
    focus_areas: list[str] | None = Field(default=None, description="Áreas específicas a evaluar (ej: ['rag', 'charts', 'email', 'mysql', 'general']). Si es None, evalúa todas las capacidades del agente.")
    custom_questions: list[str] | None = Field(default=None, description="Preguntas personalizadas adicionales para probar (se agregan a las generadas)")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Temperatura para las respuestas del agente durante el test")


class CalendarEventCreateRequest(BaseModel):
    """Modelo para crear un evento/reunión en Google Calendar."""
    summary: str = Field(..., description="Título del evento/reunión", example="Reunión de equipo")
    start_datetime: str = Field(..., description="Fecha y hora de inicio ISO 8601", example="2026-03-26T10:00:00")
    end_datetime: str = Field(..., description="Fecha y hora de fin ISO 8601", example="2026-03-26T11:00:00")
    description: str = Field(default="", description="Descripción del evento", example="Revisión semanal del sprint")
    location: str = Field(default="", description="Ubicación del evento", example="Sala de juntas")
    attendees: list[str] | None = Field(default=None, description="Emails de participantes", example=["usuario@gmail.com"])
    timezone: str = Field(default="America/Mexico_City", description="Zona horaria")
    add_meet: bool = Field(default=False, description="Agregar enlace de Google Meet")
    calendar_id: str = Field(default="primary", description="ID del calendario")
    agent_id: str | None = Field(default=None, description="ID del agente que crea el evento (para logging)")


class CalendarEventUpdateRequest(BaseModel):
    """Modelo para actualizar un evento existente en Google Calendar."""
    summary: str | None = Field(default=None, description="Nuevo título")
    start_datetime: str | None = Field(default=None, description="Nueva fecha/hora de inicio ISO 8601")
    end_datetime: str | None = Field(default=None, description="Nueva fecha/hora de fin ISO 8601")
    description: str | None = Field(default=None, description="Nueva descripción")
    location: str | None = Field(default=None, description="Nueva ubicación")
    attendees: list[str] | None = Field(default=None, description="Nueva lista de participantes")
    timezone: str = Field(default="America/Mexico_City", description="Zona horaria")
    calendar_id: str = Field(default="primary", description="ID del calendario")


class CalendarCheckAvailabilityRequest(BaseModel):
    """Modelo para verificar disponibilidad de participantes."""
    emails: list[str] = Field(..., description="Emails de participantes a verificar", example=["usuario@gmail.com"])
    time_min: str = Field(..., description="Inicio del rango ISO 8601", example="2026-03-26T09:00:00-06:00")
    time_max: str = Field(..., description="Fin del rango ISO 8601", example="2026-03-26T18:00:00-06:00")
    timezone: str = Field(default="America/Mexico_City", description="Zona horaria")


# ── WhatsApp ──────────────────────────────────────────────

class WhatsAppLinkRequest(BaseModel):
    """Vincular una sesión de WhatsApp a una organización.

    El wa_session_id es opcional. Si se omite, se genera automáticamente
    desde el nombre de la organización en formato alfanumérico + 'whts'.
    Ejemplo: 'Mi Empresa-1' → 'miempresa1whts'
    """
    organization: str = Field(..., description="Nombre de la organización", example="MiEmpresa")
    wa_session_id: str | None = Field(default=None, description="ID personalizado de la sesión WA (solo alfanumérico, se genera auto si se omite)", example="miempresawhts")
    default_agent_id: str = Field(default="default", description="Agente que atiende números no registrados", example="atencion-cliente")
    webhook_base_url: str | None = Field(default=None, description="URL base pública para registrar el webhook (ej: https://midominio.com). Si se omite, no se registra webhook automáticamente.", example="https://midominio.com")
    force: bool = Field(default=False, description="Si True, desvincula la sesión anterior automáticamente antes de re-vincular")


class WhatsAppNumberRegister(BaseModel):
    """Registrar un número telefónico con un agente específico."""
    phone_number: str = Field(..., description="Número de teléfono (formato internacional sin +)", example="5215512345678")
    agent_id: str = Field(..., description="ID del agente que atenderá este número", example="ventas-bot")


class WhatsAppNumberBulkRegister(BaseModel):
    """Registrar múltiples números telefónicos a la vez."""
    numbers: list[WhatsAppNumberRegister] = Field(..., description="Lista de números con sus agentes")


class WhatsAppUpdateDefaultAgent(BaseModel):
    """Actualizar el agente por defecto de una organización."""
    default_agent_id: str = Field(..., description="Nuevo agente por defecto para números no registrados", example="atencion-cliente")


class WhatsAppWebhookRegister(BaseModel):
    """Registrar webhook para recibir mensajes entrantes de WhatsApp."""
    webhook_base_url: str | None = Field(default=None, description="URL base pública (ej: https://midominio.com). Si se omite, usa PUBLIC_API_URL del .env", example="https://midominio.com")


class WhatsAppSendRequest(BaseModel):
    """Enviar un mensaje manualmente por WhatsApp."""
    organization: str = Field(..., description="Organización (para resolver la sesión WA)", example="MiEmpresa")
    to: str = Field(..., description="Número destino (formato internacional sin +)", example="5215512345678")
    text: str = Field(..., description="Texto del mensaje", example="Hola, ¿en qué puedo ayudarte?")


class SupervisorConfigUpdate(BaseModel):
    """Modelo para actualizar la configuración del supervisor.

    Todos los campos son opcionales. Solo se actualizan los que se envían.
    Los system prompts controlan cómo el supervisor evalúa, genera preguntas y mejora prompts.
    """
    model: str | None = Field(default=None, description="Modelo LLM para el supervisor (None=usa el modelo global)", example="llama3.1")
    prompt_evaluator: str | None = Field(default=None, description="System prompt para evaluar agentes (evaluación pasiva con historial)")
    prompt_test_generator: str | None = Field(default=None, description="System prompt para generar preguntas de prueba")
    prompt_turn_evaluator: str | None = Field(default=None, description="System prompt para evaluar cada turno individual")
    prompt_summary_evaluator: str | None = Field(default=None, description="System prompt para generar el reporte final de síntesis")
    prompt_engineer: str | None = Field(default=None, description="System prompt para generar mejoras de prompts de agentes")
