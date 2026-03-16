"""
Servidor MCP MySQL - farmacia_db

Servidor de solo lectura (SELECT) para consultar la base de datos farmacia_db.
Tablas disponibles:
  - farmacia        : locales con nombre, dirección, comuna, teléfono
  - medicamento     : catálogo con laboratorio, clase terapéutica, precio
  - stock           : inventario por local con alertas (OK / STOCK BAJO / SIN STOCK)
  - historial_compra: transacciones con cantidad, precio, método pago, receta
  - usuario         : clientes con condición crónica, plan de salud, tipo cliente
"""

import json
import os
from typing import Any, Dict, List, Optional

import mysql.connector
from mysql.connector import pooling

from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
    ListToolsResult,
)

# ---------------------------------------------------------------------------
# Configuración de conexión (variables de entorno con valores por defecto)
# ---------------------------------------------------------------------------
MYSQL_HOST     = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT     = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER     = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "!qazxsW#123")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "farmacia_db")

# Palabras clave que NO se permiten (solo SELECT)
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
    """Abre una conexión a farmacia_db."""
    return mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
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
        # Convertir tipos no serializables (Decimal, datetime, etc.)
        for row in rows:
            for k, v in row.items():
                if hasattr(v, "isoformat"):          # datetime / date
                    row[k] = v.isoformat()
                elif hasattr(v, "__float__"):         # Decimal
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

