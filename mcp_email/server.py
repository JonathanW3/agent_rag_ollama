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
from .imap_reader import IMAPReader


class EmailMCPServer:
    """Servidor MCP para envío de emails."""
    
    def __init__(self):
        self.server = Server("email-mcp-server")
        self.smtp_sender = SMTPSender()
        self.imap_reader = IMAPReader()
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
                    ),
                    Tool(
                        name="read_inbox",
                        description="Lee los últimos N emails de la bandeja de entrada mediante IMAP. "
                                    "Requiere imap_config con server, port, email y password.",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "imap_config": {
                                    "type": "object",
                                    "description": "Configuración del servidor IMAP",
                                    "properties": {
                                        "server": {"type": "string", "description": "Servidor IMAP (ej: imap.gmail.com)"},
                                        "port": {"type": "integer", "description": "Puerto IMAP (993 para SSL)"},
                                        "email": {"type": "string", "description": "Email de la cuenta"},
                                        "password": {"type": "string", "description": "Password o App Password"}
                                    },
                                    "required": ["server", "port", "email", "password"]
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "Número máximo de emails a retornar (default: 10)",
                                    "default": 10
                                },
                                "folder": {
                                    "type": "string",
                                    "description": "Carpeta IMAP a leer (default: INBOX)",
                                    "default": "INBOX"
                                }
                            },
                            "required": ["imap_config"]
                        }
                    ),
                    Tool(
                        name="search_emails",
                        description="Busca emails en la bandeja según criterios: remitente, asunto, fecha, palabra clave o no leídos.",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "imap_config": {
                                    "type": "object",
                                    "description": "Configuración del servidor IMAP",
                                    "properties": {
                                        "server": {"type": "string"},
                                        "port": {"type": "integer"},
                                        "email": {"type": "string"},
                                        "password": {"type": "string"}
                                    },
                                    "required": ["server", "port", "email", "password"]
                                },
                                "from_addr": {"type": "string", "description": "Filtrar por remitente (ej: juan@example.com)"},
                                "subject": {"type": "string", "description": "Filtrar por asunto"},
                                "since_date": {"type": "string", "description": "Desde fecha (formato YYYY-MM-DD)"},
                                "keyword": {"type": "string", "description": "Palabra clave en el cuerpo"},
                                "unseen_only": {"type": "boolean", "description": "Solo emails no leídos", "default": False},
                                "limit": {"type": "integer", "description": "Número máximo de resultados", "default": 10},
                                "folder": {"type": "string", "description": "Carpeta IMAP", "default": "INBOX"}
                            },
                            "required": ["imap_config"]
                        }
                    ),
                    Tool(
                        name="read_email",
                        description="Lee el contenido completo de un email por su ID IMAP (obtenido de read_inbox o search_emails).",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "imap_config": {
                                    "type": "object",
                                    "description": "Configuración del servidor IMAP",
                                    "properties": {
                                        "server": {"type": "string"},
                                        "port": {"type": "integer"},
                                        "email": {"type": "string"},
                                        "password": {"type": "string"}
                                    },
                                    "required": ["server", "port", "email", "password"]
                                },
                                "email_id": {
                                    "type": "string",
                                    "description": "ID del email a leer"
                                },
                                "folder": {
                                    "type": "string",
                                    "description": "Carpeta donde está el email",
                                    "default": "INBOX"
                                }
                            },
                            "required": ["imap_config", "email_id"]
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
                elif name == "read_inbox":
                    result = await self._read_inbox(arguments)
                elif name == "search_emails":
                    result = await self._search_emails(arguments)
                elif name == "read_email":
                    result = await self._read_email(arguments)
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

    async def _read_inbox(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Lee los últimos N emails de la bandeja de entrada."""
        return await self.imap_reader.read_inbox(
            imap_config=arguments.get("imap_config"),
            limit=arguments.get("limit", 10),
            folder=arguments.get("folder", "INBOX"),
        )

    async def _search_emails(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Busca emails según criterios."""
        return await self.imap_reader.search_emails(
            imap_config=arguments.get("imap_config"),
            from_addr=arguments.get("from_addr"),
            subject=arguments.get("subject"),
            since_date=arguments.get("since_date"),
            keyword=arguments.get("keyword"),
            unseen_only=arguments.get("unseen_only", False),
            limit=arguments.get("limit", 10),
            folder=arguments.get("folder", "INBOX"),
        )

    async def _read_email(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Lee el contenido completo de un email por ID."""
        return await self.imap_reader.read_email(
            imap_config=arguments.get("imap_config"),
            email_id=str(arguments.get("email_id", "")),
            folder=arguments.get("folder", "INBOX"),
        )

    def get_server(self) -> Server:
        """Retorna la instancia del servidor MCP."""
        return self.server
