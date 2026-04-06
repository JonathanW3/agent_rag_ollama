"""
Router del Agente Supervisor.

Evalúa la calidad de los agentes, genera propuestas de mejora de prompts,
gestiona el flujo de aprobación humana para cambios, y ejecuta pruebas
activas simulando conversaciones de usuario contra los agentes.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from ..auth import get_current_org, OrgContext
from ..schemas import FeedbackRequest, PromptProposalRequest, SupervisorTestRequest, SupervisorConfigUpdate, ChatRequest
from ..agents import get_agent, list_agents, update_agent, get_agent_stats
from ..memory import get_history, get_all_sessions, clear_session
from ..ollama_client import ollama_chat
from ..config import settings
from ..redis_client import get_redis_client
from mcp_sqlite.client import get_mcp_client
from .chat import chat as execute_chat

router = APIRouter(prefix="/supervisor", tags=["🔍 Supervisor"])

# ── Configuración del supervisor ──
EVAL_SAMPLE_SIZE = 20  # Conversaciones a evaluar por agente
REDIS_SUPERVISOR_CONFIG_KEY = "supervisor:config"

# System prompts por defecto del supervisor
_DEFAULT_PROMPTS = {
    "prompt_evaluator": """Eres un evaluador experto de agentes de IA. Tu tarea es analizar el rendimiento de un agente basándote en:
1. Su prompt de sistema (instrucciones)
2. Muestras de sus conversaciones reales
3. Feedback de usuarios (thumbs up/down)
4. Métricas de actividad

Debes responder SIEMPRE en formato JSON con esta estructura exacta:
{
    "score": <número del 1 al 10>,
    "summary": "<resumen ejecutivo de 2-3 líneas>",
    "strengths": ["<fortaleza 1>", "<fortaleza 2>"],
    "weaknesses": ["<debilidad 1>", "<debilidad 2>"],
    "recommendations": ["<recomendación 1>", "<recomendación 2>", "<recomendación 3>"],
    "prompt_issues": ["<problema del prompt 1>", "<problema del prompt 2>"],
    "critical_alerts": ["<alerta crítica si hay>"]
}

Criterios de evaluación:
- Adherencia al prompt: ¿sigue sus instrucciones?
- Calidad de respuestas: ¿son precisas, útiles y profesionales?
- Uso de herramientas: ¿genera charts/emails cuando debe?
- Alucinaciones: ¿inventa datos o formatos?
- Feedback del usuario: ¿satisfacción positiva o negativa?

RESPONDE SOLO CON EL JSON, sin explicación adicional.""",

    "prompt_test_generator": """Eres un generador de escenarios de prueba para agentes de IA.
Tu tarea es crear preguntas realistas que un usuario final haría, diseñadas para
evaluar exhaustivamente las capacidades del agente.

REGLAS:
1. Las preguntas deben ser naturales, como las haría un usuario real
2. Cada pregunta debe probar una capacidad específica o combinación de capacidades
3. Incluye preguntas fáciles, medias y difíciles
4. Incluye al menos 1 pregunta que fuerce el uso de cada herramienta habilitada
5. Incluye 1 pregunta edge-case que podría confundir al agente
6. Incluye 1 pregunta multi-paso que requiera combinar varias capacidades
7. Las preguntas deben estar en el mismo idioma que el prompt del agente

Responde SOLO con un JSON array de strings, sin explicación:
["pregunta 1", "pregunta 2", ...]""",

    "prompt_turn_evaluator": """Evalúa este turno de un agente IA. Responde SOLO JSON breve:
{"s":<1-10>,"te":["herramienta esperada"],"tu":["herramienta usada"],"ta":"correcto|parcial|incorrecto|na","i":["issue max 8 palabras"],"h":["highlight max 8 palabras"]}
Máximo 2 issues y 2 highlights.""",

    "prompt_summary_evaluator": """Genera el reporte FINAL de evaluación consolidando los datos parciales.
Responde SOLO JSON:
{"overall_score":<1-10>,"summary":"<resumen 2-3 líneas>","tool_usage_report":{"rag":{"expected":<N>,"actual":<N>,"assessment":"<breve>"},"charts":{"expected":<N>,"actual":<N>,"assessment":"<breve>"},"mysql":{"expected":<N>,"actual":<N>,"assessment":"<breve>"},"email":{"expected":<N>,"actual":<N>,"assessment":"<breve>"}},"strengths":["<max 5>"],"weaknesses":["<max 5>"],"prompt_issues":["<max 3>"],"prompt_improvements":["<max 3>"],"suggested_prompt":"<prompt completo mejorado>","critical_alerts":["<si hay>"]}
IMPORTANTE: "suggested_prompt" = prompt COMPLETO mejorado.""",

    "prompt_engineer": """Eres un experto en prompt engineering para agentes de IA conversacionales.
Tu tarea es mejorar el system prompt de un agente basándote en su evaluación de rendimiento.

REGLAS:
1. Mantén el rol y personalidad del agente
2. Corrige los problemas identificados en la evaluación
3. Refuerza las fortalezas existentes
4. Añade instrucciones específicas para resolver las debilidades
5. NO cambies el formato de acciones especiales ([EMAIL_ACTION], [CHART_ACTION]) si ya existen
6. Mantén el idioma original del prompt

