"""
Servidor MCP Email

Implementa un servidor MCP que permite enviar emails mediante SMTP.
"""

import json
from typing import Any, Dict
from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
    ListToolsResult,
)
from .smtp_sender import SMTPSender


class EmailMCPServer:
    """Servidor MCP para envío de emails."""
    
    def __init__(self):
        self.server = Server("email-mcp-server")
        self.smtp_sender = SMTPSender()
        self._register_handlers()
    
    def _register_handlers(self):
        """Registra los handlers del servidor MCP."""
        
        @self.server.list_tools()
        async def list_tools() -> ListToolsResult:
            """Lista las herramientas disponibles."""
            return ListToolsResult(
                tools=[
                    Tool(
                        name="send_email",
                        description="Envía un email mediante SMTP. Soporta Gmail, Outlook, Yahoo y servidores personalizados. "
                                    "El agente debe tener configuración SMTP (smtp_config) para usar esta herramienta.",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "smtp_config": {
                                    "type": "object",
                                    "description": "Configuración del servidor SMTP",
                                    "properties": {
                                        "server": {"type": "string", "description": "Servidor SMTP (ej: smtp.gmail.com)"},
                                        "port": {"type": "integer", "description": "Puerto SMTP (587 para TLS, 465 para SSL)"},
                                        "email": {"type": "string", "description": "Email del remitente"},
                                        "password": {"type": "string", "description": "Password o App Password"},
                                        "use_tls": {"type": "boolean", "description": "Usar TLS (puerto 587)"},
                                        "use_ssl": {"type": "boolean", "description": "Usar SSL (puerto 465)"}
                                    },
                                    "required": ["server", "port", "email", "password"]
                                },
                                "to": {
                                    "type": "string",
                                    "description": "Email del destinatario"
                                },
                                "subject": {
                                    "type": "string",
                                    "description": "Asunto del email"
                                },
                                "body": {
                                    "type": "string",
                                    "description": "Cuerpo del email"
                                },
                                "cc": {
                                    "type": "array",
                                    "description": "Lista de emails en copia (opcional)",
                                    "items": {"type": "string"}
                                },
                                "bcc": {
                                    "type": "array",
                                    "description": "Lista de emails en copia oculta (opcional)",
                                    "items": {"type": "string"}
                                },
                                "html": {
                                    "type": "boolean",
                                    "description": "Si True, el body se interpreta como HTML",
                                    "default": False
                                },
                                "attachments": {
                                    "type": "array",
                                    "description": "Lista de rutas de archivos a adjuntar (opcional)",
                                    "items": {"type": "string"}
                                }
                            },
                            "required": ["smtp_config", "to", "subject", "body"]
                        }
                    ),
                    Tool(
                        name="validate_email",
                        description="Valida el formato de un email.",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "email": {
                                    "type": "string",
                                    "description": "Email a validar"
                                }
                            },
                            "required": ["email"]
                        }
                    ),
                    Tool(
                        name="list_providers",
                        description="Lista los proveedores SMTP predefinidos (gmail, outlook, yahoo, office365).",
                        inputSchema={
                            "type": "object",
                            "properties": {}
                        }
                    )
                ]
            )
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> CallToolResult:
            """Ejecuta una herramienta del servidor."""
            try:
                if name == "send_email":
                    result = await self._send_email(arguments)
                elif name == "validate_email":
                    result = await self._validate_email(arguments)
                elif name == "list_providers":
                    result = await self._list_providers()
                else:
                    result = {"error": f"Herramienta desconocida: {name}"}
                
                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))],
                    isError=not result.get("success", False)
                )
            except Exception as e:
                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))],
                    isError=True
                )
    
    async def _send_email(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Envía un email mediante SMTP."""
        smtp_config = arguments.get("smtp_config")
        to = arguments.get("to")
        subject = arguments.get("subject")
        body = arguments.get("body")
        cc = arguments.get("cc", [])
        bcc = arguments.get("bcc", [])
        html = arguments.get("html", False)
        attachments = arguments.get("attachments", [])
        
        result = await self.smtp_sender.send_email(
            smtp_config=smtp_config,
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            html=html,
            attachments=attachments
        )
        
        return result
    
    async def _validate_email(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Valida el formato de un email."""
        email = arguments.get("email", "")
        
        # Validación simple
        is_valid = '@' in email and '.' in email.split('@')[-1]
        
        return {
            "success": True,
            "email": email,
            "valid": is_valid,
            "message": "Email válido" if is_valid else "Formato de email inválido"
        }
    
    async def _list_providers(self) -> Dict[str, Any]:
        """Lista los proveedores SMTP predefinidos."""
        from .smtp_sender import SMTP_PROVIDERS
        
        return {
            "success": True,
            "providers": SMTP_PROVIDERS
        }
    
    def get_server(self) -> Server:
        """Retorna la instancia del servidor MCP."""
        return self.server
