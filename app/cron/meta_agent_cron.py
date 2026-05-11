"""
Cron del meta-agente: ejecuta una consulta predefinida a un sub-agente
(LicenciasEC, CorreosEC, etc.) y envía alerta por WhatsApp solo cuando
hay datos relevantes y la respuesta no es un duplicado de la última enviada.

Estrategias de deduplicación
─────────────────────────────
  hash  — hash normalizado de la respuesta + TTL configurable.
          Elimina conteos de días y fechas concretas antes de hashear,
          así el hash es estable mientras el conjunto de entidades no cambie.
          Recomendado para LicenciasEC.

  date  — sin hash; la consulta ya filtra por "hoy" y evaluate_response()
          descarta respuestas vacías. Si no llegaron facturas nuevas,
          el agente dice "no hay datos" y el cron no envía nada.
          Recomendado para CorreosEC.

  none  — siempre envía cuando evaluate_response() devuelve True.
"""

import hashlib
import logging
import re
import time
from datetime import datetime, timezone


def _imap_invoice_count(imap_summary: str) -> int:
    """Suma el total de facturas en todas las entradas del resumen IMAP."""
    matches = re.findall(r'→\s*(\d+)\s*factura', imap_summary, re.IGNORECASE)
    return sum(int(m) for m in matches)


def _clean_imap_summary(imap_summary: str) -> str:
    """Elimina las etiquetas internas del bloque IMAP dejando solo el contenido."""
    return re.sub(r'\[/?RESULTADO DE IMAP FACTURAS\]', '', imap_summary).strip()

from ..meta_agent import evaluate_response, format_for_whatsapp
from ..redis_client import get_redis_client

logger = logging.getLogger("cron.meta_agent")


# ── Deduplicación por hash ────────────────────────────────────────────────────

def _redis_key_hash(agent_id: str) -> str:
    return f"cron:meta_agent:{agent_id}:last_hash"


