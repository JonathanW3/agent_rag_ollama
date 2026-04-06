"""
Cliente MCP FEPA - Facturación Electrónica

Permite a los agentes interactuar con la API FEPA directamente,
sin necesidad de construir URLs ni manejar HTTP manualmente.
El ambiente (test/prod) se toma de FEPA_AMB en el .env.
"""

from typing import Any, Dict, Optional

from .server import (
    FEMCPServer,
    _get_result_fe,
    _get_cufe_by_system_ref,
    _get_pdf,
)


class FEMCPClient:
    """Cliente para interactuar con la API FEPA desde los agentes."""

    def __init__(self):
        self._server = FEMCPServer()

    # ── Consulta de resultados ───────────────────────────────────────────────

    async def get_result_fe(self, cufe: str) -> Dict[str, Any]:
        """Obtiene los datos de una FE por CUFE."""
        return _get_result_fe({"cufe": cufe})

    # ── Búsqueda por referencia ──────────────────────────────────────────────

    async def get_cufe_by_system_ref(
        self, doc_type: str, system_ref: str
    ) -> Dict[str, Any]:
        """Obtiene los datos de una FE a partir de la referencia interna del sistema."""
        return _get_cufe_by_system_ref({"docType": doc_type, "systemRef": system_ref})

    # ── Documentos ──────────────────────────────────────────────────────────

    async def get_pdf(self, cufe: str) -> Dict[str, Any]:
        """Obtiene el PDF de una FE en base64."""
        return _get_pdf({"cufe": cufe})

    # ── Interfaz genérica para agentes ──────────────────────────────────────

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interfaz genérica para que los agentes llamen a cualquier herramienta
        por nombre, igual que hacen con mcp_mysql y mcp_email.
        """
        dispatch = {
            "getResultFe":        _get_result_fe,
            "getCufeBySystemRef": _get_cufe_by_system_ref,
            "getPdf":             _get_pdf,
        }
        fn = dispatch.get(tool_name)
        if fn is None:
            return {"error": f"Herramienta desconocida: {tool_name}"}
        return fn(arguments)


# ── Instancia global ─────────────────────────────────────────────────────────
_fe_client: Optional[FEMCPClient] = None


def get_fe_client() -> FEMCPClient:
    """Retorna (o crea) la instancia global del cliente FEPA MCP."""
    global _fe_client
    if _fe_client is None:
        _fe_client = FEMCPClient()
    return _fe_client
