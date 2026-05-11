"""
Meta-agente coordinador para LicenciasEC y CorreosEC.

Clasifica consultas, delega al agente especializado, valida la respuesta
y reintenta con reformulación si no se obtienen datos útiles.
"""

import json
import logging
from .redis_client import get_redis_client
from .ollama_client import ollama_chat
from .config import settings

logger = logging.getLogger("meta_agent")

META_AGENT_CONFIG_KEY = "meta_agent:config"

_SALUDO_BIENVENIDA = (
    "¡Hola! Soy Robertito, tu asistente gerencial. Estoy especializado en información "
    "sobre las licencias de las empresas de WebPOS Ecuador, así como de los correos de "
    "facturación que se han enviado este año. ¿En qué necesitas que te ayude? "
    "¿Deseas saber cuántas facturas se han realizado este mes y cuántas te faltan "
    "respecto al mes anterior? ¿O deseas saber qué empresas están próximas a expirar "
    "sus licencias? Recuerda que las empresas tienen Licencias Tipo Licenciamiento y Tipo Nube."
)

_DEFAULT_SYSTEM_PROMPT = (
    "Eres Robertito, un asistente gerencial especializado en licencias de software "
    "y facturas electrónicas de WebPOS Ecuador.\n\n"

    "COMPORTAMIENTO DIRECTO (responde tú mismo, NO consultes sub-agentes):\n"
    "- Saludos y bienvenida: usa SIEMPRE este mensaje exacto:\n"
    f"  \"{_SALUDO_BIENVENIDA}\"\n"
    "- Preguntas sobre tus capacidades: explica que consultas licencias y facturas.\n"
    "- Agradecimientos o despedidas: responde de forma amigable y breve.\n"
    "- Mensajes de cortesía o conversación general: atiéndelos directamente.\n\n"

    "CONSULTA A SUB-AGENTES (solo cuando el usuario pide datos concretos):\n"
    "- Licencias: estado, activación, vencimiento, empresa registrada → LicenciasEC.\n"
    "- Facturas: montos, proveedores, períodos, comparaciones → CorreosEC.\n\n"

    "CUANDO UN AGENTE NO ENCUENTRA DATOS:\n"
    "Reformula la consulta con términos alternativos o fechas más amplias. "
    "Si todos los intentos fallan, informa al usuario de forma clara y sugiere alternativas."
)

DEFAULT_CONFIG = {
    "licencias_agent_id": "LicenciasEC",
    "correos_agent_id": "CorreosEC",
    "llm_model": None,
    "max_retries": 3,
    "system_prompt": _DEFAULT_SYSTEM_PROMPT,
}

# Palabras clave que indican que NO se necesita consultar sub-agentes
_KEYWORDS_DIRECT = {
    "hola", "hello", "hi", "hey", "buenos", "buenas", "buen",
    "saludos", "qué tal", "que tal", "cómo estás", "como estas",
    "cómo te va", "como te va", "gracias", "thank", "thanks",
    "adiós", "adios", "bye", "hasta luego", "hasta pronto",
    "chao", "ciao", "nos vemos",
    "qué puedes", "que puedes", "qué haces", "que haces",
    "ayuda", "help", "capacidades", "funciones", "para qué sirves",
    "para que sirves",
}

# Palabras clave para clasificación rápida sin LLM
_KEYWORDS_LICENCIAS = {
    "licencia", "licencias", "activación", "activacion", "activar", "activada",
    "vencimiento", "vence", "vencida", "vencido", "expira", "expiración",
    "expiracion", "expirado", "expirada", "registro", "registrado", "registrada",
    "renovación", "renovacion", "renovar", "serial", "clave de activación",
    "codigo de activacion", "empresa registrada", "cliente registrado",
    "estado de licencia", "licenciado", "licenciada",
    # Tipos de cliente WebPOS Ecuador
    "licenciamiento", "on-premise", "nube", "efiscaldocs", "efiscal",
    "webpospa", "webpos", "ecuador", "vencer", "caducar", "caduca", "caducó",
}

