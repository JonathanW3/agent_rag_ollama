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


class AgentCreate(BaseModel):
    """Modelo para crear un nuevo agente."""
    name: str = Field(..., description="Nombre del agente", example="Experto en Python")
    prompt: str = Field(..., description="Prompt del sistema que define la personalidad y expertise del agente", example="Eres un experto en Python con 10 años de experiencia...")
    description: str = Field(default="", description="Descripción breve del agente", example="Especialista en desarrollo Python")
    agent_id: str | None = Field(default=None, description="ID personalizado (opcional, se genera automáticamente si se omite)", example="python-expert")
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
    top_k: int = Field(default=4, ge=1, le=100, description="Número de documentos RAG a recuperar por defecto")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Temperatura del modelo por defecto")


class AgentUpdate(BaseModel):
    """Modelo para actualizar un agente existente."""
    name: str | None = Field(default=None, description="Nuevo nombre del agente")
    prompt: str | None = Field(default=None, description="Nuevo prompt del sistema")
    description: str | None = Field(default=None, description="Nueva descripción")
    llm_model: str | None = Field(default=None, description="Nuevo modelo LLM (usa None para mantener el actual, '' para usar el global)")
    sqlite_db_path: str | None = Field(default=None, description="Ruta a base de datos SQLite personalizada (ej: 'Monitoring.db')")
    use_rag: bool | None = Field(default=None, description="Habilitar/deshabilitar RAG para este agente")
    smtp_config: dict | None = Field(default=None, description="Configuración SMTP para envío de emails")
    use_mysql: bool | None = Field(default=None, description="Habilitar/deshabilitar MySQL para este agente")
    use_email: bool | None = Field(default=None, description="Habilitar/deshabilitar email para este agente")
    use_charts: bool | None = Field(default=None, description="Habilitar/deshabilitar gráficos Plotly para este agente")
    top_k: int | None = Field(default=None, ge=1, le=100, description="Número de documentos RAG a recuperar por defecto")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0, description="Temperatura del modelo por defecto")


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


class OrchestratorConfigRequest(BaseModel):
    """Modelo para configurar el orquestador."""
    allowed_agent_ids: list[str] = Field(..., description="Lista de agent_ids que el orquestador puede consultar", example=["farmacia-bot", "python-expert"])
    fallback_agent_id: str = Field(default="default", description="Agente a usar si ninguno es adecuado", example="default")
    llm_model: str | None = Field(default=None, description="Modelo LLM para clasificación (None=usa el global)", example="llama3.1")


class OrchestratorAddAgentsRequest(BaseModel):
    """Modelo para agregar agentes al orquestador."""
    agent_ids: list[str] = Field(..., description="IDs de agentes a agregar", example=["nuevo-agente"])
