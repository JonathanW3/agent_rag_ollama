"""
Cliente MCP IMAP Facturas — acceso a base de datos MySQL.

El buzón IMAP se sincroniza automáticamente cada hora mediante un cron.
Este cliente consulta directamente la base de datos (platform_db) sin
abrir ninguna conexión IMAP.
"""

import asyncio
from typing import Any, Dict, Optional

from .db import facturas_en_periodo, comparar_periodos, comunicaciones_en_periodo


class IMAPFacturasClient:
    """Cliente asíncrono para consultas de facturación contra MySQL."""

    @staticmethod
    async def facturas_del_periodo(
        since_date: str,
        before_date: str,
        empresa: Optional[str] = None,
    ) -> Dict[str, Any]:
        loop = asyncio.get_event_loop()
        rows = await loop.run_in_executor(
            None, lambda: facturas_en_periodo(since_date, before_date, empresa)
        )
        records = [
            {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in row.items()}
            for row in rows
        ]
        total_importe = round(sum(float(r.get("total") or 0) for r in records), 2)
        return {
            "success": True,
            "since_date": since_date,
            "before_date": before_date,
            **({"empresa_filtro": empresa} if empresa else {}),
            "count": len(records),
            "total_importe": total_importe,
            "facturas": records,
        }

    @staticmethod
    async def comparar_periodos_facturas(
        period_a_start: str,
        period_a_end: str,
        period_b_start: str,
        period_b_end: str,
    ) -> Dict[str, Any]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: comparar_periodos(
                period_a_start, period_a_end,
                period_b_start, period_b_end,
            ),
        )
        import json
        return json.loads(json.dumps(result, default=str))

    @staticmethod
    async def comunicaciones_del_periodo(
        since_date: str,
        before_date: str,
        empresa: Optional[str] = None,
    ) -> Dict[str, Any]:
        loop = asyncio.get_event_loop()
        rows = await loop.run_in_executor(
            None, lambda: comunicaciones_en_periodo(since_date, before_date, empresa)
        )
        records = [
            {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in row.items()}
            for row in rows
        ]
        return {
            "success": True,
            "since_date": since_date,
            "before_date": before_date,
            **({"empresa_filtro": empresa} if empresa else {}),
            "count": len(records),
            "comunicaciones": records,
        }

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Interfaz genérica para invocar tools por nombre."""
        dispatch = {
            "facturas_del_periodo":      lambda a: self.facturas_del_periodo(**a),
            "comparar_periodos_facturas": lambda a: self.comparar_periodos_facturas(**a),
            "comunicaciones_del_periodo": lambda a: self.comunicaciones_del_periodo(**a),
        }
        fn = dispatch.get(tool_name)
        if fn is None:
            return {
                "success": False,
                "error": (
                    f"Herramienta desconocida: {tool_name!r}. "
                    "Disponibles: facturas_del_periodo, comparar_periodos_facturas, comunicaciones_del_periodo"
                ),
            }
        return await fn(arguments)


# ── Singleton global ──────────────────────────────────────────────────────────

_client: Optional[IMAPFacturasClient] = None


def get_imap_facturas_client() -> IMAPFacturasClient:
    global _client
    if _client is None:
        _client = IMAPFacturasClient()
    return _client
