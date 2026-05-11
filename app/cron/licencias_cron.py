"""
Cron: Chequeo de licencias por vencer — webpospa (SQL Server / Ecuador)

Flujo:
  1. Consulta mcp_sqlserver → licencias_por_vencer(dias, campo_fecha="ambas")
  2. Llama al LLM (Ollama) para generar un reporte ejecutivo formateado
  3. Guarda el reporte en Redis:
     a. Clave por agente → cron:licencias:{agent_id}:ultimo_reporte  (TTL configurable)
     b. Sesión del agente → chat_session:{agent_id}:{session_id}

La función run_licencias_check recibe un dict 'config' con:
  agent_id   — ID del agente que ejecuta y recibe el reporte
  session_id — ID de sesión donde guardar el reporte (default: licencias_diario)
  dias       — Días hacia adelante a consultar (default: 30)
  ttl        — TTL en segundos del reporte en Redis (default: 604800 = 7 días)

Si config es None se usan los valores de settings (compatibilidad con versiones anteriores).
"""

import json
import logging
import time
from datetime import datetime, timezone

from ..config import settings
from ..redis_client import get_redis_client
from ..ollama_client import ollama_chat

logger = logging.getLogger("cron.licencias")


def redis_key_reporte(agent_id: str) -> str:
    return f"cron:licencias:{agent_id}:ultimo_reporte"


# Clave fija legacy (usada antes de soportar múltiples agentes)
REDIS_KEY_ULTIMO_REPORTE = f"cron:licencias:{settings.CRON_LICENCIAS_AGENT_ID or 'default'}:ultimo_reporte"

_SYSTEM_PROMPT = """Eres un asistente especializado en renovación de licencias eFiscalDocs Ecuador para clientes con contrato de Licenciamiento (instalación local).

Tu tarea es analizar las empresas cuya renovación de eFiscalDocs vence en el mes actual o en los próximos días y generar un reporte ejecutivo claro y accionable.

Formato del reporte:
1. Resumen ejecutivo (total de empresas a renovar y urgencia general)
2. Lista de empresas ordenadas por proximidad de vencimiento:
   - Nombre, RUC, mes de vencimiento, días restantes para esa fecha, correo de contacto
3. Acción recomendada para cada empresa (contactar, enviar cotización, etc.)

Nota: El año del campo EFiscalDocsExpirationDate no es relevante; la renovación ocurre cada año en ese mismo mes.
"""


def _construir_prompt_usuario(rows: list, dias: int) -> str:
    total    = len(rows)
    urgentes = [r for r in rows if 0 <= (r.get("DiasParaVencer") or 999) <= 7]

    resumen_rapido = (
        f"Consulta ejecutada: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Ventana revisada: próximos {dias} días (por mes de vencimiento eFiscalDocs)\n"
        f"Empresas con Licenciamiento a renovar: {total}\n"
        f"  - Urgentes (≤ 7 días): {len(urgentes)}\n\n"
        f"Datos completos:\n"
    )
    return resumen_rapido + json.dumps(rows, indent=2, ensure_ascii=False, default=str)