class MySQLMCPServer:
    """Servidor MCP de solo lectura para farmacia_db (MySQL)."""

    def __init__(self):
        self.server = Server("mysql-farmacia-mcp-server")
        self._register_handlers()

    def _register_handlers(self):

        @self.server.list_tools()
        async def list_tools() -> ListToolsResult:
            return ListToolsResult(tools=[

                # ── 1. Consulta libre ────────────────────────────────────────
                Tool(
                    name="query_farmacia",
                    description=(
                        "Ejecuta cualquier consulta SELECT en farmacia_db. "
                        "Úsala cuando necesites cruzar varias tablas o hacer "
                        "consultas personalizadas. SOLO SELECT, sin escritura."
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

                # ── 2. Esquema de la BD ──────────────────────────────────────
                Tool(
                    name="get_schema_farmacia",
                    description="Retorna el esquema completo de farmacia_db: tablas, columnas y tipos.",
                    inputSchema={"type": "object", "properties": {}}
                ),

                # ── 3. Buscar medicamento ────────────────────────────────────
                Tool(
                    name="buscar_medicamento",
                    description=(
                        "Busca medicamentos por nombre (búsqueda parcial), "
                        "laboratorio o clase terapéutica. "
                        "Retorna nombre, laboratorio, concentración, forma farmacéutica, precio."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "nombre": {
                                "type": "string",
                                "description": "Nombre o parte del nombre del medicamento"
                            },
                            "laboratorio": {
                                "type": "string",
                                "description": "Nombre del laboratorio (opcional)"
                            },
                            "clase_terapeutica": {
                                "type": "string",
                                "description": "Clase terapéutica (opcional)"
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

                # ── 4. Verificar stock por farmacia ──────────────────────────
                Tool(
                    name="verificar_stock",
                    description=(
                        "Consulta el stock de un medicamento en una o todas las farmacias. "
                        "Retorna local, cantidad, stock mínimo y alerta."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "medicamento_nombre": {
                                "type": "string",
                                "description": "Nombre o parte del nombre del medicamento"
                            },
                            "local_id": {
                                "type": "integer",
                                "description": "ID del local (opcional, si se omite retorna todos los locales)"
                            },
                            "solo_disponibles": {
                                "type": "boolean",
                                "description": "Si true, excluye los locales con SIN STOCK",
                                "default": False
                            }
                        },
                        "required": ["medicamento_nombre"]
                    }
                ),

                # ── 5. Alertas de stock ──────────────────────────────────────
                Tool(
                    name="alertas_stock",
                    description=(
                        "Lista todos los registros con alerta 'STOCK BAJO' o 'SIN STOCK'. "
                        "Puede filtrar por local o por tipo de alerta."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "local_id": {
                                "type": "integer",
                                "description": "Filtrar por ID de local (opcional)"
                            },
                            "tipo_alerta": {
                                "type": "string",
                                "enum": ["STOCK BAJO", "SIN STOCK", "TODOS"],
                                "description": "Tipo de alerta a consultar (default: TODOS)",
                                "default": "TODOS"
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

                # ── 6. Historial de ventas ───────────────────────────────────
                Tool(
                    name="historial_ventas",
                    description=(
                        "Consulta el historial de compras. Permite filtrar por local, "
                        "medicamento, usuario, rango de fechas o método de pago."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "local_id": {
                                "type": "integer",
                                "description": "ID del local (opcional)"
                            },
                            "medicamento_nombre": {
                                "type": "string",
                                "description": "Nombre o parte del medicamento (opcional)"
                            },
                            "fecha_desde": {
                                "type": "string",
                                "description": "Fecha inicio formato YYYY-MM-DD (opcional)"
                            },
                            "fecha_hasta": {
                                "type": "string",
                                "description": "Fecha fin formato YYYY-MM-DD (opcional)"
                            },
                            "metodo_pago": {
                                "type": "string",
                                "description": "Método de pago (opcional)"
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

                # ── 7. Top medicamentos vendidos ─────────────────────────────
                Tool(
                    name="top_medicamentos",
                    description=(
                        "Retorna los medicamentos más vendidos ordenados por cantidad total "
                        "o por ingresos generados. Puede filtrar por local y periodo."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "local_id": {
                                "type": "integer",
                                "description": "Filtrar por local (opcional)"
                            },
                            "fecha_desde": {
                                "type": "string",
                                "description": "Fecha inicio YYYY-MM-DD (opcional)"
                            },
                            "fecha_hasta": {
                                "type": "string",
                                "description": "Fecha fin YYYY-MM-DD (opcional)"
                            },
                            "ordenar_por": {
                                "type": "string",
                                "enum": ["cantidad", "ingresos"],
                                "description": "Criterio de orden (default: cantidad)",
                                "default": "cantidad"
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

                # ── 8. Resumen por farmacia ──────────────────────────────────
                Tool(
                    name="resumen_farmacia",
                    description=(
                        "Retorna un resumen de KPIs por farmacia: total ventas, "
                        "ingresos, medicamentos distintos vendidos y alertas de stock activas."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "local_id": {
                                "type": "integer",
                                "description": "ID del local (opcional, si se omite retorna todos)"
                            }
                        },
                        "required": []
                    }
                ),

                # ── 9. Buscar cliente / usuario ──────────────────────────────
                Tool(
                    name="buscar_usuario",
                    description=(
                        "Busca clientes por nombre, email, condición crónica, "
                        "plan de salud o tipo de cliente."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "nombre": {
                                "type": "string",
                                "description": "Nombre o parte del nombre del usuario (opcional)"
                            },
                            "condicion_cronica": {
                                "type": "string",
                                "description": "Condición crónica (opcional)"
                            },
                            "plan_salud": {
                                "type": "string",
                                "description": "Plan de salud (opcional)"
                            },
                            "tipo_cliente": {
                                "type": "string",
                                "description": "Tipo de cliente (opcional)"
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
            ])

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> CallToolResult:
            try:
                if name == "query_farmacia":
                    result = self._query_farmacia(arguments)
                elif name == "get_schema_farmacia":
                    result = self._get_schema()
                elif name == "buscar_medicamento":
                    result = self._buscar_medicamento(arguments)
                elif name == "verificar_stock":
                    result = self._verificar_stock(arguments)
                elif name == "alertas_stock":
                    result = self._alertas_stock(arguments)
                elif name == "historial_ventas":
                    result = self._historial_ventas(arguments)
                elif name == "top_medicamentos":
                    result = self._top_medicamentos(arguments)
                elif name == "resumen_farmacia":
                    result = self._resumen_farmacia(arguments)
                elif name == "buscar_usuario":
                    result = self._buscar_usuario(arguments)
                else:
                    result = {"error": f"Herramienta desconocida: {name}"}

                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
                )
            except Exception as e:
                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))],
                    isError=True
                )

    # -----------------------------------------------------------------------
    # Implementaciones de cada herramienta
    # -----------------------------------------------------------------------

    def _query_farmacia(self, args: Dict) -> Dict:
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
                [MYSQL_DATABASE]
            )
            tables = [r["TABLE_NAME"] for r in cursor.fetchall()]
            for table in tables:
                cursor.execute(
                    "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, COLUMN_DEFAULT "
                    "FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
                    [MYSQL_DATABASE, table]
                )
                schema[table] = cursor.fetchall()
            return {"success": True, "database": MYSQL_DATABASE, "tables": schema}
        except mysql.connector.Error as e:
            return {"error": f"Error MySQL: {e.msg}"}
        finally:
            if conn and conn.is_connected():
                conn.close()

    def _buscar_medicamento(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        nombre = args.get("nombre", "").strip()
        if nombre:
            conditions.append("m.medicamento LIKE %s")
            params.append(f"%{nombre}%")

        laboratorio = args.get("laboratorio", "").strip()
        if laboratorio:
            conditions.append("m.laboratorio LIKE %s")
            params.append(f"%{laboratorio}%")

        clase = args.get("clase_terapeutica", "").strip()
        if clase:
            conditions.append("m.clase_terapeutica LIKE %s")
            params.append(f"%{clase}%")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit = int(args.get("limit", 20))

        query = f"""
            SELECT m.medicamento_id,
                   m.medicamento,
                   m.laboratorio,
                   m.clase_terapeutica,
                   m.concentracion,
                   m.forma_farmaceutica,
                   m.empaque,
                   m.precio,
                   m.restriccion_hospitalaria
            FROM medicamento m
            {where}
            ORDER BY m.medicamento
            LIMIT %s
        """
        params.append(limit)
        return _execute_select(query, params)

    def _verificar_stock(self, args: Dict) -> Dict:
        nombre = args.get("medicamento_nombre", "").strip()
        local_id = args.get("local_id")
        solo_disponibles = args.get("solo_disponibles", False)

        conditions = ["m.medicamento LIKE %s"]
        params: List[Any] = [f"%{nombre}%"]

        if local_id is not None:
            conditions.append("s.local_id = %s")
            params.append(int(local_id))

        if solo_disponibles:
            conditions.append("s.alerta != 'SIN STOCK'")

        where = "WHERE " + " AND ".join(conditions)
        query = f"""
            SELECT f.local_nombre,
                   f.comuna_nombre,
                   m.medicamento,
                   m.concentracion,
                   s.cantidad_stock,
                   s.stock_minimo,
                   s.ultima_actualizacion,
                   s.alerta
            FROM stock s
            JOIN farmacia f ON f.local_id = s.local_id
            JOIN medicamento m ON m.medicamento_id = s.medicamento_id
            {where}
            ORDER BY s.alerta DESC, f.local_nombre
        """
        return _execute_select(query, params)

    def _alertas_stock(self, args: Dict) -> Dict:
        local_id = args.get("local_id")
        tipo_alerta = args.get("tipo_alerta", "TODOS")
        limit = int(args.get("limit", 50))

        conditions = []
        params: List[Any] = []

        if tipo_alerta == "STOCK BAJO":
            conditions.append("s.alerta = 'STOCK BAJO'")
        elif tipo_alerta == "SIN STOCK":
            conditions.append("s.alerta = 'SIN STOCK'")
        else:
            conditions.append("s.alerta IN ('STOCK BAJO', 'SIN STOCK')")

        if local_id is not None:
            conditions.append("s.local_id = %s")
            params.append(int(local_id))

        where = "WHERE " + " AND ".join(conditions)
        params.append(limit)

        query = f"""
            SELECT f.local_nombre,
                   f.comuna_nombre,
                   m.medicamento,
                   m.concentracion,
                   s.cantidad_stock,
                   s.stock_minimo,
                   s.alerta,
                   s.ultima_actualizacion
            FROM stock s
            JOIN farmacia f ON f.local_id = s.local_id
            JOIN medicamento m ON m.medicamento_id = s.medicamento_id
            {where}
            ORDER BY s.alerta DESC, f.local_nombre, m.medicamento
            LIMIT %s
        """
        return _execute_select(query, params)

    def _historial_ventas(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        if args.get("local_id"):
            conditions.append("h.local_id = %s")
            params.append(int(args["local_id"]))

        if args.get("medicamento_nombre", "").strip():
            conditions.append("m.medicamento LIKE %s")
            params.append(f"%{args['medicamento_nombre'].strip()}%")

        if args.get("fecha_desde", "").strip():
            conditions.append("h.fecha_compra >= %s")
            params.append(args["fecha_desde"].strip())

        if args.get("fecha_hasta", "").strip():
            conditions.append("h.fecha_compra <= %s")
            params.append(args["fecha_hasta"].strip() + " 23:59:59")

        if args.get("metodo_pago", "").strip():
            conditions.append("h.metodo_pago LIKE %s")
            params.append(f"%{args['metodo_pago'].strip()}%")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit = int(args.get("limit", 50))
        params.append(limit)

        query = f"""
            SELECT h.compra_id,
                   f.local_nombre,
                   m.medicamento,
                   m.concentracion,
                   h.cantidad,
                   h.precio_unitario,
                   h.total_compra,
                   h.metodo_pago,
                   h.tipo_receta,
                   h.fecha_compra
            FROM historial_compra h
            JOIN farmacia f ON f.local_id = h.local_id
            JOIN medicamento m ON m.medicamento_id = h.medicamento_id
            {where}
            ORDER BY h.fecha_compra DESC
            LIMIT %s
        """
        return _execute_select(query, params)

    def _top_medicamentos(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        if args.get("local_id"):
            conditions.append("h.local_id = %s")
            params.append(int(args["local_id"]))

        if args.get("fecha_desde", "").strip():
            conditions.append("h.fecha_compra >= %s")
            params.append(args["fecha_desde"].strip())

        if args.get("fecha_hasta", "").strip():
            conditions.append("h.fecha_compra <= %s")
            params.append(args["fecha_hasta"].strip() + " 23:59:59")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        ordenar_por = args.get("ordenar_por", "cantidad")
        order_col = "total_cantidad DESC" if ordenar_por == "cantidad" else "total_ingresos DESC"
        limit = int(args.get("limit", 10))
        params.append(limit)

        query = f"""
            SELECT m.medicamento,
                   m.laboratorio,
                   m.clase_terapeutica,
                   SUM(h.cantidad)     AS total_cantidad,
                   SUM(h.total_compra) AS total_ingresos
            FROM historial_compra h
            JOIN medicamento m ON m.medicamento_id = h.medicamento_id
            {where}
            GROUP BY h.medicamento_id, m.medicamento, m.laboratorio, m.clase_terapeutica
            ORDER BY {order_col}
            LIMIT %s
        """
        return _execute_select(query, params)

    def _resumen_farmacia(self, args: Dict) -> Dict:
        local_id = args.get("local_id")
        conditions_h = []
        conditions_s = []
        params_h: List[Any] = []
        params_s: List[Any] = []

        if local_id is not None:
            conditions_h.append("h.local_id = %s")
            params_h.append(int(local_id))
            conditions_s.append("s.local_id = %s")
            params_s.append(int(local_id))

        where_h = ("WHERE " + " AND ".join(conditions_h)) if conditions_h else ""
        where_s = ("WHERE " + " AND ".join(conditions_s) + " AND s.alerta != 'OK'") if conditions_s else "WHERE s.alerta != 'OK'"

        ventas_query = f"""
            SELECT f.local_id,
                   f.local_nombre,
                   f.comuna_nombre,
                   COUNT(h.compra_id)       AS total_ventas,
                   SUM(h.total_compra)      AS total_ingresos,
                   COUNT(DISTINCT h.medicamento_id) AS medicamentos_distintos
            FROM farmacia f
            LEFT JOIN historial_compra h ON h.local_id = f.local_id
            {where_h}
            GROUP BY f.local_id, f.local_nombre, f.comuna_nombre
            ORDER BY total_ingresos DESC
        """
        ventas = _execute_select(ventas_query, params_h)

        alertas_query = f"""
            SELECT s.local_id,
                   COUNT(*) AS total_alertas,
                   SUM(CASE WHEN s.alerta = 'SIN STOCK'  THEN 1 ELSE 0 END) AS sin_stock,
                   SUM(CASE WHEN s.alerta = 'STOCK BAJO' THEN 1 ELSE 0 END) AS stock_bajo
            FROM stock s
            {where_s}
            GROUP BY s.local_id
        """
        alertas = _execute_select(alertas_query, params_s)

        return {
            "success": True,
            "ventas": ventas.get("rows", []),
            "alertas_stock": alertas.get("rows", [])
        }

    def _buscar_usuario(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        if args.get("nombre", "").strip():
            conditions.append("u.usuario_nombre LIKE %s")
            params.append(f"%{args['nombre'].strip()}%")

        if args.get("condicion_cronica", "").strip():
            conditions.append("u.condicion_cronica LIKE %s")
            params.append(f"%{args['condicion_cronica'].strip()}%")

        if args.get("plan_salud", "").strip():
            conditions.append("u.plan_salud LIKE %s")
            params.append(f"%{args['plan_salud'].strip()}%")

        if args.get("tipo_cliente", "").strip():
            conditions.append("u.tipo_cliente LIKE %s")
            params.append(f"%{args['tipo_cliente'].strip()}%")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit = int(args.get("limit", 20))
        params.append(limit)

        query = f"""
            SELECT u.usuario_id,
                   u.usuario_nombre,
                   u.usuario_email,
                   u.genero,
                   u.comuna,
                   u.plan_salud,
                   u.condicion_cronica,
                   u.tipo_cliente,
                   u.total_compras,
                   u.fecha_ultima_visita
            FROM usuario u
            {where}
            ORDER BY u.total_compras DESC
            LIMIT %s
        """
        return _execute_select(query, params)

    def get_server(self) -> Server:
        return self.server
