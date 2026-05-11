"""
Módulo central del scheduler APScheduler.

Expone una instancia única del scheduler y funciones para gestionar
dinámicamente los jobs de cron de licencias (añadir, eliminar, listar).
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("cron.scheduler")

scheduler = AsyncIOScheduler()

_JOB_PREFIX = "licencias_"
_IMAP_FACTURAS_JOB_ID = "imap_facturas_sync"
_SYNC_LICENCIAS_JOB_IDS = ("sync_licencias_ecuador_8", "sync_licencias_ecuador_14")


def add_licencias_job(config: dict) -> None:
    """Registra o reemplaza el job de licencias para el agent_id del config."""
    from .licencias_cron import run_licencias_check

    agent_id = config["agent_id"]
    scheduler.add_job(
        run_licencias_check,
        CronTrigger(
            hour=config["hora"],
            minute=config["minuto"],
            timezone=config["timezone"],
        ),
        id=f"{_JOB_PREFIX}{agent_id}",
        replace_existing=True,
        kwargs={"config": config},
    )
    logger.info(
        f"[CRON] Job registrado: agent={agent_id} "
        f"{config['hora']:02d}:{config['minuto']:02d} ({config['timezone']})"
    )


def remove_licencias_job(agent_id: str) -> bool:
    """Elimina el job de licencias para un agente. Retorna True si existía."""
    job_id = f"{_JOB_PREFIX}{agent_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"[CRON] Job eliminado: agent={agent_id}")
        return True
    return False


def add_imap_facturas_job(interval_minutes: int = 60) -> None:
    """Registra el job de sync de facturas IMAP con intervalo fijo en minutos."""
    from .imap_facturas_cron import run_imap_facturas_sync
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(
        run_imap_facturas_sync,
        IntervalTrigger(minutes=interval_minutes),
        id=_IMAP_FACTURAS_JOB_ID,
        replace_existing=True,
    )
    logger.info(f"[CRON] Job imap_facturas_sync registrado — cada {interval_minutes} min")


def add_sync_licencias_jobs(timezone: str = "America/Panama") -> None:
    """Registra los jobs de sincronización SQL Server → MySQL a las 8:00 y 14:00."""
    from .sync_licencias_cron import run_sync_licencias

    for job_id, hour in zip(_SYNC_LICENCIAS_JOB_IDS, (8, 14)):
        scheduler.add_job(
            run_sync_licencias,
            CronTrigger(hour=hour, minute=0, timezone=timezone),
            id=job_id,
            replace_existing=True,
        )
        logger.info(f"[CRON] Job registrado: {job_id} a las {hour:02d}:00 ({timezone})")


def remove_sync_licencias_jobs() -> None:
    """Elimina los jobs de sincronización de licencias."""
    for job_id in _SYNC_LICENCIAS_JOB_IDS:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info(f"[CRON] Job eliminado: {job_id}")


_META_AGENT_JOB_PREFIX = "meta_agent_cron_"


def add_meta_agent_job(config: dict) -> None:
    """Registra o reemplaza el job del meta-agente para el agent_id del config."""
    from .meta_agent_cron import run_meta_agent_check

    agent_id = config["agent_id"]
    scheduler.add_job(
        run_meta_agent_check,
        CronTrigger(
            hour=config["hora"],
            minute=config["minuto"],
            timezone=config["timezone"],
        ),
        id=f"{_META_AGENT_JOB_PREFIX}{agent_id}",
        replace_existing=True,
        kwargs={"config": config},
    )
    logger.info(
        f"[CRON] Meta-agente job registrado: agent={agent_id} "
        f"{config['hora']:02d}:{config['minuto']:02d} ({config['timezone']})"
    )


def remove_meta_agent_job(agent_id: str) -> bool:
    """Elimina el job del meta-agente para un agente. Retorna True si existía."""
    job_id = f"{_META_AGENT_JOB_PREFIX}{agent_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"[CRON] Meta-agente job eliminado: agent={agent_id}")
        return True
    return False


def list_meta_agent_jobs() -> list[dict]:
    """Lista todos los jobs del meta-agente activos en el scheduler."""
    result = []
    for job in scheduler.get_jobs():
        if job.id.startswith(_META_AGENT_JOB_PREFIX):
            next_run = getattr(job, "next_run_time", None)
            result.append({
                "job_id":   job.id,
                "agent_id": job.id[len(_META_AGENT_JOB_PREFIX):],
                "next_run": next_run.isoformat() if next_run else None,
            })
    return result


def list_licencias_jobs() -> list[dict]:
    """Lista todos los jobs de licencias activos en el scheduler."""
    result = []
    for job in scheduler.get_jobs():
        if job.id.startswith(_JOB_PREFIX):
            next_run = getattr(job, "next_run_time", None)
            result.append({
                "job_id":   job.id,
                "agent_id": job.id[len(_JOB_PREFIX):],
                "next_run": next_run.isoformat() if next_run else None,
            })
    return result
