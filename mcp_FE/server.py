"""
Servidor MCP FEPA - Facturación Electrónica

Herramientas expuestas:
  1. getResultFe        GET /{amb}/getResultFe/{co}/{ak}/{cufe}
  2. getCufeBySystemRef GET /getCufeBySystemRef/{co}/{ak}/{iAmb}/{docType}/{systemRef}
  3. getPdf             GET /getPDF/{co}/{ak}/{cufe}
"""

import json
import os
import sys
from typing import Any, Dict
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError


def _log(*args):
    print("[MCP_FE]", *args, file=sys.stderr, flush=True)


from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
    ListToolsResult,
)

# ---------------------------------------------------------------------------
# Configuración (variables de entorno)
# ---------------------------------------------------------------------------
BASE_URL        = os.getenv("FEPA_BASE_URL", "https://fepatest-api.webposonline.com")
AMB             = os.getenv("FEPA_AMB", "test")       # alias texto: "test" | "prod"
I_AMB           = os.getenv("FEPA_I_AMB", "2")        # valor numérico: 1=prod, 2=test
API_KEY         = os.getenv("FEPA_API_KEY", "")
COMPANY_LIC_COD = os.getenv("FEPA_COMPANY_LIC_COD", "")

_API_PREFIX = "/api/fepa/ak/v1"

# ---------------------------------------------------------------------------
# Campos permitidos por herramienta  (todo lo demás se descarta)
# ---------------------------------------------------------------------------
_FIELDS_RESULT_FE = {
    "cufe", "iAmb", "branchCod", "posCod", "docType", "systemRef",
    "docAffectedRef", "subDocType", "docDate", "dateRec", "feNumber",
    "authorized", "authNumber", "authDate",
    "subTotal", "taxTotal", "total",
    "sbt0", "sbt1", "sbt2", "sbt3",
    "tax1", "tax2", "tax3",
}

_FIELDS_CUFE_BY_SYSTEM_REF = {
    "found", "companyLicCod", "iAmb", "docType", "systemRef",
    "feNumber", "cufe", "docDate", "docSts",
    "authorized", "authDate", "authNumber",
    "canceled", "exMsg", "execTime",
}

_FIELDS_PDF = {
    "pdfGenerated", "companyLicCod", "cufe", "pdf", "fileName",
}


def _filter(data: Dict, allowed: set) -> Dict:
    return {k: v for k, v in data.items() if k in allowed}


# ---------------------------------------------------------------------------
# Helper HTTP
# ---------------------------------------------------------------------------

def _get(path: str) -> Dict[str, Any]:
    url = f"{BASE_URL}{_API_PREFIX}{path}"
    _log(f"→ GET {url}")
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            _log("← OK")
            if data is None:
                return {"error": "La API no devolvió datos. Verifica que el CUFE o referencia sean correctos."}
            return data
    except HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        _log(f"← ERROR HTTP {e.code}: {err}")
        return {"error": f"HTTP {e.code}: {err}"}
    except URLError as e:
        _log(f"← ERROR URL: {e.reason}")
        return {"error": f"URL error: {e.reason}"}


# ---------------------------------------------------------------------------
# Implementaciones
# ---------------------------------------------------------------------------

def _get_result_fe(args: Dict) -> Dict:
    """Busca datos de la factura por CUFE."""
    data = _get(f"/{AMB}/getResultFe/{COMPANY_LIC_COD}/{API_KEY}/{args['cufe']}")
    if "error" in data:
        return data
    return _filter(data, _FIELDS_RESULT_FE)


def _get_cufe_by_system_ref(args: Dict) -> Dict:
    """Busca datos de la factura por systemRef."""
    data = _get(
        f"/getCufeBySystemRef/{COMPANY_LIC_COD}/{API_KEY}"
        f"/{I_AMB}/{args['docType']}/{args['systemRef']}"
    )
    if "error" in data:
        return data
    return _filter(data, _FIELDS_CUFE_BY_SYSTEM_REF)


def _get_pdf(args: Dict) -> Dict:
    """Obtiene el PDF en base64 de la factura por CUFE."""
    data = _get(f"/getPDF/{COMPANY_LIC_COD}/{API_KEY}/{args['cufe']}")
    if "error" in data:
        return data
    filtered = _filter(data, _FIELDS_PDF)
    if filtered.get("pdfGenerated") and filtered.get("pdf"):
        filtered["_downloadHint"] = (
            f"PDF disponible para descarga. "
            f"Nombre del archivo: {filtered.get('fileName', 'factura.pdf')}. "
            "El campo 'pdf' contiene el contenido codificado en base64."
        )
    return filtered


# ---------------------------------------------------------------------------
# Servidor MCP
# ---------------------------------------------------------------------------

class FEMCPServer:
    """Servidor MCP para la API FEPA de Facturación Electrónica."""

    def __init__(self):
        self.server = Server("fe-mcp-server")
        self._register_handlers()

    def _register_handlers(self):

        @self.server.list_tools()
        async def list_tools() -> ListToolsResult:
            return ListToolsResult(tools=[

                Tool(
                    name="getResultFe",
                    description=(
                        "Busca los datos de una factura electrónica por CUFE. "
                        "Retorna: cufe, iAmb, branchCod, posCod, docType, systemRef, "
                        "docAffectedRef, subDocType, docDate, dateRec, feNumber, "
                        "authorized, authNumber, authDate, subTotal, taxTotal, total, "
                        "sbt0, sbt1, sbt2, sbt3, tax1, tax2, tax3."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "cufe": {
                                "type": "string",
                                "description": "Código CUFE de la factura electrónica",
                            },
                        },
                        "required": ["cufe"],
                    },
                ),

                Tool(
                    name="getCufeBySystemRef",
                    description=(
                        "Busca los datos de una factura electrónica por la referencia interna "
                        "del sistema (systemRef) y tipo de documento. "
                        "Retorna: found, companyLicCod, iAmb, docType, systemRef, feNumber, "
                        "cufe, docDate, docSts, authorized, authDate, authNumber, "
                        "canceled, exMsg, execTime."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "docType": {
                                "type": "string",
                                "description": "Tipo de documento (ej: F para factura)",
                            },
                            "systemRef": {
                                "type": "string",
                                "description": "Referencia interna del sistema (ej: 1-0000-780-0000000064)",
                            },
                        },
                        "required": ["docType", "systemRef"],
                    },
                ),

                Tool(
                    name="getPdf",
                    description=(
                        "Extrae el PDF de una factura electrónica en base64 dado su CUFE. "
                        "Retorna: pdfGenerated, companyLicCod, cufe, pdf (base64), fileName. "
                        "Usar el campo 'pdf' (base64) junto a 'fileName' para ofrecer la descarga al usuario."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "cufe": {
                                "type": "string",
                                "description": "Código CUFE de la factura electrónica",
                            },
                        },
                        "required": ["cufe"],
                    },
                ),

            ])

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> CallToolResult:
            _log(f"TOOL LLAMADO: {name} args={json.dumps(arguments, ensure_ascii=False)}")
            try:
                dispatch = {
                    "getResultFe":        _get_result_fe,
                    "getCufeBySystemRef": _get_cufe_by_system_ref,
                    "getPdf":             _get_pdf,
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
                    isError=True,
                )

    def get_server(self) -> Server:
        return self.server