Responde SOLO con el prompt mejorado, sin explicación ni markdown. Solo el texto del prompt.""",
}


def _get_supervisor_config() -> dict:
    """Obtiene la configuración del supervisor desde Redis, o devuelve defaults."""
    r = get_redis_client()
    raw = r.get(REDIS_SUPERVISOR_CONFIG_KEY)
    if raw:
        return json.loads(raw)
    return {"model": None, **{k: None for k in _DEFAULT_PROMPTS}}


def _save_supervisor_config(config: dict):
    """Guarda la configuración del supervisor en Redis."""
    r = get_redis_client()
    r.set(REDIS_SUPERVISOR_CONFIG_KEY, json.dumps(config, ensure_ascii=False))


def _get_supervisor_model() -> str:
    """Retorna el modelo configurado para el supervisor, o el global."""
    config = _get_supervisor_config()
    return config.get("model") or settings.CHAT_MODEL


def _get_supervisor_prompt(prompt_key: str) -> str:
    """Retorna un system prompt del supervisor (personalizado o default)."""
    config = _get_supervisor_config()
    custom = config.get(prompt_key)
    if custom:
        return custom
    return _DEFAULT_PROMPTS.get(prompt_key, "")


# ══════════════════════════════════════════════════════════════
#  CONFIGURACIÓN DEL SUPERVISOR (endpoints)
# ══════════════════════════════════════════════════════════════

@router.get("/config", summary="Ver configuración del supervisor")
async def get_config(org: OrgContext = Depends(get_current_org)):
    """Retorna la configuración actual del supervisor: modelo y system prompts.

    Los campos con valor null usan el valor por defecto del sistema.
    """
    config = _get_supervisor_config()
    return {
        "model": config.get("model"),
        "model_effective": config.get("model") or settings.CHAT_MODEL,
        "prompts": {
            key: {
                "custom": config.get(key),
                "using_default": config.get(key) is None,
                "effective": config.get(key) or _DEFAULT_PROMPTS[key],
            }
            for key in _DEFAULT_PROMPTS
        },
    }


@router.put("/config", summary="Actualizar configuración del supervisor")
async def update_config(req: SupervisorConfigUpdate, org: OrgContext = Depends(get_current_org)):
    """Actualiza modelo y/o system prompts del supervisor.

    Solo se modifican los campos enviados (no-null). Para restaurar un campo
    al valor por defecto, envía una cadena vacía `""`.
    """
    config = _get_supervisor_config()
    updated_fields = []

    if req.model is not None:
        config["model"] = req.model if req.model != "" else None
        updated_fields.append("model")

    for key in _DEFAULT_PROMPTS:
        value = getattr(req, key, None)
        if value is not None:
            config[key] = value if value != "" else None
            updated_fields.append(key)

    if not updated_fields:
        raise HTTPException(status_code=400, detail="No se enviaron campos para actualizar")

    _save_supervisor_config(config)

    return {
        "status": "ok",
        "updated_fields": updated_fields,
        "config": {
            "model": config.get("model"),
            "model_effective": config.get("model") or settings.CHAT_MODEL,
            "prompts_customized": [k for k in _DEFAULT_PROMPTS if config.get(k)],
        },
    }


@router.delete("/config", summary="Restaurar configuración del supervisor a defaults")
async def reset_config(org: OrgContext = Depends(get_current_org)):
    """Elimina toda la configuración personalizada y restaura los valores por defecto."""
    r = get_redis_client()
    r.delete(REDIS_SUPERVISOR_CONFIG_KEY)
    return {
        "status": "ok",
        "message": "Configuración del supervisor restaurada a valores por defecto",
        "model_effective": settings.CHAT_MODEL,
    }


def _repair_json(text: str) -> str:
    """Intenta reparar errores comunes de JSON generado por LLMs."""
    # Trailing commas antes de } o ]
    text = re.sub(r',\s*([}\]])', r'\1', text)
    # Comillas simples → dobles (solo en claves/valores, no dentro de texto)
    # Esto es heurístico: reemplaza 'clave': 'valor' → "clave": "valor"
    text = re.sub(r"(?<=[\[{,:\s])'([^']*?)'(?=\s*[,:\]}])", r'"\1"', text)
    # Saltos de línea dentro de strings (no escapados)
    text = re.sub(r'(?<=": ")(.*?)(?="[,}\]])', lambda m: m.group(0).replace('\n', '\\n'), text, flags=re.DOTALL)
    # Eliminar caracteres de control (excepto \n \r \t dentro de strings)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    return text


def _extract_json_block(raw: str) -> str | None:
    """Extrae el primer bloque JSON ({...} o [...]) de un texto con regex."""
    # Buscar bloque que empiece con { y termine con } (greedy para capturar todo)
    match = re.search(r'(\{[\s\S]*\})', raw)
    if match:
        return match.group(1)
    # Intentar con array
    match = re.search(r'(\[[\s\S]*\])', raw)
    if match:
        return match.group(1)
    return None


def _parse_llm_json(raw: str) -> dict | list:
    """Parsea JSON de una respuesta LLM con múltiples estrategias de recuperación.

    Estrategias (en orden):
    1. Limpiar markdown fences y parsear directo
    2. Extraer bloque JSON con regex y parsear
    3. Reparar errores comunes (trailing commas, comillas simples) y parsear
    4. Combinar extracción + reparación

    Raises ValueError si ninguna estrategia funciona.
    """
    if not raw or not raw.strip():
        raise ValueError("El modelo devolvió una respuesta vacía")

    # ── Estrategia 1: Limpiar markdown y parsear directo ──
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    if not cleaned:
        raise ValueError(f"Respuesta vacía tras limpiar markdown. Original: {raw[:200]}")

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # ── Estrategia 2: Extraer bloque JSON con regex ──
    extracted = _extract_json_block(cleaned)
    if extracted:
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            pass

    # ── Estrategia 3: Reparar JSON común y parsear ──
    repaired = _repair_json(cleaned)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # ── Estrategia 4: Extraer + reparar combinado ──
    if extracted:
        repaired_extracted = _repair_json(extracted)
        try:
            return json.loads(repaired_extracted)
        except json.JSONDecodeError:
            pass

    # Ninguna estrategia funcionó
    raise ValueError(
        f"No se pudo parsear JSON del LLM tras 4 intentos de recuperación. "
        f"Fragmento de respuesta: {cleaned[:300]}"
    )


def _llm_json_call(messages: list[dict], temperature: float, model: str,
                    max_retries: int = 2, num_predict: int = None,
                    timeout: int = None) -> dict | list:
    """Llama al LLM y parsea la respuesta como JSON, con reintentos automáticos.

    Usa format_json=True (Ollama format:"json") para forzar JSON válido a nivel
    de sampling, combinado con parsing robusto como fallback.

    Args:
        num_predict: Máximo de tokens de salida. Usar valores altos (4096+)
                     para evaluaciones que generan JSONs extensos.
        timeout: Timeout en segundos para cada llamada a Ollama.
    """
    last_error = None

    for attempt in range(max_retries):
        raw = ollama_chat(messages, temperature=temperature, model=model,
                          num_predict=num_predict, timeout=timeout,
                          format_json=True)

        try:
            return _parse_llm_json(raw)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            # En el reintento, agregar instrucción de corrección
            if attempt < max_retries - 1:
                messages = messages + [{
                    "role": "user",
                    "content": (
                        "Tu respuesta anterior no fue JSON válido. "
                        f"Error: {str(e)[:200]}. "
                        "Responde ÚNICAMENTE con el JSON, sin texto adicional, "
                        "sin bloques markdown. Solo el JSON puro."
                    )
                }, {
                    "role": "assistant",
                    "content": raw[:500] if raw else "(vacío)"
                }]

    raise ValueError(
        f"El LLM no generó JSON válido tras {max_retries} intentos. "
        f"Último error: {str(last_error)}"
    )


# ══════════════════════════════════════════════════════════════
#  FEEDBACK
# ══════════════════════════════════════════════════════════════

@router.post("/feedback", summary="Enviar feedback de un mensaje")
async def submit_feedback(req: FeedbackRequest, org: OrgContext = Depends(get_current_org)):
    """Registra feedback thumbs up/down para un mensaje específico del asistente."""
    if req.score not in (-1, 1):
        raise HTTPException(status_code=422, detail="Score debe ser 1 (👍 positivo) o -1 (👎 negativo). Campos requeridos: agent_id, session_id, message_index, score")

    # Verificar que el agente existe
    agent = get_agent(req.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agente '{req.agent_id}' no encontrado")

    # Obtener el historial para extraer el mensaje
    history = get_history(req.agent_id, req.session_id)
    if req.message_index >= len(history):
        raise HTTPException(status_code=400, detail=f"message_index {req.message_index} fuera de rango (historial tiene {len(history)} mensajes)")

    target_msg = history[req.message_index]
    if target_msg.get("role") != "assistant":
        raise HTTPException(status_code=400, detail="Solo se puede dar feedback a mensajes del asistente")

    # Obtener mensaje del usuario (el anterior)
    user_msg = ""
    if req.message_index > 0:
        prev = history[req.message_index - 1]
        if prev.get("role") == "user":
            user_msg = prev.get("content", "")

    # Guardar en SQLite del agente
    mcp_client = get_mcp_client()
    await mcp_client.init_agent_db(req.agent_id)

    result = await mcp_client.execute_write(
        db_name=f"agent_{req.agent_id}",
        query="""
            INSERT OR REPLACE INTO message_feedback
            (session_id, message_index, score, user_message, assistant_message)
            VALUES (?, ?, ?, ?, ?)
        """,
        params=[req.session_id, req.message_index, req.score,
                user_msg[:500], target_msg.get("content", "")[:1000]]
    )

    # Registrar métrica
    await mcp_client.add_metric(
        agent_id=req.agent_id,
        metric_name="feedback_score",
        metric_value=float(req.score),
        metadata={"session_id": req.session_id, "message_index": req.message_index}
    )

    return {
        "status": "ok",
        "agent_id": req.agent_id,
        "session_id": req.session_id,
        "message_index": req.message_index,
        "score": req.score
    }


# ══════════════════════════════════════════════════════════════
#  EVALUACIÓN
# ══════════════════════════════════════════════════════════════

def _build_evaluation_prompt(agent: dict, conversations: list[dict], feedback_stats: dict, log_stats: dict) -> list[dict]:
    """Construye el prompt para que el LLM evalúe un agente."""
    system = _get_supervisor_prompt("prompt_evaluator")

    # Construir contexto de evaluación
    context_parts = []

    # Info del agente
    context_parts.append(f"## Agente: {agent['name']} (ID: {agent['id']})")
    context_parts.append(f"**Descripción:** {agent.get('description', 'Sin descripción')}")
    context_parts.append(f"**Modelo:** {agent.get('llm_model') or settings.CHAT_MODEL}")
    context_parts.append(f"**Capacidades:** RAG={'sí' if agent.get('use_rag') else 'no'}, "
                        f"MySQL={'sí' if agent.get('use_mysql') else 'no'}, "
                        f"Email={'sí' if agent.get('use_email') else 'no'}, "
                        f"Charts={'sí' if agent.get('use_charts') else 'no'}")
    context_parts.append(f"\n## Prompt del sistema\n```\n{agent['prompt'][:3000]}\n```")

    # Feedback
    context_parts.append(f"\n## Feedback de usuarios")
    context_parts.append(f"- Positivos (👍): {feedback_stats.get('positive', 0)}")
    context_parts.append(f"- Negativos (👎): {feedback_stats.get('negative', 0)}")
    if feedback_stats.get('negative_samples'):
        context_parts.append("**Mensajes con feedback negativo:**")
        for sample in feedback_stats['negative_samples'][:5]:
            context_parts.append(f"  - Pregunta: {sample.get('user_message', 'N/A')[:200]}")
            context_parts.append(f"    Respuesta: {sample.get('assistant_message', 'N/A')[:200]}")

    # Logs
    context_parts.append(f"\n## Actividad")
    context_parts.append(f"- Total interacciones: {log_stats.get('total_logs', 0)}")
    context_parts.append(f"- Sesiones activas: {log_stats.get('active_sessions', 0)}")

    # Conversaciones de muestra
    context_parts.append(f"\n## Conversaciones recientes ({len(conversations)} muestras)")
    for i, conv in enumerate(conversations[:10]):
        context_parts.append(f"\n### Conversación {i+1}")
        for msg in conv[:6]:  # Max 6 mensajes por conversación
            role = "👤 Usuario" if msg['role'] == 'user' else "🤖 Agente"
            content = msg.get('content', '')[:300]
            context_parts.append(f"**{role}:** {content}")

    user_content = "\n".join(context_parts)

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content}
    ]


async def _get_feedback_stats(agent_id: str) -> dict:
    """Obtiene estadísticas de feedback de un agente."""
    mcp_client = get_mcp_client()
    await mcp_client.init_agent_db(agent_id)

    positive = await mcp_client.query_for_agent(
        agent_id=agent_id,
        query="SELECT COUNT(*) as total FROM message_feedback WHERE score = 1"
    )
    negative = await mcp_client.query_for_agent(
        agent_id=agent_id,
        query="SELECT COUNT(*) as total FROM message_feedback WHERE score = -1"
    )
    negative_samples = await mcp_client.query_for_agent(
        agent_id=agent_id,
        query="SELECT user_message, assistant_message FROM message_feedback WHERE score = -1 ORDER BY timestamp DESC LIMIT 5"
    )

    return {
        "positive": positive.get("rows", [{}])[0].get("total", 0) if positive.get("success") else 0,
        "negative": negative.get("rows", [{}])[0].get("total", 0) if negative.get("success") else 0,
        "negative_samples": negative_samples.get("rows", []) if negative_samples.get("success") else []
    }


async def _get_agent_conversations(agent_id: str, max_sessions: int = 10) -> list[list[dict]]:
    """Obtiene conversaciones recientes de un agente desde Redis."""
    sessions = get_all_sessions(agent_id=agent_id)
    conversations = []

    for session_info in sessions[:max_sessions]:
        history = get_history(agent_id, session_info["session_id"])
        if history:
            conversations.append(history)

    return conversations


@router.post("/evaluate/{agent_id}", summary="Evaluar calidad de un agente")
async def evaluate_agent(agent_id: str, org: OrgContext = Depends(get_current_org)):
    """Evalúa la calidad de un agente analizando sus conversaciones, feedback y métricas."""
    agent = get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no encontrado")

    # Recopilar datos
    feedback_stats = await _get_feedback_stats(agent_id)
    conversations = await _get_agent_conversations(agent_id)
    agent_stats = get_agent_stats(agent_id)

    mcp_client = get_mcp_client()
    await mcp_client.init_agent_db(agent_id)
    logs_count = await mcp_client.query_for_agent(
        agent_id=agent_id,
        query="SELECT COUNT(*) as total FROM agent_logs"
    )
    log_stats = {
        "total_logs": logs_count.get("rows", [{}])[0].get("total", 0) if logs_count.get("success") else 0,
        "active_sessions": agent_stats.get("active_sessions", 0)
    }

    if not conversations:
        return {
            "agent_id": agent_id,
            "agent_name": agent["name"],
            "status": "insufficient_data",
            "message": "No hay conversaciones disponibles para evaluar. Necesita al menos 1 sesión activa.",
            "feedback_stats": feedback_stats,
            "log_stats": log_stats
        }

    # Evaluar con LLM
    messages = _build_evaluation_prompt(agent, conversations, feedback_stats, log_stats)
    model = _get_supervisor_model()

    try:
        evaluation = _llm_json_call(messages, temperature=0.2, model=model)
    except (ValueError, Exception) as e:
        evaluation = {
            "score": 0,
            "summary": f"Error al parsear evaluación del LLM: {str(e)}",
            "strengths": [],
            "weaknesses": [],
            "recommendations": [],
            "prompt_issues": [],
            "critical_alerts": ["Error en evaluación automática"]
        }

    # Guardar evaluación como métrica
    await mcp_client.add_metric(
        agent_id=agent_id,
        metric_name="evaluation_score",
        metric_value=float(evaluation.get("score", 0)),
        metadata={"summary": evaluation.get("summary", "")}
    )

    return {
        "agent_id": agent_id,
        "agent_name": agent["name"],
        "evaluation": evaluation,
        "feedback_stats": feedback_stats,
        "conversations_analyzed": len(conversations),
        "log_stats": log_stats
    }


# ══════════════════════════════════════════════════════════════
#  REPORTE EJECUTIVO
# ══════════════════════════════════════════════════════════════

@router.get("/report", summary="Reporte ejecutivo de todos los agentes")
async def supervisor_report(org: OrgContext = Depends(get_current_org)):
    """Genera un resumen ejecutivo del estado de todos los agentes."""
    agents = list_agents()
    mcp_client = get_mcp_client()

    report = []
    for agent in agents:
        aid = agent["id"]
        stats = get_agent_stats(aid)
        feedback = await _get_feedback_stats(aid)

        # Última evaluación
        await mcp_client.init_agent_db(aid)
        last_eval = await mcp_client.query_for_agent(
            agent_id=aid,
            query="SELECT metric_value, metadata, timestamp FROM agent_metrics WHERE metric_name = 'evaluation_score' ORDER BY timestamp DESC LIMIT 1"
        )
        last_score = None
        last_eval_date = None
        if last_eval.get("success") and last_eval.get("rows"):
            row = last_eval["rows"][0]
            last_score = row.get("metric_value")
            last_eval_date = row.get("timestamp")

        # Total de interacciones
        total_logs = await mcp_client.query_for_agent(
            agent_id=aid,
            query="SELECT COUNT(*) as total FROM agent_logs"
        )

        report.append({
            "agent_id": aid,
            "agent_name": agent["name"],
            "description": agent.get("description", ""),
            "model": agent.get("llm_model") or settings.CHAT_MODEL,
            "capabilities": {
                "rag": agent.get("use_rag", False),
                "mysql": agent.get("use_mysql", False),
                "email": agent.get("use_email", False),
                "charts": agent.get("use_charts", False)
            },
            "activity": {
                "active_sessions": stats.get("active_sessions", 0),
                "total_messages": stats.get("total_messages", 0),
                "total_interactions": total_logs.get("rows", [{}])[0].get("total", 0) if total_logs.get("success") else 0
            },
            "feedback": {
                "positive": feedback.get("positive", 0),
                "negative": feedback.get("negative", 0),
                "satisfaction_rate": round(feedback["positive"] / max(feedback["positive"] + feedback["negative"], 1) * 100, 1)
            },
            "last_evaluation": {
                "score": last_score,
                "date": last_eval_date
            }
        })

    # Ordenar por score (los sin evaluación al final)
    report.sort(key=lambda x: x["last_evaluation"]["score"] or 0, reverse=True)

    return {
        "total_agents": len(report),
        "report_date": datetime.now(timezone.utc).isoformat(),
        "agents": report
    }


# ══════════════════════════════════════════════════════════════
#  PROPUESTAS DE PROMPT
# ══════════════════════════════════════════════════════════════

def _build_prompt_suggestion(agent: dict, evaluation: dict) -> list[dict]:
    """Construye el prompt para generar una mejora del system prompt del agente."""
    system = _get_supervisor_prompt("prompt_engineer")

    user_content = f"""## Prompt actual del agente "{agent['name']}"
