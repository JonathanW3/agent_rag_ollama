"""
Cron job para sincronización incremental de facturas IMAP → MySQL.
Se registra en el scheduler de APScheduler al arrancar la app.
"""

import logging

logger = logging.getLogger("cron.imap_facturas")


async def run_imap_facturas_sync() -> None:
    """Ejecuta la sync en un thread pool para no bloquear el event loop."""
    import asyncio
    from mcp_imap_facturas.sync import sync_imap_facturas

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, sync_imap_facturas)
        logger.info(
            f"[CRON IMAP_FACTURAS] Sync completada: "
            f"procesados={result['processed']} facturas={result['facturas']} "
            f"comunicaciones={result['comunicaciones']} errores={result['errors']}"
        )
    except Exception as exc:
        logger.error(f"[CRON IMAP_FACTURAS] Error en sync: {exc}")
