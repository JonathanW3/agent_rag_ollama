"""
MCP SQLite Integration Module

Proporciona servidor y cliente MCP para consultas SQLite.
Permite a los agentes acceder a datos estructurados mediante el protocolo MCP.
"""

from .server import SQLiteMCPServer
from .client import SQLiteMCPClient

__all__ = ["SQLiteMCPServer", "SQLiteMCPClient"]
