"""
Cliente MCP MySQL Autopart

Permite a los agentes consultar la base de datos autopart directamente a través del servidor MCP.
Todas las operaciones son de solo lectura (SELECT).
"""

import json
from typing import Any, Dict, List, Optional

from .server import AutopartMCPServer, _execute_select


class AutopartMCPClient:
    """Cliente para interactuar con la base de datos autopart desde los agentes."""

    def __init__(self):
        self._server = AutopartMCPServer()

    # ── Consulta libre ────────────────────────────────────────────────────
    async def query(self, query: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
        """Ejecuta un SELECT arbitrario en la base de datos autopart."""
        return _execute_select(query, params)

    # ── Esquema ───────────────────────────────────────────────────────────
    async def get_schema(self) -> Dict[str, Any]:
        """Retorna el esquema completo de la base de datos autopart."""
        return self._server._get_schema()

    # ── Tablas ────────────────────────────────────────────────────────────
    async def list_tables(self) -> Dict[str, Any]:
        """Lista todas las tablas con conteo de filas."""
        return self._server._list_tables()

    # ── Vehicles ─────────────────────────────────────────────────────────
    async def buscar_vehiculo(
        self,
        modelo: str = "",
        fabricante: str = "",
        tipo_vehiculo: str = "",
        limit: int = 20
    ) -> Dict[str, Any]:
        """Busca vehículos por modelo, fabricante o tipo."""
        return self._server._buscar_vehiculo({
            "modelo": modelo,
            "fabricante": fabricante,
            "tipo_vehiculo": tipo_vehiculo,
            "limit": limit,
        })

    async def resumen_vehiculos(
        self,
        agrupar_por: str = "fabricante",
        limit: int = 20
    ) -> Dict[str, Any]:
        """Resumen de vehículos agrupado por fabricante o tipo."""
        return self._server._resumen_vehiculos({
            "agrupar_por": agrupar_por,
            "limit": limit,
        })

    # ── Product Category ─────────────────────────────────────────────────
    async def buscar_categoria(
        self,
        nombre: str = "",
        limit: int = 50
    ) -> Dict[str, Any]:
        """Busca categorías de producto por nombre."""
        return self._server._buscar_categoria({
            "nombre": nombre,
            "limit": limit,
        })

    async def arbol_categorias(self) -> Dict[str, Any]:
        """Retorna la jerarquía completa de categorías con conteo de aplicaciones."""
        return self._server._arbol_categorias()

    # ── Seller ───────────────────────────────────────────────────────────
    async def buscar_vendedor(
        self,
        nombre: str = "",
        direccion: str = "",
        limit: int = 20
    ) -> Dict[str, Any]:
        """Busca vendedores por nombre o dirección."""
        return self._server._buscar_vendedor({
            "nombre": nombre,
            "direccion": direccion,
            "limit": limit,
        })

    async def resumen_vendedores(self, limit: int = 20) -> Dict[str, Any]:
        """Resumen de vendedores con estadísticas de publicaciones."""
        return self._server._resumen_vendedores({"limit": limit})

    # ── Applications ─────────────────────────────────────────────────────
    async def buscar_aplicacion(
        self,
        headline: str = "",
        precio_min_usd: Optional[float] = None,
        precio_max_usd: Optional[float] = None,
        precio_min_gel: Optional[float] = None,
        precio_max_gel: Optional[float] = None,
        condicion: str = "",
        categoria: str = "",
        vendedor: str = "",
        estado: str = "",
        fecha_desde: str = "",
        fecha_hasta: str = "",
        limit: int = 50
    ) -> Dict[str, Any]:
        """Busca publicaciones de autopartes con filtros opcionales."""
        return self._server._buscar_aplicacion({
            "headline": headline,
            "precio_min_usd": precio_min_usd,
            "precio_max_usd": precio_max_usd,
            "precio_min_gel": precio_min_gel,
            "precio_max_gel": precio_max_gel,
            "condicion": condicion,
            "categoria": categoria,
            "vendedor": vendedor,
            "estado": estado,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "limit": limit,
        })

    async def resumen_aplicaciones(
        self,
        agrupar_por: str = "estado",
        limit: int = 20
    ) -> Dict[str, Any]:
        """Resumen de publicaciones agrupado por estado, categoría, condición o vendedor."""
        return self._server._resumen_aplicaciones({
            "agrupar_por": agrupar_por,
            "limit": limit,
        })

    async def top_aplicaciones(
        self,
        categoria: str = "",
        condicion: str = "",
        ordenar_por: str = "precio_usd",
        limit: int = 10
    ) -> Dict[str, Any]:
        """Ranking de publicaciones por precio."""
        return self._server._top_aplicaciones({
            "categoria": categoria,
            "condicion": condicion,
            "ordenar_por": ordenar_por,
            "limit": limit,
        })

    # ── Compatibility ────────────────────────────────────────────────────
    async def buscar_compatibilidad(
        self,
        modelo_vehiculo: str = "",
        fabricante: str = "",
        anio: Optional[int] = None,
        headline: str = "",
        limit: int = 50
    ) -> Dict[str, Any]:
        """Busca compatibilidades pieza-vehículo."""
        return self._server._buscar_compatibilidad({
            "modelo_vehiculo": modelo_vehiculo,
            "fabricante": fabricante,
            "anio": anio,
            "headline": headline,
            "limit": limit,
        })

    async def resumen_compatibilidad(
        self,
        agrupar_por: str = "fabricante",
        limit: int = 20
    ) -> Dict[str, Any]:
        """Resumen de compatibilidades agrupado por fabricante, modelo o tipo."""
        return self._server._resumen_compatibilidad({
            "agrupar_por": agrupar_por,
            "limit": limit,
        })

    # ── Método de conveniencia para agentes ───────────────────────────────
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interfaz genérica para que los agentes llamen a cualquier herramienta
        por nombre, igual que hacen con mcp_mysql y mcp_sqlite.
        """
        dispatch = {
            "query_autopart":          self._server._query_autopart,
            "get_schema_autopart":     lambda _: self._server._get_schema(),
            "list_tables_autopart":    lambda _: self._server._list_tables(),
            "buscar_vehiculo":         self._server._buscar_vehiculo,
            "resumen_vehiculos":       self._server._resumen_vehiculos,
            "buscar_categoria":        self._server._buscar_categoria,
            "arbol_categorias":        lambda _: self._server._arbol_categorias(),
            "buscar_vendedor":         self._server._buscar_vendedor,
            "resumen_vendedores":      self._server._resumen_vendedores,
            "buscar_aplicacion":       self._server._buscar_aplicacion,
            "resumen_aplicaciones":    self._server._resumen_aplicaciones,
            "top_aplicaciones":        self._server._top_aplicaciones,
            "buscar_compatibilidad":   self._server._buscar_compatibilidad,
            "resumen_compatibilidad":  self._server._resumen_compatibilidad,
        }
        fn = dispatch.get(tool_name)
        if fn is None:
            return {"error": f"Herramienta desconocida: {tool_name}"}
        return fn(arguments)


# ── Instancia global ──────────────────────────────────────────────────────
_autopart_client: Optional[AutopartMCPClient] = None


def get_autopart_client() -> AutopartMCPClient:
    """Retorna (o crea) la instancia global del cliente Autopart MCP."""
    global _autopart_client
    if _autopart_client is None:
        _autopart_client = AutopartMCPClient()
    return _autopart_client
