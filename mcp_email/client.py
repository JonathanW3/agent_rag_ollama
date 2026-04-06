"""
Cliente MCP Email

Cliente para interactuar con el servidor MCP Email desde FastAPI.
"""

import json
from typing import Any, Dict, List, Optional
from .imap_reader import IMAPReader


class EmailMCPClient:
    """Cliente para interactuar con el servidor MCP Email."""
    
    def __init__(self):
        """Inicializa el cliente MCP Email."""
        from .server import EmailMCPServer
        self._server = EmailMCPServer()
        self._imap = IMAPReader()
    
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

    async def read_inbox(
        self,
        imap_config: Dict[str, Any],
        limit: int = 10,
        folder: str = "INBOX",
    ) -> Dict[str, Any]:
        """
        Lee los últimos N emails de la bandeja de entrada.

        Args:
            imap_config: {"server": str, "port": int, "email": str, "password": str}
            limit: Número máximo de emails a retornar
            folder: Carpeta IMAP (default: "INBOX")

        Returns:
            {"success": bool, "count": int, "emails": [...], "folder": str}
        """
        return await self._imap.read_inbox(
            imap_config=imap_config,
            limit=limit,
            folder=folder,
        )

    async def search_emails(
        self,
        imap_config: Dict[str, Any],
        from_addr: Optional[str] = None,
        subject: Optional[str] = None,
        since_date: Optional[str] = None,
        keyword: Optional[str] = None,
        unseen_only: bool = False,
        limit: int = 10,
        folder: str = "INBOX",
    ) -> Dict[str, Any]:
        """
        Busca emails según criterios.

        Args:
            imap_config: {"server": str, "port": int, "email": str, "password": str}
            from_addr: Filtrar por remitente
            subject: Filtrar por asunto
            since_date: Desde fecha (YYYY-MM-DD)
            keyword: Palabra clave en el cuerpo
            unseen_only: Solo emails no leídos
            limit: Número máximo de resultados
            folder: Carpeta IMAP

        Returns:
            {"success": bool, "count": int, "emails": [...], "criteria": str}
        """
        return await self._imap.search_emails(
            imap_config=imap_config,
            from_addr=from_addr,
            subject=subject,
            since_date=since_date,
            keyword=keyword,
            unseen_only=unseen_only,
            limit=limit,
            folder=folder,
        )

    async def read_email(
        self,
        imap_config: Dict[str, Any],
        email_id: str,
        folder: str = "INBOX",
    ) -> Dict[str, Any]:
        """
        Lee el contenido completo de un email por su ID IMAP.

        Args:
            imap_config: {"server": str, "port": int, "email": str, "password": str}
            email_id: ID del email obtenido de read_inbox o search_emails
            folder: Carpeta donde está el email

        Returns:
            {"success": bool, "email": {id, from, to, subject, date, body, has_attachments}}
        """
        return await self._imap.read_email(
            imap_config=imap_config,
            email_id=email_id,
            folder=folder,
        )


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
