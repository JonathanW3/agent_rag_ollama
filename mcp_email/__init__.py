"""
MCP Email Integration Module

Proporciona servidor y cliente MCP para envío de emails mediante SMTP.
Permite a los agentes enviar emails usando cualquier proveedor SMTP.
"""

from .server import EmailMCPServer
from .client import EmailMCPClient

__all__ = ["EmailMCPServer", "EmailMCPClient"]
