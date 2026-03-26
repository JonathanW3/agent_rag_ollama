import os
import re
import json
from fastapi import APIRouter, HTTPException
from ..config import settings
from ..schemas import ChatRequest
from ..agents import get_agent
from ..memory import save_message, get_history
from ..ollama_client import ollama_chat
from ..rag.retrieve import retrieve, build_context
from ..utils.email_helpers import parse_email_actions, execute_email_actions
from ..utils.chart_helpers import parse_chart_actions
from ..utils.calendar_helpers import parse_calendar_actions, execute_calendar_actions
from mcp_sqlite.client import get_mcp_client
from mcp_email.client import get_email_client
from mcp_mysql.client import get_mysql_client
from mcp_mysql_ibm.client import get_ibm_client
from mcp_mysql_autopart.client import get_autopart_client
from mcp_google_calendar.client import get_calendar_client

router = APIRouter(tags=["💬 Chat"])


@router.post("/chat", summary="Conversar con un agente")
async def chat(req: ChatRequest):
    """Envía un mensaje a un agente y obtiene una respuesta con contexto RAG opcional y/o SQL."""
    # Verificar que el agente existe
    agent = get_agent(req.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agente '{req.agent_id}' no encontrado")

    # Resolver configuración: request > agente > defaults globales
    eff_use_rag = req.use_rag if req.use_rag is not None else agent.get("use_rag", True)
    eff_use_mysql = req.use_mysql if req.use_mysql is not None else agent.get("use_mysql", False)
    # Email: si el agente tiene smtp_config, habilitar por defecto (True)
    # El frontend puede deshabilitarlo explícitamente enviando use_email=false
    agent_default_email = agent.get("use_email", bool(agent.get("smtp_config")))
    eff_use_email = req.use_email if req.use_email is not None else agent_default_email
    agent_default_charts = agent.get("use_charts", False)
    eff_use_charts = req.use_charts if req.use_charts is not None else agent_default_charts
    agent_default_calendar = agent.get("use_calendar", False)
    eff_use_calendar = req.use_calendar if req.use_calendar is not None else agent_default_calendar
    agent_default_ibm = agent.get("use_ibm", False)
    eff_use_ibm = req.use_ibm if req.use_ibm is not None else agent_default_ibm
    agent_default_autopart = agent.get("use_autopart", False)
    eff_use_autopart = req.use_autopart if req.use_autopart is not None else agent_default_autopart
    eff_top_k = req.top_k if req.top_k is not None else agent.get("top_k", settings.TOP_K)
    eff_temperature = req.temperature if req.temperature is not None else agent.get("temperature", 0.7)

    # Inicializar cliente MCP si se requiere SQL
    mcp_client = None
    sql_context_used = False
    sql_results = []

    if req.use_sql:
        mcp_client = get_mcp_client()
        # Solo inicializar BD automática si no tiene BD personalizada
        if not agent.get("sqlite_db_path"):
            await mcp_client.init_agent_db(req.agent_id)

    # Obtener historial de la sesión para este agente
    history = get_history(req.agent_id, req.session_id)

    # Preparar mensajes base con el prompt del agente
    sys_prompt = agent["prompt"]
    messages = [{"role": "system", "content": sys_prompt}]

    # Inyectar capacidad de email si está habilitado y el agente tiene SMTP
    email_enabled = eff_use_email and bool(agent.get("smtp_config"))
    if email_enabled:
        email_instructions = (
            "\n\n--- CAPACIDAD DE EMAIL ---\n"
            "Tienes la capacidad de enviar emails. Cuando el usuario te pida enviar un correo, "
            "o cuando determines que es apropiado (alertas críticas, reportes solicitados), "
            "incluye un bloque de acción al final de tu respuesta con este formato EXACTO:\n\n"
            "[EMAIL_ACTION]\n"
            '{"to": "destinatario@example.com", "subject": "Asunto", "body": "Contenido completo del correo aquí", "html": false}\n'
            "[/EMAIL_ACTION]\n\n"
            "IMPORTANTE: El contenido entre [EMAIL_ACTION] y [/EMAIL_ACTION] DEBE ser JSON válido puro, "
            "sin texto adicional, sin bloques markdown, sin explicaciones. Solo el objeto JSON.\n"
            "Campos obligatorios: to, subject, body\n"
            "Campos opcionales: html (bool), cc (lista), bcc (lista)\n"
            "Si html es true, el body debe ser HTML válido.\n\n"
            "REGLA CRÍTICA SOBRE EL BODY DEL EMAIL:\n"
            "El campo 'body' DEBE contener TODO el contenido informativo que mostraste en el chat. "
            "NUNCA pongas mensajes genéricos como 'Adjunto el reporte' o 'Revisa los detalles'. "
            "El destinatario SOLO verá lo que esté en el body del email, NO ve el chat.\n"
            "- Si generaste un reporte con tablas, datos y análisis → el body debe incluir TODOS esos datos\n"
            "- Si el body contiene tablas, usa formato Markdown (el sistema lo convertirá a HTML automáticamente)\n"
            "- Incluye encabezados, tablas, listas y conclusiones completas en el body\n"
            "- El body debe ser autocontenido: el destinatario debe entender todo sin contexto adicional\n\n"
            "Ejemplo CORRECTO de body para un reporte:\n"
            '  "body": "## Reporte de Ventas Febrero 2025\\n\\n| Categoría | Ventas |\\n|---|---|\\n| Anti-infecciosos | $12,450,000 |\\n\\n### Análisis\\n- La categoría X creció 10%..."\n\n'
            "Ejemplo INCORRECTO de body (NUNCA hagas esto):\n"
            '  "body": "Te envío el reporte solicitado. Revisa los detalles."\n\n'
            "Reglas generales:\n"
            "- Escribe tu respuesta normal al usuario PRIMERO y luego el bloque [EMAIL_ACTION] al final\n"
            "- NO inventes direcciones de email; usa solo las que el usuario proporcione o estén en los datos\n"
            "- Confirma con el usuario antes de enviar información sensible\n"
            "- Puedes incluir múltiples bloques [EMAIL_ACTION] para enviar varios emails\n"
            "- NUNCA generes un bloque [EMAIL_ACTION] vacío (sin JSON dentro)\n"
            "- Para que un email se envíe SIEMPRE debes incluir el bloque [EMAIL_ACTION] con el JSON. "
            "Sin ese bloque, el email NO se enviará aunque digas que lo hiciste\n"
            "- PROHIBIDO generar bloques [RESULTADO DE EMAILS]. Esos bloques los genera el SISTEMA automáticamente "
            "después de enviar. Tú NUNCA debes escribirlos. Si los escribes, estarás mintiendo al usuario\n"
            "- NO digas 'El reporte ha sido enviado' ni 'Confirmación: enviado'. En su lugar di algo como "
            "'Procesando el envío del correo...' ya que el resultado real lo añade el sistema\n\n"
            "HISTORIAL DE EMAILS:\n"
            "En el historial de conversación puedes encontrar bloques [RESULTADO DE EMAILS]...[/RESULTADO DE EMAILS] "
            "generados por el SISTEMA (no por ti). Cada línea muestra:\n"
            "  - ENVIADO a <destinatario> | Asunto: \"<asunto>\" → el email se envió correctamente\n"
            "  - FALLÓ envío a <destinatario> | Error: <motivo> → el email no se pudo enviar\n"
            "Usa esta información para:\n"
            "  1. Informar al usuario si pregunta si ya se envió un correo o qué se envió\n"
            "  2. No reenviar emails que ya fueron enviados exitosamente, a menos que el usuario lo pida explícitamente\n"
            "  3. Reintentar envíos fallidos si el usuario lo solicita\n"
            "  4. Dar un resumen de los correos enviados en la sesión cuando sea relevante\n"
            "--- FIN CAPACIDAD DE EMAIL ---"
        )
        messages[0]["content"] += email_instructions

    # Inyectar capacidad de gráficos si está habilitado
    if eff_use_charts:
        chart_instructions = (
            "\n\n--- CAPACIDAD DE GRAFICOS (OBLIGATORIO) ---\n"
            "TIENES UN SISTEMA DE GRÁFICOS INTEGRADO. Cuando tu respuesta incluya datos numéricos, "
            "comparaciones, rankings, distribuciones o tendencias, SIEMPRE DEBES incluir un bloque "
            "[CHART_ACTION] al final de tu respuesta. El sistema renderiza automáticamente el gráfico "
            "como una visualización interactiva profesional para el usuario. NO es opcional.\n\n"

            "CUÁNDO GENERAR GRÁFICOS (SIEMPRE en estos casos):\n"
            "- Cualquier respuesta que contenga datos numéricos en tablas\n"
            "- Comparaciones entre sucursales, productos, periodos, etc.\n"
            "- Rankings o tops (productos más vendidos, sucursales con más ventas, etc.)\n"
            "- Distribuciones (por categoría, método de pago, tipo de cliente, etc.)\n"
            "- Tendencias temporales (ventas mensuales, evolución de stock, etc.)\n"
            "- Alertas de stock con cantidades por sucursal\n"
            "- EN RESUMEN: si hay números, hay gráfico\n\n"

            "CÓMO FUNCIONA:\n"
            "1. Tú escribes tu análisis con datos reales + tabla markdown detallada\n"
            "2. Al final incluyes el bloque [CHART_ACTION] con los MISMOS datos\n"
            "3. El SISTEMA renderiza el gráfico interactivo automáticamente\n"
            "4. El usuario VE tabla de datos + gráfico profesional juntos\n\n"

            "FORMATO del bloque (JSON puro, sin markdown, sin texto extra):\n\n"
            "[CHART_ACTION]\n"
            '{"data": [...], "layout": {...}}\n'
            "[/CHART_ACTION]\n\n"

            "TIPOS DE GRÁFICO según el caso:\n"
            '- Rankings/comparaciones → "type": "bar"\n'
            '- Tendencias en el tiempo → "type": "line" (con markers)\n'
            '- Distribuciones/proporciones → "type": "pie" (usar "labels" y "values")\n'
            '- Barras agrupadas → múltiples trazas con "barmode": "group"\n'
            '- Barras apiladas → múltiples trazas con "barmode": "stack"\n\n'

            "ESTILO PROFESIONAL OBLIGATORIO:\n"
            "Todos los gráficos DEBEN incluir estas propiedades de layout para verse profesionales:\n"
            '{\n'
            '  "layout": {\n'
            '    "title": {"text": "Título Descriptivo", "font": {"size": 18, "color": "#1e293b", "family": "Arial Black"}},\n'
            '    "paper_bgcolor": "#ffffff",\n'
            '    "plot_bgcolor": "#f8fafc",\n'
            '    "font": {"family": "Arial, sans-serif", "size": 12, "color": "#334155"},\n'
            '    "xaxis": {"title": {"text": "Etiqueta X", "font": {"size": 13, "color": "#475569"}}, '
            '"gridcolor": "#e2e8f0", "linecolor": "#cbd5e1", "tickfont": {"size": 11}},\n'
            '    "yaxis": {"title": {"text": "Etiqueta Y", "font": {"size": 13, "color": "#475569"}}, '
            '"gridcolor": "#e2e8f0", "linecolor": "#cbd5e1", "tickfont": {"size": 11}, "tickformat": ",.0f"},\n'
            '    "legend": {"bgcolor": "rgba(255,255,255,0.8)", "bordercolor": "#e2e8f0", "borderwidth": 1, '
            '"font": {"size": 11}},\n'
            '    "margin": {"l": 80, "r": 40, "t": 60, "b": 80},\n'
            '    "hoverlabel": {"bgcolor": "#1e293b", "font": {"color": "#ffffff", "size": 12}}\n'
            '  }\n'
            '}\n\n'

            "PALETA DE COLORES CORPORATIVA (usar siempre):\n"
            "- Colores principales: #2563eb (azul), #16a34a (verde), #dc2626 (rojo), #f59e0b (amarillo), "
            "#7c3aed (violeta), #06b6d4 (cyan), #ea580c (naranja), #ec4899 (rosa)\n"
            "- Para barras: usa 'marker': {'color': '#2563eb'} o array de colores para cada barra\n"
            "- Para líneas: usa 'line': {'color': '#2563eb', 'width': 3} y 'marker': {'size': 8, 'color': '#2563eb'}\n"
            "- Para pie: usa 'marker': {'colors': ['#2563eb', '#16a34a', '#dc2626', ...], "
            "'line': {'color': '#ffffff', 'width': 2}}\n"
            "- Para alertas: rojo (#dc2626) = SIN STOCK/crítico, amarillo (#f59e0b) = STOCK BAJO/advertencia, "
            "verde (#16a34a) = OK/positivo\n\n"

            "ENRIQUECIMIENTO DE DATOS:\n"
            "- Incluye SIEMPRE la mayor cantidad de datos disponibles (mínimo 5-10 items si existen)\n"
            "- Agrega 'text' en las trazas para mostrar valores sobre las barras/puntos: "
            "'text': ['$4.2M', '$3.1M'], 'textposition': 'outside', 'textfont': {'size': 11, 'color': '#1e293b'}\n"
            "- Para pie: usa 'textinfo': 'label+percent', 'hoverinfo': 'label+value+percent', 'hole': 0.4 (donut)\n"
            "- Para líneas: usa 'mode': 'lines+markers+text' para mostrar puntos y valores\n"
            "- Agrega 'hovertemplate' para tooltips informativos: "
            "'hovertemplate': '<b>%{x}</b><br>Ventas: $%{y:,.0f}<extra></extra>'\n\n"

            "ESTRUCTURA DE RESPUESTA OBLIGATORIA:\n"
            "Tu respuesta SIEMPRE debe tener estas 3 partes en este orden:\n"
            "1. ANÁLISIS EJECUTIVO: interpretación de los datos, hallazgos clave, recomendaciones\n"
            "2. TABLA DE DATOS: tabla markdown completa y detallada con todos los datos relevantes "
            "(posición, nombre, valor, %, variación, etc.)\n"
            "3. GRÁFICO: bloque [CHART_ACTION] con los mismos datos de la tabla, estilo profesional\n\n"

            "EJEMPLO COMPLETO:\n"
            "---INICIO EJEMPLO---\n"
            "## Análisis de Productos Más Vendidos\n\n"
            "El Paracetamol lidera las ventas con $4.25M representando el 28.5% del total. "
            "Los 5 productos principales concentran el 72% de las ventas.\n\n"
            "| # | Producto | Laboratorio | Ventas | % Part. | Unidades |\n"
            "|---|---------|------------|-------:|--------:|---------:|\n"
            "| 1 | Paracetamol 500mg | Chile Lab | $4,250,000 | 28.5% | 8,500 |\n"
            "| 2 | Ibuprofeno 400mg | Saval | $3,180,000 | 21.3% | 5,300 |\n"
            "| 3 | Amoxicilina 500mg | Bagó | $2,890,000 | 19.4% | 2,890 |\n"
            "| 4 | Omeprazol 20mg | Andrómaco | $2,450,000 | 16.4% | 4,900 |\n"
            "| 5 | Losartán 50mg | Recalcine | $2,150,000 | 14.4% | 4,300 |\n\n"
            "A continuación la gráfica:\n\n"
            "[CHART_ACTION]\n"
            '{"data": [{"type": "bar", "x": ["Paracetamol 500mg", "Ibuprofeno 400mg", "Amoxicilina 500mg", '
            '"Omeprazol 20mg", "Losartán 50mg"], "y": [4250000, 3180000, 2890000, 2450000, 2150000], '
            '"name": "Ventas ($)", "marker": {"color": ["#2563eb", "#16a34a", "#7c3aed", "#f59e0b", "#06b6d4"], '
            '"line": {"color": "#ffffff", "width": 1}}, '
            '"text": ["$4.25M", "$3.18M", "$2.89M", "$2.45M", "$2.15M"], '
            '"textposition": "outside", "textfont": {"size": 11, "color": "#1e293b"}, '
            '"hovertemplate": "<b>%{x}</b><br>Ventas: $%{y:,.0f}<extra></extra>"}], '
            '"layout": {"title": {"text": "Top 5 Productos Más Vendidos", '
            '"font": {"size": 18, "color": "#1e293b", "family": "Arial Black"}}, '
            '"paper_bgcolor": "#ffffff", "plot_bgcolor": "#f8fafc", '
            '"font": {"family": "Arial, sans-serif", "size": 12, "color": "#334155"}, '
            '"xaxis": {"title": {"text": "Producto", "font": {"size": 13, "color": "#475569"}}, '
            '"gridcolor": "#e2e8f0", "tickfont": {"size": 10}, "tickangle": -25}, '
            '"yaxis": {"title": {"text": "Ventas ($)", "font": {"size": 13, "color": "#475569"}}, '
            '"gridcolor": "#e2e8f0", "tickfont": {"size": 11}, "tickformat": "$,.0f"}, '
            '"margin": {"l": 80, "r": 40, "t": 60, "b": 120}, '
            '"hoverlabel": {"bgcolor": "#1e293b", "font": {"color": "#ffffff", "size": 12}}}}\n'
            "[/CHART_ACTION]\n"
            "---FIN EJEMPLO---\n\n"

            "PROHIBICIONES ABSOLUTAS:\n"
            "- NUNCA respondas con datos numéricos SIN incluir un [CHART_ACTION]. Si hay números, hay gráfico.\n"
            "- NUNCA hagas gráficos sin estilo profesional. SIEMPRE incluye la paleta de colores, fuentes y formato.\n"
            "- NUNCA menciones 'CHART_ACTION', 'Plotly', 'JSON', 'bloque' al usuario.\n"
            "- NUNCA digas 'copia y pega', 'usa esta herramienta'. El gráfico aparece solo.\n"
            "- NUNCA inventes datos. Usa SOLO datos reales de la base de datos.\n"
            "- NUNCA generes un [CHART_ACTION] vacío o sin el campo 'data'.\n"
            "- NUNCA hagas gráficos con menos de 5 datos si hay más disponibles. Muestra la mayor cantidad posible.\n"
            "- PROHIBIDO generar bloques [RESULTADO DE GRAFICOS]. Esos los genera el SISTEMA.\n"
            "--- FIN CAPACIDAD DE GRAFICOS ---"
        )
        messages[0]["content"] += chart_instructions

    # Inyectar capacidad de Google Calendar si está habilitado
    if eff_use_calendar:
        calendar_instructions = (
            "\n\n--- CAPACIDAD DE GOOGLE CALENDAR ---\n"
            "Tienes la capacidad de gestionar eventos y reuniones en Google Calendar. "
            "Puedes crear reuniones, listar eventos, verificar disponibilidad, actualizar y eliminar eventos.\n\n"

            "CUÁNDO USAR ESTA CAPACIDAD:\n"
            "- El usuario pide agendar/programar/crear una reunión o evento\n"
            "- El usuario pregunta qué reuniones tiene hoy, mañana o en una fecha específica\n"
            "- El usuario pide verificar si alguien está disponible en un horario\n"
            "- El usuario pide cancelar, mover o modificar una reunión existente\n"
            "- El usuario pide ver su agenda o calendario\n\n"

            "CÓMO FUNCIONA:\n"
            "Incluye un bloque [CALENDAR_ACTION] al final de tu respuesta con JSON válido puro.\n"
            "El SISTEMA ejecuta la acción automáticamente y muestra el resultado al usuario.\n\n"

            "FORMATO (JSON puro, sin markdown, sin texto extra):\n\n"
            "[CALENDAR_ACTION]\n"
            '{"action_type": "...", ...campos...}\n'
            "[/CALENDAR_ACTION]\n\n"

            "ACCIONES DISPONIBLES:\n\n"

            "1. CREAR EVENTO/REUNIÓN:\n"
            "[CALENDAR_ACTION]\n"
            "{\n"
            '  "action_type": "create_event",\n'
            '  "summary": "Reunión de equipo",\n'
            '  "start_datetime": "2026-03-26T10:00:00",\n'
            '  "end_datetime": "2026-03-26T11:00:00",\n'
            '  "description": "Revisión semanal del sprint",\n'
            '  "location": "Sala de juntas",\n'
            '  "attendees": ["juan@gmail.com", "maria@gmail.com"],\n'
            '  "timezone": "America/Mexico_City",\n'
            '  "add_meet": true,\n'
            '  "calendar_id": "primary"\n'
            "}\n"
            "[/CALENDAR_ACTION]\n"
            "Campos obligatorios: action_type, summary, start_datetime, end_datetime\n"
            "Campos opcionales: description, location, attendees, timezone, add_meet, calendar_id\n\n"

            "2. LISTAR EVENTOS (consultar agenda):\n"
            "[CALENDAR_ACTION]\n"
            "{\n"
            '  "action_type": "list_events",\n'
            '  "max_results": 10,\n'
            '  "time_min": "2026-03-26T00:00:00-06:00",\n'
            '  "time_max": "2026-03-26T23:59:59-06:00",\n'
            '  "calendar_id": "primary"\n'
            "}\n"
            "[/CALENDAR_ACTION]\n"
            "Campos obligatorios: action_type\n"
            "Campos opcionales: max_results (default 10), time_min (default ahora), time_max, calendar_id\n"
            "IMPORTANTE: Para consultar un día específico, usa time_min con las 00:00:00 y time_max con las 23:59:59 de ese día.\n\n"

            "3. VERIFICAR DISPONIBILIDAD:\n"
            "[CALENDAR_ACTION]\n"
            "{\n"
            '  "action_type": "check_availability",\n'
            '  "emails": ["juan@gmail.com", "maria@gmail.com"],\n'
            '  "time_min": "2026-03-26T09:00:00-06:00",\n'
            '  "time_max": "2026-03-26T18:00:00-06:00",\n'
            '  "timezone": "America/Mexico_City"\n'
            "}\n"
            "[/CALENDAR_ACTION]\n"
            "Campos obligatorios: action_type, emails, time_min, time_max\n\n"

            "4. ACTUALIZAR EVENTO:\n"
            "[CALENDAR_ACTION]\n"
            "{\n"
            '  "action_type": "update_event",\n'
            '  "event_id": "abc123",\n'
            '  "summary": "Nuevo título",\n'
            '  "start_datetime": "2026-03-26T14:00:00",\n'
            '  "end_datetime": "2026-03-26T15:00:00"\n'
            "}\n"
            "[/CALENDAR_ACTION]\n"
            "Campos obligatorios: action_type, event_id\n"
            "Campos opcionales: summary, start_datetime, end_datetime, description, location, attendees\n\n"

            "5. ELIMINAR EVENTO:\n"
            "[CALENDAR_ACTION]\n"
            "{\n"
            '  "action_type": "delete_event",\n'
            '  "event_id": "abc123"\n'
            "}\n"
            "[/CALENDAR_ACTION]\n"
            "Campos obligatorios: action_type, event_id\n\n"

            "REGLAS IMPORTANTES:\n"
            "- SIEMPRE escribe tu respuesta al usuario PRIMERO, luego el bloque [CALENDAR_ACTION] al final\n"
            "- Las fechas DEBEN estar en formato ISO 8601 (YYYY-MM-DDTHH:MM:SS)\n"
            "- Si el usuario dice 'mañana a las 10', calcula la fecha correcta basándote en la fecha actual\n"
            "- Si el usuario no especifica hora de fin, asume 1 hora de duración\n"
            "- Si el usuario no especifica zona horaria, usa America/Mexico_City\n"
            "- Para 'hoy' o 'mañana', genera time_min y time_max cubriendo el día completo (00:00 a 23:59)\n"
            "- Puedes incluir múltiples bloques [CALENDAR_ACTION] para ejecutar varias acciones\n"
            "- NO inventes event_ids; solo úsalos cuando el usuario te los proporcione o los hayas listado antes\n"
            "- PROHIBIDO generar bloques [RESULTADO DE CALENDARIO]. Esos los genera el SISTEMA automáticamente\n"
            "- NO digas 'La reunión ha sido creada'. Di 'Procesando la creación de la reunión...'\n"
            "- Si necesitas listar eventos para responder una pregunta, usa list_events y el sistema mostrará los resultados\n\n"

            "HISTORIAL DE CALENDARIO:\n"
            "En el historial puedes encontrar bloques [RESULTADO DE CALENDARIO]...[/RESULTADO DE CALENDARIO] "
            "generados por el SISTEMA. Usa esta información para:\n"
            "  1. Informar al usuario sobre eventos creados, modificados o eliminados\n"
            "  2. Referenciar event_ids de eventos previamente listados\n"
            "  3. No duplicar eventos que ya fueron creados exitosamente\n"
            "--- FIN CAPACIDAD DE GOOGLE CALENDAR ---"
        )
        messages[0]["content"] += calendar_instructions

    # Agregar contexto SQL si está habilitado y es relevante
    if req.use_sql and mcp_client:
        # Detectar si la pregunta requiere datos estructurados
        sql_keywords = ["estadísticas", "métricas", "logs", "historial", "cuántos", "cuántas",
                        "total", "promedio", "suma", "documentos procesados", "conversaciones",
                        "datos", "registros", "tabla", "consulta"]

        message_lower = req.message.lower()
        needs_sql = any(keyword in message_lower for keyword in sql_keywords)

        if needs_sql:
            try:
                # Verificar si el agente tiene BD personalizada
                custom_db_path = agent.get("sqlite_db_path")

                if custom_db_path:
                    # Usar BD personalizada (ej: Monitoring.db)
                    # Obtener esquema primero
                    db_name_only = os.path.splitext(os.path.basename(custom_db_path))[0]

                    # Intentar obtener esquema
                    schema_result = await mcp_client.get_schema(f"custom/{db_name_only}")

                    if schema_result.get("success"):
                        tables = schema_result.get("tables", {})
                        schema_info = f"Base de datos: {custom_db_path}\nTablas disponibles: {list(tables.keys())}"

                        # Ejecutar una consulta genérica a la primera tabla encontrada
                        if tables:
                            first_table = list(tables.keys())[0]
                            # Sanitizar nombre de tabla: solo permitir alfanuméricos y _
                            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', first_table):
                                first_table = None
                            if first_table:
                                data_result = await mcp_client.query_custom_db(
                                    db_path=custom_db_path,
                                    query=f'SELECT * FROM "{first_table}" LIMIT 10'
                                )

                                if data_result.get("success"):
                                    sql_context_parts = [
                                        schema_info,
                                        f"\nDatos de ejemplo de {first_table}:",
                                        json.dumps(data_result.get("rows", []), indent=2)
                                    ]
                                    sql_context = "\n".join(sql_context_parts)
                                    messages.append({"role": "system", "content": f"Datos estructurados disponibles:\n{sql_context}"})
                                    sql_context_used = True
                                    sql_results.append({"type": "custom_db", "table": first_table, "data": data_result.get("rows", [])})
                    else:
                        # Si no se puede obtener esquema, informar al usuario
                        messages.append({"role": "system", "content": f"Base de datos personalizada configurada: {custom_db_path}\nNota: No se pudo acceder al esquema. Verifica que la ruta sea correcta."})
                else:
                    # Usar BD automática del agente
                    # Consultar métricas recientes del agente
                    metrics_result = await mcp_client.query_for_agent(
                        agent_id=req.agent_id,
                        query="SELECT metric_name, metric_value, timestamp FROM agent_metrics ORDER BY timestamp DESC LIMIT 10"
                    )

                    # Consultar logs recientes
                    logs_result = await mcp_client.query_for_agent(
                        agent_id=req.agent_id,
                        query="SELECT action, success, timestamp FROM agent_logs ORDER BY timestamp DESC LIMIT 10"
                    )

                    # Consultar documentos procesados
                    docs_result = await mcp_client.query_for_agent(
                        agent_id=req.agent_id,
                        query="SELECT filename, chunks_count, processed_at FROM processed_documents ORDER BY processed_at DESC LIMIT 10"
                    )

                    # Construir contexto SQL si hay resultados
                    sql_context_parts = []

                    if metrics_result.get("success") and metrics_result.get("count", 0) > 0:
                        sql_context_parts.append(f"Métricas recientes:\n{json.dumps(metrics_result['rows'], indent=2)}")
                        sql_results.append({"type": "metrics", "data": metrics_result["rows"]})

                    if logs_result.get("success") and logs_result.get("count", 0) > 0:
                        sql_context_parts.append(f"Logs recientes:\n{json.dumps(logs_result['rows'], indent=2)}")
                        sql_results.append({"type": "logs", "data": logs_result["rows"]})

                    if docs_result.get("success") and docs_result.get("count", 0) > 0:
                        sql_context_parts.append(f"Documentos procesados:\n{json.dumps(docs_result['rows'], indent=2)}")
                        sql_results.append({"type": "documents", "data": docs_result["rows"]})

                    if sql_context_parts:
                        sql_context = "\n\n".join(sql_context_parts)
                        messages.append({"role": "system", "content": f"Datos estructurados disponibles:\n{sql_context}"})
                        sql_context_used = True

            except Exception as e:
                print(f"Error consultando SQL: {e}")
                # No fallar el chat, simplemente continuar sin contexto SQL

    # Agregar contexto MySQL (farmacia_db) si está habilitado
    if eff_use_mysql:
        mysql_keywords = [
            "medicamento", "farmacia", "stock", "precio", "laboratorio",
            "compra", "venta", "historial", "usuario", "cliente",
            "disponible", "agotado", "alerta", "receta", "clase terapéutica",
            "cuánto", "cuántos", "cuántas", "total", "top", "más vendido",
            "sin stock", "stock bajo", "local", "comuna"
        ]
        message_lower = req.message.lower()
        needs_mysql = any(kw in message_lower for kw in mysql_keywords)

        if needs_mysql:
            try:
                mysql_client = get_mysql_client()
                mysql_parts = []

                # Alertas de stock activas
                alertas = await mysql_client.alertas_stock(limit=20)
                if alertas.get("success") and alertas.get("count", 0) > 0:
                    mysql_parts.append(
                        f"Alertas de stock (STOCK BAJO / SIN STOCK):\n"
                        f"{json.dumps(alertas['rows'], indent=2, ensure_ascii=False)}"
                    )

                # Top 5 medicamentos más vendidos
                top = await mysql_client.top_medicamentos(limit=5)
                if top.get("success") and top.get("count", 0) > 0:
                    mysql_parts.append(
                        f"Top 5 medicamentos más vendidos:\n"
                        f"{json.dumps(top['rows'], indent=2, ensure_ascii=False)}"
                    )

                if mysql_parts:
                    mysql_context = "\n\n".join(mysql_parts)
                    messages.append({
                        "role": "system",
                        "content": (
                            "Datos de farmacia_db (MySQL) disponibles para responder:\n"
                            + mysql_context
                        )
                    })
            except Exception as e:
                print(f"Error consultando MySQL MCP: {e}")

    # Agregar contexto IBM (ibm DB) si está habilitado
    if eff_use_ibm:
        ibm_keywords = [
            "tarjeta", "crédito", "credit", "card", "banco", "emisor", "visa", "amex",
            "mastercard", "límite", "titular", "transacción", "depósito", "retiro",
            "balance", "bank", "empleado", "employee", "salario", "salary", "hire",
            "attrition", "rotación", "deserción", "departamento", "overtime",
            "satisfacción", "venta", "sales", "order", "revenue", "profit",
            "región", "country", "producto", "channel", "ibm"
        ]
        message_lower = req.message.lower()
        needs_ibm = any(kw in message_lower for kw in ibm_keywords)

        if needs_ibm:
            try:
                ibm_client = get_ibm_client()
                ibm_parts = []

                # Resumen de tablas disponibles
                tables = await ibm_client.list_tables()
                if tables.get("success"):
                    ibm_parts.append(
                        f"Tablas disponibles en IBM:\n"
                        f"{json.dumps(tables['tables'], indent=2, ensure_ascii=False)}"
                    )

                # Factores de attrition (resumen compacto y útil)
                factores = await ibm_client.factores_attrition()
                if factores.get("success") and factores.get("count", 0) > 0:
                    ibm_parts.append(
                        f"Factores de attrition (Yes vs No):\n"
                        f"{json.dumps(factores['rows'], indent=2, ensure_ascii=False)}"
                    )

                # Resumen general de ventas
                ventas = await ibm_client.resumen_ventas()
                if ventas.get("success") and ventas.get("count", 0) > 0:
                    ibm_parts.append(
                        f"KPIs generales de ventas:\n"
                        f"{json.dumps(ventas['rows'], indent=2, ensure_ascii=False)}"
                    )

                if ibm_parts:
                    ibm_context = "\n\n".join(ibm_parts)
                    messages.append({
                        "role": "system",
                        "content": (
                            "Datos de la base de datos IBM (MySQL) disponibles para responder:\n"
                            + ibm_context
                        )
                    })
            except Exception as e:
                print(f"Error consultando IBM MCP: {e}")

    # Agregar contexto Autopart (autopart DB) si está habilitado
    if eff_use_autopart:
        autopart_keywords = [
            "vehículo", "vehiculo", "vehicle", "auto", "carro", "coche", "modelo",
            "fabricante", "manufacturer", "toyota", "honda", "bmw", "mercedes",
            "ford", "chevrolet", "nissan", "hyundai", "kia", "volkswagen",
            "categoría", "categoria", "category", "repuesto", "pieza", "parte",
            "autoparte", "autopart", "vendedor", "seller", "precio", "price",
            "publicación", "publicacion", "application", "compatibilidad",
            "compatibility", "año", "anio", "year", "condición", "condicion",
            "nuevo", "usado", "new", "used", "gel", "usd", "autopart"
        ]
        message_lower = req.message.lower()
        needs_autopart = any(kw in message_lower for kw in autopart_keywords)

        if needs_autopart:
            try:
                autopart_client = get_autopart_client()
                autopart_parts = []

                # Resumen de tablas disponibles
                tables = await autopart_client.list_tables()
                if tables.get("success"):
                    autopart_parts.append(
                        f"Tablas disponibles en Autopart:\n"
                        f"{json.dumps(tables['tables'], indent=2, ensure_ascii=False)}"
                    )

                # Resumen de vehículos por fabricante
                vehiculos = await autopart_client.resumen_vehiculos("fabricante", 10)
                if vehiculos.get("success") and vehiculos.get("count", 0) > 0:
                    autopart_parts.append(
                        f"Vehículos por fabricante (top 10):\n"
                        f"{json.dumps(vehiculos['rows'], indent=2, ensure_ascii=False)}"
                    )

                # Resumen de aplicaciones por estado
                aplicaciones = await autopart_client.resumen_aplicaciones("estado", 10)
                if aplicaciones.get("success") and aplicaciones.get("count", 0) > 0:
                    autopart_parts.append(
                        f"Publicaciones por estado:\n"
                        f"{json.dumps(aplicaciones['rows'], indent=2, ensure_ascii=False)}"
                    )

                if autopart_parts:
                    autopart_context = "\n\n".join(autopart_parts)
                    messages.append({
                        "role": "system",
                        "content": (
                            "Datos de la base de datos Autopart (MySQL) disponibles para responder:\n"
                            + autopart_context
                        )
                    })
            except Exception as e:
                print(f"Error consultando Autopart MCP: {e}")

    # Agregar contexto RAG si está habilitado (verificar config del agente Y el parámetro de la request)
    agent_uses_rag = agent.get("use_rag", True)  # Por defecto True para retrocompatibilidad
    if eff_use_rag and agent_uses_rag:
        try:
            snippets = retrieve(req.message, agent_id=req.agent_id, top_k=eff_top_k)
            if snippets:
                context = build_context(snippets)
                messages.append({"role": "system", "content": f"Contexto relevante:\n{context}"})
        except Exception as e:
            print(f"Error en RAG (ChromaDB no disponible): {e}")
            snippets = []
    else:
        snippets = []

    # Agregar historial de conversación
    messages.extend(history)

    # Agregar mensaje actual del usuario
    messages.append({"role": "user", "content": req.message})

    # Determinar qué modelo LLM usar
    agent_model = agent.get("llm_model") or settings.CHAT_MODEL

    # Obtener respuesta del modelo
    try:
        answer = ollama_chat(messages, temperature=eff_temperature, model=agent_model)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al comunicarse con Ollama: {str(e)}"
        )

    # ── EMAIL POST-PROCESSING ──────────────────────────────────────────────
    email_sent = False
    email_results = []

    # Limpiar bloques [RESULTADO DE EMAILS] falsos generados por el LLM
    fake_result_pattern = r'\[RESULTADO DE EMAILS\].*?\[/RESULTADO DE EMAILS\]'
    answer = re.sub(fake_result_pattern, '', answer, flags=re.DOTALL).strip()

    # DEBUG: Log para diagnóstico de email
    print(f"[EMAIL DEBUG] email_enabled={email_enabled}")
    if email_enabled:
        has_action_tag = "[EMAIL_ACTION]" in answer
        print(f"[EMAIL DEBUG] ¿Contiene [EMAIL_ACTION]? {has_action_tag}")
        if not has_action_tag:
            # Mostrar los últimos 500 chars de la respuesta para ver qué generó el LLM
            print(f"[EMAIL DEBUG] Final de respuesta LLM (últimos 500 chars): ...{answer[-500:]}")

    if email_enabled:
        email_actions, cleaned_answer = parse_email_actions(answer)
        print(f"[EMAIL DEBUG] Acciones parseadas: {len(email_actions)}")

        if email_actions:
            email_client = get_email_client()
            email_results = await execute_email_actions(
                actions=email_actions,
                smtp_config=agent["smtp_config"],
                email_client=email_client,
                agent_name=agent.get("name", "Asistente IA"),
            )
            email_sent = any(r.get("success") for r in email_results)
            answer = cleaned_answer
    # ── END EMAIL POST-PROCESSING ──────────────────────────────────────────

    # ── CHART POST-PROCESSING ─────────────────────────────────────────────
    charts = []
    if eff_use_charts:
        # Limpiar bloques falsos de resultado generados por el LLM
        fake_chart_pattern = r'\[RESULTADO DE GRAFICOS\].*?\[/RESULTADO DE GRAFICOS\]'
        answer = re.sub(fake_chart_pattern, '', answer, flags=re.DOTALL).strip()

        chart_actions, answer = parse_chart_actions(answer)
        charts = [c for c in chart_actions if "_parse_error" not in c]
        chart_errors = [c for c in chart_actions if "_parse_error" in c]
        if chart_errors:
            print(f"[CHART DEBUG] Errores de parsing: {chart_errors}")
    # ── END CHART POST-PROCESSING ─────────────────────────────────────────

    # ── CALENDAR POST-PROCESSING ────────────────────────────────────────
    calendar_results = []
    calendar_executed = False

    if eff_use_calendar:
        # Limpiar bloques falsos de resultado generados por el LLM
        fake_calendar_pattern = r'\[RESULTADO DE CALENDARIO\].*?\[/RESULTADO DE CALENDARIO\]'
        answer = re.sub(fake_calendar_pattern, '', answer, flags=re.DOTALL).strip()

        calendar_actions, cleaned_answer = parse_calendar_actions(answer)
        print(f"[CALENDAR DEBUG] Acciones parseadas: {len(calendar_actions)}")

        if calendar_actions:
            cal_client = get_calendar_client()
            calendar_results = await execute_calendar_actions(
                actions=calendar_actions,
                calendar_client=cal_client,
            )
            calendar_executed = any(r.get("success") for r in calendar_results)
            answer = cleaned_answer
    # ── END CALENDAR POST-PROCESSING ────────────────────────────────────

    # Construir resumen de emails para inyectar en el historial
    email_summary = ""
    if email_results:
        lines = []
        for r in email_results:
            if r.get("success"):
                lines.append(f"  - ENVIADO a {r.get('to')} | Asunto: \"{r.get('subject')}\"")
            else:
                lines.append(f"  - FALLÓ envío a {r.get('to', 'desconocido')} | Error: {r.get('error', 'desconocido')}")
        email_summary = "[RESULTADO DE EMAILS]\n" + "\n".join(lines) + "\n[/RESULTADO DE EMAILS]"

    # Construir resumen de calendario para inyectar en el historial
    calendar_summary = ""
    if calendar_results:
        lines = []
        for r in calendar_results:
            action_type = r.get("action_type", "unknown")
            if r.get("success"):
                if action_type == "create_event":
                    meet_info = f" | Meet: {r['meet_link']}" if r.get("meet_link") else ""
                    lines.append(f"  - CREADO: \"{r.get('summary')}\" | ID: {r.get('event_id')}{meet_info}")
                elif action_type == "list_events":
                    events = r.get("events", [])
                    lines.append(f"  - LISTADO: {r.get('count', 0)} eventos encontrados")
                    for ev in events:
                        lines.append(f"    - [{ev.get('id')}] {ev.get('summary')} | {ev.get('start')} → {ev.get('end')}")
                elif action_type == "update_event":
                    lines.append(f"  - ACTUALIZADO: {r.get('event_id')} | {r.get('message')}")
                elif action_type == "delete_event":
                    lines.append(f"  - ELIMINADO: {r.get('event_id')}")
                elif action_type == "check_availability":
                    avail = r.get("availability", {})
                    status = "Todos disponibles" if r.get("all_available") else "Hay conflictos"
                    lines.append(f"  - DISPONIBILIDAD: {status}")
                    for email_addr, info in avail.items():
                        emoji = "libre" if info.get("is_available") else "ocupado"
                        lines.append(f"    - {email_addr}: {emoji}")
            else:
                lines.append(f"  - FALLÓ {action_type}: {r.get('error', 'desconocido')}")
        calendar_summary = "[RESULTADO DE CALENDARIO]\n" + "\n".join(lines) + "\n[/RESULTADO DE CALENDARIO]"

    # Guardar mensaje del usuario y respuesta limpia en Redis
    save_message(req.agent_id, req.session_id, "user", req.message)
    # Guardar respuesta del asistente con el resumen de emails, gráficos y calendario
    answer_to_save = answer
    if email_summary:
        answer_to_save = f"{answer_to_save}\n\n{email_summary}"
    if calendar_summary:
        answer_to_save = f"{answer_to_save}\n\n{calendar_summary}"
    save_message(req.agent_id, req.session_id, "assistant", answer_to_save, charts=charts if charts else None)

    # Registrar la conversación en SQLite si está habilitado
    if req.use_sql and mcp_client:
        try:
            await mcp_client.log_agent_action(
                agent_id=req.agent_id,
                action="chat_response",
                session_id=req.session_id,
                details={
                    "message_length": len(req.message),
                    "response_length": len(answer),
                    "rag_used": eff_use_rag,
                    "sql_used": sql_context_used,
                    "email_sent": email_sent,
                    "email_count": len(email_results),
                    "charts_count": len(charts),
                    "calendar_executed": calendar_executed,
                    "calendar_actions_count": len(calendar_results),
                    "temperature": eff_temperature
                },
                success=True
            )
        except Exception as e:
            print(f"Error logging to SQLite: {e}")

    # Loguear emails enviados individualmente en SQLite
    if email_sent and mcp_client:
        try:
            for er in email_results:
                if er.get("success"):
                    await mcp_client.log_agent_action(
                        agent_id=req.agent_id,
                        action="email_sent_from_chat",
                        session_id=req.session_id,
                        details={"to": er.get("to"), "subject": er.get("subject")},
                        success=True,
                    )
        except Exception as e:
            print(f"Error logging email to SQLite: {e}")

    return {
        "answer": answer,
        "sources": snippets,
        "agent_id": req.agent_id,
        "agent_name": agent["name"],
        "llm_model": agent_model,
        "session_id": req.session_id,
        "history_length": len(history) + 2,
        "sql_used": sql_context_used,
        "sql_results_count": len(sql_results),
        "email_sent": email_sent,
        "email_results": email_results,
        "charts": charts,
        "charts_count": len(charts),
        "calendar_executed": calendar_executed,
        "calendar_results": calendar_results,
    }