def _stable_hash(text: str) -> str:
    """
    Hash normalizado: elimina conteos de días y fechas concretas para que
    el hash represente QUÉ entidades hay (empresas, licencias) y no
    cuántos días faltan, evitando falsos cambios día a día.
    """
    t = re.sub(r'\b\d+\s*d[íi]as?\b', 'N_DAYS', text, flags=re.IGNORECASE)
    t = re.sub(r'\d{4}-\d{2}-\d{2}', 'DATE', t)
    t = re.sub(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', 'DATE', t)
    t = re.sub(r'\$[\d,\.]+', 'AMOUNT', t)
    return hashlib.sha256(t[:3000].encode()).hexdigest()[:20]


def _is_duplicate_hash(agent_id: str, answer: str, ttl: int) -> bool:
    """
    Devuelve True si el hash normalizado del answer coincide con el último
    hash guardado en Redis.  Si no coincide (o no hay registro previo),
    guarda el nuevo hash con el TTL dado y devuelve False.
    """
    redis = get_redis_client()
    key = _redis_key_hash(agent_id)
    new_hash = _stable_hash(answer)
    old_raw = redis.get(key)
    old_str = old_raw.decode() if isinstance(old_raw, bytes) else old_raw
    if old_str and old_str == new_hash:
        return True
    redis.set(key, new_hash, ex=ttl)
    return False


# ── Tarea principal ───────────────────────────────────────────────────────────

async def run_meta_agent_check(config: dict) -> dict:
    """
    Ejecuta el chequeo periódico del meta-agente para un sub-agente específico.

    Parámetros esperados en config
    ──────────────────────────────
      agent_id          str   — ID del sub-agente a consultar
      query             str   — Consulta predefinida (ej. "licencias que vencen en 7 días")
      session_id        str   — ID de sesión Redis (default: cron_{agent_id})
      dedup_strategy    str   — "hash" | "date" | "none"
      dedup_ttl         int   — TTL del hash en Redis, segundos (default: 82800 = 23 h)
      wa_notify_phones  list? — Lista de números WhatsApp destino
      wa_notify_session str?  — Sesión WhatsApp de origen
    """
    agent_id       = config["agent_id"]
    query          = config.get("query", "")
    session_id     = config.get("session_id") or f"cron_{agent_id}"
    dedup_strategy = config.get("dedup_strategy", "hash")
    dedup_ttl      = int(config.get("dedup_ttl", 82800))
    wa_phones      = config.get("wa_notify_phones") or []
    wa_session     = config.get("wa_notify_session")

    timestamp = datetime.now(timezone.utc).isoformat()
    t_inicio  = time.monotonic()

    def _ms() -> int:
        return int((time.monotonic() - t_inicio) * 1000)

    def _log_error(msg: str) -> dict:
        from ..db_platform import insert_cron_meta_agent_log
        insert_cron_meta_agent_log(
            agent_id=agent_id, success=False, duracion_ms=_ms(), error=msg
        )
        logger.error(f"[CRON META] agent={agent_id} — {msg}")
        return {"success": False, "timestamp": timestamp, "agent_id": agent_id, "error": msg}

    logger.info(
        f"[CRON META] ══ INICIO agent={agent_id} "
        f"dedup={dedup_strategy} ttl={dedup_ttl}s ══"
    )

    # ── 1. Llamar al sub-agente directamente vía chat ─────────────────────
    try:
        from ..routers.chat import chat as execute_chat
        from ..schemas import ChatRequest

        chat_req = ChatRequest(
            message=query,
            agent_id=agent_id,
            session_id=session_id,
            save_history=False,
        )
        result = await execute_chat(chat_req)

        # Procesar resumen IMAP si la herramienta lo devuelve (CorreosEC)
        imap_summary = result.get("imap_facturas_summary", "")
        imap_log_note = ""  # Se usará como reporte cuando no haya datos
        if imap_summary:
            imap_count = _imap_invoice_count(imap_summary)
            if imap_count > 0:
                # Hay facturas reales: usar el contenido IMAP limpio como respuesta
                result["answer"] = _clean_imap_summary(imap_summary)
                logger.info(f"[CRON META] agent={agent_id} — IMAP: {imap_count} factura(s) encontrada(s)")
            else:
                # 0 facturas: vaciar el answer pero guardar nota para el log
                imap_log_note = _clean_imap_summary(imap_summary) or f"IMAP: 0 facturas en el período"
                result["answer"] = ""
                logger.info(f"[CRON META] agent={agent_id} — IMAP: 0 facturas → no se enviará nada")

        answer = result.get("answer", "")
        logger.info(f"[CRON META] agent={agent_id} — respuesta {len(answer)} chars")

    except Exception as e:
        return _log_error(f"Error llamando al agente '{agent_id}': {e}")

    # ── 2. Evaluar si la respuesta contiene datos útiles ──────────────────
    has_data = False
    try:
        has_data = evaluate_response(answer, strict=True)
    except Exception as e:
        logger.warning(f"[CRON META] evaluate_response falló: {e} — asumiendo válida")
        has_data = bool(answer.strip())

    if not has_data:
        logger.info(
            f"[CRON META] agent={agent_id} — "
            "sin datos relevantes → no se envía WhatsApp"
        )
        from ..db_platform import insert_cron_meta_agent_log
        insert_cron_meta_agent_log(
            agent_id=agent_id, success=True,
            enviado_wa=False, dedup_skip=False,
            duracion_ms=_ms(), reporte=(answer or imap_log_note)[:500],
        )
        return {
            "success": True, "timestamp": timestamp,
            "agent_id": agent_id, "enviado_wa": False, "motivo": "sin_datos",
        }

    # ── 3. Deduplicación ──────────────────────────────────────────────────
    if dedup_strategy == "hash":
        try:
            is_dup = _is_duplicate_hash(agent_id, answer, dedup_ttl)
        except Exception as e:
            logger.warning(f"[CRON META] Error en dedup hash: {e} — continuando sin dedup")
            is_dup = False

        if is_dup:
            logger.info(
                f"[CRON META] agent={agent_id} — "
                "hash idéntico al último envío → se omite (dedup_hash)"
            )
            from ..db_platform import insert_cron_meta_agent_log
            insert_cron_meta_agent_log(
                agent_id=agent_id, success=True,
                enviado_wa=False, dedup_skip=True,
                duracion_ms=_ms(), reporte=answer[:500],
            )
            return {
                "success": True, "timestamp": timestamp,
                "agent_id": agent_id, "enviado_wa": False, "motivo": "dedup_hash",
            }

    # ── 4. Formatear para WhatsApp ────────────────────────────────────────
    wa_message = answer
    try:
        wa_message = format_for_whatsapp(answer)
    except Exception as e:
        logger.warning(f"[CRON META] Error en format_for_whatsapp: {e} — usando original")

    # ── 5. Enviar por WhatsApp (a todos los números configurados) ─────────
    enviado_wa = False
    if wa_phones and wa_session:
        from ..whatsapp_client import wa_send_message
        for phone in wa_phones:
            try:
                await wa_send_message(wa_session, phone, wa_message)
                enviado_wa = True
                logger.info(
                    f"[CRON META] agent={agent_id} — "
                    f"alerta enviada a {phone} ({len(wa_message)} chars)"
                )
            except Exception as e:
                logger.warning(f"[CRON META] agent={agent_id} — error enviando WA a {phone}: {e}")
    else:
        logger.info(
            f"[CRON META] agent={agent_id} — "
            "sin destino WA configurado, resultado guardado solo en log"
        )

    # ── 6. Registrar ejecución ────────────────────────────────────────────
    from ..db_platform import insert_cron_meta_agent_log
    insert_cron_meta_agent_log(
        agent_id=agent_id, success=True,
        enviado_wa=enviado_wa, dedup_skip=False,
        duracion_ms=_ms(), reporte=wa_message,
    )

    logger.info(
        f"[CRON META] ══ FIN agent={agent_id} "
        f"enviado_wa={enviado_wa} {_ms()}ms ══"
    )
    return {
        "success":    True,
        "timestamp":  timestamp,
        "agent_id":   agent_id,
        "enviado_wa": enviado_wa,
        "reporte":    wa_message,
    }
