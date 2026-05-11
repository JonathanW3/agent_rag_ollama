"""
Cron: Sincronización de licencias SQL Server → MySQL platform_db

Flujo:
  1. Consulta mcp_sqlserver (SQL Server) con _QUERY_LICENCIAS_ECUADOR
  2. Hace upsert en licencias_ecuador de platform_db (MySQL)
     Preserva el campo Licenciamiento de registros existentes.

Se ejecuta 2 veces al día: 8:00 y 14:00 (timezone configurable).
"""

import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger("cron.sync_licencias")


async def run_sync_licencias() -> dict:
    """Ejecuta la sincronización SQL Server → MySQL. Retorna dict con resultado."""
    timestamp = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()
    logger.info("[SYNC licencias] Iniciando sincronización SQL Server → MySQL")

    # ── 1. Consultar SQL Server ───────────────────────────────────────────
    try:
        from mcp_sqlserver.server import _execute_raw, _QUERY_LICENCIAS_ECUADOR
        result = _execute_raw(_QUERY_LICENCIAS_ECUADOR)
    except Exception as e:
        msg = f"Error consultando SQL Server: {e}"
        logger.error(f"[SYNC licencias] {msg}")
        return {"success": False, "timestamp": timestamp, "error": msg}

    if "error" in result:
        logger.error(f"[SYNC licencias] Error en query: {result['error']}")
        return {"success": False, "timestamp": timestamp, "error": result["error"]}

    rows = result.get("rows", [])
    logger.info(f"[SYNC licencias] {len(rows)} empresas obtenidas de SQL Server")

    # ── 2. Upsert en MySQL ────────────────────────────────────────────────
    try:
        from app.db_platform import upsert_licencias_ecuador
        synced = upsert_licencias_ecuador(rows)
    except Exception as e:
        msg = f"Error en upsert MySQL: {e}"
        logger.error(f"[SYNC licencias] {msg}")
        return {"success": False, "timestamp": timestamp, "error": msg}

    ms = int((time.monotonic() - t0) * 1000)
    logger.info(f"[SYNC licencias] Completado: {synced} empresas en {ms}ms")
    return {"success": True, "timestamp": timestamp, "synced": synced, "duration_ms": ms}
