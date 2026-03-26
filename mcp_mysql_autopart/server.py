"""
Servidor MCP MySQL - autopart

Servidor de solo lectura (SELECT) para consultar la base de datos autopart.
Tablas disponibles:
  - vehicle_type       : tipos de vehículo
  - vehicles           : vehículos (modelo, fabricante, tipo)
  - product_category   : categorías de producto (jerárquica)
  - application_status : estados de aplicación
  - seller             : vendedores
  - applications       : publicaciones de autopartes
  - compatibility      : compatibilidad pieza-vehículo por rango de año
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
AUTOPART_MYSQL_HOST     = os.getenv("AUTOPART_MYSQL_HOST", os.getenv("MYSQL_HOST", "localhost"))
AUTOPART_MYSQL_PORT     = int(os.getenv("AUTOPART_MYSQL_PORT", os.getenv("MYSQL_PORT", "3306")))
AUTOPART_MYSQL_USER     = os.getenv("AUTOPART_MYSQL_USER", os.getenv("MYSQL_USER", "root"))
AUTOPART_MYSQL_PASSWORD = os.getenv("AUTOPART_MYSQL_PASSWORD", os.getenv("MYSQL_PASSWORD", ""))
AUTOPART_MYSQL_DATABASE = os.getenv("AUTOPART_MYSQL_DATABASE", "autopart")

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
    """Abre una conexión a la base de datos autopart."""
    return mysql.connector.connect(
        host=AUTOPART_MYSQL_HOST,
        port=AUTOPART_MYSQL_PORT,
        user=AUTOPART_MYSQL_USER,
        password=AUTOPART_MYSQL_PASSWORD,
        database=AUTOPART_MYSQL_DATABASE,
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

class AutopartMCPServer:
    """Servidor MCP de solo lectura para la base de datos autopart (MySQL)."""

    def __init__(self):
        self.server = Server("mysql-autopart-mcp-server")
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
                    name="query_autopart",
                    description=(
                        "Ejecuta cualquier consulta SELECT en la base de datos autopart. "
                        "Tablas: vehicle_type, vehicles, product_category, application_status, "
                        "seller, applications, compatibility. SOLO SELECT, sin escritura."
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
                    name="get_schema_autopart",
                    description="Retorna el esquema completo de la base de datos autopart: tablas, columnas y tipos.",
                    inputSchema={"type": "object", "properties": {}}
                ),

                # ── 3. Listar tablas ──────────────────────────────────────────
                Tool(
                    name="list_tables_autopart",
                    description="Lista todas las tablas disponibles en la base de datos autopart con su conteo de filas.",
                    inputSchema={"type": "object", "properties": {}}
                ),

                # ══════════════════════════════════════════════════════════════
                # TOOLS — vehicles / vehicle_type
                # ══════════════════════════════════════════════════════════════

                # ── 4. Buscar vehículo ────────────────────────────────────────
                Tool(
                    name="buscar_vehiculo",
                    description=(
                        "Busca vehículos por modelo, fabricante o tipo de vehículo. "
                        "Retorna modelo, fabricante y tipo de vehículo."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "modelo": {
                                "type": "string",
                                "description": "Nombre o parte del modelo (opcional)"
                            },
                            "fabricante": {
                                "type": "string",
                                "description": "Nombre del fabricante/manufacturer (opcional)"
                            },
                            "tipo_vehiculo": {
                                "type": "string",
                                "description": "Tipo de vehículo (opcional)"
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

                # ── 5. Resumen vehículos ──────────────────────────────────────
                Tool(
                    name="resumen_vehiculos",
                    description=(
                        "Resumen estadístico de vehículos agrupado por fabricante o tipo de vehículo. "
                        "Retorna cantidad de modelos por grupo."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agrupar_por": {
                                "type": "string",
                                "enum": ["fabricante", "tipo"],
                                "description": "Agrupar por fabricante o tipo de vehículo (default: fabricante)",
                                "default": "fabricante"
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
                # TOOLS — product_category
                # ══════════════════════════════════════════════════════════════

                # ── 6. Buscar categoría ───────────────────────────────────────
                Tool(
                    name="buscar_categoria",
                    description=(
                        "Busca categorías de producto por nombre. "
                        "Retorna id, nombre de categoría y categoría padre."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "nombre": {
                                "type": "string",
                                "description": "Nombre o parte del nombre de la categoría (opcional)"
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

                # ── 7. Árbol de categorías ────────────────────────────────────
                Tool(
                    name="arbol_categorias",
                    description=(
                        "Muestra la jerarquía completa de categorías de producto "
                        "(categoría padre → subcategorías). Incluye conteo de aplicaciones por categoría."
                    ),
                    inputSchema={"type": "object", "properties": {}}
                ),

                # ══════════════════════════════════════════════════════════════
                # TOOLS — seller
                # ══════════════════════════════════════════════════════════════

                # ── 8. Buscar vendedor ────────────────────────────────────────
                Tool(
                    name="buscar_vendedor",
                    description=(
                        "Busca vendedores por nombre o dirección. "
                        "Retorna nombre, dirección y teléfono."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "nombre": {
                                "type": "string",
                                "description": "Nombre o parte del nombre del vendedor (opcional)"
                            },
                            "direccion": {
                                "type": "string",
                                "description": "Texto en la dirección del vendedor (opcional)"
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

                # ── 9. Resumen vendedores ─────────────────────────────────────
                Tool(
                    name="resumen_vendedores",
                    description=(
                        "Resumen de vendedores: total de publicaciones, precio promedio (GEL y USD), "
                        "agrupado por vendedor. Retorna los vendedores con más publicaciones."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Máximo de vendedores a retornar (default 20)",
                                "default": 20
                            }
                        },
                        "required": []
                    }
                ),

                # ══════════════════════════════════════════════════════════════
                # TOOLS — applications
                # ══════════════════════════════════════════════════════════════

                # ── 10. Buscar aplicación (publicación) ───────────────────────
                Tool(
                    name="buscar_aplicacion",
                    description=(
                        "Busca publicaciones de autopartes por título, rango de precio, "
                        "estado, categoría, vendedor o condición del artículo."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "headline": {
                                "type": "string",
                                "description": "Texto en el título de la publicación (opcional)"
                            },
                            "precio_min_usd": {
                                "type": "number",
                                "description": "Precio mínimo en USD (opcional)"
                            },
                            "precio_max_usd": {
                                "type": "number",
                                "description": "Precio máximo en USD (opcional)"
                            },
                            "precio_min_gel": {
                                "type": "number",
                                "description": "Precio mínimo en GEL (opcional)"
                            },
                            "precio_max_gel": {
                                "type": "number",
                                "description": "Precio máximo en GEL (opcional)"
                            },
                            "condicion": {
                                "type": "string",
                                "description": "Condición del artículo (ej: New, Used) (opcional)"
                            },
                            "categoria": {
                                "type": "string",
                                "description": "Nombre de la categoría de producto (opcional)"
                            },
                            "vendedor": {
                                "type": "string",
                                "description": "Nombre del vendedor (opcional)"
                            },
                            "estado": {
                                "type": "string",
                                "description": "Estado de la aplicación/status_name (opcional)"
                            },
                            "fecha_desde": {
                                "type": "string",
                                "description": "Fecha inicio registro YYYY-MM-DD (opcional)"
                            },
                            "fecha_hasta": {
                                "type": "string",
                                "description": "Fecha fin registro YYYY-MM-DD (opcional)"
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

                # ── 11. Resumen aplicaciones ──────────────────────────────────
                Tool(
                    name="resumen_aplicaciones",
                    description=(
                        "Resumen estadístico de publicaciones agrupado por estado, categoría, "
                        "condición o vendedor. Retorna cantidad, precio promedio y rangos."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agrupar_por": {
                                "type": "string",
                                "enum": ["estado", "categoria", "condicion", "vendedor"],
                                "description": "Criterio de agrupación (default: estado)",
                                "default": "estado"
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

                # ── 12. Top aplicaciones por precio ───────────────────────────
                Tool(
                    name="top_aplicaciones",
                    description=(
                        "Ranking de publicaciones por precio (USD o GEL). "
                        "Puede filtrar por categoría o condición."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "categoria": {
                                "type": "string",
                                "description": "Filtrar por categoría (opcional)"
                            },
                            "condicion": {
                                "type": "string",
                                "description": "Filtrar por condición (opcional)"
                            },
                            "ordenar_por": {
                                "type": "string",
                                "enum": ["precio_usd", "precio_gel"],
                                "description": "Ordenar por precio USD o GEL (default: precio_usd)",
                                "default": "precio_usd"
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

                # ══════════════════════════════════════════════════════════════
                # TOOLS — compatibility
                # ══════════════════════════════════════════════════════════════

                # ── 13. Buscar compatibilidad ─────────────────────────────────
                Tool(
                    name="buscar_compatibilidad",
                    description=(
                        "Busca compatibilidades de piezas con vehículos. "
                        "Filtra por modelo de vehículo, fabricante, año o publicación. "
                        "Retorna la pieza, vehículo compatible y rango de años."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "modelo_vehiculo": {
                                "type": "string",
                                "description": "Modelo del vehículo (opcional)"
                            },
                            "fabricante": {
                                "type": "string",
                                "description": "Fabricante del vehículo (opcional)"
                            },
                            "anio": {
                                "type": "integer",
                                "description": "Año específico (busca dentro del rango bottom_year-top_year) (opcional)"
                            },
                            "headline": {
                                "type": "string",
                                "description": "Texto en el título de la publicación (opcional)"
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

                # ── 14. Resumen compatibilidad ────────────────────────────────
                Tool(
                    name="resumen_compatibilidad",
                    description=(
                        "Resumen de compatibilidades agrupado por fabricante, modelo o tipo de vehículo. "
                        "Retorna cantidad de piezas compatibles por grupo."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agrupar_por": {
                                "type": "string",
                                "enum": ["fabricante", "modelo", "tipo_vehiculo"],
                                "description": "Criterio de agrupación (default: fabricante)",
                                "default": "fabricante"
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
                dispatch = {
                    "query_autopart":          self._query_autopart,
                    "get_schema_autopart":     lambda _: self._get_schema(),
                    "list_tables_autopart":    lambda _: self._list_tables(),
                    "buscar_vehiculo":         self._buscar_vehiculo,
                    "resumen_vehiculos":       self._resumen_vehiculos,
                    "buscar_categoria":        self._buscar_categoria,
                    "arbol_categorias":        lambda _: self._arbol_categorias(),
                    "buscar_vendedor":         self._buscar_vendedor,
                    "resumen_vendedores":      self._resumen_vendedores,
                    "buscar_aplicacion":       self._buscar_aplicacion,
                    "resumen_aplicaciones":    self._resumen_aplicaciones,
                    "top_aplicaciones":        self._top_aplicaciones,
                    "buscar_compatibilidad":   self._buscar_compatibilidad,
                    "resumen_compatibilidad":  self._resumen_compatibilidad,
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

    def _query_autopart(self, args: Dict) -> Dict:
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
                [AUTOPART_MYSQL_DATABASE]
            )
            tables = [r["TABLE_NAME"] for r in cursor.fetchall()]
            for table in tables:
                cursor.execute(
                    "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, COLUMN_DEFAULT "
                    "FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
                    [AUTOPART_MYSQL_DATABASE, table]
                )
                schema[table] = cursor.fetchall()
            return {"success": True, "database": AUTOPART_MYSQL_DATABASE, "tables": schema}
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
                [AUTOPART_MYSQL_DATABASE]
            )
            tables = cursor.fetchall()
            return {"success": True, "database": AUTOPART_MYSQL_DATABASE, "tables": tables}
        except mysql.connector.Error as e:
            return {"error": f"Error MySQL: {e.msg}"}
        finally:
            if conn and conn.is_connected():
                conn.close()

    # -----------------------------------------------------------------------
    # TOOLS — vehicles / vehicle_type
    # -----------------------------------------------------------------------

    def _buscar_vehiculo(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        modelo = args.get("modelo", "").strip()
        if modelo:
            conditions.append("v.model_name LIKE %s")
            params.append(f"%{modelo}%")

        fabricante = args.get("fabricante", "").strip()
        if fabricante:
            conditions.append("v.manufacturer_name LIKE %s")
            params.append(f"%{fabricante}%")

        tipo = args.get("tipo_vehiculo", "").strip()
        if tipo:
            conditions.append("vt.vehicle_type_name LIKE %s")
            params.append(f"%{tipo}%")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit = int(args.get("limit", 20))
        params.append(limit)

        query = f"""
            SELECT v.id,
                   v.model_name,
                   v.manufacturer_name,
                   vt.vehicle_type_name
            FROM vehicles v
            LEFT JOIN vehicle_type vt ON v.vehicle_type_id = vt.id
            {where}
            ORDER BY v.manufacturer_name, v.model_name
            LIMIT %s
        """
        return _execute_select(query, params)

    def _resumen_vehiculos(self, args: Dict) -> Dict:
        agrupar = args.get("agrupar_por", "fabricante")
        limit = int(args.get("limit", 20))

        if agrupar == "tipo":
            group_col = "vt.vehicle_type_name"
        else:
            group_col = "v.manufacturer_name"

        query = f"""
            SELECT {group_col}  AS grupo,
                   COUNT(*)     AS total_vehiculos
            FROM vehicles v
            LEFT JOIN vehicle_type vt ON v.vehicle_type_id = vt.id
            GROUP BY {group_col}
            ORDER BY total_vehiculos DESC
            LIMIT %s
        """
        return _execute_select(query, [limit])

    # -----------------------------------------------------------------------
    # TOOLS — product_category
    # -----------------------------------------------------------------------

    def _buscar_categoria(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        nombre = args.get("nombre", "").strip()
        if nombre:
            conditions.append("c.category_name LIKE %s")
            params.append(f"%{nombre}%")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit = int(args.get("limit", 50))
        params.append(limit)

        query = f"""
            SELECT c.id,
                   c.category_name,
                   p.category_name AS parent_category_name
            FROM product_category c
            LEFT JOIN product_category p ON c.parent_category_id = p.id
            {where}
            ORDER BY c.category_name
            LIMIT %s
        """
        return _execute_select(query, params)

    def _arbol_categorias(self) -> Dict:
        query = """
            SELECT c.id,
                   c.category_name,
                   c.parent_category_id,
                   p.category_name                 AS parent_category_name,
                   COUNT(a.app_id)                  AS total_aplicaciones
            FROM product_category c
            LEFT JOIN product_category p ON c.parent_category_id = p.id
            LEFT JOIN applications a ON a.category_id = c.id
            GROUP BY c.id, c.category_name, c.parent_category_id, p.category_name
            ORDER BY p.category_name, c.category_name
        """
        return _execute_select(query)

    # -----------------------------------------------------------------------
    # TOOLS — seller
    # -----------------------------------------------------------------------

    def _buscar_vendedor(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        nombre = args.get("nombre", "").strip()
        if nombre:
            conditions.append("s.seller_name LIKE %s")
            params.append(f"%{nombre}%")

        direccion = args.get("direccion", "").strip()
        if direccion:
            conditions.append("s.address LIKE %s")
            params.append(f"%{direccion}%")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit = int(args.get("limit", 20))
        params.append(limit)

        query = f"""
            SELECT s.id,
                   s.seller_name,
                   s.address,
                   s.mobile_number
            FROM seller s
            {where}
            ORDER BY s.seller_name
            LIMIT %s
        """
        return _execute_select(query, params)

    def _resumen_vendedores(self, args: Dict) -> Dict:
        limit = int(args.get("limit", 20))

        query = """
            SELECT s.seller_name,
                   COUNT(a.app_id)                   AS total_publicaciones,
                   ROUND(AVG(a.price_usd), 2)        AS precio_promedio_usd,
                   ROUND(AVG(a.price_gel), 2)         AS precio_promedio_gel,
                   MIN(a.price_usd)                   AS precio_min_usd,
                   MAX(a.price_usd)                   AS precio_max_usd
            FROM seller s
            LEFT JOIN applications a ON a.seller_id = s.id
            GROUP BY s.id, s.seller_name
            ORDER BY total_publicaciones DESC
            LIMIT %s
        """
        return _execute_select(query, [limit])

    # -----------------------------------------------------------------------
    # TOOLS — applications
    # -----------------------------------------------------------------------

    def _buscar_aplicacion(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        headline = args.get("headline", "").strip()
        if headline:
            conditions.append("a.headline LIKE %s")
            params.append(f"%{headline}%")

        precio_min_usd = args.get("precio_min_usd")
        if precio_min_usd is not None:
            conditions.append("a.price_usd >= %s")
            params.append(float(precio_min_usd))

        precio_max_usd = args.get("precio_max_usd")
        if precio_max_usd is not None:
            conditions.append("a.price_usd <= %s")
            params.append(float(precio_max_usd))

        precio_min_gel = args.get("precio_min_gel")
        if precio_min_gel is not None:
            conditions.append("a.price_gel >= %s")
            params.append(float(precio_min_gel))

        precio_max_gel = args.get("precio_max_gel")
        if precio_max_gel is not None:
            conditions.append("a.price_gel <= %s")
            params.append(float(precio_max_gel))

        condicion = args.get("condicion", "").strip()
        if condicion:
            conditions.append("a.item_condition LIKE %s")
            params.append(f"%{condicion}%")

        categoria = args.get("categoria", "").strip()
        if categoria:
            conditions.append("pc.category_name LIKE %s")
            params.append(f"%{categoria}%")

        vendedor = args.get("vendedor", "").strip()
        if vendedor:
            conditions.append("s.seller_name LIKE %s")
            params.append(f"%{vendedor}%")

        estado = args.get("estado", "").strip()
        if estado:
            conditions.append("ast.status_name LIKE %s")
            params.append(f"%{estado}%")

        fecha_desde = args.get("fecha_desde", "").strip()
        if fecha_desde:
            conditions.append("a.app_register_date >= %s")
            params.append(fecha_desde)

        fecha_hasta = args.get("fecha_hasta", "").strip()
        if fecha_hasta:
            conditions.append("a.app_register_date <= %s")
            params.append(fecha_hasta)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit = int(args.get("limit", 50))
        params.append(limit)

        query = f"""
            SELECT a.app_id,
                   a.headline,
                   a.price_gel,
                   a.price_usd,
                   a.item_condition,
                   a.app_register_date,
                   ast.status_name,
                   pc.category_name,
                   s.seller_name,
                   a.insert_date
            FROM applications a
            LEFT JOIN application_status ast ON a.satus_id = ast.id
            LEFT JOIN product_category pc ON a.category_id = pc.id
            LEFT JOIN seller s ON a.seller_id = s.id
            {where}
            ORDER BY a.price_usd DESC
            LIMIT %s
        """
        return _execute_select(query, params)

    def _resumen_aplicaciones(self, args: Dict) -> Dict:
        agrupar = args.get("agrupar_por", "estado")
        limit = int(args.get("limit", 20))

        group_map = {
            "estado":    "ast.status_name",
            "categoria": "pc.category_name",
            "condicion": "a.item_condition",
            "vendedor":  "s.seller_name",
        }
        group_col = group_map.get(agrupar, "ast.status_name")

        query = f"""
            SELECT {group_col}                        AS grupo,
                   COUNT(*)                            AS total_publicaciones,
                   ROUND(AVG(a.price_usd), 2)          AS precio_promedio_usd,
                   ROUND(AVG(a.price_gel), 2)           AS precio_promedio_gel,
                   MIN(a.price_usd)                    AS precio_min_usd,
                   MAX(a.price_usd)                    AS precio_max_usd
            FROM applications a
            LEFT JOIN application_status ast ON a.satus_id = ast.id
            LEFT JOIN product_category pc ON a.category_id = pc.id
            LEFT JOIN seller s ON a.seller_id = s.id
            GROUP BY {group_col}
            ORDER BY total_publicaciones DESC
            LIMIT %s
        """
        return _execute_select(query, [limit])

    def _top_aplicaciones(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        categoria = args.get("categoria", "").strip()
        if categoria:
            conditions.append("pc.category_name LIKE %s")
            params.append(f"%{categoria}%")

        condicion = args.get("condicion", "").strip()
        if condicion:
            conditions.append("a.item_condition LIKE %s")
            params.append(f"%{condicion}%")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        ordenar = args.get("ordenar_por", "precio_usd")
        order_map = {
            "precio_usd": "a.price_usd DESC",
            "precio_gel": "a.price_gel DESC",
        }
        order_col = order_map.get(ordenar, "a.price_usd DESC")
        limit = int(args.get("limit", 10))
        params.append(limit)

        query = f"""
            SELECT a.app_id,
                   a.headline,
                   a.price_gel,
                   a.price_usd,
                   a.item_condition,
                   pc.category_name,
                   s.seller_name,
                   ast.status_name
            FROM applications a
            LEFT JOIN application_status ast ON a.satus_id = ast.id
            LEFT JOIN product_category pc ON a.category_id = pc.id
            LEFT JOIN seller s ON a.seller_id = s.id
            {where}
            ORDER BY {order_col}
            LIMIT %s
        """
        return _execute_select(query, params)

    # -----------------------------------------------------------------------
    # TOOLS — compatibility
    # -----------------------------------------------------------------------

    def _buscar_compatibilidad(self, args: Dict) -> Dict:
        conditions = []
        params: List[Any] = []

        modelo = args.get("modelo_vehiculo", "").strip()
        if modelo:
            conditions.append("v.model_name LIKE %s")
            params.append(f"%{modelo}%")

        fabricante = args.get("fabricante", "").strip()
        if fabricante:
            conditions.append("v.manufacturer_name LIKE %s")
            params.append(f"%{fabricante}%")

        anio = args.get("anio")
        if anio is not None:
            conditions.append("c.bottom_year <= %s AND c.top_year >= %s")
            params.append(int(anio))
            params.append(int(anio))

        headline = args.get("headline", "").strip()
        if headline:
            conditions.append("a.headline LIKE %s")
            params.append(f"%{headline}%")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit = int(args.get("limit", 50))
        params.append(limit)

        query = f"""
            SELECT a.app_id,
                   a.headline,
                   a.price_usd,
                   a.price_gel,
                   a.item_condition,
                   v.model_name,
                   v.manufacturer_name,
                   vt.vehicle_type_name,
                   c.bottom_year,
                   c.top_year
            FROM compatibility c
            INNER JOIN applications a ON c.app_id = a.app_id
            INNER JOIN vehicles v ON c.vehicles_id = v.id
            LEFT JOIN vehicle_type vt ON v.vehicle_type_id = vt.id
            {where}
            ORDER BY v.manufacturer_name, v.model_name, c.bottom_year
            LIMIT %s
        """
        return _execute_select(query, params)

    def _resumen_compatibilidad(self, args: Dict) -> Dict:
        agrupar = args.get("agrupar_por", "fabricante")
        limit = int(args.get("limit", 20))

        group_map = {
            "fabricante":     "v.manufacturer_name",
            "modelo":         "v.model_name",
            "tipo_vehiculo":  "vt.vehicle_type_name",
        }
        group_col = group_map.get(agrupar, "v.manufacturer_name")

        query = f"""
            SELECT {group_col}                        AS grupo,
                   COUNT(DISTINCT c.app_id)            AS total_piezas,
                   COUNT(DISTINCT c.vehicles_id)       AS total_vehiculos,
                   MIN(c.bottom_year)                  AS anio_minimo,
                   MAX(c.top_year)                     AS anio_maximo
            FROM compatibility c
            INNER JOIN vehicles v ON c.vehicles_id = v.id
            LEFT JOIN vehicle_type vt ON v.vehicle_type_id = vt.id
            GROUP BY {group_col}
            ORDER BY total_piezas DESC
            LIMIT %s
        """
        return _execute_select(query, [limit])

    def get_server(self) -> Server:
        return self.server
