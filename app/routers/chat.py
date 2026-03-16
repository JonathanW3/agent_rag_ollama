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
from mcp_sqlite.client import get_mcp_client
from mcp_email.client import get_email_client
from mcp_mysql.client import get_mysql_client

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

    # Guardar mensaje del usuario y respuesta limpia en Redis
    save_message(req.agent_id, req.session_id, "user", req.message)
    # Guardar respuesta del asistente con el resumen de emails anexado
    answer_to_save = answer
    if email_summary:
        answer_to_save = f"{answer}\n\n{email_summary}"
    save_message(req.agent_id, req.session_id, "assistant", answer_to_save)

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
    }
