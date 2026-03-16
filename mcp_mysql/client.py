"""
Cliente MCP MySQL

Permite a los agentes consultar farmacia_db directamente a través del servidor MCP MySQL.
Todas las operaciones son de solo lectura (SELECT).
"""

import json
from typing import Any, Dict, List, Optional

from .server import MySQLMCPServer, _execute_select


class MySQLMCPClient:
    """Cliente para interactuar con farmacia_db desde los agentes."""

    def __init__(self):
        self._server = MySQLMCPServer()

    # ── Consulta libre ──────────────────────────────────────────────────────
    async def query(self, query: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
        """Ejecuta un SELECT arbitrario en farmacia_db."""
        return _execute_select(query, params)

    # ── Esquema ─────────────────────────────────────────────────────────────
    async def get_schema(self) -> Dict[str, Any]:
        """Retorna el esquema completo de farmacia_db."""
        return self._server._get_schema()

    # ── Medicamentos ────────────────────────────────────────────────────────
    async def buscar_medicamento(
        self,
        nombre: str = "",
        laboratorio: str = "",
        clase_terapeutica: str = "",
        limit: int = 20
    ) -> Dict[str, Any]:
        """Busca medicamentos por nombre, laboratorio o clase terapéutica."""
        return self._server._buscar_medicamento({
            "nombre": nombre,
            "laboratorio": laboratorio,
            "clase_terapeutica": clase_terapeutica,
            "limit": limit,
        })

    # ── Stock ───────────────────────────────────────────────────────────────
    async def verificar_stock(
        self,
        medicamento_nombre: str,
        local_id: Optional[int] = None,
        solo_disponibles: bool = False
    ) -> Dict[str, Any]:
        """Verifica el stock de un medicamento en una o todas las farmacias."""
        return self._server._verificar_stock({
            "medicamento_nombre": medicamento_nombre,
            "local_id": local_id,
            "solo_disponibles": solo_disponibles,
        })

    async def alertas_stock(
        self,
        local_id: Optional[int] = None,
        tipo_alerta: str = "TODOS",
        limit: int = 50
    ) -> Dict[str, Any]:
        """Retorna registros con STOCK BAJO o SIN STOCK."""
        return self._server._alertas_stock({
            "local_id": local_id,
            "tipo_alerta": tipo_alerta,
            "limit": limit,
        })

    # ── Ventas ──────────────────────────────────────────────────────────────
    async def historial_ventas(
        self,
        local_id: Optional[int] = None,
        medicamento_nombre: str = "",
        fecha_desde: str = "",
        fecha_hasta: str = "",
        metodo_pago: str = "",
        limit: int = 50
    ) -> Dict[str, Any]:
        """Consulta el historial de compras con filtros opcionales."""
        return self._server._historial_ventas({
            "local_id": local_id,
            "medicamento_nombre": medicamento_nombre,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "metodo_pago": metodo_pago,
            "limit": limit,
        })

    async def top_medicamentos(
        self,
        local_id: Optional[int] = None,
        fecha_desde: str = "",
        fecha_hasta: str = "",
        ordenar_por: str = "cantidad",
        limit: int = 10
    ) -> Dict[str, Any]:
        """Retorna los medicamentos más vendidos."""
        return self._server._top_medicamentos({
            "local_id": local_id,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "ordenar_por": ordenar_por,
            "limit": limit,
        })

    async def resumen_farmacia(self, local_id: Optional[int] = None) -> Dict[str, Any]:
        """KPIs por farmacia: ventas, ingresos, alertas de stock."""
        return self._server._resumen_farmacia({"local_id": local_id})

    # ── Usuarios ────────────────────────────────────────────────────────────
    async def buscar_usuario(
        self,
        nombre: str = "",
        condicion_cronica: str = "",
        plan_salud: str = "",
        tipo_cliente: str = "",
        limit: int = 20
    ) -> Dict[str, Any]:
        """Busca clientes con filtros opcionales."""
        return self._server._buscar_usuario({
            "nombre": nombre,
            "condicion_cronica": condicion_cronica,
            "plan_salud": plan_salud,
            "tipo_cliente": tipo_cliente,
            "limit": limit,
        })

    # ── Método de conveniencia para agentes ─────────────────────────────────
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interfaz genérica para que los agentes llamen a cualquier herramienta
        por nombre, igual que hacen con mcp_sqlite y mcp_email.
        """
        dispatch = {
            "query_farmacia":        self._server._query_farmacia,
            "get_schema_farmacia":   lambda _: self._server._get_schema(),
            "buscar_medicamento":    self._server._buscar_medicamento,
            "verificar_stock":       self._server._verificar_stock,
            "alertas_stock":         self._server._alertas_stock,
            "historial_ventas":      self._server._historial_ventas,
            "top_medicamentos":      self._server._top_medicamentos,
            "resumen_farmacia":      self._server._resumen_farmacia,
            "buscar_usuario":        self._server._buscar_usuario,
        }
        fn = dispatch.get(tool_name)
        if fn is None:
            return {"error": f"Herramienta desconocida: {tool_name}"}
        return fn(arguments)


# ── Instancia global ────────────────────────────────────────────────────────
_mysql_client: Optional[MySQLMCPClient] = None


def get_mysql_client() -> MySQLMCPClient:
    """Retorna (o crea) la instancia global del cliente MySQL MCP."""
    global _mysql_client
    if _mysql_client is None:
        _mysql_client = MySQLMCPClient()
    return _mysql_client