```
{agent['prompt']}
```

## Evaluación del agente
- Score: {evaluation.get('score', 'N/A')}/10
- Resumen: {evaluation.get('summary', 'N/A')}
- Debilidades: {json.dumps(evaluation.get('weaknesses', []), ensure_ascii=False)}
- Problemas del prompt: {json.dumps(evaluation.get('prompt_issues', []), ensure_ascii=False)}
- Recomendaciones: {json.dumps(evaluation.get('recommendations', []), ensure_ascii=False)}

Genera un prompt mejorado que solucione estos problemas manteniendo la esencia del agente."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content}
    ]


@router.post("/suggest-prompt/{agent_id}", summary="Generar propuesta de prompt mejorado")
async def suggest_prompt(agent_id: str, org: OrgContext = Depends(get_current_org)):
    """Evalúa un agente y genera una propuesta de prompt mejorado para aprobación humana."""
    agent = get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no encontrado")

    # Primero evaluar
    feedback_stats = await _get_feedback_stats(agent_id)
    conversations = await _get_agent_conversations(agent_id)
    agent_stats = get_agent_stats(agent_id)

    mcp_client = get_mcp_client()
    await mcp_client.init_agent_db(agent_id)

    log_stats = {"total_logs": 0, "active_sessions": agent_stats.get("active_sessions", 0)}
    logs_count = await mcp_client.query_for_agent(
        agent_id=agent_id,
        query="SELECT COUNT(*) as total FROM agent_logs"
    )
    if logs_count.get("success"):
        log_stats["total_logs"] = logs_count.get("rows", [{}])[0].get("total", 0)

    # Evaluar
    eval_messages = _build_evaluation_prompt(agent, conversations, feedback_stats, log_stats)
    model = _get_supervisor_model()

    try:
        evaluation = _llm_json_call(eval_messages, temperature=0.2, model=model)
    except Exception:
        evaluation = {
            "score": 5,
            "summary": "Evaluación parcial",
            "weaknesses": [],
            "prompt_issues": [],
            "recommendations": []
        }

    # Generar prompt mejorado
    suggest_messages = _build_prompt_suggestion(agent, evaluation)
    suggested_prompt = ollama_chat(suggest_messages, temperature=0.3, model=model) or ""

    # Guardar propuesta en Redis (pendiente de aprobación)
    client = get_redis_client()
    proposal_id = f"proposal--{agent_id}--{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    proposal = {
        "id": proposal_id,
        "agent_id": agent_id,
        "agent_name": agent["name"],
        "current_prompt": agent["prompt"],
        "suggested_prompt": suggested_prompt.strip(),
        "evaluation": evaluation,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    client.set(proposal_id, json.dumps(proposal))
    # Propuestas expiran en 7 días
    client.expire(proposal_id, 604800)

    return {
        "proposal_id": proposal_id,
        "agent_id": agent_id,
        "agent_name": agent["name"],
        "status": "pending",
        "evaluation": evaluation,
        "current_prompt": agent["prompt"][:500] + ("..." if len(agent["prompt"]) > 500 else ""),
        "suggested_prompt": suggested_prompt.strip(),
        "message": "Propuesta generada. Usa POST /supervisor/approve/{proposal_id} para aplicar o POST /supervisor/reject/{proposal_id} para rechazar."
    }


