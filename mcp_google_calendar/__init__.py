"""
MCP Google Calendar Integration Module

Proporciona servidor y cliente MCP para gestión de eventos y reuniones
en Google Calendar mediante OAuth2.
"""

from .server import GoogleCalendarMCPServer
from .client import GoogleCalendarMCPClient

__all__ = ["GoogleCalendarMCPServer", "GoogleCalendarMCPClient"]