_KEYWORDS_CORREOS = {
    "factura", "facturas", "correo", "correos", "email", "emails",
    "proveedor", "proveedores", "bandeja", "adjunto", "adjuntos",
    "imap", "mensaje", "mensajes", "recibido", "recibidos",
    "inbox", "facturación", "facturacion", "comprobante", "comprobantes",
    "remitente", "asunto",
}

# Frases que indican ausencia de datos útiles
_NO_DATA_PHRASES = [
    "no encontré", "no encontre", "no hay datos", "no tengo información",
    "no tengo informacion", "sin resultados", "no se encontraron",
    "no pude encontrar", "no hay registros", "no hay información",
    "no hay facturas", "no hay licencias", "no hay correos", "no hay emails",
    "no tengo acceso", "no dispongo", "no cuento con", "no data", "not found",
    "sin datos", "sin información", "sin informacion", "sin licencias",
    "no existe", "no existen", "no disponible", "no se encontró",
    "no se encontro", "no puedo obtener", "no tengo acceso a",
    "ningún resultado", "ningun resultado", "sin registros",
    "no hay información disponible", "no se encontró información",
    "no hay licencias por vencer", "no hay licencias próximas",
    "no hay vencimientos próximos", "sin alertas de vencimiento",
    "no hay facturas nuevas", "no hay facturas hoy", "no se recibieron facturas",
    "no hay correos nuevos", "no llegaron facturas",
    "consultando la base de datos",
]


def get_meta_agent_config() -> dict:
    """Lee la configuración del meta-agente desde Redis."""
    client = get_redis_client()
    data = client.get(META_AGENT_CONFIG_KEY)
    if data is None:
        return dict(DEFAULT_CONFIG)
    stored = json.loads(data)
    if not stored.get("system_prompt"):
        stored["system_prompt"] = _DEFAULT_SYSTEM_PROMPT
    return stored


def save_meta_agent_config(
    licencias_agent_id: str,
    correos_agent_id: str,
    llm_model: str | None = None,
    max_retries: int = 3,
    system_prompt: str | None = None,
) -> dict:
    """Guarda la configuración del meta-agente en Redis."""
    client = get_redis_client()
    config = {
        "licencias_agent_id": licencias_agent_id,
        "correos_agent_id": correos_agent_id,
        "llm_model": llm_model,
        "max_retries": max_retries,
        "system_prompt": system_prompt or _DEFAULT_SYSTEM_PROMPT,
    }
    client.set(META_AGENT_CONFIG_KEY, json.dumps(config))
    logger.info(
        f"[META-AGENT] Configuración guardada — "
        f"licencias='{licencias_agent_id}' correos='{correos_agent_id}' "
        f"max_retries={max_retries} llm_model={llm_model!r}"
    )
    return config


