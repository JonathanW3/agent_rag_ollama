"""
Router del meta-agente coordinador.

Expone /meta-agent/chat que:
  1. Clasifica la consulta → 'licencias' o 'correos' (keywords primero, LLM si hay empate)
  2. Rutea al agente especializado (LicenciasEC o CorreosEC)
  3. Valida que la respuesta tenga datos útiles
  4. Si no los tiene, reformula la pregunta y reintenta (hasta max_retries)
  5. Solo guarda en historial el intento final (exitoso o de cierre)
  6. Si se agotan los reintentos, genera una respuesta de cierre coherente
"""

import time
import logging
from fastapi import APIRouter, HTTPException, Depends
from ..auth import get_current_org, OrgContext
from ..schemas import MetaAgentChatRequest, MetaAgentConfigRequest, ChatRequest
from ..agents import get_agent
from ..meta_agent import (
    get_meta_agent_config,
    save_meta_agent_config,
    classify_domain,
    rephrase_query,
    evaluate_response,
    generate_fallback_response,
    requires_routing,
    generate_direct_response,
    format_for_whatsapp,
)
from .chat import chat as execute_chat

logger = logging.getLogger("meta_agent")

router = APIRouter(prefix="/meta-agent", tags=["🧠 Meta-Agente"])


def _ms(t: float) -> str:
    """Convierte segundos a string legible en ms o s."""
    elapsed = time.time() - t
    return f"{elapsed * 1000:.0f}ms" if elapsed < 1 else f"{elapsed:.2f}s"


