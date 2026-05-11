"""
Servidor MCP SQL Server - Webpospa

Solo lectura (SELECT) sobre la base de datos webpospa.
Tabla: [webpospa].[dbo].[RegisteredLicenses]

Campos clave de búsqueda:
  - CompanyRUC        : identificador único de empresa
  - CompanyName       : nombre de la empresa
  - ExpirationDate    : vencimiento de la licencia
  - SwSExpirationDate : vencimiento del soporte de software
"""

import json
import os
from typing import Any, Dict, List, Optional

import pyodbc

from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
    ListToolsResult,
)

# ---------------------------------------------------------------------------
# Configuración de conexión
# ---------------------------------------------------------------------------
SQLSERVER_HOST     = os.getenv("SQLSERVER_HOST", r"DESKTOP-I1LPUVB\SQLEXPRESS")
SQLSERVER_DATABASE = os.getenv("SQLSERVER_DATABASE", "webpospa")
SQLSERVER_USER     = os.getenv("SQLSERVER_USER", "wpfe")
SQLSERVER_PASSWORD = os.getenv("SQLSERVER_PASSWORD", "")
SQLSERVER_DRIVER   = os.getenv("SQLSERVER_DRIVER", "ODBC Driver 17 for SQL Server")

# Palabras clave bloqueadas (solo SELECT)
_BLOCKED_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "REPLACE", "CALL", "GRANT", "REVOKE", "LOCK", "EXEC",
}

# Query principal de licencias Ecuador
_QUERY_LICENCIAS_ECUADOR = """
SELECT
    [CompanyRUC],
    MAX([CompanyName])    AS CompanyName,
    MAX([Country])        AS Country,
    MAX([ContactEmail])   AS ContactEmail,
    COUNT(*)              AS TotalLicencias,
    SUM(CASE WHEN [SubProduct] = 'eFiscalDocs Ecuador' THEN 1 ELSE 0 END)
        AS EFiscalDocsCount,
    MAX(CASE WHEN [SubProduct] = 'eFiscalDocs Ecuador' THEN [ExpirationDate] END)
        AS EFiscalDocsExpirationDate,
    (
        SELECT
            r2.[CompanyName],
            r2.[CompanyRUC],
            r2.[StorePhone],
            r2.[CreationDate],
            r2.[ExpirationDate],
            r2.[SwSExpirationDate],
            r2.[LicStatus],
            r2.[QtyOfUsers],
            r2.[Comments],
            r2.[SubProduct],
            r2.[Technician],
            r2.[ContactName],
            r2.[ContactEmail]
        FROM [webpospa].[dbo].[RegisteredLicenses] r2
        WHERE r2.[CompanyRUC] = r1.[CompanyRUC]
          AND r2.[Country] = 'Ecuador'
        ORDER BY r2.[ModDate] DESC
        FOR JSON PATH
    ) AS LicenciasJSON
FROM [webpospa].[dbo].[RegisteredLicenses] r1
WHERE [Country] = 'Ecuador'
GROUP BY [CompanyRUC]
ORDER BY MAX([ModDate]) DESC
"""


def _is_select_only(query: str) -> bool:
    first_word = query.strip().split()[0].upper()
    if first_word != "SELECT":
        return False
    upper = query.upper()
    for kw in _BLOCKED_KEYWORDS:
        if kw in upper.split():
            return False
    return True


def _get_connection() -> pyodbc.Connection:
    conn_str = (
        f"DRIVER={{{SQLSERVER_DRIVER}}};"
        f"SERVER={SQLSERVER_HOST};"
        f"DATABASE={SQLSERVER_DATABASE};"
        f"UID={SQLSERVER_USER};"
        f"PWD={SQLSERVER_PASSWORD};"
        "Encrypt=no;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, timeout=30)


def _row_to_dict(cursor, row) -> Dict[str, Any]:
    """Convierte una fila pyodbc a dict, parseando columnas JSON si aplica."""
    cols = [col[0] for col in cursor.description]
    result = {}
    for col, val in zip(cols, row):
        if isinstance(val, bytes):
            val = val.decode("utf-8", errors="replace")
        if col.endswith("JSON") and isinstance(val, str) and val:
            try:
                val = json.loads(val)
            except json.JSONDecodeError:
                pass
        if hasattr(val, "isoformat"):
            val = val.isoformat()
        result[col] = val
    return result


def _execute_select(query: str, params: Optional[List] = None) -> Dict[str, Any]:
    """Ejecuta un SELECT y retorna filas como lista de dicts."""
    if not _is_select_only(query):
        return {"error": "Solo se permiten consultas SELECT."}

    conn = None
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params or [])
        rows = [_row_to_dict(cursor, row) for row in cursor.fetchall()]
        return {"success": True, "rows": rows, "count": len(rows)}
    except pyodbc.Error as e:
        return {"error": f"Error SQL Server: {str(e)}"}
    finally:
        if conn:
            conn.close()


