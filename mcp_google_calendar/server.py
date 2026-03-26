"""
Servidor MCP Google Calendar

Implementa un servidor MCP que permite gestionar reuniones y eventos
en Google Calendar mediante OAuth2.
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
from .calendar_service import GoogleCalendarService


class GoogleCalendarMCPServer:
    """Servidor MCP para gestión de Google Calendar."""

    def __init__(self):
        self.server = Server("google-calendar-mcp-server")
        self.calendar_service = GoogleCalendarService()
        self._register_handlers()

    def _register_handlers(self):
        """Registra los handlers del servidor MCP."""

        @self.server.list_tools()
        async def list_tools() -> ListToolsResult:
            """Lista las herramientas disponibles."""
            return ListToolsResult(
                tools=[
                    Tool(
                        name="create_calendar_event",
                        description=(
                            "Crea un evento o reunión en Google Calendar. "
                            "Puede agregar participantes, ubicación y enlace de Google Meet."
                        ),
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "summary": {
                                    "type": "string",
                                    "description": "Título del evento/reunión",
                                },
                                "start_datetime": {
                                    "type": "string",
                                    "description": "Fecha y hora de inicio en ISO 8601 (ej: 2026-03-26T10:00:00)",
                                },
                                "end_datetime": {
                                    "type": "string",
                                    "description": "Fecha y hora de fin en ISO 8601 (ej: 2026-03-26T11:00:00)",
                                },
                                "description": {
                                    "type": "string",
                                    "description": "Descripción del evento (opcional)",
                                    "default": "",
                                },
                                "location": {
                                    "type": "string",
                                    "description": "Ubicación del evento (opcional)",
                                    "default": "",
                                },
                                "attendees": {
                                    "type": "array",
                                    "description": "Lista de emails de participantes (opcional)",
                                    "items": {"type": "string"},
                                },
                                "timezone": {
                                    "type": "string",
                                    "description": "Zona horaria (default: America/Mexico_City)",
                                    "default": "America/Mexico_City",
                                },
                                "add_meet": {
                                    "type": "boolean",
                                    "description": "Agregar enlace de Google Meet (default: false)",
                                    "default": False,
                                },
                                "calendar_id": {
                                    "type": "string",
                                    "description": "ID del calendario (default: primary)",
                                    "default": "primary",
                                },
                            },
                            "required": ["summary", "start_datetime", "end_datetime"],
                        },
                    ),
                    Tool(
                        name="list_calendar_events",
                        description=(
                            "Lista eventos del calendario en un rango de fechas. "
                            "Por defecto muestra los próximos 10 eventos desde ahora."
                        ),
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "max_results": {
                                    "type": "integer",
                                    "description": "Número máximo de eventos (default: 10)",
                                    "default": 10,
                                },
                                "time_min": {
                                    "type": "string",
                                    "description": "Fecha/hora mínima ISO 8601 (default: ahora)",
                                },
                                "time_max": {
                                    "type": "string",
                                    "description": "Fecha/hora máxima ISO 8601 (opcional)",
                                },
                                "calendar_id": {
                                    "type": "string",
                                    "description": "ID del calendario (default: primary)",
                                    "default": "primary",
                                },
                            },
                        },
                    ),
                    Tool(
                        name="update_calendar_event",
                        description=(
                            "Actualiza un evento existente. Solo se modifican los campos proporcionados. "
                            "Requiere el event_id del evento."
                        ),
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "event_id": {
                                    "type": "string",
                                    "description": "ID del evento a actualizar",
                                },
                                "summary": {
                                    "type": "string",
                                    "description": "Nuevo título (opcional)",
                                },
                                "start_datetime": {
                                    "type": "string",
                                    "description": "Nueva fecha/hora de inicio ISO 8601 (opcional)",
                                },
                                "end_datetime": {
                                    "type": "string",
                                    "description": "Nueva fecha/hora de fin ISO 8601 (opcional)",
                                },
                                "description": {
                                    "type": "string",
                                    "description": "Nueva descripción (opcional)",
                                },
                                "location": {
                                    "type": "string",
                                    "description": "Nueva ubicación (opcional)",
                                },
                                "attendees": {
                                    "type": "array",
                                    "description": "Nueva lista de emails de participantes (reemplaza la anterior)",
                                    "items": {"type": "string"},
                                },
                                "timezone": {
                                    "type": "string",
                                    "description": "Zona horaria (default: America/Mexico_City)",
                                    "default": "America/Mexico_City",
                                },
                                "calendar_id": {
                                    "type": "string",
                                    "description": "ID del calendario (default: primary)",
                                    "default": "primary",
                                },
                            },
                            "required": ["event_id"],
                        },
                    ),
                    Tool(
                        name="delete_calendar_event",
                        description="Elimina un evento del calendario. Notifica a los participantes.",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "event_id": {
                                    "type": "string",
                                    "description": "ID del evento a eliminar",
                                },
                                "calendar_id": {
                                    "type": "string",
                                    "description": "ID del calendario (default: primary)",
                                    "default": "primary",
                                },
                            },
                            "required": ["event_id"],
                        },
                    ),
                    Tool(
                        name="check_availability",
                        description=(
                            "Verifica la disponibilidad de uno o más participantes "
                            "en un rango de tiempo usando Google Calendar FreeBusy."
                        ),
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "emails": {
                                    "type": "array",
                                    "description": "Lista de emails de los participantes a verificar",
                                    "items": {"type": "string"},
                                },
                                "time_min": {
                                    "type": "string",
                                    "description": "Inicio del rango en ISO 8601 (ej: 2026-03-26T09:00:00-06:00)",
                                },
                                "time_max": {
                                    "type": "string",
                                    "description": "Fin del rango en ISO 8601 (ej: 2026-03-26T18:00:00-06:00)",
                                },
                                "timezone": {
                                    "type": "string",
                                    "description": "Zona horaria (default: America/Mexico_City)",
                                    "default": "America/Mexico_City",
                                },
                            },
                            "required": ["emails", "time_min", "time_max"],
                        },
                    ),
                    Tool(
                        name="list_calendars",
                        description="Lista todos los calendarios disponibles del usuario autenticado.",
                        inputSchema={
                            "type": "object",
                            "properties": {},
                        },
                    ),
                ]
            )

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> CallToolResult:
            """Ejecuta una herramienta del servidor."""
            try:
                if name == "create_calendar_event":
                    result = await self._create_event(arguments)
                elif name == "list_calendar_events":
                    result = await self._list_events(arguments)
                elif name == "update_calendar_event":
                    result = await self._update_event(arguments)
                elif name == "delete_calendar_event":
                    result = await self._delete_event(arguments)
                elif name == "check_availability":
                    result = await self._check_availability(arguments)
                elif name == "list_calendars":
                    result = await self._list_calendars()
                else:
                    result = {"error": f"Herramienta desconocida: {name}"}

                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=json.dumps(result, indent=2, ensure_ascii=False),
                        )
                    ],
                    isError=not result.get("success", False),
                )
            except Exception as e:
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=json.dumps({"error": str(e)}, indent=2),
                        )
                    ],
                    isError=True,
                )

    async def _create_event(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Crea un evento en Google Calendar."""
        return await self.calendar_service.create_event(
            summary=arguments["summary"],
            start_datetime=arguments["start_datetime"],
            end_datetime=arguments["end_datetime"],
            description=arguments.get("description", ""),
            location=arguments.get("location", ""),
            attendees=arguments.get("attendees"),
            timezone=arguments.get("timezone", "America/Mexico_City"),
            add_meet=arguments.get("add_meet", False),
            calendar_id=arguments.get("calendar_id", "primary"),
        )

    async def _list_events(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Lista eventos del calendario."""
        return await self.calendar_service.list_events(
            max_results=arguments.get("max_results", 10),
            time_min=arguments.get("time_min"),
            time_max=arguments.get("time_max"),
            calendar_id=arguments.get("calendar_id", "primary"),
        )

    async def _update_event(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Actualiza un evento existente."""
        return await self.calendar_service.update_event(
            event_id=arguments["event_id"],
            summary=arguments.get("summary"),
            start_datetime=arguments.get("start_datetime"),
            end_datetime=arguments.get("end_datetime"),
            description=arguments.get("description"),
            location=arguments.get("location"),
            attendees=arguments.get("attendees"),
            timezone=arguments.get("timezone", "America/Mexico_City"),
            calendar_id=arguments.get("calendar_id", "primary"),
        )

    async def _delete_event(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Elimina un evento del calendario."""
        return await self.calendar_service.delete_event(
            event_id=arguments["event_id"],
            calendar_id=arguments.get("calendar_id", "primary"),
        )

    async def _check_availability(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Verifica disponibilidad de participantes."""
        return await self.calendar_service.check_availability(
            emails=arguments["emails"],
            time_min=arguments["time_min"],
            time_max=arguments["time_max"],
            timezone=arguments.get("timezone", "America/Mexico_City"),
        )

    async def _list_calendars(self) -> Dict[str, Any]:
        """Lista calendarios disponibles."""
        return await self.calendar_service.list_calendars()

    def get_server(self) -> Server:
        """Retorna la instancia del servidor MCP."""
        return self.server