async def run_licencias_check(config: dict | None = None) -> dict:
    """
    Ejecuta el chequeo de licencias por vencer.

    config: dict con agent_id, session_id, dias, ttl.
            Si es None usa settings (compatibilidad hacia atrás).

    Retorna dict con: success, timestamp, total, reporte, error (si falla).
    """
    # Resolver configuración efectiva
    if config is None:
        config = {
            "agent_id":  settings.CRON_LICENCIAS_AGENT_ID or "default",
            "session_id": settings.CRON_LICENCIAS_SESSION_ID,
            "dias":       settings.CRON_LICENCIAS_DIAS,
            "ttl":        settings.CRON_LICENCIAS_TTL,
        }

    agent_id   = config["agent_id"]
    session_id = config.get("session_id", "licencias_diario")
    dias       = config.get("dias", 30)
    ttl        = config.get("ttl", 604800)

    timestamp  = datetime.now(timezone.utc).isoformat()
    t_inicio   = time.monotonic()
    logger.info(f"[CRON licencias] agent={agent_id} — iniciando chequeo, próximos {dias} días")

    def _duracion_ms() -> int:
        return int((time.monotonic() - t_inicio) * 1000)

    def _log_error(msg: str) -> dict:
        from ..db_platform import insert_cron_log
        insert_cron_log(agent_id=agent_id, success=False, duracion_ms=_duracion_ms(), error=msg)
        logger.error(f"[CRON licencias] agent={agent_id} — {msg}")
        return {"success": False, "timestamp": timestamp, "agent_id": agent_id, "error": msg}

    # ── 1. Consultar MySQL: Licenciamiento + mes de EFiscalDocsExpirationDate ─
    try:
        from ..db_platform import get_licencias_efiscal_por_mes
        rows = get_licencias_efiscal_por_mes(dias=dias)
    except Exception as e:
        return _log_error(f"Error consultando licencias eFiscalDocs: {str(e)})")
    logger.info(f"[CRON licencias] agent={agent_id} — {len(rows)} licencias encontradas")

    # ── 2. Generar reporte con LLM ────────────────────────────────────────
    if not rows:
        reporte = (
            f"✅ Reporte eFiscalDocs Licenciamiento — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n"
            f"No hay empresas con Licenciamiento cuyo mes de renovación eFiscalDocs "
            f"caiga en los próximos {dias} días."
        )
    else:
        try:
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": _construir_prompt_usuario(rows, dias)},
            ]
            reporte = ollama_chat(messages, temperature=0.2, model=settings.CHAT_MODEL)
        except Exception as e:
            logger.warning(f"[CRON licencias] agent={agent_id} — LLM no disponible, usando fallback: {e}")
            reporte = _reporte_fallback(rows, dias, timestamp)

    # ── 3a. Guardar en Redis (clave por agente) ───────────────────────────
    payload = {
        "timestamp":        timestamp,
        "agent_id":         agent_id,
        "dias_consultados": dias,
        "total":            len(rows),
        "rows":             rows,
        "reporte":          reporte,
    }
    try:
        redis = get_redis_client()
        redis.set(redis_key_reporte(agent_id), json.dumps(payload, default=str), ex=ttl)
        logger.info(f"[CRON licencias] agent={agent_id} — reporte guardado en Redis (TTL {ttl}s)")
    except Exception as e:
        logger.error(f"[CRON licencias] agent={agent_id} — error guardando en Redis: {e}")

    # ── 3b. Guardar como mensaje en la sesión del agente ──────────────────
    if agent_id and agent_id != "default":
        try:
            redis = get_redis_client()
            key = f"chat_session:{agent_id}:{session_id}"

            # Mensaje 1 — datos crudos completos para que el agente tenga todos los campos
            # (emails, RUCs, fechas exactas) sin depender del resumen del LLM
            datos_crudos = (
                f"A continuación los datos completos de licencias por vencer "
                f"(próximos {dias} días). Úsalos como fuente de verdad para responder "
                f"cualquier pregunta sobre empresas, contactos o fechas:\n\n"
                + json.dumps(rows, indent=2, ensure_ascii=False, default=str)
            ) if rows else f"No hay licencias por vencer en los próximos {dias} días."

            msg_datos  = json.dumps({"role": "user",      "content": datos_crudos})
            msg_reporte = json.dumps({"role": "assistant", "content": reporte})

            redis.delete(key)
            redis.rpush(key, msg_datos)   # raw JSON primero
            redis.rpush(key, msg_reporte) # reporte formateado segundo
            redis.expire(key, ttl)
            logger.info(f"[CRON licencias] agent={agent_id} — sesión guardada → session={session_id}")
        except Exception as e:
            logger.error(f"[CRON licencias] agent={agent_id} — error guardando sesión: {e}")

    # ── 4. Notificar por WhatsApp si está configurado ─────────────────────
    wa_phone   = config.get("wa_notify_phone")
    wa_session = config.get("wa_notify_session")
    if not wa_phone or not wa_session:
        logger.info(
            f"[CRON licencias] agent={agent_id} — sin notificación WA "
            f"(wa_notify_phone={wa_phone!r}, wa_notify_session={wa_session!r})"
        )
    else:
        from ..whatsapp_client import wa_send_message
        import os as _os
        logger.info(
            f"[CRON licencias] agent={agent_id} — enviando WA a {wa_phone} "
            f"vía sesión {wa_session} (WHATSAPP_API_URL={_os.getenv('WHATSAPP_API_URL','http://localhost:3001')})"
        )
        try:
            await wa_send_message(wa_session, wa_phone, reporte)
            logger.info(f"[CRON licencias] agent={agent_id} — WA enviado OK a {wa_phone}")
        except Exception as e:
            logger.error(f"[CRON licencias] agent={agent_id} — ERROR enviando WA a {wa_phone}: {e}")

    # ── 5. Guardar en log de ejecuciones ─────────────────────────────────
    try:
        from ..db_platform import insert_cron_log
        insert_cron_log(
            agent_id=agent_id,
            success=True,
            total_licencias=len(rows),
            duracion_ms=_duracion_ms(),
            reporte=reporte,
        )
    except Exception as e:
        logger.warning(f"[CRON licencias] agent={agent_id} — no se pudo guardar log: {e}")

    logger.info(f"[CRON licencias] agent={agent_id} — completado en {_duracion_ms()}ms, {len(rows)} licencias")
    return {"success": True, "timestamp": timestamp, "agent_id": agent_id, "total": len(rows), "reporte": reporte}


def _reporte_fallback(rows: list, dias: int, timestamp: str) -> str:
    """Reporte en texto plano cuando Ollama no está disponible."""
    MESES = {
        1:"Ene", 2:"Feb", 3:"Mar", 4:"Abr", 5:"May", 6:"Jun",
        7:"Jul", 8:"Ago", 9:"Sep", 10:"Oct", 11:"Nov", 12:"Dic",
    }
    lines = [
        f"📋 Renovaciones eFiscalDocs — Clientes Licenciamiento — {timestamp[:10]}",
        f"Ventana: próximos {dias} días (por mes)  |  Total: {len(rows)} empresas\n",
    ]
    for r in rows:
        dias_v = r.get("DiasParaVencer")
        mes    = MESES.get(r.get("MesVencimiento", 0), "—")
        estado = f"⚠️ {dias_v}d" if dias_v is not None and dias_v <= 7 else (f"{dias_v}d" if dias_v is not None else "—")
        lines.append(
            f"• {r.get('CompanyName', '?')} (RUC: {r.get('CompanyRUC', '?')})\n"
            f"  Vence mes: {mes}  |  Próxima fecha: {r.get('ProximaFechaVencimiento', '—')} [{estado}]\n"
            f"  eFiscalDocs count: {r.get('EFiscalDocsCount', 0)}  |  "
            f"Contacto: {r.get('ContactEmail', '—')}"
        )
    return "\n".join(lines)