def _execute_raw(query: str, params: Optional[List] = None) -> Dict[str, Any]:
    """Ejecuta una query sin validación SELECT (uso interno para queries conocidas)."""
    conn = None
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params or [])
        rows = [_row_to_dict(cursor, row) for row in cursor.fetchall()]
        return {"success": True, "rows": rows, "count": len(rows)}
    except pyodbc.Error as e:
        return {"error": f"Error SQL Server: {str(e)}"}
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Clase principal del servidor MCP
# ---------------------------------------------------------------------------

class WebposMCPServer:
    """Servidor MCP de solo lectura para la base de datos webpospa (SQL Server)."""

    def __init__(self):
        self.server = Server("sqlserver-webpospa-mcp-server")
        self._register_handlers()

    def _register_handlers(self):

        @self.server.list_tools()
        async def list_tools() -> ListToolsResult:
            return ListToolsResult(tools=[

                # ── 1. Buscar empresa ──────────────────────────────────────────
                Tool(
                    name="buscar_empresa_ecuador",
                    description=(
                        "Busca empresas en Ecuador desde la base local (MySQL). "
                        "Filtra por nombre (búsqueda parcial LIKE), RUC (búsqueda parcial LIKE) "
                        "y/o tipo de contrato (Licenciamiento=true → instalación local, "
                        "Licenciamiento=false → Nube). Todos los parámetros son opcionales. "
                        "Retorna el perfil de la empresa con TotalLicencias, EFiscalDocsCount, "
                        "fechas mínimas de vencimiento y el detalle completo en LicenciasJSON."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "nombre": {
                                "type": "string",
                                "description": "Nombre de la empresa — búsqueda parcial (LIKE, insensible a mayúsculas)"
                            },
                            "ruc": {
                                "type": "string",
                                "description": "CompanyRUC — búsqueda parcial (LIKE)"
                            },
                            "licenciamiento": {
                                "type": "boolean",
                                "description": "true = Licenciamiento (local), false = Nube. Omitir para traer ambos tipos."
                            }
                        },
                        "required": []
                    }
                ),

                # ── 2. Licencias por vencer ────────────────────────────────────
                Tool(
                    name="licencias_por_vencer",
                    description=(
                        "Lista las licencias individuales de Ecuador que vencen dentro de los "
                        "próximos N días, consultando la base local (MySQL). "
                        "Incluye DiasParaExpiracion, DiasParaSwSExpiracion, LicStatus, "
                        "Technician, ContactName, ContactEmail y el flag Licenciamiento. "
                        "Útil para alertas de renovación y seguimiento comercial."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "dias": {
                                "type": "integer",
                                "description": "Días hacia adelante para buscar vencimientos (default: 45)",
                                "default": 45
                            },
                            "campo_fecha": {
                                "type": "string",
                                "enum": ["ExpirationDate", "SwSExpirationDate", "ambas"],
                                "description": "Qué fecha evaluar (default: ambas)",
                                "default": "ambas"
                            }
                        },
                        "required": []
                    }
                ),

                # ── 6. Resumen liviano por tipo de cliente ────────────────────
                Tool(
                    name="resumen_tipo_licenciamiento",
                    description=(
                        "Retorna un resumen liviano de empresas Ecuador sin el detalle de licencias. "
                        "Ideal para listar todas las empresas de un tipo (Licenciamiento u Nube) "
                        "sin saturar el contexto. "
                        "Campos: CompanyRUC, CompanyName, ContactEmail, TotalLicencias, EFiscalDocsCount, "
                        "EFiscalDocsExpirationDate, MinExpirationDate, MinSwSExpirationDate, Licenciamiento. "
                        "licenciamiento: true=on-premise, false=Nube, omitir=todos."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "licenciamiento": {
                                "type": "boolean",
                                "description": "true = Licenciamiento (on-premise), false = Nube, omitir = todos"
                            }
                        },
                        "required": []
                    }
                ),

                # ── 5. eFiscalDocs vencimiento por mes ────────────────────────
                Tool(
                    name="licencias_efiscal_por_mes",
                    description=(
                        "Lista empresas de Licenciamiento (on-premise) cuyo eFiscalDocs "
                        "vence en los próximos N días, evaluando SOLO el mes y día del campo "
                        "EFiscalDocsExpirationDate (el año es ignorado — renovación anual). "
                        "Retorna DiasParaVencer y ProximaFechaVencimiento calculados al año actual o siguiente."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "dias": {
                                "type": "integer",
                                "description": "Días hacia adelante para buscar vencimientos (default: 45)",
                                "default": 45
                            }
                        },
                        "required": []
                    }
                ),

                # ── 3. Sincronización manual ───────────────────────────────────
                Tool(
                    name="sync_licencias_ecuador",
                    description=(
                        "Fuerza una sincronización inmediata de los datos de licencias desde "
                        "SQL Server (webpospa) hacia la base local MySQL. "
                        "Normalmente el cron hace esto automáticamente a las 8:00 y 14:00. "
                        "Úsalo solo si necesitas datos actualizados ahora mismo."
                    ),
                    inputSchema={"type": "object", "properties": {}}
                ),

                # ── 4. Consulta SELECT libre (SQL Server directo) ──────────────
                Tool(
                    name="query_webpospa",
                    description=(
                        "Ejecuta cualquier consulta SELECT directamente en la base de datos "
                        "webpospa (SQL Server). Tabla principal: [webpospa].[dbo].[RegisteredLicenses]. "
                        "SOLO SELECT, sin escritura. Usa ? como placeholder para parámetros."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Consulta SQL SELECT a ejecutar"
                            },
                            "params": {
                                "type": "array",
                                "description": "Parámetros para placeholders ? (opcional)",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["query"]
                    }
                ),
            ])

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> CallToolResult:
            try:
                dispatch = {
                    "buscar_empresa_ecuador":       self._buscar_empresa_ecuador,
                    "licencias_por_vencer":         self._licencias_por_vencer,
                    "licencias_efiscal_por_mes":    self._licencias_efiscal_por_mes,
                    "resumen_tipo_licenciamiento":  self._resumen_tipo_licenciamiento,
                    "sync_licencias_ecuador":       lambda _: self._sync_licencias_ecuador(),
                    "query_webpospa":               self._query_webpospa,
                }
                fn = dispatch.get(name)
                if fn is None:
                    result = {"error": f"Herramienta desconocida: {name}"}
                else:
                    result = fn(arguments)

                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False, default=str))]
                )
            except Exception as e:
                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))],
                    isError=True
                )

    # -----------------------------------------------------------------------
    # Implementaciones de herramientas
    # -----------------------------------------------------------------------

    def _buscar_empresa_ecuador(self, args: Dict) -> Dict:
        from app.db_platform import buscar_licencias_ecuador
        nombre        = args.get("nombre", "").strip()
        ruc           = args.get("ruc", "").strip()
        licenciamiento = args.get("licenciamiento")  # bool | None

        rows = buscar_licencias_ecuador(
            nombre=nombre,
            ruc=ruc,
            licenciamiento=licenciamiento,
        )
        return {"success": True, "rows": rows, "count": len(rows)}

    def _licencias_por_vencer(self, args: Dict) -> Dict:
        from app.db_platform import get_licencias_por_vencer
        dias        = int(args.get("dias", 45))
        campo_fecha = args.get("campo_fecha", "ambas")
        rows = get_licencias_por_vencer(dias=dias, campo=campo_fecha)
        return {"success": True, "rows": rows, "count": len(rows)}

    def _licencias_efiscal_por_mes(self, args: Dict) -> Dict:
        from app.db_platform import get_licencias_efiscal_por_mes
        dias = int(args.get("dias", 45))
        rows = get_licencias_efiscal_por_mes(dias=dias)
        return {"success": True, "rows": rows, "count": len(rows)}

    def _resumen_tipo_licenciamiento(self, args: Dict) -> Dict:
        from app.db_platform import resumen_tipo_licenciamiento
        val = args.get("licenciamiento")
        if val is not None:
            val = bool(val)
        rows = resumen_tipo_licenciamiento(licenciamiento=val)
        return {"success": True, "rows": rows, "count": len(rows)}

    def _sync_licencias_ecuador(self) -> Dict:
        result = _execute_raw(_QUERY_LICENCIAS_ECUADOR)
        if "error" in result:
            return result
        from app.db_platform import upsert_licencias_ecuador
        synced = upsert_licencias_ecuador(result.get("rows", []))
        return {"success": True, "synced": synced}

    def _query_webpospa(self, args: Dict) -> Dict:
        query  = args.get("query", "").strip()
        params = args.get("params", [])
        return _execute_select(query, params)

    def get_server(self) -> Server:
        return self.server