@router.post("/chat", summary="Chat coordinado entre LicenciasEC y CorreosEC")
async def meta_agent_chat(
    req: MetaAgentChatRequest,
    org: OrgContext = Depends(get_current_org),
):
    """
    Coordina la consulta entre los agentes LicenciasEC y CorreosEC.

    - Clasifica el dominio por keywords; solo llama al LLM si hay ambigüedad.
    - Los reintentos intermedios no se guardan en el historial de Redis.
    - En cada reintento fallido reformula la pregunta antes de volver a consultar.
    - Si se agotan los intentos sin datos, genera un mensaje de cierre coherente.
    """
    t_total = time.time()
    config = get_meta_agent_config()
    llm_model = config.get("llm_model")
    max_retries = config.get("max_retries", 3)
    system_prompt = config.get("system_prompt")

    logger.info(
        f"[META-AGENT] ═══ NUEVA CONSULTA ═══ "
        f"session='{req.session_id}' "
        f"mensaje={req.message[:80]!r}"
    )

    # ── 1. Verificar si requiere enrutamiento o respuesta directa ────────
    t_routing = time.time()
    try:
        needs_routing = requires_routing(req.message, llm_model)
    except Exception as e:
        logger.warning(f"[META-AGENT] Error en requires_routing ({_ms(t_routing)}): {e} — asumiendo True")
        needs_routing = True

    if not needs_routing:
        logger.info(
            f"[META-AGENT] Respuesta DIRECTA (sin sub-agentes) — "
            f"({_ms(t_routing)}) — mensaje={req.message[:60]!r}"
        )
        try:
            direct_answer = generate_direct_response(req.message, system_prompt, llm_model)
        except Exception as e:
            logger.error(f"[META-AGENT] Error en respuesta directa: {e}")
            from ..meta_agent import _SALUDO_BIENVENIDA
            direct_answer = _SALUDO_BIENVENIDA

        from ..memory import save_message
        save_message("meta_agent", req.session_id, "user", req.message)
        save_message("meta_agent", req.session_id, "assistant", direct_answer)

        logger.info(
            f"[META-AGENT] ═══ FIN ═══ resultado=DIRECTO "
            f"tiempo_total={_ms(t_total)}"
        )
        return {
            "answer": direct_answer,
            "sources": [],
            "agent_id": "meta_agent",
            "session_id": req.session_id,
            "meta_agent": {
                "domain": "direct",
                "routed_to": None,
                "attempts": 0,
                "max_retries": max_retries,
                "has_valid_data": True,
                "final_message_used": req.message,
            },
        }

    # ── 2. Clasificar dominio ─────────────────────────────────────────────
    t_classify = time.time()
    try:
        domain = classify_domain(req.message, llm_model)
    except Exception as e:
        logger.warning(f"[META-AGENT] Error en clasificación ({_ms(t_classify)}): {e} — usando 'licencias'")
        domain = "licencias"

    if domain == "correos":
        target_agent_id = config["correos_agent_id"]
        domain_label = "correos/facturas"
    else:
        target_agent_id = config["licencias_agent_id"]
        domain_label = "licencias"

    logger.info(
        f"[META-AGENT] Dominio: '{domain_label}' → agente destino: '{target_agent_id}' "
        f"({_ms(t_classify)})"
    )

    # ── 3. Verificar existencia del agente ───────────────────────────────
    if get_agent(target_agent_id) is None:
        logger.error(f"[META-AGENT] Agente '{target_agent_id}' no encontrado en Redis")
        raise HTTPException(
            status_code=404,
            detail=(
                f"Agente '{target_agent_id}' no encontrado. "
                "Configura el meta-agente con PUT /meta-agent/config."
            ),
        )

    # ── 4. Loop de reintentos con reformulación ───────────────────────────
    attempt = 0
    last_result = None
    has_valid_data = False
    current_message = req.message

    while attempt < max_retries and not has_valid_data:
        attempt += 1
        is_last_attempt = attempt == max_retries
        t_attempt = time.time()

        logger.info(
            f"[META-AGENT] ── Intento {attempt}/{max_retries} "
            f"── Llamando a agente '{target_agent_id}' "
            f"── mensaje={current_message[:80]!r}"
        )

        chat_req = ChatRequest(
            message=current_message,
            agent_id=target_agent_id,
            session_id=req.session_id,
            use_rag=req.use_rag,
            save_history=False,
        )

        try:
            last_result = await execute_chat(chat_req)

            # Enriquecer el answer con el summary de herramientas (IMAP facturas, etc.)
            # El answer devuelto por chat.py es el texto limpio sin los resultados de tool;
            # los resultados reales vienen en campos separados.
            imap_facturas_summary = last_result.get("imap_facturas_summary", "")
            if imap_facturas_summary:
                last_result["answer"] = (
                    f"{last_result['answer']}\n\n{imap_facturas_summary}".strip()
                )
                logger.info(
                    f"[META-AGENT] imap_facturas_executed=True — "
                    f"answer enriquecido con summary ({len(imap_facturas_summary)} chars)"
                )

            answer_preview = last_result["answer"][:120].replace("\n", " ")
            logger.info(
                f"[META-AGENT] Agente '{target_agent_id}' respondió en {_ms(t_attempt)} "
                f"— {len(last_result['answer'])} chars "
                f"— preview: {answer_preview!r}"
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"[META-AGENT] Error llamando a agente '{target_agent_id}' "
                f"en intento {attempt} ({_ms(t_attempt)}): {e}"
            )
            if is_last_attempt:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error al consultar el agente '{target_agent_id}': {str(e)}",
                )
            continue

        # ── 4. Validar respuesta ──────────────────────────────────────────
        t_eval = time.time()
        try:
            has_valid_data = evaluate_response(last_result["answer"], llm_model)
        except Exception as e:
            logger.warning(f"[META-AGENT] Error en validación ({_ms(t_eval)}): {e} — asumiendo válida")
            has_valid_data = True

        logger.info(
            f"[META-AGENT] Validación intento {attempt}: "
            f"{'✓ VÁLIDA' if has_valid_data else '✗ SIN DATOS'} ({_ms(t_eval)})"
        )

        # ── 5. Reformular si no hay datos y quedan intentos ───────────────
        if not has_valid_data and not is_last_attempt:
            t_rephrase = time.time()
            logger.info(f"[META-AGENT] Reformulando consulta para intento {attempt + 1}...")
            try:
                current_message = rephrase_query(
                    original_message=req.message,
                    attempt=attempt,
                    domain_label=domain_label,
                    system_prompt=system_prompt,
                    llm_model=llm_model,
                )
                logger.info(f"[META-AGENT] Nueva consulta ({_ms(t_rephrase)}): {current_message[:80]!r}")
            except Exception as e:
                logger.warning(f"[META-AGENT] Error reformulando ({_ms(t_rephrase)}): {e} — usando original")
                current_message = req.message

    # ── 6. Respuesta de cierre si todos los intentos fallaron ─────────────
    if not has_valid_data:
        t_fallback = time.time()
        logger.warning(
            f"[META-AGENT] ✗ {max_retries} intentos agotados sin datos válidos. "
            f"Generando respuesta de cierre..."
        )
        try:
            fallback_answer = generate_fallback_response(
                original_message=req.message,
                domain_label=domain_label,
                system_prompt=system_prompt,
                llm_model=llm_model,
            )
            logger.info(f"[META-AGENT] Respuesta de cierre lista ({_ms(t_fallback)})")
        except Exception as e:
            logger.error(f"[META-AGENT] Error generando cierre ({_ms(t_fallback)}): {e}")
            fallback_answer = last_result["answer"] if last_result else (
                "No se encontró información disponible en este momento."
            )

        if last_result is None:
            last_result = {
                "answer": fallback_answer,
                "sources": [],
                "agent_id": target_agent_id,
                "session_id": req.session_id,
            }
        else:
            last_result["answer"] = fallback_answer
    else:
        logger.info(
            f"[META-AGENT] ✓ Datos válidos obtenidos en intento {attempt}/{max_retries}"
        )
        # Formatear para WhatsApp cuando la sesión proviene del webhook (prefijo wa_)
        if req.session_id.startswith("wa_"):
            t_fmt = time.time()
            last_result["answer"] = format_for_whatsapp(
                last_result["answer"], llm_model, domain=domain_label
            )
            logger.info(f"[META-AGENT] Formateo WhatsApp completado ({_ms(t_fmt)})")

        from ..memory import save_message
        save_message(target_agent_id, req.session_id, "user", req.message)
        save_message(target_agent_id, req.session_id, "assistant", last_result["answer"])

    # ── 7. Log de cierre con tiempo total ────────────────────────────────
    logger.info(
        f"[META-AGENT] ═══ FIN ═══ "
        f"resultado={'OK' if has_valid_data else 'FALLBACK'} "
        f"intentos={attempt}/{max_retries} "
        f"agente='{target_agent_id}' "
        f"tiempo_total={_ms(t_total)}"
    )

    last_result["meta_agent"] = {
        "domain": domain_label,
        "routed_to": target_agent_id,
        "attempts": attempt,
        "max_retries": max_retries,
        "has_valid_data": has_valid_data,
        "final_message_used": current_message if has_valid_data else req.message,
    }

    return last_result


