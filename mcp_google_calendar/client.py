"""
Cliente MCP Google Calendar

Cliente para interactuar con el servidor MCP Google Calendar desde FastAPI.
"""

from typing import Any, Dict, List, Optional


class GoogleCalendarMCPClient:
    """Cliente para interactuar con el servidor MCP Google Calendar."""

    def __init__(self):
        """Inicializa el cliente MCP Google Calendar."""
        from .server import GoogleCalendarMCPServer
        self._server = GoogleCalendarMCPServer()

    async def create_event(
        self,
        summary: str,
        start_datetime: str,
        end_datetime: str,
        description: str = "",
        location: str = "",
        attendees: Optional[List[str]] = None,
        timezone: str = "America/Mexico_City",
        add_meet: bool = False,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """
        Crea un evento/reunión en Google Calendar.

        Args:
            summary: Título del evento
            start_datetime: Inicio en ISO 8601
            end_datetime: Fin en ISO 8601
            description: Descripción del evento
            location: Ubicación
            attendees: Lista de emails de participantes
            timezone: Zona horaria
            add_meet: Agregar enlace de Google Meet
            calendar_id: ID del calendario

        Returns:
            Diccionario con resultado y detalles del evento creado
        """
        arguments = {
            "summary": summary,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            "description": description,
            "location": location,
            "attendees": attendees or [],
            "timezone": timezone,
            "add_meet": add_meet,
            "calendar_id": calendar_id,
        }
        return await self._server._create_event(arguments)

    async def list_events(
        self,
        max_results: int = 10,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """
        Lista eventos del calendario.

        Args:
            max_results: Número máximo de eventos
            time_min: Fecha/hora mínima (ISO 8601)
            time_max: Fecha/hora máxima (ISO 8601)
            calendar_id: ID del calendario

        Returns:
            Diccionario con lista de eventos
        """
        arguments = {
            "max_results": max_results,
            "calendar_id": calendar_id,
        }
        if time_min:
            arguments["time_min"] = time_min
        if time_max:
            arguments["time_max"] = time_max
        return await self._server._list_events(arguments)

    async def update_event(
        self,
        event_id: str,
        summary: Optional[str] = None,
        start_datetime: Optional[str] = None,
        end_datetime: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        timezone: str = "America/Mexico_City",
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """
        Actualiza un evento existente.

        Args:
            event_id: ID del evento a actualizar
            summary: Nuevo título
            start_datetime: Nueva fecha/hora de inicio
            end_datetime: Nueva fecha/hora de fin
            description: Nueva descripción
            location: Nueva ubicación
            attendees: Nueva lista de participantes
            timezone: Zona horaria
            calendar_id: ID del calendario

        Returns:
            Diccionario con resultado de la actualización
        """
        arguments: Dict[str, Any] = {
            "event_id": event_id,
            "timezone": timezone,
            "calendar_id": calendar_id,
        }
        if summary is not None:
            arguments["summary"] = summary
        if start_datetime is not None:
            arguments["start_datetime"] = start_datetime
        if end_datetime is not None:
            arguments["end_datetime"] = end_datetime
        if description is not None:
            arguments["description"] = description
        if location is not None:
            arguments["location"] = location
        if attendees is not None:
            arguments["attendees"] = attendees
        return await self._server._update_event(arguments)

    async def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """
        Elimina un evento del calendario.

        Args:
            event_id: ID del evento a eliminar
            calendar_id: ID del calendario

        Returns:
            Diccionario con resultado de la eliminación
        """
        arguments = {"event_id": event_id, "calendar_id": calendar_id}
        return await self._server._delete_event(arguments)

    async def check_availability(
        self,
        emails: List[str],
        time_min: str,
        time_max: str,
        timezone: str = "America/Mexico_City",
    ) -> Dict[str, Any]:
        """
        Verifica disponibilidad de participantes.

        Args:
            emails: Lista de emails a verificar
            time_min: Inicio del rango (ISO 8601)
            time_max: Fin del rango (ISO 8601)
            timezone: Zona horaria

        Returns:
            Diccionario con disponibilidad por participante
        """
        arguments = {
            "emails": emails,
            "time_min": time_min,
            "time_max": time_max,
            "timezone": timezone,
        }
        return await self._server._check_availability(arguments)

    async def list_calendars(self) -> Dict[str, Any]:
        """
        Lista todos los calendarios disponibles.

        Returns:
            Diccionario con lista de calendarios
        """
        return await self._server._list_calendars()


# Singleton
_calendar_client_instance = None


def get_calendar_client() -> GoogleCalendarMCPClient:
    """
    Obtiene una instancia singleton del cliente Google Calendar MCP.

    Returns:
        Instancia del GoogleCalendarMCPClient
    """
    global _calendar_client_instance
    if _calendar_client_instance is None:
        _calendar_client_instance = GoogleCalendarMCPClient()
    return _calendar_client_instance
