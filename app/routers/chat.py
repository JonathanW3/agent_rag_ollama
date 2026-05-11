import os
import re
import json
from fastapi import APIRouter, HTTPException, Depends
from ..auth import get_current_org, OrgContext
from ..config import settings
from ..schemas import ChatRequest
from ..agents import get_agent
from ..memory import save_message, get_history
from ..ollama_client import ollama_chat
from ..rag.retrieve import retrieve, build_context
from ..utils.email_helpers import parse_email_actions, execute_email_actions
from ..utils.imap_helpers import parse_imap_actions, execute_imap_actions, format_imap_results_for_history
from ..utils.imap_facturas_helpers import parse_imap_facturas_actions, execute_imap_facturas_actions, format_imap_facturas_results_for_history
from mcp_imap_facturas.client import get_imap_facturas_client
from ..utils.chart_helpers import parse_chart_actions
from ..utils.calendar_helpers import parse_calendar_actions, execute_calendar_actions
from ..utils.cotizacion_helpers import parse_cotizacion_actions
from ..utils.alert_helpers import build_calendar_alert, build_cotizacion_alert, send_alert
from mcp_sqlite.client import get_mcp_client
from mcp_email.client import get_email_client
from mcp_mysql.client import get_mysql_client
from mcp_mysql_ibm.client import get_ibm_client
from mcp_mysql_autopart.client import get_autopart_client
from mcp_sqlserver.client import get_webpos_client
from mcp_google_calendar.client import get_calendar_client
from mcp_FE.client import get_fe_client
from ..utils.fe_helpers import parse_fe_actions, execute_fe_actions

router = APIRouter(tags=["💬 Chat"])