@router.get("/proposals", summary="Listar propuestas pendientes")
async def list_proposals(org: OrgContext = Depends(get_current_org)):
    """Lista todas las propuestas de prompt pendientes de aprobación."""
    client = get_redis_client()
    proposals = []

    # Buscar propuestas con formato nuevo (--) y legacy (:)
    for pattern in ["proposal--*", "proposal:*"]:
        for key in client.scan_iter(pattern):
            data = client.get(key)
            if data:
                proposal = json.loads(data)
                proposals.append({
                    "proposal_id": proposal["id"],
                    "agent_id": proposal["agent_id"],
                    "agent_name": proposal["agent_name"],
                    "status": proposal["status"],
                    "score": proposal.get("evaluation", {}).get("score"),
                    "created_at": proposal["created_at"]
                })

    proposals.sort(key=lambda x: x["created_at"], reverse=True)
    return {"proposals": proposals, "count": len(proposals)}


# ══════════════════════════════════════════════════════════════
#  APROBACIÓN / RECHAZO
# ══════════════════════════════════════════════════════════════

@router.post("/approve/{proposal_id:path}", summary="Aprobar propuesta de prompt")
async def approve_proposal(proposal_id: str, req: PromptProposalRequest = None, org: OrgContext = Depends(get_current_org)):
    """Aprueba una propuesta y aplica el nuevo prompt al agente."""
    client = get_redis_client()
    data = client.get(proposal_id)

    # Fallback: intentar formato legacy con ':'
    if data is None and "--" in proposal_id:
        legacy_id = proposal_id.replace("--", ":", 2)
        data = client.get(legacy_id)
        if data is not None:
            proposal_id = legacy_id

    if data is None:
        raise HTTPException(status_code=404, detail=f"Propuesta '{proposal_id}' no encontrada o expirada")

    proposal = json.loads(data)
    if proposal["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Propuesta ya fue procesada (status: {proposal['status']})")

    agent_id = proposal["agent_id"]
    agent = get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' ya no existe")

    # Guardar versión anterior en SQLite
    mcp_client = get_mcp_client()
    await mcp_client.init_agent_db(agent_id)

    # Obtener última versión
    last_version = await mcp_client.query_for_agent(
        agent_id=agent_id,
        query="SELECT COALESCE(MAX(version), 0) as max_ver FROM prompt_versions"
    )
    current_version = last_version.get("rows", [{}])[0].get("max_ver", 0) if last_version.get("success") else 0

    # Marcar versión anterior como reemplazada
    if current_version > 0:
        await mcp_client.execute_write(
            db_name=f"agent_{agent_id}",
            query="UPDATE prompt_versions SET status = 'replaced' WHERE status = 'active'"
        )

    # Guardar nueva versión
    new_version = current_version + 1
    await mcp_client.execute_write(
        db_name=f"agent_{agent_id}",
        query="""
            INSERT INTO prompt_versions (prompt, version, change_reason, approved_by, status)
            VALUES (?, ?, ?, ?, 'active')
        """,
        params=[proposal["current_prompt"], new_version,
                req.reason if req else "Aprobado por supervisor",
                "human"]
    )

    # Aplicar nuevo prompt
    update_agent(agent_id=agent_id, prompt=proposal["suggested_prompt"])

    # Actualizar propuesta
    proposal["status"] = "approved"
    proposal["approved_at"] = datetime.now(timezone.utc).isoformat()
    proposal["reason"] = req.reason if req else ""
    client.set(proposal_id, json.dumps(proposal))

    # Log
    await mcp_client.log_agent_action(
        agent_id=agent_id,
        action="prompt_updated_by_supervisor",
        details={
            "proposal_id": proposal_id,
            "version": new_version,
            "reason": req.reason if req else ""
        }
    )

    return {
        "status": "approved",
        "agent_id": agent_id,
        "agent_name": proposal["agent_name"],
        "version": new_version,
        "message": f"Prompt actualizado. Versión anterior guardada (v{new_version}). Usa POST /supervisor/rollback/{agent_id} para revertir."
    }


