"""
Servidor MCP IMAP Facturas — herramientas de base de datos.

El buzón IMAP se sincroniza automáticamente cada hora mediante un cron.
El agente NO accede directamente al buzón; consulta la base de datos MySQL
(platform_db) que ya contiene todos los emails indexados y estructurados.

Herramientas expuestas:
  · facturas_del_periodo      — lista facturas de un período con datos completos
  · comparar_periodos_facturas — tabla comparativa entre dos períodos por empresa
  · comunicaciones_del_periodo — emails de comunicación con clientes en un período
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict

from mcp.server import Server
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    TextContent,
    Tool,
)

from .db import (
    facturas_en_periodo,
    comparar_periodos,
    comunicaciones_en_periodo,
)

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

server = Server("imap-facturas")


@server.list_tools()
async def list_tools() -> ListToolsResult:
    return ListToolsResult(
        tools=[
            Tool(
                name="facturas_del_periodo",
                description=(
                    "Lista todas las facturas electrónicas recibidas en un período. "
                    "Los datos provienen de la base de datos (sincronizada cada hora desde IMAP), "
                    "por lo que la respuesta es instantánea. "
                    "Devuelve por cada factura: empresa, RUC, subtotal, IVA, total, tipo de documento, "
                    "número, descripción del servicio/producto y fecha. "
                    "Úsala para responder preguntas como: "
                    "'¿qué facturas recibimos este mes?', "
                    "'¿cuánto pagamos a empresa X en abril?', "
                    "'muéstrame las facturas de marzo'."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "since_date": {
                            "type": "string",
                            "description": "Inicio del período inclusive (YYYY-MM-DD).",
                        },
                        "before_date": {
                            "type": "string",
                            "description": "Fin del período exclusivo (YYYY-MM-DD). "
                                           "Para 'todo abril': since_date=2026-04-01, before_date=2026-05-01.",
                        },
                        "empresa": {
                            "type": "string",
                            "description": "Filtro opcional por nombre o RUC de empresa (búsqueda parcial).",
                        },
                    },
                    "required": ["since_date", "before_date"],
                },
            ),
            Tool(
                name="comparar_periodos_facturas",
                description=(
                    "Compara las facturas recibidas entre dos períodos de tiempo y devuelve "
                    "una tabla por empresa con: cantidad de facturas y total en cada período, "
                    "y estado (OK / FALTA EN B / NUEVO EN B). "
                    "FALTA EN B = empresa que facturó en el período A pero NO en el período B "
                    "(es decir, facturas pendientes o clientes que dejaron de facturar). "
                    "Úsala para: "
                    "'¿qué empresas facturaron el mes pasado pero no este mes?', "
                    "'compara marzo vs abril', "
                    "'¿cuánto subió o bajó la facturación por empresa?'."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "period_a_start": {
                            "type": "string",
                            "description": "Inicio del período A inclusive (YYYY-MM-DD).",
                        },
                        "period_a_end": {
                            "type": "string",
                            "description": "Fin del período A exclusivo (YYYY-MM-DD).",
                        },
                        "period_b_start": {
                            "type": "string",
                            "description": "Inicio del período B inclusive (YYYY-MM-DD).",
                        },
                        "period_b_end": {
                            "type": "string",
                            "description": "Fin del período B exclusivo (YYYY-MM-DD).",
                        },
                    },
                    "required": [
                        "period_a_start", "period_a_end",
                        "period_b_start", "period_b_end",
                    ],
                },
            ),
            Tool(
                name="comunicaciones_del_periodo",
                description=(
                    "Lista los emails de comunicación con clientes/proveedores recibidos "
                    "en un período. No incluye las facturas electrónicas (esas están en "
                    "facturas_del_periodo). Devuelve: fecha, remitente, destinatarios, "
                    "asunto y cuerpo del email. "
                    "Úsala para: "
                    "'¿qué nos escribió empresa X este mes?', "
                    "'¿hubo comunicaciones en marzo?', "
                    "'muéstrame los emails de soporte recibidos'."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "since_date": {
                            "type": "string",
                            "description": "Inicio del período inclusive (YYYY-MM-DD).",
                        },
                        "before_date": {
                            "type": "string",
                            "description": "Fin del período exclusivo (YYYY-MM-DD).",
                        },
                        "empresa": {
                            "type": "string",
                            "description": "Filtro opcional: busca en remitente y asunto (búsqueda parcial).",
                        },
                    },
                    "required": ["since_date", "before_date"],
                },
            ),
        ]
    )


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    loop = asyncio.get_event_loop()
    try:
        result = await _dispatch(loop, name, arguments)
        is_error = not result.get("success", True)
    except Exception as exc:
        logger.exception("Error inesperado en tool %r", name)
        result = {"success": False, "error": str(exc)}
        is_error = True

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False, default=str))],
        isError=is_error,
    )


async def _dispatch(loop: asyncio.AbstractEventLoop, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name == "facturas_del_periodo":
        since  = args["since_date"]
        before = args["before_date"]
        empresa = args.get("empresa")
        rows = await loop.run_in_executor(
            None, lambda: facturas_en_periodo(since, before, empresa)
        )
        # Convertir dates a string para JSON
        records = [
            {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in row.items()}
            for row in rows
        ]
        total_importe = round(sum(float(r.get("total") or 0) for r in records), 2)
        return {
            "success": True,
            "since_date": since,
            "before_date": before,
            **({"empresa_filtro": empresa} if empresa else {}),
            "count": len(records),
            "total_importe": total_importe,
            "facturas": records,
        }

    if name == "comparar_periodos_facturas":
        result = await loop.run_in_executor(
            None,
            lambda: comparar_periodos(
                args["period_a_start"], args["period_a_end"],
                args["period_b_start"], args["period_b_end"],
            ),
        )
        # Serializar fechas si las hubiera
        result = json.loads(json.dumps(result, default=str))
        return result

    if name == "comunicaciones_del_periodo":
        since   = args["since_date"]
        before  = args["before_date"]
        empresa = args.get("empresa")
        rows = await loop.run_in_executor(
            None, lambda: comunicaciones_en_periodo(since, before, empresa)
        )
        records = [
            {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in row.items()}
            for row in rows
        ]
        return {
            "success": True,
            "since_date": since,
            "before_date": before,
            **({"empresa_filtro": empresa} if empresa else {}),
            "count": len(records),
            "comunicaciones": records,
        }

    return {"success": False, "error": f"Herramienta desconocida: {name!r}"}


def get_server() -> Server:
    return server


async def _run_stdio() -> None:
    from mcp.server.stdio import stdio_server

    logger.info("Iniciando servidor MCP IMAP Facturas en modo stdio...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(_run_stdio())
