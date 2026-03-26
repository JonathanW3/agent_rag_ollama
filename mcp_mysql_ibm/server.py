"""
Servidor MCP MySQL - ibm

Servidor de solo lectura (SELECT) para consultar la base de datos ibm.
Tablas disponibles:
  - credit_cards       : tarjetas de crédito (tipo, banco emisor, titular, límite)
  - bank_transactions  : transacciones bancarias (depósitos, retiros, balance)
  - employees          : datos de empleados (info personal, salario, ubicación)
  - hr_attrition       : rotación de personal (satisfacción, performance, años)
  - sales_orders       : órdenes de venta por región/país (revenue, profit, costos)
"""

import json
import os
from typing import Any, Dict, List, Optional

import mysql.connector

from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
    ListToolsResult,
)

# ---------------------------------------------------------------------------
# Configuración de conexión — reutiliza credenciales MySQL, DB distinta
# ---------------------------------------------------------------------------
IBM_MYSQL_HOST     = os.getenv("IBM_MYSQL_HOST", os.getenv("MYSQL_HOST", "localhost"))
IBM_MYSQL_PORT     = int(os.getenv("IBM_MYSQL_PORT", os.getenv("MYSQL_PORT", "3306")))
IBM_MYSQL_USER     = os.getenv("IBM_MYSQL_USER", os.getenv("MYSQL_USER", "root"))
IBM_MYSQL_PASSWORD = os.getenv("IBM_MYSQL_PASSWORD", os.getenv("MYSQL_PASSWORD", ""))
IBM_MYSQL_DATABASE = os.getenv("IBM_MYSQL_DATABASE", "ibm")

# Palabras clave bloqueadas (solo SELECT)
_BLOCKED_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "REPLACE", "CALL", "GRANT", "REVOKE", "LOCK",
}


def _is_select_only(query: str) -> bool:
    """Verifica que la consulta sea solo SELECT."""
    first_word = query.strip().split()[0].upper()
    if first_word != "SELECT":
        return False
    upper = query.upper()
    for kw in _BLOCKED_KEYWORDS:
        if kw in upper:
            return False
    return True


def _get_connection() -> mysql.connector.MySQLConnection:
    """Abre una conexión a la base de datos ibm."""
    return mysql.connector.connect(
        host=IBM_MYSQL_HOST,
        port=IBM_MYSQL_PORT,
        user=IBM_MYSQL_USER,
        password=IBM_MYSQL_PASSWORD,
        database=IBM_MYSQL_DATABASE,
        charset="utf8mb4",
    )


def _execute_select(query: str, params: Optional[List] = None) -> Dict[str, Any]:
    """Ejecuta un SELECT y retorna filas como lista de diccionarios."""
    if not _is_select_only(query):
        return {"error": "Solo se permiten consultas SELECT. Operaciones de escritura no están permitidas."}

    conn = None
    try:
        conn = _get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or [])
        rows = cursor.fetchall()
        for row in rows:
            for k, v in row.items():
                if hasattr(v, "isoformat"):
                    row[k] = v.isoformat()
                elif hasattr(v, "__float__"):
                    row[k] = float(v)
        return {"success": True, "rows": rows, "count": len(rows)}
    except mysql.connector.Error as e:
        return {"error": f"Error MySQL [{e.errno}]: {e.msg}"}
    finally:
        if conn and conn.is_connected():
            conn.close()


# ---------------------------------------------------------------------------
# Clase principal del servidor MCP
# ---------------------------------------------------------------------------