@router.post("/reject/{proposal_id:path}", summary="Rechazar propuesta de prompt")
async def reject_proposal(proposal_id: str, req: PromptProposalRequest = None, org: OrgContext = Depends(get_current_org)):
    """Rechaza una propuesta de prompt sin aplicar cambios."""
    client = get_redis_client()
    data = client.get(proposal_id)

    # Fallback: intentar formato legacy con ':'
    if data is None and "--" in proposal_id:
        legacy_id = proposal_id.replace("--", ":", 2)
        data = client.get(legacy_id)
        if data is not None:
            proposal_id = legacy_id

    if data is None:
        raise HTTPException(status_code=404, detail=f"Propuesta '{proposal_id}' no encontrada o expirada")

    proposal = json.loads(data)
    if proposal["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Propuesta ya fue procesada (status: {proposal['status']})")

    proposal["status"] = "rejected"
    proposal["rejected_at"] = datetime.now(timezone.utc).isoformat()
    proposal["reason"] = req.reason if req else ""
    client.set(proposal_id, json.dumps(proposal))

    return {
        "status": "rejected",
        "proposal_id": proposal_id,
        "agent_id": proposal["agent_id"],
        "message": "Propuesta rechazada. No se aplicaron cambios."
    }


# ══════════════════════════════════════════════════════════════
#  PRUEBA ACTIVA (SIMULADOR DE USUARIO)
# ══════════════════════════════════════════════════════════════