def classify_domain(message: str, llm_model: str | None = None) -> str:
    """
    Clasifica la consulta como 'licencias' o 'correos'.

    Primero intenta clasificar por palabras clave (sin costo LLM).
    Solo si no hay señal clara usa el LLM como desempate.

    Returns:
        'licencias' o 'correos'
    """
    message_lower = message.lower()
    tokens = set(message_lower.split())

    hits_licencias = len(tokens & _KEYWORDS_LICENCIAS) + sum(
        1 for kw in _KEYWORDS_LICENCIAS if " " in kw and kw in message_lower
    )
    hits_correos = len(tokens & _KEYWORDS_CORREOS) + sum(
        1 for kw in _KEYWORDS_CORREOS if " " in kw and kw in message_lower
    )

    if hits_licencias > hits_correos:
        logger.info(
            f"[META-AGENT] Clasificación por KEYWORDS → 'licencias' "
            f"(hits_licencias={hits_licencias} hits_correos={hits_correos})"
        )
        return "licencias"

    if hits_correos > hits_licencias:
        logger.info(
            f"[META-AGENT] Clasificación por KEYWORDS → 'correos' "
            f"(hits_correos={hits_correos} hits_licencias={hits_licencias})"
        )
        return "correos"

    # Empate o sin señal → LLM
    logger.info(
        f"[META-AGENT] Clasificación ambigua (hits_licencias={hits_licencias} "
        f"hits_correos={hits_correos}) → consultando LLM para desempate"
    )
    system_prompt = (
        "Eres un clasificador de consultas. Tu ÚNICA tarea es decidir a cuál categoría pertenece la pregunta:\n\n"
        "  - 'licencias': licencias de software, activaciones, registros, vencimientos, renovaciones.\n"
        "  - 'correos': facturas por email, correos de proveedores, bandeja IMAP, adjuntos.\n\n"
        "REGLAS:\n"
        "- Responde ÚNICAMENTE con una de estas dos palabras exactas: licencias | correos\n"
        "- Sin explicación, sin puntuación, sin texto extra.\n"
        "- Si hay duda, responde: licencias"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]
    model = llm_model or settings.CHAT_MODEL
    raw = ollama_chat(messages, temperature=0.0, model=model)
    domain = raw.strip().lower().strip('"').strip("'").strip()
    result = domain if domain in ("licencias", "correos") else "licencias"
    logger.info(f"[META-AGENT] Clasificación por LLM → '{result}' (raw={raw.strip()!r})")
    return result


def rephrase_query(
    original_message: str,
    attempt: int,
    domain_label: str,
    system_prompt: str | None = None,
    llm_model: str | None = None,
) -> str:
    """
    Reformula la pregunta original para el siguiente reintento.

    Returns:
        Pregunta reformulada, o la original si el LLM falla.
    """
    coordinator_ctx = system_prompt or _DEFAULT_SYSTEM_PROMPT
    rephraser_prompt = (
        f"{coordinator_ctx}\n\n"
        f"El intento {attempt} de consulta sobre '{domain_label}' no retornó datos útiles.\n"
        "Reformula la pregunta original para el siguiente intento usando alguna de estas estrategias:\n"
        "  - Ser más específico en el criterio de búsqueda\n"
        "  - Usar términos alternativos o sinónimos del dominio\n"
        "  - Simplificar la pregunta a sus elementos esenciales\n"
        "  - Quitar filtros o restricciones que puedan ser demasiado estrictos\n\n"
        "RESPONDE ÚNICAMENTE con la pregunta reformulada. Sin prefijos, sin explicación."
    )
    messages = [
        {"role": "system", "content": rephraser_prompt},
        {"role": "user", "content": f"Pregunta original: {original_message}"},
    ]
    model = llm_model or settings.CHAT_MODEL
    try:
        raw = ollama_chat(messages, temperature=0.3, model=model)
        rephrased = raw.strip()
        if rephrased:
            logger.info(
                f"[META-AGENT] Reformulación intento {attempt}: "
                f"{original_message[:60]!r} → {rephrased[:60]!r}"
            )
            return rephrased
        logger.warning(f"[META-AGENT] Reformulación vacía en intento {attempt} — usando original")
        return original_message
    except Exception as e:
        logger.warning(f"[META-AGENT] Error en reformulación intento {attempt}: {e} — usando original")
        return original_message


