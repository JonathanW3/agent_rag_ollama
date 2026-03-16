"""
Cliente MCP Email

Cliente para interactuar con el servidor MCP Email desde FastAPI.
"""

import json
from typing import Any, Dict, List, Optional


class EmailMCPClient:
    """Cliente para interactuar con el servidor MCP Email."""
    
    def __init__(self):
        """Inicializa el cliente MCP Email."""
        # Importar el servidor localmente para uso directo
        from .server import EmailMCPServer
        self._server = EmailMCPServer()
    
    async def send_email(
        self,
        smtp_config: Dict[str, Any],
        to: str,
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        html: bool = False,
        attachments: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Envía un email mediante SMTP.
        
        Args:
            smtp_config: Configuración SMTP del agente
            to: Email del destinatario
            subject: Asunto del email
            body: Cuerpo del email
            cc: Lista de emails en copia (opcional)
            bcc: Lista de emails en copia oculta (opcional)
            html: Si True, el body se interpreta como HTML
            attachments: Lista de rutas de archivos a adjuntar (opcional)
            
        Returns:
            Diccionario con resultado: {"success": bool, "message": str}
        """
        arguments = {
            "smtp_config": smtp_config,
            "to": to,
            "subject": subject,
            "body": body,
            "cc": cc or [],
            "bcc": bcc or [],
            "html": html,
            "attachments": attachments or []
        }
        
        result = await self._server._send_email(arguments)
        return result
    
    async def validate_email(self, email: str) -> Dict[str, Any]:
        """
        Valida el formato de un email.
        
        Args:
            email: Email a validar
            
        Returns:
            Diccionario con resultado: {"success": bool, "valid": bool, "message": str}
        """
        arguments = {"email": email}
        result = await self._server._validate_email(arguments)
        return result
    
    async def list_providers(self) -> Dict[str, Any]:
        """
        Lista los proveedores SMTP predefinidos.
        
        Returns:
            Diccionario con proveedores disponibles
        """
        result = await self._server._list_providers()
        return result


# Función helper singleton
_email_client_instance = None


def get_email_client() -> EmailMCPClient:
    """
    Obtiene una instancia singleton del cliente Email MCP.
    
    Returns:
        Instancia del EmailMCPClient
    """
    global _email_client_instance
    if _email_client_instance is None:
        _email_client_instance = EmailMCPClient()
    return _email_client_instance