def _build_test_questions_prompt(agent: dict) -> list[dict]:
    """Construye el prompt para que el LLM genere preguntas de prueba adaptadas al agente."""
    capabilities = []
    if agent.get("use_rag"):
        capabilities.append("RAG (búsqueda semántica en documentos)")
    if agent.get("use_mysql"):
        capabilities.append("MySQL (base de datos de farmacia: medicamentos, stock, ventas, sucursales)")
    if agent.get("use_email") or agent.get("smtp_config"):
        capabilities.append("Email (envío de correos electrónicos)")
    if agent.get("use_charts"):
        capabilities.append("Charts (generación de gráficos Plotly interactivos)")
    if agent.get("sqlite_db_path"):
        capabilities.append(f"SQLite personalizado ({agent['sqlite_db_path']})")

    caps_text = "\n".join(f"  - {c}" for c in capabilities) if capabilities else "  - Ninguna herramienta especial (solo conversación)"

    system = _get_supervisor_prompt("prompt_test_generator")

    user_content = f"""Genera preguntas de prueba para este agente:

**Nombre:** {agent['name']}
**Descripción:** {agent.get('description', 'Sin descripción')}
**Prompt del sistema:**
```
{agent['prompt'][:2000]}
```

**Herramientas habilitadas:**
{caps_text}

**Modelo:** {agent.get('llm_model') or settings.CHAT_MODEL}

Genera las preguntas de prueba."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content}
    ]


async def _execute_test_conversation(agent_id: str, questions: list[str], temperature: float) -> list[dict]:
    """Ejecuta las preguntas contra el agente usando la lógica real de chat.

    Simula un usuario real: usa una única sesión continua para toda la prueba,
    de modo que el agente recuerda el contexto de turnos anteriores.

    - use_sql=False (no necesario para evaluación, ahorra queries SQLite)
    - use_email=False (no enviar emails reales)
    - Los charts se mantienen habilitados si el agente los tiene, para evaluar su uso

    Retorna los resultados completos de cada interacción.
    """
    session_id = f"supervisor-test-{uuid.uuid4().hex[:8]}"
    results = []

    agent = get_agent(agent_id)

    try:
        for i, question in enumerate(questions):
            try:
                chat_req = ChatRequest(
                    message=question,
                    agent_id=agent_id,
                    session_id=session_id,
                    temperature=temperature,
                    use_rag=agent.get("use_rag", True) if agent.get("use_rag") else False,
                    use_sql=False,  # No necesario para evaluación
                    use_mysql=agent.get("use_mysql", False),
                    use_email=False,
                    use_charts=agent.get("use_charts", False),
                )

                response = await execute_chat(chat_req)

                results.append({
                    "turn": i + 1,
                    "question": question,
                    "answer": response.get("answer", ""),
                    "sources_count": len(response.get("sources", [])),
                    "sources": [s.get("text", "")[:200] for s in response.get("sources", [])[:3]],
                    "charts_count": response.get("charts_count", 0),
                    "charts_types": [
                        trace.get("type", "unknown")
                        for chart in response.get("charts", [])
                        for trace in chart.get("data", [])
                    ],
                    "email_sent": response.get("email_sent", False),
                    "email_results": response.get("email_results", []),
                    "sql_used": response.get("sql_used", False),
                    "model": response.get("llm_model", ""),
                    "history_length": response.get("history_length", 0),
                    "success": True
                })
            except Exception as e:
                results.append({
                    "turn": i + 1,
                    "question": question,
                    "answer": "",
                    "error": str(e),
                    "success": False
                })
    finally:
        # Limpiar la sesión completa al terminar la prueba
        try:
            clear_session(agent_id, session_id)
        except Exception:
            pass

    return results


def _get_agent_capabilities(agent: dict) -> list[str]:
    """Extrae las capacidades habilitadas de un agente."""
    capabilities = []
    if agent.get("use_rag"):
        capabilities.append("RAG")
    if agent.get("use_mysql"):
        capabilities.append("MySQL")
    if agent.get("use_email") or agent.get("smtp_config"):
        capabilities.append("Email")
    if agent.get("use_charts"):
        capabilities.append("Charts/Plotly")
    return capabilities


def _format_turn_context(r: dict, max_answer_len: int = 500) -> str:
    """Formatea un turno de prueba como texto para el prompt de evaluación."""
    parts = []
    parts.append(f"### Turno {r['turn']}")
    parts.append(f"**Pregunta:** {r['question']}")
    if r.get("success"):
        parts.append(f"**Respuesta:** {r['answer'][:max_answer_len]}")
        parts.append(f"**RAG fuentes:** {r.get('sources_count', 0)} | **Gráficos:** {r.get('charts_count', 0)} | **SQL:** {'sí' if r.get('sql_used') else 'no'} | **Email:** {'sí' if r.get('email_sent') else 'no'}")
    else:
        parts.append(f"**ERROR:** {r.get('error', 'Error desconocido')}")
    return "\n".join(parts)



def _build_single_turn_evaluation_prompt(agent: dict, turn_result: dict) -> list[dict]:
    """Construye el prompt de evaluación para UN solo turno.

    Genera un JSON mínimo (~100 tokens) que es prácticamente imposible de truncar.
    """
    capabilities = _get_agent_capabilities(agent)

    system = _get_supervisor_prompt("prompt_turn_evaluator")

    context = f"Agente: {agent['name']} | Tools: {','.join(capabilities) or 'ninguna'}\n"
    context += f"Prompt (resumen): {agent['prompt'][:300]}\n\n"
    context += _format_turn_context(turn_result, max_answer_len=400)

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": context}
    ]


def _build_summary_evaluation_prompt(agent: dict, batch_evaluations: list[dict], test_results: list[dict]) -> list[dict]:
    """Construye el prompt final que sintetiza las evaluaciones por lote en un reporte global."""
    capabilities = _get_agent_capabilities(agent)

    # Recopilar todos los per_turn_analysis y fortalezas/debilidades
    all_turns = []
    all_strengths = []
    all_weaknesses = []
    for batch_eval in batch_evaluations:
        # Soportar formato compacto (t/s/te/tu/ta/i/h) y formato expandido
        for t in batch_eval.get("per_turn_analysis", batch_eval.get("turns", [])):
            all_turns.append({
                "turn": t.get("turn", t.get("t")),
                "score": t.get("score", t.get("s")),
                "tools_assessment": t.get("tools_assessment", t.get("ta")),
                "tools_expected": t.get("tools_expected", t.get("te", [])),
                "tools_used": t.get("tools_used", t.get("tu", [])),
                "issues": t.get("issues", t.get("i", [])),
                "highlights": t.get("highlights", t.get("h", [])),
            })
        all_strengths.extend(batch_eval.get("batch_strengths", batch_eval.get("str", [])))
        all_weaknesses.extend(batch_eval.get("batch_weaknesses", batch_eval.get("wk", [])))

    # Calcular estadísticas de herramientas desde test_results
    successful = [r for r in test_results if r.get("success")]
    tool_stats = {
        "rag": sum(1 for r in successful if r.get("sources_count", 0) > 0),
        "charts": sum(r.get("charts_count", 0) for r in successful),
        "sql": sum(1 for r in successful if r.get("sql_used")),
        "email": sum(1 for r in successful if r.get("email_sent")),
    }

    system = _get_supervisor_prompt("prompt_summary_evaluator")

    # Construir datos compactos
    scores = [{"t": t["turn"], "s": t["score"], "ta": t["tools_assessment"]} for t in all_turns]
    issues = list(set(i for t in all_turns for i in t.get("issues", [])))[:10]
    highlights = list(set(h for t in all_turns for h in t.get("highlights", [])))[:10]

    user_content = f"""Agente: {agent['name']} | Tools: {','.join(capabilities) or 'ninguna'}