class IBMMCPServer:
    """Servidor MCP de solo lectura para la base de datos ibm (MySQL)."""

    def __init__(self):
        self.server = Server("mysql-ibm-mcp-server")
        self._register_handlers()

    def _register_handlers(self):

        @self.server.list_tools()
        async def list_tools() -> ListToolsResult:
            return ListToolsResult(tools=[

                # ══════════════════════════════════════════════════════════════
                # TOOLS GENERALES
                # ══════════════════════════════════════════════════════════════

                # ── 1. Consulta libre ─────────────────────────────────────────
                Tool(
                    name="query_ibm",
                    description=(
                        "Ejecuta cualquier consulta SELECT en la base de datos ibm. "
                        "Tablas: credit_cards, bank_transactions, employees, hr_attrition, sales_orders. "
                        "SOLO SELECT, sin escritura."
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
                                "description": "Parámetros para placeholders %s (opcional)",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["query"]
                    }
                ),

                # ── 2. Esquema de la BD ───────────────────────────────────────
                Tool(
                    name="get_schema_ibm",
                    description="Retorna el esquema completo de la base de datos ibm: tablas, columnas y tipos.",
                    inputSchema={"type": "object", "properties": {}}
                ),

                # ── 3. Listar tablas ──────────────────────────────────────────
                Tool(
                    name="list_tables_ibm",
                    description="Lista todas las tablas disponibles en la base de datos ibm con su conteo de filas.",
                    inputSchema={"type": "object", "properties": {}}
                ),

                # ══════════════════════════════════════════════════════════════
                # TOOLS — credit_cards
                # ══════════════════════════════════════════════════════════════

                # ── 4. Buscar tarjeta ─────────────────────────────────────────
                Tool(
                    name="buscar_tarjeta",
                    description=(
                        "Busca tarjetas de crédito por titular, banco emisor o tipo de tarjeta. "
                        "Retorna tipo, banco, titular, fecha expiración y límite de crédito."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "titular": {
                                "type": "string",
                                "description": "Nombre o parte del nombre del titular (opcional)"
                            },
                            "banco": {
                                "type": "string",
                                "description": "Banco emisor (ej: U.S. Bancorp, American Express) (opcional)"
                            },
                            "tipo_tarjeta": {
                                "type": "string",
                                "description": "Tipo de tarjeta: VI (Visa), AX (Amex), MC (Mastercard), etc. (opcional)"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Máximo de resultados (default 20)",
                                "default": 20
                            }
                        },
                        "required": []
                    }
                ),

                # ── 5. Resumen tarjetas por banco ─────────────────────────────
                Tool(
                    name="resumen_tarjetas",
                    description=(
                        "Resumen estadístico de tarjetas de crédito agrupado por banco emisor o tipo. "
                        "Retorna cantidad de tarjetas, límite promedio, mínimo y máximo."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agrupar_por": {
                                "type": "string",
                                "enum": ["banco", "tipo"],
                                "description": "Agrupar por banco emisor o tipo de tarjeta (default: banco)",
                                "default": "banco"
                            }
                        },
                        "required": []
                    }
                ),

                # ══════════════════════════════════════════════════════════════
                # TOOLS — bank_transactions
                # ══════════════════════════════════════════════════════════════

                # ── 6. Buscar transacciones ───────────────────────────────────
                Tool(
                    name="buscar_transaccion",
                    description=(
                        "Busca transacciones bancarias por descripción, rango de fechas o tipo "
                        "(depósito/retiro). Retorna fecha, descripción, depósitos, retiros y balance."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "descripcion": {
                                "type": "string",
                                "description": "Texto en la descripción de la transacción (opcional)"
                            },
                            "fecha_desde": {
                                "type": "string",
                                "description": "Fecha inicio YYYY-MM-DD (opcional)"
                            },
                            "fecha_hasta": {
                                "type": "string",
                                "description": "Fecha fin YYYY-MM-DD (opcional)"
                            },
                            "tipo": {
                                "type": "string",
                                "enum": ["deposito", "retiro", "todos"],
                                "description": "Filtrar solo depósitos o retiros (default: todos)",
                                "default": "todos"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Máximo de resultados (default 50)",
                                "default": 50
                            }
                        },
                        "required": []
                    }
                ),

                # ── 7. Resumen transacciones ──────────────────────────────────
                Tool(
                    name="resumen_transacciones",
                    description=(
                        "Resumen de transacciones bancarias: total depósitos, total retiros, "
                        "balance final y número de transacciones. Puede filtrar por rango de fechas."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "fecha_desde": {
                                "type": "string",
                                "description": "Fecha inicio YYYY-MM-DD (opcional)"
                            },
                            "fecha_hasta": {
                                "type": "string",
                                "description": "Fecha fin YYYY-MM-DD (opcional)"
                            }
                        },
                        "required": []
                    }
                ),

                # ══════════════════════════════════════════════════════════════
                # TOOLS — employees
                # ══════════════════════════════════════════════════════════════

                # ── 8. Buscar empleado ────────────────────────────────────────
                Tool(
                    name="buscar_empleado",
                    description=(
                        "Busca empleados por nombre, estado, ciudad o rango salarial. "
                        "Retorna datos personales, cargo, salario y ubicación."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "nombre": {
                                "type": "string",
                                "description": "Nombre o apellido del empleado (opcional)"
                            },
                            "estado": {
                                "type": "string",
                                "description": "Estado/State (ej: OH, DC, CA) (opcional)"
                            },
                            "ciudad": {
                                "type": "string",
                                "description": "Ciudad (opcional)"
                            },
                            "salario_min": {
                                "type": "number",
                                "description": "Salario mínimo (opcional)"
                            },
                            "salario_max": {
                                "type": "number",
                                "description": "Salario máximo (opcional)"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Máximo de resultados (default 20)",
                                "default": 20
                            }
                        },
                        "required": []
                    }
                ),

                # ── 9. Resumen empleados ──────────────────────────────────────
                Tool(
                    name="resumen_empleados",
                    description=(
                        "Estadísticas de empleados agrupadas por estado, región o género. "
                        "Retorna cantidad, salario promedio, mínimo y máximo."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agrupar_por": {
                                "type": "string",
                                "enum": ["estado", "region", "genero"],
                                "description": "Criterio de agrupación (default: region)",
                                "default": "region"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Máximo de resultados (default 20)",
                                "default": 20
                            }
                        },
                        "required": []
                    }
                ),

                # ══════════════════════════════════════════════════════════════
                # TOOLS — hr_attrition
                # ══════════════════════════════════════════════════════════════

                # ── 10. Análisis de attrition ─────────────────────────────────
                Tool(
                    name="analisis_attrition",
                    description=(
                        "Analiza la rotación de personal (attrition). Filtra por departamento, "
                        "rol, nivel de satisfacción o si hubo attrition (Yes/No)."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "attrition": {
                                "type": "string",
                                "enum": ["Yes", "No", "todos"],
                                "description": "Filtrar por attrition Yes/No (default: todos)",
                                "default": "todos"
                            },
                            "departamento": {
                                "type": "string",
                                "description": "Departamento (ej: Sales, Support, Research & Development) (opcional)"
                            },
                            "rol": {
                                "type": "string",
                                "description": "Rol/JobRole (ej: Sales Executive, Manager) (opcional)"
                            },
                            "overtime": {
                                "type": "string",
                                "enum": ["Yes", "No", "todos"],
                                "description": "Filtrar por overtime (default: todos)",
                                "default": "todos"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Máximo de resultados (default 50)",
                                "default": 50
                            }
                        },
                        "required": []
                    }
                ),

                # ── 11. Attrition por departamento ────────────────────────────
                Tool(
                    name="attrition_por_departamento",
                    description=(
                        "Resumen de attrition agrupado por departamento o rol. "
                        "Retorna total empleados, cantidad con attrition, tasa de rotación, "
                        "ingreso mensual promedio y satisfacción promedio."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agrupar_por": {
                                "type": "string",
                                "enum": ["departamento", "rol", "overtime", "estado_civil"],
                                "description": "Criterio de agrupación (default: departamento)",
                                "default": "departamento"
                            }
                        },
                        "required": []
                    }
                ),

                # ── 12. Factores de attrition ─────────────────────────────────
                Tool(
                    name="factores_attrition",
                    description=(
                        "Compara promedios de factores clave entre empleados con y sin attrition: "
                        "satisfacción, ingreso, distancia al trabajo, años en la empresa, overtime, etc."
                    ),
                    inputSchema={"type": "object", "properties": {}}
                ),

                # ══════════════════════════════════════════════════════════════
                # TOOLS — sales_orders
                # ══════════════════════════════════════════════════════════════

                # ── 13. Buscar órdenes ────────────────────────────────────────
                Tool(
                    name="buscar_orden",
                    description=(
                        "Busca órdenes de venta por región, país, tipo de producto, "
                        "canal de venta o rango de fechas."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "region": {
                                "type": "string",
                                "description": "Región (ej: Europe, Asia, Sub-Saharan Africa) (opcional)"
                            },
                            "pais": {
                                "type": "string",
                                "description": "País (opcional)"
                            },
                            "tipo_producto": {
                                "type": "string",
                                "description": "Tipo de producto/Item Type (ej: Office Supplies, Beverages) (opcional)"
                            },
                            "canal": {
                                "type": "string",
                                "enum": ["Online", "Offline", "todos"],
                                "description": "Canal de venta (default: todos)",
                                "default": "todos"
                            },
                            "fecha_desde": {
                                "type": "string",
                                "description": "Fecha inicio YYYY-MM-DD (opcional)"
                            },
                            "fecha_hasta": {
                                "type": "string",
                                "description": "Fecha fin YYYY-MM-DD (opcional)"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Máximo de resultados (default 50)",
                                "default": 50
                            }
                        },
                        "required": []
                    }
                ),

                # ── 14. Ventas por región ─────────────────────────────────────
                Tool(
                    name="ventas_por_region",
                    description=(
                        "Resumen de ventas agrupado por región, país o tipo de producto. "
                        "Retorna total órdenes, unidades vendidas, revenue total, costo total y profit."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agrupar_por": {
                                "type": "string",
                                "enum": ["region", "pais", "producto", "canal", "prioridad"],
                                "description": "Criterio de agrupación (default: region)",
                                "default": "region"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Máximo de resultados (default 20)",
                                "default": 20
                            }
                        },
                        "required": []
                    }
                ),

                # ── 15. Top productos vendidos ────────────────────────────────
                Tool(
                    name="top_productos",
                    description=(
                        "Ranking de tipos de producto por unidades vendidas, revenue o profit. "
                        "Puede filtrar por región o canal de venta."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "region": {
                                "type": "string",
                                "description": "Filtrar por región (opcional)"
                            },
                            "canal": {
                                "type": "string",
                                "enum": ["Online", "Offline", "todos"],
                                "description": "Canal de venta (default: todos)",
                                "default": "todos"
                            },
                            "ordenar_por": {
                                "type": "string",
                                "enum": ["unidades", "revenue", "profit"],
                                "description": "Criterio de orden (default: revenue)",
                                "default": "revenue"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Máximo de resultados (default 10)",
                                "default": 10
                            }
                        },
                        "required": []
                    }
                ),

                # ── 16. Resumen general ventas ────────────────────────────────
                Tool(
                    name="resumen_ventas",
                    description=(
                        "KPIs generales de ventas: total órdenes, unidades, revenue, costo, "
                        "profit y margen promedio. Puede filtrar por región o rango de fechas."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "region": {
                                "type": "string",
                                "description": "Filtrar por región (opcional)"
                            },
                            "fecha_desde": {
                                "type": "string",
                                "description": "Fecha inicio YYYY-MM-DD (opcional)"
                            },
                            "fecha_hasta": {
                                "type": "string",
                                "description": "Fecha fin YYYY-MM-DD (opcional)"
                            }
                        },
                        "required": []
                    }
                ),
            ])

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> CallToolResult:
            try:
                dispatch = {
                    "query_ibm":                  self._query_ibm,
                    "get_schema_ibm":             lambda _: self._get_schema(),
                    "list_tables_ibm":            lambda _: self._list_tables(),
                    "buscar_tarjeta":             self._buscar_tarjeta,
                    "resumen_tarjetas":           self._resumen_tarjetas,
                    "buscar_transaccion":         self._buscar_transaccion,
                    "resumen_transacciones":      self._resumen_transacciones,
                    "buscar_empleado":            self._buscar_empleado,
                    "resumen_empleados":          self._resumen_empleados,
                    "analisis_attrition":         self._analisis_attrition,
                    "attrition_por_departamento": self._attrition_por_departamento,
                    "factores_attrition":         lambda _: self._factores_attrition(),
                    "buscar_orden":               self._buscar_orden,
                    "ventas_por_region":          self._ventas_por_region,
                    "top_productos":              self._top_productos,
                    "resumen_ventas":             self._resumen_ventas,
                }
                fn = dispatch.get(name)
                if fn is None:
                    result = {"error": f"Herramienta desconocida: {name}"}
                else:
                    result = fn(arguments)

                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
                )
            except Exception as e:
                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))],
                    isError=True
                )

    # -----------------------------------------------------------------------
    # TOOLS GENERALES
    # -----------------------------------------------------------------------

    def _query_ibm(self, args: Dict) -> Dict:
        query = args.get("query", "").strip()
        params = args.get("params", [])
        return _execute_select(query, params)

    def _get_schema(self) -> Dict:
        schema = {}
        conn = None
        try:
            conn = _get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT TABLE_NAME FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s ORDER BY TABLE_NAME",
                [IBM_MYSQL_DATABASE]
            )
            tables = [r["TABLE_NAME"] for r in cursor.fetchall()]
            for table in tables:
                cursor.execute(
                    "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, COLUMN_DEFAULT "
                    "FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
                    [IBM_MYSQL_DATABASE, table]
                )
                schema[table] = cursor.fetchall()
            return {"success": True, "database": IBM_MYSQL_DATABASE, "tables": schema}
        except mysql.connector.Error as e:
            return {"error": f"Error MySQL: {e.msg}"}
        finally:
            if conn and conn.is_connected():
                conn.close()

    def _list_tables(self) -> Dict:
        conn = None
        try:
            conn = _get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT TABLE_NAME, TABLE_ROWS "
                "FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s ORDER BY TABLE_NAME",
                [IBM_MYSQL_DATABASE]
            )
            tables = cursor.fetchall()
            return {"success": True, "database": IBM_MYSQL_DATABASE, "tables": tables}
        except mysql.connector.Error as e:
            return {"error": f"Error MySQL: {e.msg}"}
        finally:
            if conn and conn.is_connected():
                conn.close()

    # -----------------------------------------------------------------------
    # TOOLS — credit_cards
    # -----------------------------------------------------------------------

    def _buscar_tarjeta(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        titular = args.get("titular", "").strip()
        if titular:
            conditions.append("`Card Holder's Name` LIKE %s")
            params.append(f"%{titular}%")

        banco = args.get("banco", "").strip()
        if banco:
            conditions.append("`Issuing Bank` LIKE %s")
            params.append(f"%{banco}%")

        tipo = args.get("tipo_tarjeta", "").strip()
        if tipo:
            conditions.append("`Card Type Code` = %s")
            params.append(tipo)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit = int(args.get("limit", 20))
        params.append(limit)

        query = f"""
            SELECT `Card Type Code`,
                   `Card Type Full Name`,
                   `Issuing Bank`,
                   `Card Holder's Name`,
                   `Issue Date`,
                   `Expiry Date`,
                   `Billing Date`,
                   `Credit Limit`
            FROM credit_cards
            {where}
            ORDER BY `Credit Limit` DESC
            LIMIT %s
        """
        return _execute_select(query, params)

    def _resumen_tarjetas(self, args: Dict) -> Dict:
        agrupar = args.get("agrupar_por", "banco")

        if agrupar == "tipo":
            group_col = "`Card Type Full Name`"
        else:
            group_col = "`Issuing Bank`"

        query = f"""
            SELECT {group_col}                     AS grupo,
                   COUNT(*)                         AS total_tarjetas,
                   ROUND(AVG(`Credit Limit`), 2)    AS limite_promedio,
                   MIN(`Credit Limit`)              AS limite_minimo,
                   MAX(`Credit Limit`)              AS limite_maximo
            FROM credit_cards
            GROUP BY {group_col}
            ORDER BY total_tarjetas DESC
        """
        return _execute_select(query)

    # -----------------------------------------------------------------------
    # TOOLS — bank_transactions
    # -----------------------------------------------------------------------

    def _buscar_transaccion(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        desc = args.get("descripcion", "").strip()
        if desc:
            conditions.append("`Description` LIKE %s")
            params.append(f"%{desc}%")

        fecha_desde = args.get("fecha_desde", "").strip()
        if fecha_desde:
            conditions.append("`Date` >= %s")
            params.append(fecha_desde)

        fecha_hasta = args.get("fecha_hasta", "").strip()
        if fecha_hasta:
            conditions.append("`Date` <= %s")
            params.append(fecha_hasta)

        tipo = args.get("tipo", "todos")
        if tipo == "deposito":
            conditions.append("`Deposits` > 0")
        elif tipo == "retiro":
            conditions.append("`Withdrawls` > 0")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit = int(args.get("limit", 50))
        params.append(limit)

        query = f"""
            SELECT `Date`,
                   `Description`,
                   `Deposits`,
                   `Withdrawls`,
                   `Balance`
            FROM bank_transactions
            {where}
            ORDER BY `Date` DESC
            LIMIT %s
        """
        return _execute_select(query, params)

    def _resumen_transacciones(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        fecha_desde = args.get("fecha_desde", "").strip()
        if fecha_desde:
            conditions.append("`Date` >= %s")
            params.append(fecha_desde)

        fecha_hasta = args.get("fecha_hasta", "").strip()
        if fecha_hasta:
            conditions.append("`Date` <= %s")
            params.append(fecha_hasta)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        query = f"""
            SELECT COUNT(*)                        AS total_transacciones,
                   ROUND(SUM(`Deposits`), 2)       AS total_depositos,
                   ROUND(SUM(`Withdrawls`), 2)     AS total_retiros,
                   ROUND(MAX(`Balance`), 2)         AS balance_maximo,
                   ROUND(MIN(`Balance`), 2)         AS balance_minimo
            FROM bank_transactions
            {where}
        """
        return _execute_select(query, params)

    # -----------------------------------------------------------------------
    # TOOLS — employees
    # -----------------------------------------------------------------------

    def _buscar_empleado(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        nombre = args.get("nombre", "").strip()
        if nombre:
            conditions.append("(CONCAT(`First Name`, ' ', `Last Name`) LIKE %s)")
            params.append(f"%{nombre}%")

        estado = args.get("estado", "").strip()
        if estado:
            conditions.append("`State` = %s")
            params.append(estado)

        ciudad = args.get("ciudad", "").strip()
        if ciudad:
            conditions.append("`City` LIKE %s")
            params.append(f"%{ciudad}%")

        salario_min = args.get("salario_min")
        if salario_min is not None:
            conditions.append("`Salary` >= %s")
            params.append(float(salario_min))

        salario_max = args.get("salario_max")
        if salario_max is not None:
            conditions.append("`Salary` <= %s")
            params.append(float(salario_max))

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit = int(args.get("limit", 20))
        params.append(limit)

        query = f"""
            SELECT `Emp ID`,
                   `First Name`,
                   `Last Name`,
                   `Gender`,
                   `E Mail`,
                   `Date of Birth`,
                   `Date of Joining`,
                   `Salary`,
                   `Last % Hike`,
                   `City`,
                   `State`,
                   `Region`
            FROM employees
            {where}
            ORDER BY `Salary` DESC
            LIMIT %s
        """
        return _execute_select(query, params)

    def _resumen_empleados(self, args: Dict) -> Dict:
        agrupar = args.get("agrupar_por", "region")
        limit = int(args.get("limit", 20))

        group_map = {
            "estado": "`State`",
            "region": "`Region`",
            "genero": "`Gender`",
        }
        group_col = group_map.get(agrupar, "`Region`")

        query = f"""
            SELECT {group_col}                     AS grupo,
                   COUNT(*)                         AS total_empleados,
                   ROUND(AVG(`Salary`), 2)          AS salario_promedio,
                   MIN(`Salary`)                    AS salario_minimo,
                   MAX(`Salary`)                    AS salario_maximo
            FROM employees
            GROUP BY {group_col}
            ORDER BY total_empleados DESC
            LIMIT %s
        """
        return _execute_select(query, [limit])

    # -----------------------------------------------------------------------
    # TOOLS — hr_attrition
    # -----------------------------------------------------------------------

    def _analisis_attrition(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        attrition = args.get("attrition", "todos")
        if attrition in ("Yes", "No"):
            conditions.append("`Attrition` = %s")
            params.append(attrition)

        dept = args.get("departamento", "").strip()
        if dept:
            conditions.append("`Department` LIKE %s")
            params.append(f"%{dept}%")

        rol = args.get("rol", "").strip()
        if rol:
            conditions.append("`JobRole` LIKE %s")
            params.append(f"%{rol}%")

        overtime = args.get("overtime", "todos")
        if overtime in ("Yes", "No"):
            conditions.append("`OverTime` = %s")
            params.append(overtime)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit = int(args.get("limit", 50))
        params.append(limit)

        query = f"""
            SELECT `Age`,
                   `Attrition`,
                   `Department`,
                   `JobRole`,
                   `MonthlyIncome`,
                   `OverTime`,
                   `JobSatisfaction`,
                   `EnvironmentSatisfaction`,
                   `YearsAtCompany`,
                   `WorkLifeBalance`,
                   `MaritalStatus`
            FROM hr_attrition
            {where}
            ORDER BY `MonthlyIncome` DESC
            LIMIT %s
        """
        return _execute_select(query, params)

    def _attrition_por_departamento(self, args: Dict) -> Dict:
        agrupar = args.get("agrupar_por", "departamento")

        group_map = {
            "departamento":  "`Department`",
            "rol":           "`JobRole`",
            "overtime":      "`OverTime`",
            "estado_civil":  "`MaritalStatus`",
        }
        group_col = group_map.get(agrupar, "`Department`")

        query = f"""
            SELECT {group_col}                                          AS grupo,
                   COUNT(*)                                              AS total_empleados,
                   SUM(CASE WHEN `Attrition` = 'Yes' THEN 1 ELSE 0 END) AS con_attrition,
                   ROUND(SUM(CASE WHEN `Attrition` = 'Yes' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2)
                                                                         AS tasa_rotacion_pct,
                   ROUND(AVG(`MonthlyIncome`), 2)                        AS ingreso_promedio,
                   ROUND(AVG(`JobSatisfaction`), 2)                      AS satisfaccion_promedio,
                   ROUND(AVG(`YearsAtCompany`), 1)                       AS anos_empresa_promedio
            FROM hr_attrition
            GROUP BY {group_col}
            ORDER BY tasa_rotacion_pct DESC
        """
        return _execute_select(query)

    def _factores_attrition(self) -> Dict:
        query = """
            SELECT `Attrition`,
                   COUNT(*)                                    AS total,
                   ROUND(AVG(`Age`), 1)                        AS edad_promedio,
                   ROUND(AVG(`MonthlyIncome`), 2)              AS ingreso_promedio,
                   ROUND(AVG(`DistanceFromHome`), 1)           AS distancia_promedio,
                   ROUND(AVG(`YearsAtCompany`), 1)             AS anos_empresa_promedio,
                   ROUND(AVG(`JobSatisfaction`), 2)            AS satisfaccion_promedio,
                   ROUND(AVG(`EnvironmentSatisfaction`), 2)    AS satisfaccion_ambiente_promedio,
                   ROUND(AVG(`WorkLifeBalance`), 2)            AS balance_vida_promedio,
                   ROUND(AVG(`TotalWorkingYears`), 1)          AS anos_experiencia_promedio,
                   ROUND(SUM(CASE WHEN `OverTime` = 'Yes' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2)
                                                               AS pct_overtime
            FROM hr_attrition
            GROUP BY `Attrition`
        """
        return _execute_select(query)

    # -----------------------------------------------------------------------
    # TOOLS — sales_orders
    # -----------------------------------------------------------------------

    def _buscar_orden(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        region = args.get("region", "").strip()
        if region:
            conditions.append("`Region` LIKE %s")
            params.append(f"%{region}%")

        pais = args.get("pais", "").strip()
        if pais:
            conditions.append("`Country` LIKE %s")
            params.append(f"%{pais}%")

        tipo = args.get("tipo_producto", "").strip()
        if tipo:
            conditions.append("`Item Type` LIKE %s")
            params.append(f"%{tipo}%")

        canal = args.get("canal", "todos")
        if canal in ("Online", "Offline"):
            conditions.append("`Sales Channel` = %s")
            params.append(canal)

        fecha_desde = args.get("fecha_desde", "").strip()
        if fecha_desde:
            conditions.append("`Order Date` >= %s")
            params.append(fecha_desde)

        fecha_hasta = args.get("fecha_hasta", "").strip()
        if fecha_hasta:
            conditions.append("`Order Date` <= %s")
            params.append(fecha_hasta)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit = int(args.get("limit", 50))
        params.append(limit)

        query = f"""
            SELECT `Region`,
                   `Country`,
                   `Item Type`,
                   `Sales Channel`,
                   `Order Priority`,
                   `Order Date`,
                   `Order ID`,
                   `Ship Date`,
                   `Units Sold`,
                   `Total Revenue`,
                   `Total Cost`,
                   `Total Profit`
            FROM sales_orders
            {where}
            ORDER BY `Order Date` DESC
            LIMIT %s
        """
        return _execute_select(query, params)

    def _ventas_por_region(self, args: Dict) -> Dict:
        agrupar = args.get("agrupar_por", "region")
        limit = int(args.get("limit", 20))

        group_map = {
            "region":    "`Region`",
            "pais":      "`Country`",
            "producto":  "`Item Type`",
            "canal":     "`Sales Channel`",
            "prioridad": "`Order Priority`",
        }
        group_col = group_map.get(agrupar, "`Region`")

        query = f"""
            SELECT {group_col}                             AS grupo,
                   COUNT(*)                                 AS total_ordenes,
                   SUM(`Units Sold`)                        AS total_unidades,
                   ROUND(SUM(`Total Revenue`), 2)           AS total_revenue,
                   ROUND(SUM(`Total Cost`), 2)              AS total_costo,
                   ROUND(SUM(`Total Profit`), 2)            AS total_profit,
                   ROUND(SUM(`Total Profit`) * 100.0 / NULLIF(SUM(`Total Revenue`), 0), 2)
                                                            AS margen_pct
            FROM sales_orders
            GROUP BY {group_col}
            ORDER BY total_revenue DESC
            LIMIT %s
        """
        return _execute_select(query, [limit])

    def _top_productos(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        region = args.get("region", "").strip()
        if region:
            conditions.append("`Region` LIKE %s")
            params.append(f"%{region}%")

        canal = args.get("canal", "todos")
        if canal in ("Online", "Offline"):
            conditions.append("`Sales Channel` = %s")
            params.append(canal)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        ordenar = args.get("ordenar_por", "revenue")
        order_map = {
            "unidades": "total_unidades DESC",
            "revenue":  "total_revenue DESC",
            "profit":   "total_profit DESC",
        }
        order_col = order_map.get(ordenar, "total_revenue DESC")
        limit = int(args.get("limit", 10))
        params.append(limit)

        query = f"""
            SELECT `Item Type`                              AS producto,
                   COUNT(*)                                  AS total_ordenes,
                   SUM(`Units Sold`)                         AS total_unidades,
                   ROUND(SUM(`Total Revenue`), 2)            AS total_revenue,
                   ROUND(SUM(`Total Cost`), 2)               AS total_costo,
                   ROUND(SUM(`Total Profit`), 2)             AS total_profit
            FROM sales_orders
            {where}
            GROUP BY `Item Type`
            ORDER BY {order_col}
            LIMIT %s
        """
        return _execute_select(query, params)

    def _resumen_ventas(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        region = args.get("region", "").strip()
        if region:
            conditions.append("`Region` LIKE %s")
            params.append(f"%{region}%")

        fecha_desde = args.get("fecha_desde", "").strip()
        if fecha_desde:
            conditions.append("`Order Date` >= %s")
            params.append(fecha_desde)

        fecha_hasta = args.get("fecha_hasta", "").strip()
        if fecha_hasta:
            conditions.append("`Order Date` <= %s")
            params.append(fecha_hasta)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        query = f"""
            SELECT COUNT(*)                                  AS total_ordenes,
                   SUM(`Units Sold`)                         AS total_unidades,
                   ROUND(SUM(`Total Revenue`), 2)            AS total_revenue,
                   ROUND(SUM(`Total Cost`), 2)               AS total_costo,
                   ROUND(SUM(`Total Profit`), 2)             AS total_profit,
                   ROUND(SUM(`Total Profit`) * 100.0 / NULLIF(SUM(`Total Revenue`), 0), 2)
                                                             AS margen_promedio_pct,
                   ROUND(AVG(`Unit Price`), 2)               AS precio_unitario_promedio,
                   ROUND(AVG(`Unit Cost`), 2)                AS costo_unitario_promedio
            FROM sales_orders
            {where}
        """
        return _execute_select(query, params)

    def get_server(self) -> Server:
        return self.server
