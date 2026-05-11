"""
Router del cron del meta-agente.

Cada sub-agente vinculado al meta-agente (LicenciasEC, CorreosEC, etc.)
puede tener su propia configuración de cron: horario, consulta predefinida,
estrategia de deduplicación y destino WhatsApp.

El job dispara run_meta_agent_check() que:
  1. Llama al sub-agente con la consulta configurada.
  2. Evalúa si la respuesta tiene datos útiles.
  3. Aplica dedup (hash o date).
  4. Formatea para WhatsApp y envía solo si hay algo nuevo.
"""

import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..redis_client import get_redis_client
from ..cron.meta_agent_cron import run_meta_agent_check, _redis_key_hash
from ..cron.scheduler import add_meta_agent_job, remove_meta_agent_job, list_meta_agent_jobs
from ..db_platform import (
    list_cron_meta_agent,
    get_cron_meta_agent,
    upsert_cron_meta_agent,
    set_cron_meta_agent_active,
    delete_cron_meta_agent,
    list_cron_meta_agent_logs,
    get_cron_meta_agent_log_detail,
)

router = APIRouter(prefix="/cron/meta-agent", tags=["⏰ Cron Meta-Agente"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class CronMetaAgentUpsert(BaseModel):
    agent_id: str = Field(
        ...,
        description="ID del sub-agente (LicenciasEC, CorreosEC, etc.)",
        example="LicenciasEC",
    )
    query: str = Field(
        ...,
        description="Consulta predefinida que el cron ejecutará en cada disparo",
        example="¿Qué licencias vencen en los próximos 7 días?",
    )
    session_id: str = Field(
        "cron_meta",
        description="ID de sesión Redis donde se guardará el historial",
    )
    hora: int = Field(8, ge=0, le=23, description="Hora de ejecución (0-23)")
    minuto: int = Field(0, ge=0, le=59, description="Minuto de ejecución (0-59)")
    timezone: str = Field("America/Guayaquil", description="Zona horaria IANA")
    dedup_strategy: str = Field(
        "hash",
        description=(
            "Estrategia de deduplicación:\n"
            "  hash — omite si el conjunto de entidades no cambió (LicenciasEC)\n"
            "  date — la consulta filtra por hoy; sin hash adicional (CorreosEC)\n"
            "  none — envía siempre que haya datos válidos"
        ),
        example="hash",
    )
    dedup_ttl: int = Field(
        82800,
        ge=3600,
        description="TTL del hash Redis en segundos (default 23 h = 82800)",
    )
    is_active: bool = Field(True, description="Activar el job en el scheduler al guardar")
    wa_notify_phones: list[str] | None = Field(
        None,
        description="Números WhatsApp destino (sin +, solo dígitos). Acepta uno o varios.",
        example=["5930987654321", "5931234567890"],
    )
    wa_notify_session: str | None = Field(
        None,
        description="ID de sesión WhatsApp desde la que se envía",
        example="quiamawhts",
    )


class CronMetaAgentUpdate(BaseModel):
    query: str | None = Field(None)
    session_id: str | None = Field(None)
    hora: int | None = Field(None, ge=0, le=23)
    minuto: int | None = Field(None, ge=0, le=59)
    timezone: str | None = Field(None)
    dedup_strategy: str | None = Field(None)
    dedup_ttl: int | None = Field(None, ge=3600)
    is_active: bool | None = Field(None)
    wa_notify_phones: list[str] | None = Field(None)
    wa_notify_session: str | None = Field(None)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sync_scheduler(cfg: dict) -> None:
    if cfg["is_active"]:
        add_meta_agent_job(cfg)
    else:
        remove_meta_agent_job(cfg["agent_id"])


def _enrich_with_next_run(cfg: dict) -> dict:
    jobs = {j["agent_id"]: j for j in list_meta_agent_jobs()}
    cfg["next_run"] = jobs.get(cfg["agent_id"], {}).get("next_run")
    return cfg


# ── Endpoints — configuraciones ───────────────────────────────────────────────

@router.get("/configs", summary="Listar todas las configuraciones de cron del meta-agente")
def listar_configs():
    """Devuelve todas las configuraciones registradas y el próximo disparo de cada job."""
    try:
        configs = list_cron_meta_agent()
        jobs = {j["agent_id"]: j for j in list_meta_agent_jobs()}
        for cfg in configs:
            cfg["next_run"] = jobs.get(cfg["agent_id"], {}).get("next_run")
        return {"total": len(configs), "configs": configs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configs", summary="Crear o reemplazar configuración de cron")
def crear_config(body: CronMetaAgentUpsert):
    """
    Crea o reemplaza completamente la configuración para un sub-agente.
    Si is_active=True, registra el job en el scheduler de inmediato.
    """
    try:
        cfg = upsert_cron_meta_agent(
            agent_id=body.agent_id,
            query=body.query,
            session_id=body.session_id,
            hora=body.hora,
            minuto=body.minuto,
            timezone=body.timezone,
            dedup_strategy=body.dedup_strategy,
            dedup_ttl=body.dedup_ttl,
            is_active=body.is_active,
            wa_notify_phones=body.wa_notify_phones,
            wa_notify_session=body.wa_notify_session,
        )
        _sync_scheduler(cfg)
        return _enrich_with_next_run(cfg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configs/{agent_id}", summary="Obtener configuración de un sub-agente")
def obtener_config(agent_id: str):
    cfg = get_cron_meta_agent(agent_id)
    if not cfg:
        raise HTTPException(
            status_code=404,
            detail=f"No existe configuración para agent_id='{agent_id}'",
        )
    return _enrich_with_next_run(cfg)


@router.patch("/configs/{agent_id}", summary="Actualizar parcialmente la configuración")
def actualizar_config(agent_id: str, body: CronMetaAgentUpdate):
    """Actualiza solo los campos enviados; el resto se mantiene igual."""
    existing = get_cron_meta_agent(agent_id)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"No existe configuración para agent_id='{agent_id}'",
        )
    merged = {
        "agent_id":          agent_id,
        "query":             body.query             if body.query             is not None else existing["query"],
        "session_id":        body.session_id        if body.session_id        is not None else existing["session_id"],
        "hora":              body.hora              if body.hora              is not None else existing["hora"],
        "minuto":            body.minuto            if body.minuto            is not None else existing["minuto"],
        "timezone":          body.timezone          if body.timezone          is not None else existing["timezone"],
        "dedup_strategy":    body.dedup_strategy    if body.dedup_strategy    is not None else existing["dedup_strategy"],
        "dedup_ttl":         body.dedup_ttl         if body.dedup_ttl         is not None else existing["dedup_ttl"],
        "is_active":         body.is_active         if body.is_active         is not None else existing["is_active"],
        "wa_notify_phones":  body.wa_notify_phones  if body.wa_notify_phones  is not None else existing.get("wa_notify_phones"),
        "wa_notify_session": body.wa_notify_session if body.wa_notify_session is not None else existing.get("wa_notify_session"),
    }
    try:
        cfg = upsert_cron_meta_agent(**merged)
        _sync_scheduler(cfg)
        return _enrich_with_next_run(cfg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/configs/{agent_id}", summary="Eliminar configuración de un sub-agente")
def eliminar_config(agent_id: str):
    """Elimina la configuración y cancela el job del scheduler si estaba activo."""
    if not get_cron_meta_agent(agent_id):
        raise HTTPException(
            status_code=404,
            detail=f"No existe configuración para agent_id='{agent_id}'",
        )
    try:
        remove_meta_agent_job(agent_id)
        delete_cron_meta_agent(agent_id)
        return {"eliminado": True, "agent_id": agent_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configs/{agent_id}/activar", summary="Activar el cron de un sub-agente")
def activar(agent_id: str):
    cfg = get_cron_meta_agent(agent_id)
    if not cfg:
        raise HTTPException(
            status_code=404,
            detail=f"No existe configuración para agent_id='{agent_id}'",
        )
    set_cron_meta_agent_active(agent_id, True)
    cfg["is_active"] = True
    add_meta_agent_job(cfg)
    return {"agent_id": agent_id, "is_active": True, "mensaje": "Job activado en el scheduler"}


@router.post("/configs/{agent_id}/desactivar", summary="Suspender el cron de un sub-agente")
def desactivar(agent_id: str):
    cfg = get_cron_meta_agent(agent_id)
    if not cfg:
        raise HTTPException(
            status_code=404,
            detail=f"No existe configuración para agent_id='{agent_id}'",
        )
    set_cron_meta_agent_active(agent_id, False)
    remove_meta_agent_job(agent_id)
    return {"agent_id": agent_id, "is_active": False, "mensaje": "Job suspendido en el scheduler"}


# ── Endpoints — ejecución manual ─────────────────────────────────────────────

@router.post("/configs/{agent_id}/ejecutar", summary="Ejecutar manualmente el cron de un sub-agente")
async def ejecutar(agent_id: str):
    """Lanza el chequeo de forma inmediata para el sub-agente indicado."""
    cfg = get_cron_meta_agent(agent_id)
    if not cfg:
        raise HTTPException(
            status_code=404,
            detail=f"No existe configuración para agent_id='{agent_id}'",
        )
    try:
        return await run_meta_agent_check(config=cfg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configs/{agent_id}/reset-dedup", summary="Borrar hash de deduplicación (forzar próximo envío)")
def reset_dedup(agent_id: str):
    """
    Elimina el hash guardado en Redis para que en la próxima ejecución
    se envíe el reporte aunque los datos no hayan cambiado.
    Útil para forzar un reenvío manual.
    """
    if not get_cron_meta_agent(agent_id):
        raise HTTPException(
            status_code=404,
            detail=f"No existe configuración para agent_id='{agent_id}'",
        )
    try:
        redis = get_redis_client()
        deleted = redis.delete(_redis_key_hash(agent_id))
        return {
            "agent_id": agent_id,
            "hash_eliminado": bool(deleted),
            "mensaje": "El próximo disparo enviará aunque los datos no hayan cambiado.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Endpoints — logs ──────────────────────────────────────────────────────────

@router.get("/configs/{agent_id}/logs", summary="Historial de ejecuciones de un sub-agente")
def historial(agent_id: str, limit: int = 50):
    """
    Devuelve las últimas N ejecuciones.
    Los campos enviado_wa y dedup_skip indican qué ocurrió en cada disparo.
    """
    try:
        logs = list_cron_meta_agent_logs(agent_id=agent_id, limit=limit)
        return {"agent_id": agent_id, "total": len(logs), "logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs/{log_id}", summary="Reporte completo de una ejecución")
def detalle_log(log_id: int):
    try:
        entry = get_cron_meta_agent_log_detail(log_id)
        if not entry:
            raise HTTPException(status_code=404, detail=f"No existe log con id={log_id}")
        return entry
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Endpoints — estado del scheduler ─────────────────────────────────────────

@router.get("/jobs", summary="Jobs activos del meta-agente en el scheduler")
def listar_jobs():
    return {"jobs": list_meta_agent_jobs()}