Prompt actual:
{agent['prompt'][:1500]}

Stats ({len(test_results)} turnos): RAG={tool_stats['rag']}, Charts={tool_stats['charts']}, SQL={tool_stats['sql']}, Email={tool_stats['email']}
Scores: {json.dumps(scores)}
Fortalezas: {json.dumps(list(set(all_strengths))[:8])}
Debilidades: {json.dumps(list(set(all_weaknesses))[:8])}
Issues: {json.dumps(issues)}
Highlights: {json.dumps(highlights)}"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content}
    ]



def _evaluate_per_turn(agent: dict, test_results: list[dict], model: str) -> dict:
    """Evalúa cada turno individualmente (1 llamada LLM por turno) y sintetiza al final.

    Cada llamada genera ~100 tokens de JSON, prácticamente imposible de truncar.
    Combinado con format:"json" de Ollama, garantiza JSON válido en cada llamada.

    Estrategia:
    1. Evaluar cada turno por separado (JSON mínimo, num_predict=512)
    2. Sintetizar un reporte final con los resultados (num_predict=4096)
    """
    # Paso 1: Evaluar cada turno individualmente
    turn_evaluations = []
    for r in test_results:
        turn_messages = _build_single_turn_evaluation_prompt(agent, r)
        try:
            turn_eval = _llm_json_call(
                turn_messages, temperature=0.2, model=model,
                num_predict=512, timeout=60
            )
            # Normalizar formato compacto
            turn_evaluations.append({
                "turn": r["turn"],
                "score": turn_eval.get("score", turn_eval.get("s", 5)),
                "tools_expected": turn_eval.get("tools_expected", turn_eval.get("te", [])),
                "tools_used": turn_eval.get("tools_used", turn_eval.get("tu", [])),
                "tools_assessment": turn_eval.get("tools_assessment", turn_eval.get("ta", "no_aplica")),
                "issues": turn_eval.get("issues", turn_eval.get("i", [])),
                "highlights": turn_eval.get("highlights", turn_eval.get("h", [])),
            })
        except (ValueError, Exception):
            turn_evaluations.append({
                "turn": r["turn"],
                "score": 5,
                "tools_expected": [],
                "tools_used": [],
                "tools_assessment": "no_evaluado",
                "issues": ["Error al evaluar turno"],
                "highlights": [],
            })

    # Paso 2: Sintetizar reporte final
    # Preparar datos compactos de los turnos para el prompt de síntesis
    batch_evaluations = [{
        "turns": [{"t": t["turn"], "s": t["score"], "te": t["tools_expected"],
                    "tu": t["tools_used"], "ta": t["tools_assessment"],
                    "i": t["issues"], "h": t["highlights"]} for t in turn_evaluations],
        "str": list(set(h for t in turn_evaluations for h in t.get("highlights", [])))[:5],
        "wk": list(set(i for t in turn_evaluations for i in t.get("issues", [])))[:5],
    }]

    summary_messages = _build_summary_evaluation_prompt(agent, batch_evaluations, test_results)
    try:
        final_eval = _llm_json_call(
            summary_messages, temperature=0.2, model=model,
            num_predict=4096, timeout=120
        )
    except (ValueError, Exception) as e:
        all_scores = [t.get("score", 5) for t in turn_evaluations]
        avg_score = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0

        final_eval = {
            "overall_score": avg_score,
            "summary": f"Evaluación por turno completada ({len(turn_evaluations)} turnos). Error en síntesis final: {str(e)[:200]}",
            "tool_usage_report": {},
            "strengths": list(set(h for t in turn_evaluations for h in t.get("highlights", [])))[:5],
            "weaknesses": list(set(i for t in turn_evaluations for i in t.get("issues", [])))[:5],
            "prompt_issues": [],
            "prompt_improvements": [],
            "suggested_prompt": "",
            "critical_alerts": ["Error en síntesis final de evaluación"]
        }

    # Adjuntar per_turn_analysis al resultado final
    final_eval["per_turn_analysis"] = turn_evaluations

    return final_eval