def generate_fallback_response(
    original_message: str,
    domain_label: str,
    system_prompt: str | None = None,
    llm_model: str | None = None,
) -> str:
    """
    Genera un mensaje de cierre cuando todos los reintentos se agotaron sin datos.

    Returns:
        Mensaje de cierre para el usuario final.
    """
    coordinator_ctx = system_prompt or _DEFAULT_SYSTEM_PROMPT
    fallback_prompt = (
        f"{coordinator_ctx}\n\n"
        f"El agente especializado en '{domain_label}' no encontró datos útiles después de varios intentos.\n\n"
        "Genera un mensaje claro, honesto y cordial para informar al usuario. El mensaje debe:\n"
        "  - Reconocer la consulta del usuario\n"
        "  - Informar que no se encontró información disponible en este momento\n"
        "  - Sugerir verificar los parámetros de búsqueda o intentar con términos distintos\n"
        "  - Ser conciso (máximo 3 oraciones)\n\n"
        "RESPONDE DIRECTAMENTE con el mensaje para el usuario. Sin prefijos ni explicaciones extra."
    )
    messages = [
        {"role": "system", "content": fallback_prompt},
        {"role": "user", "content": original_message},
    ]
    model = llm_model or settings.CHAT_MODEL
    try:
        raw = ollama_chat(messages, temperature=0.3, model=model)
        result = raw.strip()
        logger.info(f"[META-AGENT] Respuesta de cierre generada: {result[:100]!r}")
        return result
    except Exception as e:
        logger.error(f"[META-AGENT] Error generando respuesta de cierre: {e}")
        return (
            f"No se encontró información disponible sobre '{domain_label}' en este momento. "
            "Por favor verifica los parámetros de búsqueda o intenta con términos distintos."
        )


_WHATSAPP_PROMPT_LICENCIAS = (
    "Eres un asistente que formatea respuestas de LICENCIAS DE SOFTWARE para WhatsApp.\n\n"
    "REGLAS ESTRICTAS:\n"
    "- Máximo 30 líneas en total\n"
    "- Usa emojis para mejorar legibilidad (📊 🏢 ✅ ⚠️ 🔴 🟢 📋 etc.)\n"
    "- Lista TODAS las empresas mencionadas en la respuesta — NUNCA omitas ni resumás empresas\n"
    "- Por cada empresa: nombre real, RUC, tipo (Licenciamiento/Nube), próxima renovación\n"
    "- PROHIBIDO inventar nombres de empresas o usar placeholders como '[Empresa X]', '[Otra empresa]'\n"
    "- PROHIBIDO agregar campos que no existan en la respuesta (montos, cantidades inventadas)\n"
    "- Usa solo datos que aparezcan explícitamente en el texto recibido\n"
    "- Formato de lista simple con viñetas (•), sin markdown complejo\n"
    "- Sin tablas, sin **, sin ##, sin bloques de código\n"
    "- Termina ofreciendo detalle de empresa específica si lo desea\n\n"
    "RESPONDE ÚNICAMENTE con el mensaje formateado. Sin explicaciones previas."
)

_WHATSAPP_PROMPT_CORREOS = (
    "Eres un asistente que formatea respuestas de FACTURAS Y CORREOS para WhatsApp.\n\n"
    "REGLAS ESTRICTAS:\n"
    "- Máximo 25 líneas en total\n"
    "- Usa emojis para mejorar legibilidad (📊 📋 ✅ ⚠️ 💰 🏢 etc.)\n"
    "- Para listas grandes: muestra resumen por categoría + top 5 por monto, indica cuántos hay en total\n"
    "- Incluye SIEMPRE: total de registros, monto total y rango de fechas si aplica\n"
    "- PROHIBIDO inventar datos o usar placeholders como '[Proveedor X]'\n"
    "- Usa solo datos que aparezcan explícitamente en el texto recibido\n"
    "- Formato de lista simple con viñetas (•), sin markdown complejo\n"
    "- Sin tablas, sin **, sin ##, sin bloques de código\n"
    "- Agrupa por tipo cuando sea posible\n"
    "- Termina ofreciendo detalle de proveedor específico si lo desea\n\n"
    "RESPONDE ÚNICAMENTE con el mensaje formateado. Sin explicaciones previas."
)


