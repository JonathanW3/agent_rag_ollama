import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..redis_client import get_redis_client
from ..cron.licencias_cron import run_licencias_check, redis_key_reporte
from ..cron.scheduler import add_licencias_job, remove_licencias_job, list_licencias_jobs
from ..db_platform import (
    list_cron_licencias,
    get_cron_licencias,
    upsert_cron_licencias,
    set_cron_licencias_active,
    delete_cron_licencias,
    list_cron_logs,
    get_cron_log_detail,
)

router = APIRouter(prefix="/cron/licencias", tags=["⏰ Cron Licencias Ecuador"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class CronLicenciasUpsert(BaseModel):
    agent_id:          str       = Field(...,  description="ID del agente que ejecuta el cron", example="correosec")
    session_id:        str       = Field("licencias_diario", description="ID de sesión donde guardar el reporte")
    hora:              int       = Field(8,    ge=0,  le=23,  description="Hora de ejecución (0-23)")
    minuto:            int       = Field(0,    ge=0,  le=59,  description="Minuto de ejecución (0-59)")
    timezone:          str       = Field("America/Guayaquil", description="Zona horaria IANA")
    dias:              int       = Field(30,   ge=1,  le=365, description="Días hacia adelante a consultar")
    ttl:               int       = Field(604800, ge=1,        description="TTL del reporte en Redis (segundos)")
    is_active:         bool      = Field(True,  description="Habilitar job en el scheduler al guardar")
    wa_notify_phone:   str | None = Field(None, description="Número WhatsApp destino del reporte (ej: +5491112345678)")
    wa_notify_session: str | None = Field(None, description="ID de sesión WhatsApp para enviar la notificación")


class CronLicenciasUpdate(BaseModel):
    session_id:        str  | None = Field(None)
    hora:              int  | None = Field(None, ge=0,  le=23)
    minuto:            int  | None = Field(None, ge=0,  le=59)
    timezone:          str  | None = Field(None)
    dias:              int  | None = Field(None, ge=1,  le=365)
    ttl:               int  | None = Field(None, ge=1)
    is_active:         bool | None = Field(None)
    wa_notify_phone:   str  | None = Field(None, description="Número WhatsApp destino del reporte")
    wa_notify_session: str  | None = Field(None, description="ID de sesión WhatsApp para enviar la notificación")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sync_scheduler(cfg: dict) -> None:
    """Sincroniza el scheduler con el estado is_active del registro."""
    if cfg["is_active"]:
        add_licencias_job(cfg)
    else:
        remove_licencias_job(cfg["agent_id"])


# ── Endpoints — configuraciones ───────────────────────────────────────────────

@router.get("/configs", summary="Listar todas las configuraciones de cron")
def listar_configs():
    """Devuelve todas las configuraciones registradas y el estado de cada job en el scheduler."""
    try:
        configs = list_cron_licencias()
        jobs    = {j["agent_id"]: j for j in list_licencias_jobs()}
        for cfg in configs:
            cfg["next_run"] = jobs.get(cfg["agent_id"], {}).get("next_run")
        return {"total": len(configs), "configs": configs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configs", summary="Crear o reemplazar configuración de cron")
def crear_config(body: CronLicenciasUpsert):
    """
    Crea o reemplaza completamente la configuración para un agente.
    Si is_active=True registra el job en el scheduler de inmediato.
    """
    try:
        cfg = upsert_cron_licencias(
            agent_id=body.agent_id,
            session_id=body.session_id,
            hora=body.hora,
            minuto=body.minuto,
            timezone=body.timezone,
            dias=body.dias,
            ttl=body.ttl,
            is_active=body.is_active,
            wa_notify_phone=body.wa_notify_phone,
            wa_notify_session=body.wa_notify_session,
        )
        _sync_scheduler(cfg)
        return cfg
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configs/{agent_id}", summary="Obtener configuración de un agente")
def obtener_config(agent_id: str):
    cfg = get_cron_licencias(agent_id)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"No existe configuración para agent_id='{agent_id}'")
    jobs = {j["agent_id"]: j for j in list_licencias_jobs()}
    cfg["next_run"] = jobs.get(agent_id, {}).get("next_run")
    return cfg


@router.patch("/configs/{agent_id}", summary="Actualizar parcialmente la configuración de un agente")
def actualizar_config(agent_id: str, body: CronLicenciasUpdate):
    """Actualiza solo los campos enviados. El resto se mantiene igual."""
    existing = get_cron_licencias(agent_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"No existe configuración para agent_id='{agent_id}'")

    merged = {
        "agent_id":          agent_id,
        "session_id":        body.session_id        if body.session_id        is not None else existing["session_id"],
        "hora":              body.hora              if body.hora              is not None else existing["hora"],
        "minuto":            body.minuto            if body.minuto            is not None else existing["minuto"],
        "timezone":          body.timezone          if body.timezone          is not None else existing["timezone"],
        "dias":              body.dias              if body.dias              is not None else existing["dias"],
        "ttl":               body.ttl               if body.ttl               is not None else existing["ttl"],
        "is_active":         body.is_active         if body.is_active         is not None else existing["is_active"],
        "wa_notify_phone":   body.wa_notify_phone   if body.wa_notify_phone   is not None else existing.get("wa_notify_phone"),
        "wa_notify_session": body.wa_notify_session if body.wa_notify_session is not None else existing.get("wa_notify_session"),
    }
    try:
        cfg = upsert_cron_licencias(**merged)
        _sync_scheduler(cfg)
        return cfg
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/configs/{agent_id}", summary="Eliminar configuración de un agente")
def eliminar_config(agent_id: str):
    """Elimina la configuración y cancela el job del scheduler si estaba activo."""
    existing = get_cron_licencias(agent_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"No existe configuración para agent_id='{agent_id}'")
    try:
        remove_licencias_job(agent_id)
        delete_cron_licencias(agent_id)
        return {"eliminado": True, "agent_id": agent_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configs/{agent_id}/activar", summary="Activar el cron de un agente")
def activar(agent_id: str):
    cfg = get_cron_licencias(agent_id)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"No existe configuración para agent_id='{agent_id}'")
    set_cron_licencias_active(agent_id, True)
    cfg["is_active"] = True
    add_licencias_job(cfg)
    return {"agent_id": agent_id, "is_active": True, "mensaje": "Job activado en el scheduler"}


@router.post("/configs/{agent_id}/desactivar", summary="Suspender el cron de un agente")
def desactivar(agent_id: str):
    cfg = get_cron_licencias(agent_id)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"No existe configuración para agent_id='{agent_id}'")
    set_cron_licencias_active(agent_id, False)
    remove_licencias_job(agent_id)
    return {"agent_id": agent_id, "is_active": False, "mensaje": "Job suspendido en el scheduler"}


# ── Endpoints — ejecución y reportes ─────────────────────────────────────────

@router.post("/configs/{agent_id}/ejecutar", summary="Ejecutar manualmente el cron de un agente")
async def ejecutar_por_agente(agent_id: str):
    """Lanza el chequeo de forma inmediata para el agente indicado."""
    cfg = get_cron_licencias(agent_id)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"No existe configuración para agent_id='{agent_id}'")
    try:
        return await run_licencias_check(config=cfg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configs/{agent_id}/ultimo-reporte", summary="Último reporte del agente")
def ultimo_reporte_por_agente(agent_id: str):
    """Devuelve el último reporte generado por el cron del agente indicado."""
    try:
        redis = get_redis_client()
        raw   = redis.get(redis_key_reporte(agent_id))
        if not raw:
            return {
                "encontrado": False,
                "agent_id":   agent_id,
                "mensaje":    "Aún no se ha ejecutado el cron o el reporte expiró.",
            }
        return {"encontrado": True, **json.loads(raw)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configs/{agent_id}/logs", summary="Historial de ejecuciones de un agente")
def historial_ejecuciones(agent_id: str, limit: int = 50):
    """
    Devuelve las últimas N ejecuciones del cron para el agente indicado.
    El campo `reporte_resumen` muestra los primeros 500 caracteres del reporte.
    Usa GET /cron/licencias/logs/{log_id} para ver el reporte completo de una ejecución.
    """
    try:
        logs = list_cron_logs(agent_id=agent_id, limit=limit)
        return {"agent_id": agent_id, "total": len(logs), "logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs/{log_id}", summary="Detalle completo de una ejecución")
def detalle_log(log_id: int):
    """Devuelve el reporte completo de una ejecución específica (por su id del log)."""
    try:
        entry = get_cron_log_detail(log_id)
        if not entry:
            raise HTTPException(status_code=404, detail=f"No existe log con id={log_id}")
        return entry
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs", summary="Jobs activos en el scheduler")
def listar_jobs():
    """Lista los jobs de licencias actualmente registrados en APScheduler."""
    return {"jobs": list_licencias_jobs()}


# ── Endpoints legacy (compatibilidad hacia atrás) ─────────────────────────────

@router.post("/ejecutar", summary="[Legacy] Ejecutar el chequeo manualmente (primer agente activo)")
async def ejecutar_cron_legacy():
    """Compatibilidad con versiones anteriores. Usa el primer config activo disponible."""
    configs = list_cron_licencias(only_active=True)
    if not configs:
        raise HTTPException(status_code=404, detail="No hay configuraciones activas. Crea una en POST /cron/licencias/configs")
    try:
        return await run_licencias_check(config=configs[0])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ultimo-reporte", summary="[Legacy] Último reporte (primer agente activo)")
def ultimo_reporte_legacy():
    """Compatibilidad con versiones anteriores. Devuelve el reporte del primer agente activo."""
    configs = list_cron_licencias(only_active=True)
    if not configs:
        return {
            "encontrado": False,
            "mensaje": "No hay configuraciones activas.",
        }
    agent_id = configs[0]["agent_id"]
    try:
        redis = get_redis_client()
        raw   = redis.get(redis_key_reporte(agent_id))
        if not raw:
            return {"encontrado": False, "agent_id": agent_id, "mensaje": "El cron aún no se ha ejecutado."}
        return {"encontrado": True, **json.loads(raw)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
