"""
Cliente MCP MySQL IBM

Permite a los agentes consultar la base de datos ibm directamente a través del servidor MCP.
Todas las operaciones son de solo lectura (SELECT).
"""

import json
from typing import Any, Dict, List, Optional

from .server import IBMMCPServer, _execute_select


class IBMMCPClient:
    """Cliente para interactuar con la base de datos ibm desde los agentes."""

    def __init__(self):
        self._server = IBMMCPServer()

    # ── Consulta libre ────────────────────────────────────────────────────
    async def query(self, query: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
        """Ejecuta un SELECT arbitrario en la base de datos ibm."""
        return _execute_select(query, params)

    # ── Esquema ───────────────────────────────────────────────────────────
    async def get_schema(self) -> Dict[str, Any]:
        """Retorna el esquema completo de la base de datos ibm."""
        return self._server._get_schema()

    # ── Tablas ────────────────────────────────────────────────────────────
    async def list_tables(self) -> Dict[str, Any]:
        """Lista todas las tablas con conteo de filas."""
        return self._server._list_tables()

    # ── Credit Cards ──────────────────────────────────────────────────────
    async def buscar_tarjeta(
        self,
        titular: str = "",
        banco: str = "",
        tipo_tarjeta: str = "",
        limit: int = 20
    ) -> Dict[str, Any]:
        """Busca tarjetas de crédito por titular, banco o tipo."""
        return self._server._buscar_tarjeta({
            "titular": titular,
            "banco": banco,
            "tipo_tarjeta": tipo_tarjeta,
            "limit": limit,
        })

    async def resumen_tarjetas(self, agrupar_por: str = "banco") -> Dict[str, Any]:
        """Resumen estadístico de tarjetas agrupado por banco o tipo."""
        return self._server._resumen_tarjetas({"agrupar_por": agrupar_por})

    # ── Bank Transactions ─────────────────────────────────────────────────
    async def buscar_transaccion(
        self,
        descripcion: str = "",
        fecha_desde: str = "",
        fecha_hasta: str = "",
        tipo: str = "todos",
        limit: int = 50
    ) -> Dict[str, Any]:
        """Busca transacciones bancarias con filtros opcionales."""
        return self._server._buscar_transaccion({
            "descripcion": descripcion,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "tipo": tipo,
            "limit": limit,
        })

    async def resumen_transacciones(
        self,
        fecha_desde: str = "",
        fecha_hasta: str = ""
    ) -> Dict[str, Any]:
        """Resumen de depósitos, retiros y balance."""
        return self._server._resumen_transacciones({
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
        })

    # ── Employees ─────────────────────────────────────────────────────────
    async def buscar_empleado(
        self,
        nombre: str = "",
        estado: str = "",
        ciudad: str = "",
        salario_min: Optional[float] = None,
        salario_max: Optional[float] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """Busca empleados por nombre, ubicación o rango salarial."""
        return self._server._buscar_empleado({
            "nombre": nombre,
            "estado": estado,
            "ciudad": ciudad,
            "salario_min": salario_min,
            "salario_max": salario_max,
            "limit": limit,
        })

    async def resumen_empleados(
        self,
        agrupar_por: str = "region",
        limit: int = 20
    ) -> Dict[str, Any]:
        """Estadísticas de empleados agrupadas por estado, región o género."""
        return self._server._resumen_empleados({
            "agrupar_por": agrupar_por,
            "limit": limit,
        })

    # ── HR Attrition ──────────────────────────────────────────────────────
    async def analisis_attrition(
        self,
        attrition: str = "todos",
        departamento: str = "",
        rol: str = "",
        overtime: str = "todos",
        limit: int = 50
    ) -> Dict[str, Any]:
        """Analiza la rotación de personal con filtros opcionales."""
        return self._server._analisis_attrition({
            "attrition": attrition,
            "departamento": departamento,
            "rol": rol,
            "overtime": overtime,
            "limit": limit,
        })

    async def attrition_por_departamento(
        self,
        agrupar_por: str = "departamento"
    ) -> Dict[str, Any]:
        """Resumen de attrition agrupado por departamento, rol, overtime o estado civil."""
        return self._server._attrition_por_departamento({"agrupar_por": agrupar_por})

    async def factores_attrition(self) -> Dict[str, Any]:
        """Compara factores clave entre empleados con y sin attrition."""
        return self._server._factores_attrition()

    # ── Sales Orders ──────────────────────────────────────────────────────
    async def buscar_orden(
        self,
        region: str = "",
        pais: str = "",
        tipo_producto: str = "",
        canal: str = "todos",
        fecha_desde: str = "",
        fecha_hasta: str = "",
        limit: int = 50
    ) -> Dict[str, Any]:
        """Busca órdenes de venta con filtros opcionales."""
        return self._server._buscar_orden({
            "region": region,
            "pais": pais,
            "tipo_producto": tipo_producto,
            "canal": canal,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "limit": limit,
        })

    async def ventas_por_region(
        self,
        agrupar_por: str = "region",
        limit: int = 20
    ) -> Dict[str, Any]:
        """Resumen de ventas agrupado por región, país, producto, canal o prioridad."""
        return self._server._ventas_por_region({
            "agrupar_por": agrupar_por,
            "limit": limit,
        })

    async def top_productos(
        self,
        region: str = "",
        canal: str = "todos",
        ordenar_por: str = "revenue",
        limit: int = 10
    ) -> Dict[str, Any]:
        """Ranking de productos por unidades, revenue o profit."""
        return self._server._top_productos({
            "region": region,
            "canal": canal,
            "ordenar_por": ordenar_por,
            "limit": limit,
        })

    async def resumen_ventas(
        self,
        region: str = "",
        fecha_desde: str = "",
        fecha_hasta: str = ""
    ) -> Dict[str, Any]:
        """KPIs generales de ventas."""
        return self._server._resumen_ventas({
            "region": region,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
        })

    # ── Método de conveniencia para agentes ───────────────────────────────
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interfaz genérica para que los agentes llamen a cualquier herramienta
        por nombre, igual que hacen con mcp_mysql y mcp_sqlite.
        """
        dispatch = {
            "query_ibm":                  self._server._query_ibm,
            "get_schema_ibm":             lambda _: self._server._get_schema(),
            "list_tables_ibm":            lambda _: self._server._list_tables(),
            "buscar_tarjeta":             self._server._buscar_tarjeta,
            "resumen_tarjetas":           self._server._resumen_tarjetas,
            "buscar_transaccion":         self._server._buscar_transaccion,
            "resumen_transacciones":      self._server._resumen_transacciones,
            "buscar_empleado":            self._server._buscar_empleado,
            "resumen_empleados":          self._server._resumen_empleados,
            "analisis_attrition":         self._server._analisis_attrition,
            "attrition_por_departamento": self._server._attrition_por_departamento,
            "factores_attrition":         lambda _: self._server._factores_attrition(),
            "buscar_orden":               self._server._buscar_orden,
            "ventas_por_region":          self._server._ventas_por_region,
            "top_productos":              self._server._top_productos,
            "resumen_ventas":             self._server._resumen_ventas,
        }
        fn = dispatch.get(tool_name)
        if fn is None:
            return {"error": f"Herramienta desconocida: {tool_name}"}
        return fn(arguments)


# ── Instancia global ──────────────────────────────────────────────────────
_ibm_client: Optional[IBMMCPClient] = None


def get_ibm_client() -> IBMMCPClient:
    """Retorna (o crea) la instancia global del cliente IBM MCP."""
    global _ibm_client
    if _ibm_client is None:
        _ibm_client = IBMMCPClient()
    return _ibm_client