def format_for_whatsapp(
    answer: str,
    llm_model: str | None = None,
    domain: str = "licencias",
) -> str:
    """
    Reformatea una respuesta larga en un resumen conciso y legible para WhatsApp.
    Usa prompts diferenciados por dominio para evitar que el LLM aplique
    lógica de facturas (montos, top 5) a respuestas de licencias.
    """
    if len(answer) < 400:
        return answer

    format_prompt = (
        _WHATSAPP_PROMPT_LICENCIAS
        if domain == "licencias"
        else _WHATSAPP_PROMPT_CORREOS
    )
    messages = [
        {"role": "system", "content": format_prompt},
        {"role": "user", "content": answer},
    ]
    model = llm_model or settings.CHAT_MODEL
    try:
        raw = ollama_chat(messages, temperature=0.1, model=model)
        result = raw.strip()
        if result and len(result) >= 40:
            logger.info(
                f"[META-AGENT] Respuesta formateada para WhatsApp ({domain}): "
                f"{len(answer)} → {len(result)} chars"
            )
            return result
        logger.warning("[META-AGENT] Formateo WhatsApp produjo resultado vacío — usando original")
        return answer
    except Exception as e:
        logger.warning(f"[META-AGENT] Error al formatear para WhatsApp: {e} — usando original")
        return answer


def evaluate_response(answer: str, llm_model: str | None = None, strict: bool = False) -> bool:
    """
    Evalúa si la respuesta contiene datos reales y útiles.

    Usa detección por frases negativas como filtro rápido antes de llamar al LLM.

    Args:
        strict: Si True, cualquier frase negativa detectada = inválida (sin LLM).
                Usar en contextos automáticos (cron) donde falsos positivos son peores
                que falsos negativos.

    Returns:
        True si tiene datos válidos, False si está vacía o es negativa.
    """
    stripped = answer.strip()

    if len(stripped) < 40:
        logger.info(f"[META-AGENT] Validación: INVÁLIDA — respuesta demasiado corta ({len(stripped)} chars)")
        return False

    answer_lower = stripped.lower()
    no_data_hits = sum(1 for phrase in _NO_DATA_PHRASES if phrase in answer_lower)

    if no_data_hits >= 2:
        logger.info(
            f"[META-AGENT] Validación: INVÁLIDA — {no_data_hits} frases negativas detectadas "
            f"(sin llamar al LLM)"
        )
        return False

    if no_data_hits >= 1 and (strict or len(stripped) < 200):
        logger.info(
            f"[META-AGENT] Validación: INVÁLIDA — frase negativa detectada"
            f"{' (modo strict)' if strict else f' en respuesta corta ({len(stripped)} chars)'}"
            f" (sin llamar al LLM)"
        )
        return False

    if strict:
        # En modo strict no consultamos el LLM; si no hay frases negativas, asumimos válida
        logger.info(f"[META-AGENT] Validación: VÁLIDA — sin frases negativas (modo strict)")
        return True

    # Caso ambiguo → LLM
    logger.info(
        f"[META-AGENT] Validación ambigua (no_data_hits={no_data_hits}, "
        f"len={len(stripped)}) → consultando LLM"
    )
    system_prompt = (
        "Eres un evaluador de respuestas de un asistente IA.\n"
        "Determina si la respuesta contiene datos reales y útiles para el usuario,\n"
        "o si es una respuesta vacía, negativa o que indica que no encontró información.\n\n"
        "RESPONDE ÚNICAMENTE con: SI | NO\n"
        "SI = tiene datos concretos y útiles.\n"
        "NO = no tiene datos, es negativa o está vacía.\n"
        "Sin explicación, sin puntuación extra."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Respuesta del agente:\n{stripped[:1500]}"},
    ]
    model = llm_model or settings.CHAT_MODEL
    raw = ollama_chat(messages, temperature=0.0, model=model)
    verdict = raw.strip().upper()
    valid = "SI" in verdict or "SÍ" in verdict
    logger.info(f"[META-AGENT] Validación por LLM → {'VÁLIDA' if valid else 'INVÁLIDA'} (raw={raw.strip()!r})")
    return valid


