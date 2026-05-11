"""
Cliente MCP SQL Server - Webpospa

Los datos se leen desde MySQL (licencias_ecuador en platform_db).
La sincronización SQL Server → MySQL ocurre vía cron (8:00 y 14:00)
o mediante sync_licencias_ecuador().
"""

from typing import Any, Dict, List, Optional

from .server import WebposMCPServer, _execute_raw, _execute_select, _QUERY_LICENCIAS_ECUADOR


class WebposMCPClient:
    """Cliente para interactuar con licencias webpospa desde los agentes."""

    def __init__(self):
        self._server = WebposMCPServer()

    async def buscar_empresa_ecuador(
        self,
        nombre: str = "",
        ruc: str = "",
        licenciamiento: bool | None = None,
    ) -> Dict[str, Any]:
        """Busca empresas en MySQL por nombre (LIKE), RUC (LIKE) y/o Licenciamiento."""
        return self._server._buscar_empresa_ecuador({
            "nombre": nombre,
            "ruc": ruc,
            "licenciamiento": licenciamiento,
        })

    async def licencias_por_vencer(
        self,
        dias: int = 45,
        campo_fecha: str = "ambas",
    ) -> Dict[str, Any]:
        """Lista licencias de Ecuador que vencen en los próximos N días (desde MySQL)."""
        return self._server._licencias_por_vencer({
            "dias": dias,
            "campo_fecha": campo_fecha,
        })

    async def licencias_efiscal_por_mes(self, dias: int = 45) -> Dict[str, Any]:
        """Empresas Licenciamiento con eFiscalDocs por vencer, evaluando solo mes/día."""
        return self._server._licencias_efiscal_por_mes({"dias": dias})

    async def resumen_tipo_licenciamiento(
        self,
        licenciamiento: bool | None = None,
    ) -> Dict[str, Any]:
        """Resumen liviano de empresas por tipo (sin LicenciasJSON)."""
        args: Dict[str, Any] = {}
        if licenciamiento is not None:
            args["licenciamiento"] = licenciamiento
        return self._server._resumen_tipo_licenciamiento(args)

    async def sync_licencias_ecuador(self) -> Dict[str, Any]:
        """Fuerza una sincronización SQL Server → MySQL ahora mismo."""
        return self._server._sync_licencias_ecuador()

    async def query(
        self,
        query: str,
        params: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """Ejecuta un SELECT arbitrario directamente en SQL Server webpospa."""
        return _execute_select(query, params)

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Interfaz genérica para que los agentes llamen a cualquier herramienta por nombre."""
        dispatch = {
            "buscar_empresa_ecuador":      self._server._buscar_empresa_ecuador,
            "licencias_por_vencer":        self._server._licencias_por_vencer,
            "licencias_efiscal_por_mes":   self._server._licencias_efiscal_por_mes,
            "resumen_tipo_licenciamiento": self._server._resumen_tipo_licenciamiento,
            "sync_licencias_ecuador":      lambda _: self._server._sync_licencias_ecuador(),
            "query_webpospa":              self._server._query_webpospa,
        }
        fn = dispatch.get(tool_name)
        if fn is None:
            return {"error": f"Herramienta desconocida: {tool_name}"}
        return fn(arguments)


# ── Instancia global ──────────────────────────────────────────────────────
_webpos_client: Optional[WebposMCPClient] = None


def get_webpos_client() -> WebposMCPClient:
    """Retorna (o crea) la instancia global del cliente Webpos MCP."""
    global _webpos_client
    if _webpos_client is None:
        _webpos_client = WebposMCPClient()
    return _webpos_client