@router.post("/test/{agent_id}", summary="Prueba activa: simular usuario y evaluar agente")
async def test_agent(agent_id: str, req: SupervisorTestRequest = None, org: OrgContext = Depends(get_current_org)):
    """Ejecuta una prueba activa contra un agente simulando ser un usuario final.

    El supervisor:
    1. Analiza el prompt y capacidades del agente
    2. Genera preguntas de prueba que cubren cada herramienta habilitada
    3. Ejecuta las preguntas contra el agente (chat real con sesión aislada)
    4. Recopila respuestas, gráficos, fuentes RAG, uso de SQL
    5. Evalúa todo en conjunto: adherencia al prompt, uso correcto de herramientas, calidad
    6. Retorna evaluación detallada con prompt mejorado propuesto
    """
    if req is None:
        req = SupervisorTestRequest()

    agent = get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no encontrado")

    model = _get_supervisor_model()

    # ── Paso 1: Generar preguntas de prueba ──
    questions = []

    # Generar preguntas automáticas con LLM
    gen_messages = _build_test_questions_prompt(agent)
    try:
        generated = _llm_json_call(gen_messages, temperature=0.5, model=model,
                                       num_predict=1024, timeout=60)
        # format:"json" puede devolver un objeto {"questions":[...]} o un array directo
        if isinstance(generated, list):
            questions.extend(generated[:req.num_turns])
        elif isinstance(generated, dict):
            # Buscar el primer valor que sea una lista de strings
            for val in generated.values():
                if isinstance(val, list) and val and isinstance(val[0], str):
                    questions.extend(val[:req.num_turns])
                    break
    except (ValueError, Exception) as e:
        pass  # Se maneja abajo con el fallback

    # Fallback: si no se generaron preguntas, usar genéricas basadas en capacidades
    if not questions:
        questions.append("Hola, ¿qué puedes hacer por mí?")
        if agent.get("use_rag"):
            questions.append("¿Qué información tienes disponible en tus documentos?")
        if agent.get("use_mysql"):
            questions.append("¿Cuáles son los medicamentos más vendidos?")
        if agent.get("use_charts"):
            questions.append("Muéstrame un gráfico con los datos más relevantes que tengas")
        if agent.get("use_email") or agent.get("smtp_config"):
            questions.append("¿Puedes enviarme un reporte por email a test@example.com?")
        questions.append("Dame un resumen detallado de lo que hemos hablado")

    # Agregar preguntas personalizadas
    if req.custom_questions:
        questions.extend(req.custom_questions)

    # Limitar total
    questions = questions[:req.num_turns + len(req.custom_questions or [])]

    # ── Paso 2: Ejecutar prueba activa ──
    test_results = await _execute_test_conversation(
        agent_id=agent_id,
        questions=questions,
        temperature=req.temperature
    )

    successful_turns = [r for r in test_results if r.get("success")]
    failed_turns = [r for r in test_results if not r.get("success")]

    if not successful_turns:
        return {
            "agent_id": agent_id,
            "agent_name": agent["name"],
            "status": "test_failed",
            "message": "Todas las preguntas de prueba fallaron. Verificar que el agente y Ollama estén operativos.",
            "questions": questions,
            "errors": [r.get("error", "") for r in failed_turns]
        }

    # ── Paso 3: Evaluar resultados ──
    # Evaluación turno por turno: cada turno genera ~100 tokens de JSON,
    # con format:"json" de Ollama, prácticamente imposible de truncar.
    try:
        evaluation = _evaluate_per_turn(agent, test_results, model)
    except (ValueError, Exception) as e:
        evaluation = {
            "overall_score": 0,
            "summary": f"Error al evaluar: {str(e)}",
            "per_turn_analysis": [],
            "tool_usage_report": {},
            "strengths": [],
            "weaknesses": [],
            "prompt_issues": [],
            "prompt_improvements": [],
            "suggested_prompt": "",
            "critical_alerts": ["Error en evaluación automática"]
        }

    # ── Paso 4: Guardar resultados ──
    mcp_client = get_mcp_client()
    await mcp_client.init_agent_db(agent_id)

    # Guardar score
    await mcp_client.add_metric(
        agent_id=agent_id,
        metric_name="active_test_score",
        metric_value=float(evaluation.get("overall_score", 0)),
        metadata={
            "summary": evaluation.get("summary", ""),
            "turns_tested": len(test_results),
            "turns_successful": len(successful_turns)
        }
    )

    # Guardar log de la prueba
    await mcp_client.log_agent_action(
        agent_id=agent_id,
        action="supervisor_active_test",
        details={
            "questions_count": len(questions),
            "successful_turns": len(successful_turns),
            "failed_turns": len(failed_turns),
            "overall_score": evaluation.get("overall_score", 0)
        },
        success=True
    )

    # ── Paso 5: Crear propuesta de prompt si hay sugerencia ──
    proposal_info = None
    suggested_prompt = evaluation.get("suggested_prompt", "")
    if suggested_prompt and suggested_prompt.strip() != agent["prompt"].strip():
        client = get_redis_client()
        proposal_id = f"proposal--{agent_id}--test--{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        proposal = {
            "id": proposal_id,
            "agent_id": agent_id,
            "agent_name": agent["name"],
            "current_prompt": agent["prompt"],
            "suggested_prompt": suggested_prompt.strip(),
            "evaluation": evaluation,
            "source": "active_test",
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        client.set(proposal_id, json.dumps(proposal))
        client.expire(proposal_id, 604800)  # 7 días

        proposal_info = {
            "proposal_id": proposal_id,
            "status": "pending",
            "message": f"Propuesta creada automáticamente. Usa POST /supervisor/approve/{proposal_id} para aplicar."
        }

    # ── Respuesta ──
    return {
        "agent_id": agent_id,
        "agent_name": agent["name"],
        "status": "completed",
        "test_summary": {
            "total_turns": len(test_results),
            "successful_turns": len(successful_turns),
            "failed_turns": len(failed_turns),
            "tools_detected": {
                "rag_uses": sum(1 for r in successful_turns if r.get("sources_count", 0) > 0),
                "charts_generated": sum(r.get("charts_count", 0) for r in successful_turns),
                "sql_uses": sum(1 for r in successful_turns if r.get("sql_used")),
                "emails_triggered": sum(1 for r in successful_turns if r.get("email_sent")),
            }
        },
        "evaluation": evaluation,
        "test_results": test_results,
        "prompt_proposal": proposal_info,
        "tested_at": datetime.now(timezone.utc).isoformat()
    }


# ══════════════════════════════════════════════════════════════
#  VERSIONADO Y ROLLBACK
# ══════════════════════════════════════════════════════════════

@router.get("/history/{agent_id}", summary="Historial de versiones de prompt")
async def prompt_history(agent_id: str, org: OrgContext = Depends(get_current_org)):
    """Obtiene el historial de versiones del prompt de un agente."""
    agent = get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no encontrado")

    mcp_client = get_mcp_client()
    await mcp_client.init_agent_db(agent_id)

    versions = await mcp_client.query_for_agent(
        agent_id=agent_id,
        query="SELECT id, version, timestamp, change_reason, approved_by, status FROM prompt_versions ORDER BY version DESC"
    )

    return {
        "agent_id": agent_id,
        "agent_name": agent["name"],
        "current_prompt": agent["prompt"][:500] + ("..." if len(agent["prompt"]) > 500 else ""),
        "versions": versions.get("rows", []) if versions.get("success") else [],
        "total_versions": len(versions.get("rows", [])) if versions.get("success") else 0
    }


@router.post("/rollback/{agent_id}", summary="Revertir prompt a versión anterior")
async def rollback_prompt(agent_id: str, version: int = None, org: OrgContext = Depends(get_current_org)):
    """Revierte el prompt del agente a una versión anterior. Si no se especifica versión, usa la última guardada."""
    agent = get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no encontrado")

    mcp_client = get_mcp_client()
    await mcp_client.init_agent_db(agent_id)

    if version is not None:
        target = await mcp_client.query_for_agent(
            agent_id=agent_id,
            query="SELECT prompt, version FROM prompt_versions WHERE version = ?",
            params=[version]
        )
    else:
        target = await mcp_client.query_for_agent(
            agent_id=agent_id,
            query="SELECT prompt, version FROM prompt_versions ORDER BY version DESC LIMIT 1"
        )

    if not target.get("success") or not target.get("rows"):
        raise HTTPException(status_code=404, detail="No se encontró la versión solicitada")

    row = target["rows"][0]
    old_prompt = row["prompt"]
    rolled_version = row["version"]

    # Aplicar rollback
    update_agent(agent_id=agent_id, prompt=old_prompt)

    # Registrar rollback
    await mcp_client.execute_write(
        db_name=f"agent_{agent_id}",
        query="UPDATE prompt_versions SET status = 'replaced' WHERE status = 'active'"
    )
    await mcp_client.execute_write(
        db_name=f"agent_{agent_id}",
        query="UPDATE prompt_versions SET status = 'active' WHERE version = ?",
        params=[rolled_version]
    )

    await mcp_client.log_agent_action(
        agent_id=agent_id,
        action="prompt_rollback",
        details={"rolled_to_version": rolled_version}
    )

    return {
        "status": "ok",
        "agent_id": agent_id,
        "rolled_to_version": rolled_version,
        "message": f"Prompt revertido a versión {rolled_version}"
    }