def requires_routing(message: str, llm_model: str | None = None) -> bool:
    """
    Decide si el mensaje necesita consultar a un sub-agente o puede ser atendido
    directamente por el coordinador (saludos, cortesía, capacidades).

    Usa keywords para la detección rápida. Solo llama al LLM si la señal es ambigua.

    Returns:
        True  → debe enrutar a LicenciasEC / CorreosEC
        False → el coordinador responde directamente
    """
    message_lower = message.lower()
    tokens = set(message_lower.split())

    # Si hay keywords de dominio → siempre enrutar
    hits_domain = (
        len(tokens & _KEYWORDS_LICENCIAS)
        + len(tokens & _KEYWORDS_CORREOS)
        + sum(1 for kw in _KEYWORDS_LICENCIAS if " " in kw and kw in message_lower)
        + sum(1 for kw in _KEYWORDS_CORREOS if " " in kw and kw in message_lower)
    )
    if hits_domain > 0:
        logger.info(
            f"[META-AGENT] requires_routing=True — keywords de dominio detectadas ({hits_domain} hits)"
        )
        return True

    # Si hay keywords directos y el mensaje es corto → responder sin enrutar
    hits_direct = len(tokens & _KEYWORDS_DIRECT) + sum(
        1 for kw in _KEYWORDS_DIRECT if " " in kw and kw in message_lower
    )
    if hits_direct > 0 and len(message.split()) <= 12:
        logger.info(
            f"[META-AGENT] requires_routing=False — saludo/cortesía detectado por keywords "
            f"({hits_direct} hits, {len(message.split())} palabras)"
        )
        return False

    # Ambiguo o mensaje sin señal clara → LLM decide
    logger.info(
        f"[META-AGENT] requires_routing ambiguo (domain={hits_domain} direct={hits_direct}) "
        f"→ consultando LLM"
    )
    system_prompt = (
        "Eres un clasificador de mensajes. Tu ÚNICA tarea es decidir si el mensaje del usuario "
        "requiere consultar datos reales de licencias o facturas, o si es un saludo, "
        "cortesía, pregunta general o conversación que puede responderse sin datos.\n\n"
        "RESPONDE ÚNICAMENTE con una de estas dos palabras exactas: DATOS | DIRECTO\n"
        "DATOS   = el usuario pide información concreta (licencias, facturas, montos, empresas).\n"
        "DIRECTO = saludo, agradecimiento, pregunta sobre capacidades, conversación general.\n"
        "Sin explicación, sin puntuación extra.\n"
        "Si hay duda, responde: DATOS"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]
    model = llm_model or settings.CHAT_MODEL
    raw = ollama_chat(messages, temperature=0.0, model=model)
    verdict = raw.strip().upper()
    route = "DIRECTO" not in verdict
    logger.info(
        f"[META-AGENT] requires_routing={route} por LLM (raw={raw.strip()!r})"
    )
    return route


def generate_direct_response(
    message: str,
    system_prompt: str | None = None,
    llm_model: str | None = None,
) -> str:
    """
    Genera una respuesta directa del coordinador sin consultar sub-agentes.
    Usada para saludos, cortesía y preguntas generales.
    """
    # Mensajes cortos sin keywords de dominio → saludo de bienvenida fijo, sin LLM.
    # Cubre typos ("Hla"), variantes ("buenos días") y cualquier intro corta.
    message_lower = message.strip().lower()
    tokens = set(message_lower.split())
    has_domain = bool(tokens & (_KEYWORDS_LICENCIAS | _KEYWORDS_CORREOS))
    if not has_domain and len(message.split()) <= 4:
        logger.info(
            f"[META-AGENT] Mensaje corto sin dominio ({len(message.split())} palabras) "
            "→ retornando _SALUDO_BIENVENIDA directamente"
        )
        return _SALUDO_BIENVENIDA

    coordinator_ctx = system_prompt or _DEFAULT_SYSTEM_PROMPT
    messages = [
        {"role": "system", "content": coordinator_ctx},
        {"role": "user", "content": message},
    ]
    model = llm_model or settings.CHAT_MODEL
    try:
        raw = ollama_chat(messages, temperature=0.5, model=model)
        result = raw.strip()
        logger.info(f"[META-AGENT] Respuesta directa generada: {result[:100]!r}")
        return result
    except Exception as e:
        logger.error(f"[META-AGENT] Error generando respuesta directa: {e}")
        return _SALUDO_BIENVENIDA