# ── Configuración ─────────────────────────────────────────────────────────

@router.get("/config", summary="Ver configuración del meta-agente")
async def get_config(org: OrgContext = Depends(get_current_org)):
    """Retorna la configuración actual del meta-agente y los datos de los agentes vinculados."""
    config = get_meta_agent_config()
    licencias_agent = get_agent(config.get("licencias_agent_id", ""))
    correos_agent = get_agent(config.get("correos_agent_id", ""))
    return {
        **config,
        "licencias_agent": (
            {"id": licencias_agent["id"], "name": licencias_agent["name"]}
            if licencias_agent else None
        ),
        "correos_agent": (
            {"id": correos_agent["id"], "name": correos_agent["name"]}
            if correos_agent else None
        ),
    }


@router.put("/config", summary="Configurar los agentes del meta-agente")
async def update_config(
    req: MetaAgentConfigRequest,
    org: OrgContext = Depends(get_current_org),
):
    """
    Establece qué agente atiende licencias y cuál atiende correos/facturas.
    Configura modelo LLM, reintentos máximos y el system prompt del coordinador.
    """
    missing = []
    if not get_agent(req.licencias_agent_id):
        missing.append(req.licencias_agent_id)
    if not get_agent(req.correos_agent_id):
        missing.append(req.correos_agent_id)

    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Los siguientes agentes no existen: {missing}",
        )

    config = save_meta_agent_config(
        licencias_agent_id=req.licencias_agent_id,
        correos_agent_id=req.correos_agent_id,
        llm_model=req.llm_model,
        max_retries=req.max_retries,
        system_prompt=req.system_prompt,
    )
    return {"message": "Configuración del meta-agente actualizada", "config": config}