@router.post("/chat", summary="Conversar con un agente")
async def chat(req: ChatRequest, org: OrgContext = Depends(get_current_org)):
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
    agent_default_webpospa = agent.get("use_webpospa", False)
    eff_use_webpospa = req.use_webpospa if req.use_webpospa is not None else agent_default_webpospa
    # IMAP: si el agente tiene imap_config, habilitar por defecto
    agent_default_imap = agent.get("use_imap", bool(agent.get("imap_config")))
    eff_use_imap = req.use_imap if req.use_imap is not None else agent_default_imap
    agent_default_fe = agent.get("use_fe", False)
    eff_use_fe = req.use_fe if req.use_fe is not None else agent_default_fe
    agent_default_imap_facturas = agent.get("use_imap_facturas", False)
    eff_use_imap_facturas = req.use_imap_facturas if req.use_imap_facturas is not None else agent_default_imap_facturas
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

    # Inyectar capacidad de lectura IMAP si está habilitado y el agente tiene imap_config
    imap_enabled = eff_use_imap and bool(agent.get("imap_config"))
    if imap_enabled:
        imap_instructions = (
            "\n\n--- CAPACIDAD DE LECTURA DE EMAILS (IMAP) ---\n"
            "Tienes acceso de LECTURA a la bandeja de correos del agente. "
            "Cuando el usuario quiera revisar, buscar o leer emails, genera un bloque de acción "
            "al FINAL de tu respuesta con este formato EXACTO:\n\n"
            "[IMAP_ACTION]\n"
            '{"action": "read_inbox", "limit": 10}\n'
            "[/IMAP_ACTION]\n\n"
            "IMPORTANTE: El contenido entre [IMAP_ACTION] y [/IMAP_ACTION] DEBE ser JSON válido puro, "
            "sin texto adicional ni bloques markdown.\n\n"
            "ACCIONES DISPONIBLES:\n\n"
            "1. Leer los últimos N emails de la bandeja:\n"
            '   {"action": "read_inbox", "limit": 10, "folder": "INBOX"}\n\n'
            "2. Buscar emails por criterios (uno o más):\n"
            '   {"action": "search_emails", "from": "juan@example.com", "subject": "Factura", '
            '"since": "2024-01-15", "keyword": "pedido", "unseen_only": false, "limit": 10}\n'
            "   - from: filtrar por remitente\n"
            "   - subject: filtrar por asunto\n"
            "   - since: desde fecha (formato YYYY-MM-DD)\n"
            "   - keyword: palabra clave en el cuerpo\n"
            "   - unseen_only: true para solo no leídos\n\n"
            "3. Leer el contenido completo de un email por su ID:\n"
            '   {"action": "read_email", "id": "123"}\n'
            "   (el ID lo obtienes del resultado de read_inbox o search_emails)\n\n"
            "FLUJO DE USO:\n"
            "1. Escribe tu respuesta al usuario indicando que vas a consultar los emails\n"
            "2. Incluye el bloque [IMAP_ACTION] al final\n"
            "3. El SISTEMA ejecutará la acción y guardará los resultados en el historial\n"
            "4. En tu SIGUIENTE respuesta verás los resultados en bloques [RESULTADO DE IMAP]...[/RESULTADO DE IMAP]\n"
            "5. Usa esa información para responder al usuario con los datos reales\n\n"
            "HISTORIAL DE RESULTADOS IMAP:\n"
            "En el historial encontrarás bloques [RESULTADO DE IMAP]...[/RESULTADO DE IMAP] con:\n"
            "  - [ID:N] De: remitente | Asunto: asunto | Fecha: fecha\n"
            "  - Contenido: preview del cuerpo del email\n"
            "Usa estos datos para responder al usuario con información real de sus correos.\n\n"
            "REGLAS:\n"
            "- NUNCA inventes emails ni remitentes que no estén en los resultados IMAP\n"
            "- NUNCA generes bloques [RESULTADO DE IMAP] tú mismo, esos los genera el SISTEMA\n"
            "- Solo puedes LEER emails, no enviarlos (para enviar usa EMAIL_ACTION)\n"
            "- Si el usuario pide buscar Y enviar, primero busca con IMAP_ACTION, luego envía con EMAIL_ACTION\n"
            "--- FIN CAPACIDAD IMAP ---"
        )
        messages[0]["content"] += imap_instructions

    # Inyectar capacidad de análisis de facturación IMAP (mcp_imap_facturas)
    if eff_use_imap_facturas:
        from datetime import date as _date, timedelta as _td
        _today = _date.today()
        _curr_start  = _today.replace(day=1)
        _curr_end    = (_curr_start + _td(days=32)).replace(day=1)
        _prev_end    = _curr_start
        _prev_start  = (_prev_end - _td(days=1)).replace(day=1)
        _two_months_end   = _prev_start
        _two_months_start = (_two_months_end - _td(days=1)).replace(day=1)
        _curr_month_name       = _today.strftime("%B %Y")
        _prev_month_name       = _prev_start.strftime("%B %Y")
        _two_months_name       = _two_months_start.strftime("%B %Y")

        imap_facturas_instructions = (
            "\n\n--- CAPACIDAD DE ANÁLISIS DE FACTURACIÓN ---\n"
            "Tienes acceso a la base de datos de facturación (sincronizada cada hora desde el buzón IMAP).\n"
            "Los datos ya están indexados — las consultas son instantáneas.\n"
            "NO accedes al buzón directamente; consultas la base de datos.\n\n"

            f"FECHAS DE HOY (ya calculadas — úsalas directamente, NO las modifiques):\n"
            f"  Hoy:                        {_today}\n"
            f"  Mes actual ({_curr_month_name}):  since_date={_curr_start}  before_date={_curr_end}\n"
            f"  Mes anterior ({_prev_month_name}): since_date={_prev_start}  before_date={_prev_end}\n"
            f"  Hace 2 meses ({_two_months_name}): since_date={_two_months_start}  before_date={_two_months_end}\n"
            f"  Últimos 2 meses completos:  since_date={_two_months_start}  before_date={_curr_end}\n\n"

            "REGLA FUNDAMENTAL: Cuando el usuario pregunte sobre facturas o comparaciones entre meses, "
            "genera un bloque [IMAP_FACTURAS_ACTION] de inmediato con las fechas exactas de arriba. "
            "NUNCA uses placeholders como 'YYYY-MM-DD'.\n\n"

            "FLUJO:\n"
            "1. Escribe una línea breve ('Consultando la base de datos...').\n"
            "2. Incluye el bloque [IMAP_FACTURAS_ACTION] al final.\n"
            "3. El SISTEMA ejecutará la herramienta y guardará los resultados en el historial.\n"
            "4. En tu siguiente turno verás [RESULTADO DE IMAP FACTURAS]...[/RESULTADO DE IMAP FACTURAS].\n"
            "5. Con esos datos presenta la respuesta al usuario (tablas markdown si aplica).\n\n"

            "FORMATO DEL BLOQUE (JSON puro, sin texto extra ni markdown dentro):\n"
            "[IMAP_FACTURAS_ACTION]\n"
            '{"tool": "nombre_herramienta", "param1": "valor1"}\n'
            "[/IMAP_FACTURAS_ACTION]\n\n"

            "HERRAMIENTAS DISPONIBLES:\n\n"

            "★ 1. facturas_del_periodo — Lista facturas con empresa, RUC, subtotal, IVA, total y descripción.\n"
            "   Usar para: 'lista de facturas', 'facturas de este mes', 'facturas de abril',\n"
            "   'cuánto pagamos a empresa X', 'últimos 2 meses'.\n"
            "   Parámetro opcional 'empresa' para filtrar por nombre o RUC.\n"
            f'   {{"tool": "facturas_del_periodo", "since_date": "{_curr_start}", "before_date": "{_curr_end}"}}\n\n'

            "★ 2. comparar_periodos_facturas — Tabla comparativa A vs B por empresa con montos.\n"
            "   FALTA EN B = empresa que facturó en A pero NO en B (pendientes del mes actual).\n"
            "   Usar para: 'qué empresas faltan este mes', 'comparar meses', 'pendientes de facturar'.\n"
            f'   {{"tool": "comparar_periodos_facturas", '
            f'"period_a_start": "{_prev_start}", "period_a_end": "{_prev_end}", '
            f'"period_b_start": "{_curr_start}", "period_b_end": "{_curr_end}"}}\n\n'

            "3. comunicaciones_del_periodo — Emails de comunicación con clientes/proveedores (no facturas).\n"
            "   Usar para: '¿qué nos escribió empresa X?', 'correos de soporte', 'comunicaciones de marzo'.\n"
            "   Parámetro opcional 'empresa' para filtrar por remitente o asunto.\n"
            f'   {{"tool": "comunicaciones_del_periodo", "since_date": "{_curr_start}", "before_date": "{_curr_end}"}}\n\n'

            "EJEMPLOS DE INTERPRETACIÓN:\n"
            f"  'facturas de este mes'           → facturas_del_periodo since={_curr_start} before={_curr_end}\n"
            f"  'facturas del mes pasado'         → facturas_del_periodo since={_prev_start} before={_prev_end}\n"
            f"  'últimos 2 meses' / '2 meses'     → facturas_del_periodo since={_two_months_start} before={_curr_end}\n"
            f"  'qué empresas faltan este mes'    → comparar_periodos_facturas A={_prev_start}→{_prev_end} B={_curr_start}→{_curr_end}\n"
            f"  'comparar meses'                  → comparar_periodos_facturas A={_prev_start}→{_prev_end} B={_curr_start}→{_curr_end}\n\n"

            "REGLAS:\n"
            "- USA SIEMPRE las fechas del bloque 'FECHAS DE HOY', nunca placeholders.\n"
            "- NUNCA inventes datos que no estén en los resultados.\n"
            "- NUNCA generes bloques [RESULTADO DE IMAP FACTURAS]; esos los genera el SISTEMA.\n"
            "- before_date es EXCLUSIVA (no incluye ese día).\n"
            "--- FIN CAPACIDAD ANÁLISIS DE FACTURACIÓN ---"
        )
        messages[0]["content"] += imap_facturas_instructions

    # Inyectar capacidad de Facturación Electrónica FEPA si está habilitado
    if eff_use_fe:
        fe_instructions = (
            "\n\n--- CAPACIDAD DE FACTURACIÓN ELECTRÓNICA (FEPA) ---\n"
            "Tienes acceso a la API de Facturación Electrónica FEPA. "
            "TÚ NO CONOCES los datos de ninguna factura. TODA información de facturas viene exclusivamente "
            "de la API. Nunca puedes responder con datos de una factura sin haber llamado primero a la API.\n\n"

            "## REGLA INCONDICIONAL — CUÁNDO GENERAR [FE_ACTION]\n"
            "SIEMPRE que el mensaje del usuario contenga un CUFE o un systemRef, "
            "DEBES generar el bloque [FE_ACTION] DE INMEDIATO. SIN EXCEPCIÓN.\n"
            "NO hagas preguntas. NO pidas confirmación. NO preguntes '¿qué deseas saber?'. "
            "NO esperes más instrucciones. LLAMA A LA API PRIMERO, siempre.\n"
            "Un CUFE es una cadena alfanumérica que comienza con 'FE' seguida de números y guiones. "
            "Si la ves en el mensaje, actúa de inmediato sin importar nada más.\n\n"

            "Qué herramienta usar:\n"
            "- Mensaje contiene un CUFE (empieza con 'FE...') → getResultFe inmediatamente\n"
            "- Mensaje contiene un systemRef → getCufeBySystemRef inmediatamente\n"
            "- Usuario pide EXPLÍCITAMENTE el PDF → getPdf\n\n"

            "## FORMATO OBLIGATORIO\n"
            "Escribe SOLO una línea breve ('Voy a consultar la factura...') y luego el bloque:\n\n"
            "[FE_ACTION]\n"
            '{"tool": "nombreHerramienta", "param1": "valor1"}\n'
            "[/FE_ACTION]\n\n"
            "El bloque se llama EXACTAMENTE [FE_ACTION] y [/FE_ACTION]. Ningún otro nombre.\n\n"

            "## HERRAMIENTAS DISPONIBLES (SOLO ESTAS 3)\n\n"
            "1. getResultFe — Consultar factura por CUFE:\n"
            '   {"tool": "getResultFe", "cufe": "<CUFE completo>"}\n\n'
            "2. getCufeBySystemRef — Buscar factura por referencia interna:\n"
            '   {"tool": "getCufeBySystemRef", "docType": "<tipo>", "systemRef": "<referencia>"}\n\n'
            "3. getPdf — Obtener PDF (solo si el usuario lo pide explícitamente):\n"
            '   {"tool": "getPdf", "cufe": "<CUFE completo>"}\n\n'

            "## PROHIBICIONES ABSOLUTAS\n"
            "- PROHIBIDO inventar o suponer datos, montos, fechas, estados o números de factura\n"
            "- PROHIBIDO escribir 'RESULTADO DE FE', 'resultado de la consulta', ni ningún bloque "
            "que imite resultados de la API. Solo el SISTEMA genera esos bloques\n"
            "- PROHIBIDO responder con datos de una factura sin haber generado antes el [FE_ACTION]\n"
            "- PROHIBIDO ofrecer el PDF si el usuario no lo pidió explícitamente\n"
            "- PROHIBIDO acortar, truncar o resumir un CUFE. Cópialo carácter por carácter completo "
            "(son cadenas de 60-100 caracteres)\n"
            "- El JSON dentro de [FE_ACTION] debe ser válido: sin comentarios, sin texto extra\n"
            "- La API NO devuelve datos del cliente ni detalle de productos. Si preguntan: "
            "'La API FEPA no proporciona datos del cliente ni el detalle de productos.'\n\n"

            "## CUÁNDO USAR LOS DATOS DE LA API\n"
            "Solo cuando veas [RESULTADO DE FE] en el historial (lo genera el SISTEMA automáticamente), "
            "úsalo como única fuente de verdad para responder al usuario.\n"
            "--- FIN CAPACIDAD FEPA ---"
        )
        messages[0]["content"] += fe_instructions

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
        from datetime import datetime as _dt, timedelta as _td
        _now = _dt.now()
        _tomorrow = _now + _td(days=1)
        calendar_instructions = (
            "\n\n--- CAPACIDAD DE GOOGLE CALENDAR ---\n"
            f"FECHA Y HORA ACTUAL: {_now.strftime('%Y-%m-%dT%H:%M:%S')} (zona: America/Mexico_City)\n"
            f"FECHA MÍNIMA PARA AGENDAR EVENTOS: {_tomorrow.strftime('%Y-%m-%d')}T00:00:00\n"
            f"AÑO ACTUAL: {_now.year}\n\n"
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
            "- PROHIBIDO agendar eventos para el día de hoy o fechas pasadas. Solo se permiten eventos a partir de MAÑANA. "
            "Si el usuario pide agendar algo para hoy, respóndele que solo puedes agendar a partir de mañana y pregúntale si desea agendarlo para mañana.\n"
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

    # Inyectar capacidad de cotizaciones (siempre activa si hay alertas configuradas)
    _has_alerts = agent.get("alert_wa_number") or agent.get("alert_email")
    if _has_alerts:
        cotizacion_instructions = (
            "\n\n--- CAPACIDAD DE COTIZACIONES ---\n"
            "Cuando el usuario solicite una cotización, presupuesto o lista de precios, "
            "genera un bloque [COTIZACION_ACTION] al final de tu respuesta con los datos estructurados.\n\n"

            "FORMATO:\n"
            "[COTIZACION_ACTION]\n"
            "{\n"
            '  "cliente": "Nombre del cliente o descripción",\n'
            '  "productos": [\n'
            '    {"nombre": "Producto 1", "cantidad": 2, "precio": "$50.00"},\n'
            '    {"nombre": "Producto 2", "cantidad": 1, "precio": "$30.00"}\n'
            '  ],\n'
            '  "total": "$130.00",\n'
            '  "moneda": "USD",\n'
            '  "notas": "Observaciones adicionales"\n'
            "}\n"
            "[/COTIZACION_ACTION]\n\n"

            "CAMPOS OBLIGATORIOS: cliente, productos\n"
            "CAMPOS OPCIONALES: total, moneda (default USD), notas\n\n"

            "REGLAS:\n"
            "- SIEMPRE escribe tu respuesta al usuario PRIMERO, luego el bloque [COTIZACION_ACTION] al final\n"
            "- Incluye TODOS los productos/servicios mencionados con cantidades y precios\n"
            "- Si el precio no está disponible, usa 'Por confirmar'\n"
            "- Extrae el nombre del cliente de la conversación si fue mencionado\n"
            "- PROHIBIDO generar bloques [RESULTADO DE COTIZACION]. Esos los genera el SISTEMA\n"
            "--- FIN CAPACIDAD DE COTIZACIONES ---"
        )
        messages[0]["content"] += cotizacion_instructions

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

    # Agregar contexto SQL Server webpospa (licencias Ecuador) si está habilitado
    print(f"[WEBPOSPA DEBUG] eff_use_webpospa={eff_use_webpospa} | agente={req.agent_id}")
    if eff_use_webpospa:
        try:
            webpos = get_webpos_client()
            webpos_parts = []
            message_lower = req.message.lower()

            # Detectar RUC (13 dígitos) en el mensaje para búsqueda específica
            ruc_match = re.search(r"\b(\d{13})\b", req.message)
            # Detectar nombre de empresa entre comillas o tras palabras clave
            nombre_match = re.search(
                r'(?:empresa|compañia|compañía|cliente|busca[r]?)\s+["\']?([A-Za-záéíóúÁÉÍÓÚñÑ\s\.]+)["\']?',
                message_lower
            )

            licencias_keywords = [
                "licencia", "licencias", "vencer", "vencimiento", "vence", "expira",
                "expiración", "renovar", "renovación", "ruc", "empresa", "cliente",
                "soporte", "sws", "webpos", "efiscal", "ecuador", "contacto", "correo",
                "email", "fecha", "días", "dias", "contrato", "licenciamiento", "nube",
                "caducar", "caduca", "caduco", "caducó", "vencida", "vencidas", "meses",
                "on-premise", "on premise"
            ]
            needs_webpospa = (
                ruc_match is not None
                or nombre_match is not None
                or any(kw in message_lower for kw in licencias_keywords)
            )

            # Detectar intención: filtro por tipo de cliente Licenciamiento
            licenciamiento_kws = ["licenciamiento", "on-premise", "on premise"]
            is_licenciamiento_query = any(kw in message_lower for kw in licenciamiento_kws)

            # Detectar intención: consulta por mes/meses (calendario anual de vencimientos)
            meses_kws = ["mes ", "meses", "mes?", "mensual", "calendario", "anual"]
            is_meses_query = any(kw in message_lower for kw in meses_kws)

            print(f"[WEBPOSPA DEBUG] needs_webpospa={needs_webpospa} | licenciamiento={is_licenciamiento_query} | meses={is_meses_query} | ruc={ruc_match.group(1) if ruc_match else None} | nombre={nombre_match.group(1).strip() if nombre_match else None}")

            webpospa_no_data_msg = None

            if needs_webpospa:
                if ruc_match:
                    ruc = ruc_match.group(1)
                    print(f"[WEBPOSPA DEBUG] Consultando SQL Server — buscar_empresa_ecuador(ruc={ruc})")
                    resultado = await webpos.buscar_empresa_ecuador(ruc=ruc)
                    print(f"[WEBPOSPA DEBUG] Resultado: success={resultado.get('success')} count={resultado.get('count')} error={resultado.get('error')}")
                    if resultado.get("success") and resultado.get("count", 0) > 0:
                        print(f"[WEBPOSPA DEBUG] ✓ {resultado['count']} fila(s) encontrada(s) para RUC {ruc}")
                        webpos_parts.append(
                            f"Datos de la empresa con RUC {ruc} (SQL Server webpospa):\n"
                            + json.dumps(resultado["rows"], indent=2, ensure_ascii=False, default=str)
                        )
                    elif resultado.get("error"):
                        print(f"[WEBPOSPA DEBUG] ✗ Error SQL Server: {resultado['error']}")
                        webpospa_no_data_msg = f"Error al consultar SQL Server: {resultado['error']}. NO inventes datos."
                    else:
                        print(f"[WEBPOSPA DEBUG] ✗ RUC {ruc} no encontrado en Ecuador (0 filas)")
                        webpospa_no_data_msg = (
                            f"La consulta a SQL Server no encontró ninguna empresa con RUC {ruc} en Ecuador. "
                            "NO inventes datos. Informa al usuario que no se encontraron registros para ese RUC."
                        )
                elif nombre_match:
                    nombre = nombre_match.group(1).strip()
                    print(f"[WEBPOSPA DEBUG] Consultando SQL Server — buscar_empresa_ecuador(nombre='{nombre}')")
                    resultado = await webpos.buscar_empresa_ecuador(nombre=nombre)
                    print(f"[WEBPOSPA DEBUG] Resultado: success={resultado.get('success')} count={resultado.get('count')} error={resultado.get('error')}")
                    if resultado.get("success") and resultado.get("count", 0) > 0:
                        print(f"[WEBPOSPA DEBUG] ✓ {resultado['count']} empresa(s) encontrada(s) para nombre '{nombre}'")
                        webpos_parts.append(
                            f"Empresas que coinciden con '{nombre}' (SQL Server webpospa):\n"
                            + json.dumps(resultado["rows"], indent=2, ensure_ascii=False, default=str)
                        )
                    elif resultado.get("error"):
                        print(f"[WEBPOSPA DEBUG] ✗ Error SQL Server: {resultado['error']}")
                        webpospa_no_data_msg = f"Error al consultar SQL Server: {resultado['error']}. NO inventes datos."
                    else:
                        print(f"[WEBPOSPA DEBUG] ✗ Nombre '{nombre}' no encontrado en Ecuador (0 filas)")
                        webpospa_no_data_msg = (
                            f"La consulta a SQL Server no encontró empresas con nombre '{nombre}' en Ecuador. "
                            "NO inventes datos. Informa al usuario que no se encontraron registros."
                        )
                elif is_licenciamiento_query:
                    # Resumen liviano de empresas Licenciamiento (sin LicenciasJSON)
                    print(f"[WEBPOSPA DEBUG] Consultando — resumen_tipo_licenciamiento(licenciamiento=True)")
                    resultado = await webpos.resumen_tipo_licenciamiento(licenciamiento=True)
                    print(f"[WEBPOSPA DEBUG] Resultado: success={resultado.get('success')} count={resultado.get('count')} error={resultado.get('error')}")
                    if resultado.get("success") and resultado.get("count", 0) > 0:
                        print(f"[WEBPOSPA DEBUG] ✓ {resultado['count']} empresa(s) Licenciamiento")
                        webpos_parts.append(
                            f"Empresas de tipo Licenciamiento (on-premise) — {resultado['count']} empresa(s) total.\n"
                            "⚠️ IMPORTANTE: El campo EFiscalDocsExpirationDate almacena una fecha histórica — "
                            "el AÑO debe IGNORARSE. Solo el MES y DÍA son relevantes (renovación anual). "
                            "Para la fecha real próxima usa ProximaFechaVencimiento del bloque siguiente.\n"
                            "⚠️ INSTRUCCIÓN: Muestra TODAS las empresas con sus fechas de renovación, "
                            "sin filtrar por ventana de días. No limites la respuesta a 45 días.\n\n"
                            + json.dumps(resultado["rows"], indent=2, ensure_ascii=False, default=str)
                        )
                        # Siempre agregar calendario eFiscalDocs (año ignorado, próximos 12 meses)
                        print(f"[WEBPOSPA DEBUG] + licencias_efiscal_por_mes(dias=365)")
                        res_meses = await webpos.licencias_efiscal_por_mes(dias=365)
                        if res_meses.get("success") and res_meses.get("count", 0) > 0:
                            print(f"[WEBPOSPA DEBUG] ✓ {res_meses['count']} vencimiento(s) eFiscalDocs")
                            webpos_parts.append(
                                "Vencimientos eFiscalDocs por mes (próximos 12 meses, solo Licenciamiento).\n"
                                "Campos clave: ProximaFechaVencimiento = fecha real (año correcto), "
                                "DiasParaVencer = días hasta esa fecha, MesVencimiento = mes.\n"
                                "⚠️ INSTRUCCIÓN: Ordena por DiasParaVencer y muestra TODOS — "
                                "no cortes la lista ni filtres por ventana de días:\n\n"
                                + json.dumps(res_meses["rows"], indent=2, ensure_ascii=False, default=str)
                            )
                    elif resultado.get("error"):
                        print(f"[WEBPOSPA DEBUG] ✗ Error: {resultado['error']}")
                        webpospa_no_data_msg = f"Error al consultar: {resultado['error']}. NO inventes datos."
                    else:
                        print(f"[WEBPOSPA DEBUG] ✗ Sin empresas de tipo Licenciamiento (0 filas)")
                        webpospa_no_data_msg = (
                            "No se encontraron empresas de tipo Licenciamiento (on-premise). NO inventes datos."
                        )
                elif is_meses_query:
                    # Consulta de calendario anual de vencimientos eFiscalDocs
                    print(f"[WEBPOSPA DEBUG] Consultando SQL Server — licencias_efiscal_por_mes(dias=365)")
                    resultado = await webpos.licencias_efiscal_por_mes(dias=365)
                    print(f"[WEBPOSPA DEBUG] Resultado: success={resultado.get('success')} count={resultado.get('count')} error={resultado.get('error')}")
                    if resultado.get("success") and resultado.get("count", 0) > 0:
                        print(f"[WEBPOSPA DEBUG] ✓ {resultado['count']} empresa(s) con vencimiento eFiscalDocs próximo")
                        webpos_parts.append(
                            "Vencimientos eFiscalDocs por mes (próximos 12 meses, solo Licenciamiento).\n"
                            "El campo EFiscalDocsExpirationDate almacena una fecha histórica — el AÑO se ignora. "
                            "Usa ProximaFechaVencimiento para la fecha real del próximo vencimiento "
                            "y DiasParaVencer para los días restantes:\n\n"
                            + json.dumps(resultado["rows"], indent=2, ensure_ascii=False, default=str)
                        )
                    elif resultado.get("error"):
                        print(f"[WEBPOSPA DEBUG] ✗ Error SQL Server: {resultado['error']}")
                        webpospa_no_data_msg = f"Error al consultar SQL Server: {resultado['error']}. NO inventes datos."
                    else:
                        print(f"[WEBPOSPA DEBUG] ✗ Sin vencimientos eFiscalDocs en los próximos 12 meses (0 filas)")
                        webpospa_no_data_msg = (
                            "No se encontraron vencimientos de eFiscalDocs en los próximos 12 meses. "
                            "NO inventes datos."
                        )
                else:
                    print(f"[WEBPOSPA DEBUG] Consultando SQL Server — licencias_por_vencer(dias=60)")
                    resultado = await webpos.licencias_por_vencer(dias=60, campo_fecha="ambas")
                    print(f"[WEBPOSPA DEBUG] Resultado: success={resultado.get('success')} count={resultado.get('count')} error={resultado.get('error')}")
                    if resultado.get("success") and resultado.get("count", 0) > 0:
                        print(f"[WEBPOSPA DEBUG] ✓ {resultado['count']} licencia(s) por vencer encontrada(s)")
                        webpos_parts.append(
                            f"Licencias por vencer en los próximos 60 días (SQL Server webpospa):\n"
                            + json.dumps(resultado["rows"], indent=2, ensure_ascii=False, default=str)
                        )
                    elif resultado.get("error"):
                        print(f"[WEBPOSPA DEBUG] ✗ Error SQL Server: {resultado['error']}")
                        webpospa_no_data_msg = f"Error al consultar SQL Server: {resultado['error']}. NO inventes datos."
                    else:
                        print(f"[WEBPOSPA DEBUG] ✗ Sin licencias por vencer en 60 días (0 filas)")
                        webpospa_no_data_msg = (
                            "La consulta a SQL Server no encontró licencias por vencer en los próximos 60 días. "
                            "NO inventes datos. Informa al usuario que no hay registros."
                        )

                if webpos_parts:
                    print(f"[WEBPOSPA DEBUG] ✓ Contexto SQL Server inyectado al LLM ({len(webpos_parts)} bloque(s))")
                    messages.append({
                        "role": "system",
                        "content": (
                            "Datos reales de licencias webpospa Ecuador disponibles para responder. "
                            "USA ÚNICAMENTE ESTOS DATOS — no inventes ni supongas información:\n\n"
                            + "\n\n".join(webpos_parts)
                        )
                    })
                elif webpospa_no_data_msg:
                    print(f"[WEBPOSPA DEBUG] ✗ Sin datos — inyectando advertencia al LLM")
                    messages.append({
                        "role": "system",
                        "content": (
                            "ADVERTENCIA — Sin datos de SQL Server: " + webpospa_no_data_msg
                        )
                    })
            else:
                print(f"[WEBPOSPA DEBUG] Mensaje no requiere consulta SQL Server (sin keywords ni RUC)")
        except Exception as e:
            print(f"[WEBPOSPA DEBUG] ✗ EXCEPCIÓN conectando a SQL Server: {type(e).__name__}: {e}")
            messages.append({
                "role": "system",
                "content": (
                    f"ADVERTENCIA — No se pudo conectar a SQL Server webpospa: {e}. "
                    "NO inventes datos de licencias. Informa al usuario que hay un problema de conexión."
                )
            })
    else:
        print(f"[WEBPOSPA DEBUG] MCP SQL Server DESHABILITADO para agente '{req.agent_id}' — use_webpospa={agent.get('use_webpospa')} en config del agente")

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
    # Aumentar num_predict cuando hay contexto webpospa grande (múltiples empresas)
    _num_predict = 4096 if eff_use_webpospa else None
    try:
        answer = ollama_chat(messages, temperature=eff_temperature, model=agent_model, num_predict=_num_predict)
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

            # ── RETRY: detectar intención de email sin bloque [EMAIL_ACTION] ──
            # Si el LLM mencionó enviar/mandar correo o incluyó una dirección de email
            # pero no generó el bloque, pedirle explícitamente que lo genere.
            import re as _re
            # Patrones de envío ACTIVO (el LLM afirma que ya envió o está enviando)
            email_intent_patterns = [
                r'te mand[oé]', r'ya.*envi[eé]', r'procesando.*envío',
                r'te envío la cotización', r'enviando.*correo',
                r'te he enviado', r'correo enviado',
            ]
            # Patrones de OFRECIMIENTO (NO deben disparar retry)
            email_offer_patterns = [
                r'te puedo enviar', r'puedo enviarte', r'si lo deseas',
                r'si quieres', r'¿te envío', r'¿quieres que.*envi',
                r'¿te gustaría', r'si deseas', r'te interesa.*enviar',
            ]
            has_email_intent = any(_re.search(p, answer, _re.IGNORECASE) for p in email_intent_patterns)
            is_just_offer = any(_re.search(p, answer, _re.IGNORECASE) for p in email_offer_patterns)

            # Solo retry si hay intención ACTIVA de envío, NO si solo es un ofrecimiento
            if has_email_intent and not is_just_offer:
                print(f"[EMAIL DEBUG] Intención de email detectada sin bloque. Reintentando con prompt explícito...")
                # Extraer el email destino de la respuesta si existe
                found_email = _re.search(r'([\w.+-]+@[\w-]+\.[\w.-]+)', answer)
                email_hint = f" El destinatario es: {found_email.group(1)}" if found_email else ""

                retry_messages = messages + [
                    {"role": "assistant", "content": answer},
                    {"role": "user", "content": (
                        "SISTEMA: Tu respuesta anterior menciona enviar un correo pero NO incluiste "
                        "el bloque [EMAIL_ACTION] necesario. Sin ese bloque el correo NO se envía.\n"
                        f"{email_hint}\n"
                        "Genera SOLO el bloque [EMAIL_ACTION] con el JSON completo. "
                        "No repitas tu respuesta anterior, SOLO genera el bloque:\n\n"
                        "[EMAIL_ACTION]\n"
                        '{"to": "...", "subject": "...", "body": "...", "html": false}\n'
                        "[/EMAIL_ACTION]"
                    )}
                ]
                try:
                    retry_answer = ollama_chat(retry_messages, temperature=eff_temperature, model=agent_model)
                    print(f"[EMAIL DEBUG] Retry respuesta: {retry_answer[:300]}")
                    if "[EMAIL_ACTION]" in retry_answer:
                        # Agregar el bloque al answer original para que se parsee
                        answer = answer + "\n" + retry_answer
                        print("[EMAIL DEBUG] Retry exitoso: bloque [EMAIL_ACTION] recuperado")
                    else:
                        print("[EMAIL DEBUG] Retry fallido: el modelo sigue sin generar el bloque")
                except Exception as e:
                    print(f"[EMAIL DEBUG] Error en retry: {e}")
            # ── FIN RETRY ──

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
        try:
            # Limpiar bloques falsos de resultado generados por el LLM
            fake_calendar_pattern = r'\[RESULTADO DE CALENDARIO\].*?\[/RESULTADO DE CALENDARIO\]'
            answer = re.sub(fake_calendar_pattern, '', answer, flags=re.DOTALL).strip()

            # ── RETRY: detectar intención de calendario sin bloque [CALENDAR_ACTION] ──
            has_calendar_tag = "[CALENDAR_ACTION]" in answer
            print(f"[CALENDAR DEBUG] ¿Contiene [CALENDAR_ACTION]? {has_calendar_tag}")
            if not has_calendar_tag:
                print(f"[CALENDAR DEBUG] Final de respuesta LLM (últimos 500 chars): ...{answer[-500:]}")
                import re as _re_cal
                # Patrones de agendamiento ACTIVO (el LLM afirma que ya agendó)
                calendar_intent_patterns = [
                    r'cita.*agendada', r'reuni[oó]n.*agendada', r'cita.*programada',
                    r'reuni[oó]n.*programada', r'te agend[oé]', r'queda.*agendad[ao]',
                    r'evento.*cread[ao]', r'te he agendado', r'cita confirmada',
                    r'procesando.*cita', r'procesando.*reuni[oó]n',
                ]
                # Patrones de OFRECIMIENTO o referencia pasada (NO deben disparar retry)
                calendar_offer_patterns = [
                    r'¿te agendo', r'¿quieres.*agend', r'¿te gustaría.*agend',
                    r'puedo agendarte', r'si quieres.*agend', r'si deseas.*agend',
                    r'retomando.*cita', r'lo de tu cita', r'tu cita.*para mañana',
                    r'antes de tu visita', r'tu cita de',
                ]
                has_calendar_intent = any(_re_cal.search(p, answer, _re_cal.IGNORECASE) for p in calendar_intent_patterns)
                is_just_cal_offer = any(_re_cal.search(p, answer, _re_cal.IGNORECASE) for p in calendar_offer_patterns)

                # Solo retry si hay intención ACTIVA de agendar, NO si solo es ofrecimiento/referencia
                if has_calendar_intent and not is_just_cal_offer:
                    print(f"[CALENDAR DEBUG] Intención de calendario detectada sin bloque. Reintentando con prompt explícito...")
                    retry_messages = messages + [
                        {"role": "assistant", "content": answer},
                        {"role": "user", "content": (
                            "SISTEMA: Tu respuesta anterior menciona agendar/programar una cita o reunión pero NO incluiste "
                            "el bloque [CALENDAR_ACTION] necesario. Sin ese bloque la cita NO se agenda en Google Calendar.\n"
                            "Genera SOLO el bloque [CALENDAR_ACTION] con el JSON completo basándote en los datos "
                            "de tu respuesta anterior (fecha, hora, descripción, etc). "
                            "No repitas tu respuesta anterior, SOLO genera el bloque:\n\n"
                            "[CALENDAR_ACTION]\n"
                            '{"action_type": "create_event", "summary": "...", "start_datetime": "YYYY-MM-DDTHH:MM:SS", '
                            '"end_datetime": "YYYY-MM-DDTHH:MM:SS", "description": "...", "location": "...", '
                            '"timezone": "America/Mexico_City"}\n'
                            "[/CALENDAR_ACTION]"
                        )}
                    ]
                    try:
                        retry_answer = ollama_chat(retry_messages, temperature=eff_temperature, model=agent_model)
                        print(f"[CALENDAR DEBUG] Retry respuesta: {retry_answer[:300]}")
                        if "[CALENDAR_ACTION]" in retry_answer:
                            answer = answer + "\n" + retry_answer
                            print("[CALENDAR DEBUG] Retry exitoso: bloque [CALENDAR_ACTION] recuperado")
                        else:
                            print("[CALENDAR DEBUG] Retry fallido: el modelo sigue sin generar el bloque")
                    except Exception as e:
                        print(f"[CALENDAR DEBUG] Error en retry: {e}")
            # ── FIN RETRY CALENDARIO ──

            calendar_actions, cleaned_answer = parse_calendar_actions(answer)
            print(f"[CALENDAR DEBUG] Acciones parseadas: {len(calendar_actions)}")

            if calendar_actions:
                print(f"[CALENDAR DEBUG] Ejecutando {len(calendar_actions)} acciones: {calendar_actions}")
                cal_client = get_calendar_client()
                calendar_results = await execute_calendar_actions(
                    actions=calendar_actions,
                    calendar_client=cal_client,
                )
                calendar_executed = any(r.get("success") for r in calendar_results)
                print(f"[CALENDAR DEBUG] Resultados: {calendar_results}")
                print(f"[CALENDAR DEBUG] calendar_executed={calendar_executed}")
                answer = cleaned_answer
        except Exception as e:
            print(f"[CALENDAR ERROR] Error en post-procesamiento de calendario: {e}")
            import traceback
            traceback.print_exc()
    # ── END CALENDAR POST-PROCESSING ────────────────────────────────────

    # ── IMAP POST-PROCESSING ──────────────────────────────────────────
    imap_results = []
    imap_executed = False

    if imap_enabled:
        try:
            # Limpiar bloques [RESULTADO DE IMAP] falsos generados por el LLM
            fake_imap_pattern = r'\[RESULTADO DE IMAP\].*?\[/RESULTADO DE IMAP\]'
            answer = re.sub(fake_imap_pattern, '', answer, flags=re.DOTALL).strip()

            imap_actions, cleaned_answer = parse_imap_actions(answer)
            print(f"[IMAP DEBUG] Acciones parseadas: {len(imap_actions)}")

            if imap_actions:
                email_client = get_email_client()
                imap_results = await execute_imap_actions(
                    actions=imap_actions,
                    imap_config=agent["imap_config"],
                    imap_client=email_client,
                )
                imap_executed = any(r.get("success") for r in imap_results)
                print(f"[IMAP DEBUG] Resultados: {imap_executed}")
                answer = cleaned_answer
        except Exception as e:
            print(f"[IMAP ERROR] Error en post-procesamiento IMAP: {e}")
            import traceback
            traceback.print_exc()
    # ── END IMAP POST-PROCESSING ──────────────────────────────────────

    # ── IMAP FACTURAS POST-PROCESSING ────────────────────────────────
    imap_facturas_results = []
    imap_facturas_executed = False

    if eff_use_imap_facturas:
        try:
            fake_if_pattern = r'\[RESULTADO DE IMAP FACTURAS\].*?\[/RESULTADO DE IMAP FACTURAS\]'
            answer = re.sub(fake_if_pattern, '', answer, flags=re.DOTALL).strip()

            imap_facturas_actions, cleaned_answer = parse_imap_facturas_actions(answer)
            print(f"[IMAP_FACTURAS DEBUG] Acciones parseadas: {len(imap_facturas_actions)}")

            if imap_facturas_actions:
                imap_facturas_client = get_imap_facturas_client()
                imap_facturas_results = await execute_imap_facturas_actions(
                    actions=imap_facturas_actions,
                    client=imap_facturas_client,
                )
                imap_facturas_executed = any(r.get("success") for r in imap_facturas_results)
                print(f"[IMAP_FACTURAS DEBUG] Ejecutadas: {imap_facturas_executed} | Resultados: {len(imap_facturas_results)}")
                answer = cleaned_answer
        except Exception as e:
            print(f"[IMAP_FACTURAS ERROR] Error en post-procesamiento: {e}")
            import traceback
            traceback.print_exc()
    # ── END IMAP FACTURAS POST-PROCESSING ────────────────────────────

    # ── FE POST-PROCESSING ───────────────────────────────────────────
    fe_results = []
    fe_executed = False

    if eff_use_fe:
        try:
            fake_fe_pattern = r'\[RESULTADO DE FE\].*?(?:\[/RESULTADO DE FE\]|$)'
            answer = re.sub(fake_fe_pattern, '', answer, flags=re.DOTALL).strip()

            fe_actions, cleaned_answer = parse_fe_actions(answer)
            print(f"[FE DEBUG] Acciones parseadas: {len(fe_actions)}")

            if fe_actions:
                fe_client = get_fe_client()
                fe_results = await execute_fe_actions(
                    actions=fe_actions,
                    fe_client=fe_client,
                )
                fe_executed = any(r.get("success") for r in fe_results)
                print(f"[FE DEBUG] Resultados: {fe_results}")

                if fe_executed:
                    # Segunda llamada al LLM con los datos reales de la API.
                    # Se usa SOLO el system prompt original + pregunta del usuario + datos reales
                    # para evitar que el LLM se ancle a los datos inventados de cleaned_answer.
                    _HEAVY_FIELDS = {"xml", "pdf", "qr", "qrCode", "qrImage", "base64"}
                    fe_data_lines = []
                    for r in fe_results:
                        if r.get("success"):
                            data_for_llm = {
                                k: v for k, v in r.get("data", {}).items()
                                if k not in _HEAVY_FIELDS
                            }
                            fe_data_lines.append(
                                json.dumps(data_for_llm, ensure_ascii=False, indent=2)
                            )
                    fe_real_data = "\n\n".join(fe_data_lines)

                    # Segunda llamada: system prompt mínimo y enfocado solo en presentar datos.
                    # NO hereda el prompt del agente para evitar que el modelo entre en
                    # "modo presentación de capacidades" en lugar de mostrar los datos reales.
                    second_system = (
                        "Eres un asistente que presenta resultados de facturas electrónicas. "
                        "Responde siempre en español.\n\n"
                        "DATOS REALES de la factura consultada en la API FEPA:\n\n"
                        f"{fe_real_data}\n\n"
                        "TU ÚNICA TAREA: interpretar los datos anteriores y responderle al usuario "
                        "de forma clara y en lenguaje natural.\n\n"
                        "REGLAS:\n"
                        "- Usa SOLO los datos del JSON. No inventes nada.\n"
                        "- NO generes [FE_ACTION] ni ningún bloque de acción.\n"
                        "- NO muestres el JSON crudo.\n"
                        "- NO ofrezcas servicios adicionales (PDF, email, etc.) que el usuario no pidió.\n"
                        "- NO expliques tus capacidades ni lo que puedes hacer.\n"
                        "- Responde directamente la pregunta del usuario con los datos obtenidos."
                    )

                    second_messages = [
                        {"role": "system", "content": second_system},
                        {"role": "user", "content": req.message},
                    ]
                    try:
                        answer = ollama_chat(second_messages, temperature=eff_temperature, model=agent_model)
                        # Limpiar si el LLM echó el bloque [RESULTADO DE FE] en su respuesta
                        answer = re.sub(fake_fe_pattern, '', answer, flags=re.DOTALL).strip()
                        print(f"[FE DEBUG] Segunda llamada LLM OK, respuesta: {answer[:300]}")
                    except Exception as e:
                        print(f"[FE ERROR] Error en segunda llamada LLM: {e}")
                        answer = cleaned_answer
                else:
                    # La API fue llamada pero todas las consultas fallaron.
                    # Hacer segunda llamada con el error para que el agente lo explique al usuario.
                    fe_errors = [
                        r.get("error", "Error desconocido")
                        for r in fe_results
                        if not r.get("success") and r.get("error")
                    ]
                    if fe_errors:
                        error_text = "\n".join(fe_errors)
                        error_system = (
                            "Eres un asistente de Facturación Electrónica. "
                            "Responde siempre en español.\n\n"
                            f"La consulta a la API FEPA falló con el siguiente mensaje:\n{error_text}\n\n"
                            "TU TAREA: informar al usuario del problema de forma clara y amigable. "
                            "Sugiere que verifique el CUFE o la referencia ingresada. "
                            "NO generes [FE_ACTION] ni bloques de acción. "
                            "NO inventes datos de la factura."
                        )
                        try:
                            answer = ollama_chat(
                                [
                                    {"role": "system", "content": error_system},
                                    {"role": "user", "content": req.message},
                                ],
                                temperature=eff_temperature,
                                model=agent_model,
                            )
                            print(f"[FE DEBUG] Llamada de error LLM OK, respuesta: {answer[:200]}")
                        except Exception as e:
                            print(f"[FE ERROR] Error en llamada de error LLM: {e}")
                            answer = cleaned_answer
                    else:
                        answer = cleaned_answer
        except Exception as e:
            print(f"[FE ERROR] Error en post-procesamiento FE: {e}")
            import traceback
            traceback.print_exc()
    # ── END FE POST-PROCESSING ────────────────────────────────────────

    # ── COTIZACION POST-PROCESSING ─────────────────────────────────────
    cotizacion_actions = []
    _has_alerts = agent.get("alert_wa_number") or agent.get("alert_email")
    if _has_alerts:
        # Limpiar bloques falsos de resultado
        fake_cotiz_pattern = r'\[RESULTADO DE COTIZACION\].*?\[/RESULTADO DE COTIZACION\]'
        answer = re.sub(fake_cotiz_pattern, '', answer, flags=re.DOTALL).strip()

        cotizacion_actions, cleaned_answer = parse_cotizacion_actions(answer)
        print(f"[COTIZACION DEBUG] Acciones parseadas: {len(cotizacion_actions)}")
        if cotizacion_actions:
            answer = cleaned_answer
    # ── END COTIZACION POST-PROCESSING ─────────────────────────────────

    # ── ALERTAS (WhatsApp + Email) ─────────────────────────────────────
    alert_results = []
    if _has_alerts:
        try:
            conversation_for_alert = messages[1:]  # Excluir system prompt

            # Alerta por reunión agendada exitosamente
            if calendar_executed and calendar_actions:
                for i, r in enumerate(calendar_results):
                    if r.get("success") and r.get("action_type") == "create_event":
                        alert_text = build_calendar_alert(
                            calendar_result=r,
                            calendar_action=calendar_actions[i] if i < len(calendar_actions) else {},
                            session_id=req.session_id,
                            agent_name=agent["name"],
                            conversation_summary=conversation_for_alert,
                        )
                        result = await send_alert(
                            alert_text=alert_text,
                            alert_wa_session_id=agent.get("alert_wa_session_id"),
                            alert_wa_number=agent.get("alert_wa_number"),
                            alert_email=agent.get("alert_email"),
                            smtp_config=agent.get("smtp_config"),
                            agent_name=agent["name"],
                        )
                        alert_results.append({"type": "calendar", "result": result})

            # Alerta por cotización generada
            for cotiz_action in cotizacion_actions:
                if "_parse_error" in cotiz_action:
                    continue
                alert_text = build_cotizacion_alert(
                    cotizacion_action=cotiz_action,
                    session_id=req.session_id,
                    agent_name=agent["name"],
                    conversation_summary=conversation_for_alert,
                )
                result = await send_alert(
                    alert_text=alert_text,
                    alert_wa_session_id=agent.get("alert_wa_session_id"),
                    alert_wa_number=agent.get("alert_wa_number"),
                    alert_email=agent.get("alert_email"),
                    smtp_config=agent.get("smtp_config"),
                    agent_name=agent["name"],
                )
                alert_results.append({"type": "cotizacion", "result": result})
        except Exception as e:
            print(f"[ALERT ERROR] Error enviando alertas: {e}")
            import traceback
            traceback.print_exc()

    if alert_results:
        print(f"[ALERT DEBUG] Alertas enviadas: {len(alert_results)} — {alert_results}")
    # ── END ALERTAS ────────────────────────────────────────────────────

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

    # Construir resumen IMAP para inyectar en el historial
    imap_summary = ""
    if imap_results:
        imap_summary = format_imap_results_for_history(imap_results)

    # Construir resumen IMAP Facturas para inyectar en el historial
    imap_facturas_summary = ""
    if imap_facturas_results:
        imap_facturas_summary = format_imap_facturas_results_for_history(imap_facturas_results)

    # Construir resumen FE para inyectar en el historial
    fe_summary = ""
    if fe_results:
        lines = []
        for r in fe_results:
            if r.get("success"):
                import json as _json
                data_str = _json.dumps(r.get("data", {}), ensure_ascii=False, indent=2)
                lines.append(f"  - {r.get('tool')}: OK\n{data_str}")
            else:
                lines.append(f"  - {r.get('tool', '?')}: FALLÓ → {r.get('error', 'desconocido')}")
        fe_summary = "[RESULTADO DE FE]\n" + "\n".join(lines) + "\n[/RESULTADO DE FE]"

    # Construir resumen de cotización para inyectar en el historial
    cotizacion_summary = ""
    if cotizacion_actions:
        lines = []
        for ca in cotizacion_actions:
            if "_parse_error" in ca:
                lines.append(f"  - FALLÓ: {ca['_parse_error']}")
            else:
                lines.append(f"  - Cliente: {ca.get('cliente', '—')} | Total: {ca.get('total', '—')} {ca.get('moneda', 'USD')}")
        cotizacion_summary = "[RESULTADO DE COTIZACION]\n" + "\n".join(lines) + "\n[/RESULTADO DE COTIZACION]"

    # Construir resumen de alertas
    alert_summary = ""
    if alert_results:
        lines = []
        for ar in alert_results:
            tipo = ar["type"]
            wa_ok = ar["result"].get("whatsapp", {})
            em_ok = ar["result"].get("email", {})
            wa_status = "OK" if wa_ok and wa_ok.get("success") else ("FALLÓ" if wa_ok else "N/A")
            em_status = "OK" if em_ok and em_ok.get("success") else ("FALLÓ" if em_ok else "N/A")
            lines.append(f"  - {tipo.upper()} → WA: {wa_status} | Email: {em_status}")
        alert_summary = "[RESULTADO DE ALERTAS]\n" + "\n".join(lines) + "\n[/RESULTADO DE ALERTAS]"

    # Guardar en historial solo si save_history=True (False lo usan reintentos intermedios del meta-agente)
    if req.save_history:
        save_message(req.agent_id, req.session_id, "user", req.message)
        answer_to_save = answer
        if email_summary:
            answer_to_save = f"{answer_to_save}\n\n{email_summary}"
        if imap_summary:
            answer_to_save = f"{answer_to_save}\n\n{imap_summary}"
        if imap_facturas_summary:
            answer_to_save = f"{answer_to_save}\n\n{imap_facturas_summary}"
        if calendar_summary:
            answer_to_save = f"{answer_to_save}\n\n{calendar_summary}"
        if cotizacion_summary:
            answer_to_save = f"{answer_to_save}\n\n{cotizacion_summary}"
        if fe_summary:
            answer_to_save = f"{answer_to_save}\n\n{fe_summary}"
        if alert_summary:
            answer_to_save = f"{answer_to_save}\n\n{alert_summary}"
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

    # Limpiar bloques de acción que hayan escapado al parseo o lleguen malformados
    # Cubre: [FE_ACTION], FE_ACTION (sin corchete), [PDF ACTION], [CHART ACTION], etc.
    answer = re.sub(r'\[?FE_ACTION\]?.*?\[/FE_ACTION\]', '', answer, flags=re.DOTALL)
    answer = re.sub(r'\[[A-Z][A-Z_ ]*ACTION\].*?\[/[A-Z][A-Z_ ]*ACTION\]', '', answer, flags=re.DOTALL)
    answer = re.sub(r'\n{3,}', '\n\n', answer).strip()

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
        "imap_executed": imap_executed,
        "imap_results": imap_results,
        "imap_facturas_executed": imap_facturas_executed,
        "imap_facturas_summary": imap_facturas_summary,
        "cotizacion_count": len([c for c in cotizacion_actions if "_parse_error" not in c]),
        "fe_executed": fe_executed,
        "fe_results": fe_results,
        "alert_results": alert_results,
    }
